"""Explicit plans, durable before-state records, and guarded restoration."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .adb import DeviceError
from .audit import AURA, CACHE_TARGETS, SETTINGS, packages, recommendations


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def create_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        Path(path).unlink(missing_ok=True)
        raise


def load_approved(path, approval):
    raw = path.read_bytes()
    expected = hashlib.sha256(raw).hexdigest()
    if approval != expected:
        raise DeviceError(f"Approval must match the SHA-256 of the reviewed plan: {expected}")
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise DeviceError("Plan is not valid JSON.") from exc


@contextmanager
def device_lock(device):
    if not device.is_owner_active():
        raise DeviceError("Switch to the primary Android user before changing anything.")
    identifier = device.identity()
    folder = Path.home() / ".cyandroid"
    folder.mkdir(mode=0o700, exist_ok=True)
    lock = folder / f"{identifier}.lock"
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise DeviceError(f"Another operation owns {lock}. Check for a running cleanup before removing a stale lock.") from exc
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(f"{os.getpid()}\n")
        yield identifier
    finally:
        lock.unlink()


def write_journal(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(json_bytes(data))
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def package_state(device, package):
    dump = device.shell("dumpsys", "package", package)
    match = re.search(r"^[ \t]*User 0: [^\n]*installed=true[^\n]*\benabled=([0-4])\b", dump, re.M)
    if not match:
        raise DeviceError(f"Cannot establish the primary user's state for {package}.")
    return int(match[1])


def before_value(device, kind, target):
    if kind == "setting":
        return device.shell("settings", "get", "global", target)
    if kind == "disable":
        return package_state(device, target)
    return None


def check_operations(operations):
    if not isinstance(operations, list) or not operations:
        raise DeviceError("Provide at least one action.")
    targets = set()
    for operation in operations:
        if not isinstance(operation, dict) or set(operation) != {"kind", "target", "value"}:
            raise DeviceError("Invalid operation in plan.")
        kind, target, value = (operation[key] for key in ("kind", "target", "value"))
        if not isinstance(target, str):
            raise DeviceError("Invalid operation target.")
        if kind == "setting" and target in SETTINGS and value == "0":
            pass
        elif kind == "disable" and target == AURA and type(value) is int and value == 3:
            pass
        elif kind == "cache" and target in CACHE_TARGETS and value is None:
            pass
        else:
            raise DeviceError(f"Unsupported operation for {target}.")
        if target in targets:
            raise DeviceError(f"Repeated operation for {target}.")
        targets.add(target)


def create_plan(device, operations, path):
    if not device.is_owner_active():
        raise DeviceError("Switch to the primary Android user before preparing changes.")
    check_operations(operations)
    payload = {
        "version": 1, "device_id": device.identity(),
        "build": device.prop("ro.build.fingerprint"), "operations": operations,
    }
    verify_plan(device, payload, payload["device_id"])
    payload["observed"] = {op["target"]: before_value(device, op["kind"], op["target"])
                           for op in operations if op["kind"] != "cache"}
    create_json(path, payload)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_plan(device, plan, identity):
    if not isinstance(plan, dict) or plan.get("version") != 1 or plan.get("device_id") != identity:
        raise DeviceError("This plan does not match the attached phone.")
    if not plan.get("build") or plan["build"] != device.prop("ro.build.fingerprint"):
        raise DeviceError("The build changed. Audit the phone and create a new plan.")
    check_operations(plan.get("operations"))
    installed = packages(device)
    for operation in plan["operations"]:
        kind, target = operation["kind"], operation["target"]
        if kind == "disable" and not recommendations(device):
            raise DeviceError("An enabled, matching Nothing Aura component was not verified.")
        if kind == "cache" and (target not in installed or
                               "--cache-only" not in device.shell("pm", "help")):
            raise DeviceError(f"Use App info → Storage and cache → Clear cache for {target}.")


def apply(device, source, approval, journal_path):
    plan = load_approved(source, approval)
    with device_lock(device) as identity:
        verify_plan(device, plan, identity)
        entries = [
            {**op, "before": before_value(device, op["kind"], op["target"]), "state": "pending"}
            for op in plan["operations"]
        ]
        observed = {op["target"]: op["before"] for op in entries if op["kind"] != "cache"}
        if observed != plan.get("observed"):
            raise DeviceError("The current settings differ from the reviewed plan. Create a new plan.")
        journal = {"version": 1, "device_id": identity, "entries": entries}
        create_json(journal_path, journal)
        for op in entries:
            kind, target, desired = (op[key] for key in ("kind", "target", "value"))
            if kind != "cache" and before_value(device, kind, target) != op["before"]:
                raise DeviceError(f"{target} changed since preflight. The journal records earlier actions.")
            if kind != "cache" and op["before"] == desired:
                op["state"] = "unchanged"
                write_journal(journal_path, journal)
                continue
            op["state"] = "started"
            write_journal(journal_path, journal)
            if kind == "setting":
                device.shell("settings", "put", "global", target, desired)
            elif kind == "disable":
                device.shell("pm", "disable-user", "--user", "0", target)
            else:
                try:
                    response = device.shell("pm", "clear", "--user", "0", "--cache-only", target, timeout=12)
                except DeviceError as exc:
                    raise DeviceError(f"Cache result is unconfirmed for {target}. Check Storage and cache on the phone. Prior changes are in the journal.") from exc
                if response != "Success":
                    raise DeviceError(f"Cache clear failed for {target}. Use Storage and cache on the phone.")
            if kind != "cache" and before_value(device, kind, target) != desired:
                raise DeviceError(f"Android did not confirm {target}. Check the journal before retrying.")
            op["state"] = "applied"
            write_journal(journal_path, journal)
    return entries


def restore(device, journal_path):
    journal = json.loads(journal_path.read_bytes())
    with device_lock(device) as identity:
        if not isinstance(journal, dict) or journal.get("version") != 1 or journal.get("device_id") != identity:
            raise DeviceError("This journal does not match the attached phone.")
        entries = journal.get("entries")
        if not isinstance(entries, list) or any(not isinstance(op, dict) for op in entries):
            raise DeviceError("Invalid journal entries.")
        check_operations([{key: op.get(key) for key in ("kind", "target", "value")} for op in entries])
        for op in entries:
            if op.get("state") not in {"pending", "started", "applied", "unchanged", "restored"}:
                raise DeviceError("Invalid journal state.")
            before = op.get("before")
            if op["kind"] == "disable" and (type(before) is not int or before not in {0, 1}):
                raise DeviceError("Unexpected saved app state.")
            if op["kind"] == "setting" and (not isinstance(before, str) or not re.fullmatch(r"null|\d{1,3}", before)):
                raise DeviceError("Unexpected saved setting.")
        for op in reversed(entries):
            kind, target = op["kind"], op["target"]
            if kind == "cache" or op["state"] not in {"started", "applied"}:
                continue
            before = op["before"]
            current = before_value(device, kind, target)
            if current == op["value"] and current != before:
                if kind == "setting":
                    if before == "null":
                        device.shell("settings", "delete", "global", target)
                    else:
                        device.shell("settings", "put", "global", target, before)
                else:
                    command = "default-state" if before == 0 else "enable"
                    device.shell("pm", command, "--user", "0", target)
            if before_value(device, kind, target) != before:
                raise DeviceError(f"{target} changed independently. Resolve it on the phone before retrying.")
            op["state"] = "restored"
            write_journal(journal_path, journal)
    return entries
