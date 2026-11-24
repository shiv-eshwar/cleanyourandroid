"""Inspect shared files and stage narrowly scoped, verified removals."""

from collections import defaultdict
import hashlib
from pathlib import Path, PurePosixPath
import re
from secrets import token_hex
import sys

from .adb import DeviceError
from .plan import create_json, device_lock, load_approved

SHARED = PurePosixPath("/storage/emulated/0")
DOWNLOAD = SHARED / "Download"
CAMERA = SHARED / "DCIM/Camera"
QUICK_SHARE = DOWNLOAD / "Quick Share"
SENT = SHARED / "Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Documents/Sent"
APKS = {".apk", ".apks", ".xapk"}
VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


def absolute_file(value):
    if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise DeviceError("A file path contains unsupported control characters.")
    path = PurePosixPath(value)
    if str(path) != value or SHARED not in path.parents or ".." in path.parts:
        raise DeviceError("Enter a canonical path under /storage/emulated/0.")
    return path


def classify(source, original=None):
    if original is None and DOWNLOAD in source.parents and source.suffix.lower() in APKS:
        return "installer"
    if (original is not None and SENT in source.parents and
            any(folder in original.parents for folder in (CAMERA, QUICK_SHARE)) and
            original.suffix.lower() in VIDEO):
        return "sent_video"
    raise DeviceError("Removal supports Downloads installers and verified WhatsApp Sent video copies only.")


def regular_stat(device, path):
    if device.shell("realpath", "--", path) != str(path):
        raise DeviceError(f"Path resolves outside its listed location: {path}")
    raw = device.shell("stat", "-c", "%f %s %d:%i %h", "--", path)
    try:
        mode, size, inode, links = raw.split()
        if int(mode, 16) & 0o170000 != 0o100000 or int(links) < 1:
            raise ValueError
        return int(size), inode
    except ValueError as exc:
        raise DeviceError(f"Expected an ordinary file: {path}") from exc


def backup_path(source):
    identifier = hashlib.sha256(str(source).encode()).hexdigest()
    basename = re.sub(r"[^A-Za-z0-9._-]", "_", source.name.rstrip(" ."))[:100]
    return PurePosixPath("payload") / f"{identifier}-{basename}"


def remote_hash(device, path):
    output = device.shell("sha256sum", "--", path, timeout=180)
    digest = output.partition(" ")[0]
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise DeviceError(f"Could not get a valid file hash: {path}")
    return digest


def local_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def matches(device, source, original=None):
    if original is not None:
        other_size, other_inode = regular_stat(device, original)
        retained_hash = remote_hash(device, original)
    size, inode = regular_stat(device, source)
    digest = remote_hash(device, source)
    if original is not None:
        if other_size != size or inode == other_inode or retained_hash != digest:
            raise DeviceError(f"No independent byte-for-byte retained copy for {source.name}.")
    return size, digest


def inspect_files(device, min_mib=75, check_duplicates=False):
    if type(min_mib) is not int or min_mib < 1:
        raise DeviceError("Use a minimum file size of at least 1 MiB.")
    rows = []
    unavailable = []
    roots = (DOWNLOAD, CAMERA, SENT)
    for root in roots:
        try:
            output = device.shell_bytes("find", root, "-type", "f", "-size",
                                        f"+{min_mib * 1024 * 1024 - 1}c", "-print0", timeout=90)
        except DeviceError:
            unavailable.append(str(root))
            continue
        for raw in output.split(b"\0"):
            if not raw:
                continue
            try:
                path = absolute_file(raw.decode())
                size, _ = regular_stat(device, path)
            except (UnicodeDecodeError, DeviceError):
                continue
            rows.append(dict(path=str(path), bytes=size))
    rows.sort(key=lambda row: row["bytes"], reverse=True)
    pairs = []
    if check_duplicates:
        grouped = defaultdict(list)
        for row in rows:
            grouped[row["bytes"]].append(PurePosixPath(row["path"]))
        for size, paths in grouped.items():
            retained = [p for p in paths if (CAMERA in p.parents or QUICK_SHARE in p.parents) and p.suffix.lower() in VIDEO]
            sent = [p for p in paths if SENT in p.parents]
            if not retained or not sent:
                continue
            by_hash = {remote_hash(device, p): p for p in reversed(retained)}
            for p in sent:
                match = by_hash.get(remote_hash(device, p))
                if match:
                    pairs.append(dict(source=str(p), retain=str(match), bytes=size))
    return {"minimum_mib": min_mib, "files": rows, "confirmed_pairs": pairs,
            "unavailable_roots": unavailable}


