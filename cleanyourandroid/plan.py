"""Explicit plans, durable before-state records, and guarded restoration."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .adb import DeviceError, package_name
from .audit import ANIMATIONS, CELLULAR, SAVER, SAVER_LEVELS, SCALES, SETTINGS, cache_only_supported
from . import critical, dns, oem


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


APP_ACTIONS = {"disable": 3, "remove": -1}
RESTORABLE_APP_STATES = {0: "default-state", 1: "enable", 3: "disable-user"}
SETTING_VALUES = {CELLULAR: ("0",), SAVER: ("0", *SAVER_LEVELS), **dict.fromkeys(ANIMATIONS, SCALES)}


def before_value(device, kind, target):
    if kind == "setting":
        return device.shell("settings", "get", "global", target)
    if kind in APP_ACTIONS:
        return oem.package_state(device, target)
    if kind == "dns":
        return dns.read(device)
    return None


def expected_value(kind, value):
    return dns.desired(value) if kind == "dns" else value


def same_value(op, current, expected):
    if op["kind"] == "setting" and op["target"] in ANIMATIONS:
        if all(isinstance(v, str) and re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{1,9})?", v)
               for v in (current, expected)):
            return float(current) == float(expected)
    return current == expected


def verify_prior(op, before):
    kind = op["kind"]
    if kind in APP_ACTIONS and (type(before) is not int or before not in RESTORABLE_APP_STATES):
        raise DeviceError("Unexpected saved app state.")
    if kind == "setting":
        pattern = r"null|[0-9]{1,3}(?:\.[0-9]{1,9})?" if op["target"] in ANIMATIONS else r"null|[0-9]{1,3}"
        if not isinstance(before, str) or not re.fullmatch(pattern, before):
            raise DeviceError(f"Cannot safely restore the previous value of {op['target']}.")
    if kind == "dns":
        dns.validate_state(before)


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
        if kind == "setting":
            if value not in SETTING_VALUES.get(target, ()):
                raise DeviceError(f"Unsupported setting or value for {target}.")
        elif (kind in APP_ACTIONS and target in oem.RULES and not critical.protected(target)
              and type(value) is int and APP_ACTIONS[kind] == value):
            pass
        elif kind == "dns" and target == "private_dns" and dns.hostname(value) == value:
            pass
        elif kind == "cache" and value is None:
            package_name(target)
        else:
            raise DeviceError(f"Unsupported operation for {target}.")
        if target in targets:
            raise DeviceError(f"Repeated operation for {target}.")
        targets.add(target)


def light_operations(device, explicit):
    """Choose reversible actions only. Never increase a user's motion settings."""
    chosen = {op["target"] for op in explicit}
    extra, observed = [], {}
    for key in ANIMATIONS:
        if key in chosen:
            continue
        before = before_value(device, "setting", key)
        if before == "null" or (re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{1,9})?", before) and float(before) > 0.5):
            extra.append(dict(kind="setting", target=key, value="0.5"))
            observed[key] = before
    candidates, _ = oem.candidate_review(device)
    for row in candidates:
        name = row["package"]
        if name not in chosen and row["disable_allowed"] and oem.RULES[name].ad_service:
            extra.append(dict(kind="disable", target=name, value=3))
    return extra, observed


def create_plan(device, operations, path, *, light=False):
    if not device.is_owner_active():
        raise DeviceError("Switch to the primary Android user before preparing changes.")
    selected_from = {}
    if light:
        extra, selected_from = light_operations(device, operations)
        operations = [*operations, *extra]
        if not operations:
            raise DeviceError("No eligible changes for the light preset. No plan was written.")
    check_operations(operations)
    payload = {
        "version": 1, "device_id": device.identity(),
        "build": device.prop("ro.build.fingerprint"), "operations": operations,
    }
    verify_plan(device, payload, payload["device_id"])
    payload["observed"] = {op["target"]: before_value(device, op["kind"], op["target"])
                           for op in operations if op["kind"] != "cache"}
    if any(payload["observed"][key] != prior for key, prior in selected_from.items()):
        raise DeviceError("Motion settings changed during preview. Create a new plan.")
    for op in operations:
        verify_prior(op, payload["observed"].get(op["target"]))
    payload["review_notes"] = {op["target"]: review_note(op) for op in operations}
    create_json(path, payload)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review_note(op):
    if op["kind"] in APP_ACTIONS:
        return oem.RULES[op["target"]].impact
    if op["kind"] == "setting":
        return SETTINGS[op["target"]]
    if op["kind"] == "cache":
        return "Temporary app cache cannot be restored. The next launch may be slower or re-download content."
    return "The selected DNS provider can see DNS queries. An unavailable host can interrupt connectivity."


