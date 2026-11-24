"""Command-line entry point for Android audits and approved maintenance."""

import argparse
import sys
from pathlib import Path

from . import audit as reporting
from . import files, plan
from .adb import Device, DeviceError, devices


def target(parser):
    parser.add_argument("--serial", help="ADB device serial from the devices command")


def parser():
    root = argparse.ArgumentParser(
        prog="cleanyourandroid", description="Audit and tune your Android phone over ADB.")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("devices", help="List USB and wireless ADB transports")
    for name in ("audit", "diagnose"):
        sub = commands.add_parser(name, help=f"Collect a read-only {name} report")
        target(sub)
        sub.add_argument("--out", type=Path, help="Save JSON to a new file")
    sub = commands.add_parser("frames", help="Record cumulative graphics counters for one app")
    target(sub)
    sub.add_argument("package")
    sub.add_argument("--out", type=Path)
    sub = commands.add_parser("compare-frames", help="Compare two snapshots of the same interaction window")
    sub.add_argument("before", type=Path)
    sub.add_argument("after", type=Path)
    sub = commands.add_parser("files", help="Find large Downloads, Camera and WhatsApp Sent files")
    target(sub)
    sub.add_argument("--min-mib", type=int, default=75)
    sub.add_argument("--duplicates", action="store_true", help="Hash same-size candidates on the phone")
    sub.add_argument("--out", type=Path)
    sub = commands.add_parser("plan", help="Preview explicit package and performance changes")
    target(sub)
    sub.add_argument("--out", type=Path, required=True)
    sub.add_argument("--disable-aura", action="store_true")
    sub.add_argument("--disable-auto-saver", action="store_true")
    sub.add_argument("--disable-always-on-mobile-data", action="store_true")
    sub.add_argument("--clear-cache", action="append", default=[], choices=reporting.CACHE_TARGETS)
    sub = commands.add_parser("apply", help="Apply a reviewed plan and save a rollback journal")
    target(sub)
    sub.add_argument("plan", type=Path)
    sub.add_argument("--approve", required=True, help="SHA-256 shown when the plan was created")
    sub.add_argument("--journal", type=Path, required=True)
    sub = commands.add_parser("restore", help="Restore reversible settings in a local journal")
    target(sub)
    sub.add_argument("journal", type=Path)
    sub = commands.add_parser("backup-files", help="Back up selected APKs and confirmed duplicate videos")
    target(sub)
    sub.add_argument("--out", type=Path, required=True, help="New local backup folder")
    sub.add_argument("--apk", action="append", default=[], metavar="PATH")
    sub.add_argument("--duplicate", action="append", nargs=2, default=[], metavar=("SENT_COPY", "RETAINED_COPY"))
    sub = commands.add_parser("remove-files", help="Remove only files in a reviewed verified backup manifest")
    target(sub)
    sub.add_argument("manifest", type=Path)
    sub.add_argument("--approve", required=True, help="SHA-256 shown when the backup was created")
    return root


def operations(args):
    rows = []
    if args.disable_aura:
        rows.append(dict(kind="disable", target=reporting.AURA, value=3))
    if args.disable_auto_saver:
        rows.append(dict(kind="setting", target=reporting.SAVER, value="0"))
    if args.disable_always_on_mobile_data:
        rows.append(dict(kind="setting", target=reporting.CELLULAR, value="0"))
    rows.extend(dict(kind="cache", target=package, value=None) for package in args.clear_cache)
    return rows


def read_json(path):
    import json
    return json.loads(path.read_bytes())


def execute(args):
    command = args.command
    if command == "devices":
        return devices()
    if command == "compare-frames":
        before, after = (read_json(path) for path in (args.before, args.after))
        if before["package"] != after["package"] or before["connection"] != after["connection"]:
            raise DeviceError("Snapshots must use the same app and ADB transport.")
        return reporting.frame_delta(before["graphics"], after["graphics"])
    device = Device(args.serial)
    if command == "audit":
        return reporting.audit(device)
    if command == "diagnose":
        return reporting.diagnostic_report(device)
    if command == "frames":
        import hashlib
        return {
            "package": args.package,
            "connection": hashlib.sha256(device.serial.encode()).hexdigest(),
            "battery_saver": device.shell("settings", "get", "global", "low_power"),
            "graphics": reporting.frame_stats(device, args.package),
        }
    if command == "files":
        return files.inspect_files(device, args.min_mib, args.duplicates)
    if command == "plan":
        rows = operations(args)
        approval = plan.create_plan(device, rows, args.out)
        return {"plan": str(args.out), "approval_sha256": approval, "operations": rows}
    if command == "apply":
        return {"journal": str(args.journal), "operations": plan.apply(device, args.plan, args.approve, args.journal)}
    if command == "restore":
        return {"operations": plan.restore(device, args.journal)}
    if command == "backup-files":
        manifest, approval = files.backup(device, args.out, args.apk, args.duplicate)
        return {"manifest": str(manifest), "approval_sha256": approval}
    if command == "remove-files":
        return files.remove(device, args.manifest, args.approve)
    raise DeviceError(f"Unknown command {command}")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = execute(args)
        if args.command in {"audit", "diagnose", "frames", "files"} and args.out:
            plan.create_json(args.out, result)
        sys.stdout.buffer.write(plan.json_bytes(result))
    except (DeviceError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. Review any local journal or backup before retrying.", file=sys.stderr)
        return 130
    return 0