def backup(device, folder, installers, duplicates):
    selections = [(absolute_file(path), None) for path in installers]
    selections.extend((absolute_file(path), absolute_file(retained)) for path, retained in duplicates)
    if not selections or len({p for p, _ in selections}) != len(selections):
        raise DeviceError("Choose at least one file and specify each removal once.")
    kinds = [classify(path, original) for path, original in selections]
    with device_lock(device) as identity:
        folder.mkdir(mode=0o700, parents=True, exist_ok=False)
        entries = []
        for (source, original), kind in zip(selections, kinds):
            size, digest = matches(device, source, original)
            relative = backup_path(source)
            local = folder.joinpath(*relative.parts)
            local.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if local.exists():
                raise DeviceError("Two phone paths conflict on this computer's filesystem.")
            device.pull(source, local)
            if local.stat().st_size != size or local_hash(local) != digest:
                raise DeviceError(f"Backup verification failed for {source.name}.")
            entries.append({"kind": kind, "source": str(source), "retain": str(original) if original else None,
                            "backup": str(relative), "bytes": size, "sha256": digest})
        manifest_path = folder / "files.json"
        create_json(manifest_path, {"version": 1, "device_id": identity, "entries": entries})
    return manifest_path, hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def verified_entries(manifest_path, manifest, identity):
    if not isinstance(manifest, dict) or manifest.get("version") != 1 or manifest.get("device_id") != identity:
        raise DeviceError("This file manifest does not match the connected phone.")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise DeviceError("The file manifest is empty or invalid.")
    resolved = []
    seen = set()
    root = manifest_path.parent.resolve()
    for entry in entries:
        if not isinstance(entry, dict):
            raise DeviceError("Invalid file entry.")
        source = absolute_file(entry.get("source"))
        original = absolute_file(entry["retain"]) if entry.get("retain") is not None else None
        if source in seen or classify(source, original) != entry.get("kind"):
            raise DeviceError("Unexpected file selection.")
        seen.add(source)
        relative = backup_path(source)
        if str(relative) != entry.get("backup"):
            raise DeviceError("Backup path does not match the file selected.")
        local = root.joinpath(*relative.parts)
        if local != local.resolve() or not local.is_file() or local.stat().st_size != entry.get("bytes"):
            raise DeviceError(f"Missing or relocated backup for {source.name}.")
        if local_hash(local) != entry.get("sha256"):
            raise DeviceError(f"Backup hash changed for {source.name}.")
        resolved.append((entry, source, original, local))
    return resolved


def exists(device, path):
    return device.shell("sh", "-c", 'if [ -e "$1" ] || [ -L "$1" ]; then echo yes; else echo no; fi',
                        "cleanyourandroid", path) == "yes"


def quarantine_path(source, digest):
    identifier = hashlib.sha256(str(source).encode()).hexdigest()
    return source.parent / f".cleanyourandroid-{identifier}-{digest[:12]}.pending"


def file_stamp(device, path):
    return device.shell("stat", "-c", "%d:%i:%s:%y", "--", path)


def remove_quarantined(device, entry, source, moved, original):
    stamp = file_stamp(device, moved)
    if matches(device, moved, original) != (entry["bytes"], entry["sha256"]):
        raise DeviceError(f"The phone copy no longer matches the backup: {source.name}.")
    device.shell("sh", "-c", 'if [ "$(stat -c "%d:%i:%s:%y" -- "$1")" = "$2" ]; then rm -- "$1"; else exit 1; fi',
                 "cleanyourandroid", moved, stamp)
    if exists(device, moved):
        raise DeviceError(f"Android still shows the staged copy of {source.name}.")


def remove(device, manifest_path, approval):
    manifest = load_approved(manifest_path, approval)
    with device_lock(device) as identity:
        verified = verified_entries(manifest_path, manifest, identity)
        pending = []
        for entry, source, original, _ in verified:
            moved = quarantine_path(source, entry["sha256"])
            present, staged = exists(device, source), exists(device, moved)
            if present and staged:
                raise DeviceError(f"Both {source} and {moved} exist. Inspect them before retrying.")
            if present and matches(device, source, original) != (entry["bytes"], entry["sha256"]):
                raise DeviceError(f"Phone copy changed since backup: {source.name}.")
            if present or staged:
                pending.append((entry, source, original, moved, staged))

        removed = []
        for entry, source, original, moved, staged in pending:
            if not staged:
                device.shell("mv", "-n", "--", source, moved)
                if exists(device, source) or not exists(device, moved):
                    raise DeviceError(f"Could not stage {source.name}. Check {source} and {moved}.")
            try:
                remove_quarantined(device, entry, source, moved, original)
            except DeviceError as exc:
                try:
                    if exists(device, moved):
                        device.shell("mv", "-n", "--", moved, source)
                except DeviceError:
                    pass
                raise DeviceError(f"Stopped on {source.name}. Check {source} and {moved} before retrying. {exc}") from exc
            removed.append(str(source))
            print(f"Verified removal of {source.name}", file=sys.stderr)
    return {"removed": removed, "already_absent": len(verified) - len(pending)}


def restore(device, manifest_path, manifest):
    restored = []
    already_present = []
    with device_lock(device) as identity:
        verified = verified_entries(manifest_path, manifest, identity)
        for entry, destination, _, _ in verified:
            if device.shell("realpath", "--", destination.parent) != str(destination.parent):
                raise DeviceError(f"The original folder is unavailable for {destination.name}.")
            if exists(device, destination) and matches(device, destination) != (entry["bytes"], entry["sha256"]):
                raise DeviceError(f"A different file already exists at {destination}.")
        for entry, destination, _, local in verified:
            if exists(device, destination):
                if matches(device, destination) != (entry["bytes"], entry["sha256"]):
                    raise DeviceError(f"A different file appeared at {destination}.")
                already_present.append(str(destination))
                continue
            temporary = destination.parent / f".cleanyourandroid-{token_hex(12)}.tmp"
            try:
                device.push(local, temporary)
                if matches(device, temporary) != (entry["bytes"], entry["sha256"]):
                    raise DeviceError(f"Restored bytes did not verify for {destination.name}.")
                device.shell("mv", "-n", "--", temporary, destination)
                if matches(device, destination) != (entry["bytes"], entry["sha256"]):
                    raise DeviceError(f"Android did not confirm restoration of {destination.name}.")
            finally:
                device.shell("rm", "-f", "--", temporary)
            restored.append(str(destination))
    return {"restored": restored, "already_present": already_present}