def verify_plan(device, plan, identity):
    if not isinstance(plan, dict) or plan.get("version") != 1 or plan.get("device_id") != identity:
        raise DeviceError("This plan does not match the attached phone.")
    if not plan.get("build") or plan["build"] != device.prop("ro.build.fingerprint"):
        raise DeviceError("The build changed. Audit the phone and create a new plan.")
    check_operations(plan.get("operations"))
    caches = {op["target"] for op in plan["operations"] if op["kind"] == "cache"}
    if caches:
        if not cache_only_supported(device):
            raise DeviceError("Cannot verify the cache-only command and shell permission. "
                              "Run cache-settings PACKAGE and choose Clear cache on the phone.")
        if missing := caches - oem.packages(device):
            raise DeviceError(f"Cache target not installed for user 0: {', '.join(sorted(missing))}")
    for operation in plan["operations"]:
        kind, target = operation["kind"], operation["target"]
        if kind in APP_ACTIONS:
            verify_package_action(device, kind, target)
        if kind == "dns":
            sdk = device.prop("ro.build.version.sdk")
            if not sdk.isdecimal() or int(sdk) < 28:
                raise DeviceError("Private DNS requires Android 9 or later.")
        if kind == "setting" and target == SAVER and operation["value"] != "0":
            if device.shell("settings", "get", "global", "automatic_power_save_mode") not in {"0", "null"}:
                raise DeviceError("Battery Saver uses a different schedule. Select percentage scheduling in Settings first.")


def verify_package_action(device, kind, target):
    key = "disable_allowed" if kind == "disable" else "remove_for_primary_user_allowed"
    if not any(row["package"] == target and row[key] for row in oem.verified_candidates(device, strict=True)):
        raise DeviceError(f"No eligible {kind} action for {target} on this phone and build.")


def apply(device, source, approval, journal_path):
    plan = load_approved(source, approval)
    with device_lock(device) as identity:
        verify_plan(device, plan, identity)
        entries = [
            {**op, "before": before_value(device, op["kind"], op["target"]), "state": "pending"}
            for op in plan["operations"]
        ]
        for op in entries:
            verify_prior(op, op["before"])
        observed = {op["target"]: op["before"] for op in entries if op["kind"] != "cache"}
        if observed != plan.get("observed"):
            raise DeviceError("The current settings differ from the reviewed plan. Create a new plan.")
        journal = {"version": 1, "device_id": identity, "build": plan["build"], "entries": entries}
        create_json(journal_path, journal)
        for op in entries:
            kind, target, desired = (op[key] for key in ("kind", "target", "value"))
            if kind != "cache" and before_value(device, kind, target) != op["before"]:
                raise DeviceError(f"{target} changed since preflight. The journal records earlier actions.")
            expected = expected_value(kind, desired)
            if kind != "cache" and same_value(op, op["before"], expected):
                op["state"] = "unchanged"
                write_journal(journal_path, journal)
                continue
            op["state"] = "started"
            write_journal(journal_path, journal)
            if kind == "setting":
                dns.put_setting(device, target, desired)
            elif kind == "dns":
                dns.apply(device, desired)
            elif kind in APP_ACTIONS:
                verify_package_action(device, kind, target)
                if kind == "disable":
                    device.shell("pm", "disable-user", "--user", "0", target)
                else:
                    response = device.shell("pm", "uninstall", "-k", "--user", "0", target)
                    if response != "Success":
                        raise DeviceError(f"Android did not confirm per-user removal of {target}.")
            else:
                try:
                    response = device.shell("pm", "clear", "--user", "0", "--cache-only", target, timeout=12)
                except DeviceError as exc:
                    raise DeviceError(f"Cache result is unconfirmed for {target}. Check Storage and cache on the phone. Prior changes are in the journal.") from exc
                if response != "Success":
                    raise DeviceError(f"Cache clear failed for {target}. Use Storage and cache on the phone.")
            if kind != "cache" and not same_value(op, before_value(device, kind, target), expected):
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
            if op.get("state") not in {"pending", "started", "applied", "unchanged", "restoring", "restored"}:
                raise DeviceError("Invalid journal state.")
            verify_prior(op, op.get("before"))
            if op["kind"] in APP_ACTIONS and not oem.applies_to(oem.RULES[op["target"]], oem.manufacturer(device)):
                raise DeviceError("The saved app rule does not match this manufacturer.")
        errors = []
        for op in reversed(entries):
            if op["kind"] == "cache" or op["state"] not in {"started", "applied", "restoring"}:
                continue
            try:
                restore_one(device, journal_path, journal, op)
            except DeviceError as exc:
                errors.append(f'{op["target"]}: {exc}')
        if errors:
            raise DeviceError("Some actions could not be restored. Other eligible actions were attempted.\n"
                              + "\n".join(errors))
    return entries


def restore_one(device, journal_path, journal, op):
    kind, target, value = (op[key] for key in ("kind", "target", "value"))
    before = op["before"]
    current = before_value(device, kind, target)
    if kind == "remove" and current != before:
        if journal.get("build") != device.prop("ro.build.fingerprint"):
            raise DeviceError("The build changed after app removal. Check the OEM store or app settings before restoring.")
        if current == value or (op["state"] == "restoring" and current in RESTORABLE_APP_STATES):
            op["state"] = "restoring"
            write_journal(journal_path, journal)
            if current == value:
                device.shell("pm", "install-existing", "--user", "0", target)
            device.shell("pm", RESTORABLE_APP_STATES[before], "--user", "0", target)
    elif kind == "dns":
        dns.restore(device, before, value)
    elif same_value(op, current, value) and not same_value(op, current, before):
        if kind == "setting":
            dns.put_setting(device, target, before)
        elif kind == "disable":
            device.shell("pm", RESTORABLE_APP_STATES[before], "--user", "0", target)
    if not same_value(op, before_value(device, kind, target), before):
        raise DeviceError(f"{target} changed independently. Resolve it on the phone before retrying.")
    op["state"] = "restored"
    write_journal(journal_path, journal)
