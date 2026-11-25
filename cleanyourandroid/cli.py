"""Command-line entry point for Android audits and approved maintenance."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from . import audit as reporting
from . import dns, oem, plan
from .adb import Device, DeviceError, devices


def target(parser):
    parser.add_argument("--serial", help="ADB device serial from the devices command")


def parser():
    root = argparse.ArgumentParser(
        prog="cleanyourandroid", description="Audit and tune your Android phone over ADB.")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("devices", help="List USB and wireless ADB transports")
    for name in ("audit", "diagnose", "standby", "ads"):
        sub = commands.add_parser(name, help=f"Collect a read-only {name} report")
        target(sub)
        sub.add_argument("--out", type=Path, help="Save JSON to a new file")
    sub = commands.add_parser("frames", help="Record cumulative graphics counters for one app")
    target(sub)
    sub.add_argument("package")
    sub.add_argument("--out", type=Path)
    for name in ("compare-frames", "compare-standby"):
        sub = commands.add_parser(name, help=f"Calculate the delta between two {name[8:]} snapshots")
        sub.add_argument("before", type=Path)
        sub.add_argument("after", type=Path)
    sub = commands.add_parser("plan", help="Preview explicit package and performance changes")
    target(sub)
    sub.add_argument("--out", type=Path, required=True)
    sub.add_argument("--disable-aura", action="store_true", help="Alias for --disable-package com.aura.oobe.solutions")
    sub.add_argument("--disable-package", action="append", default=[], choices=oem.RULES,
                     help="Disable one verified optional OEM package, preserving its data")
    sub.add_argument("--remove-preinstall", action="append", default=[], choices=oem.RULES,
                     help="Remove a verified base-image package for primary user 0 and keep its data")
    sub.add_argument("--private-dns", metavar="HOSTNAME", help="Use an explicitly selected DNS-over-TLS resolver")
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
    return root


def operations(args):
    rows = []
    disabled = [*args.disable_package, *([oem.AURA] if args.disable_aura else [])]
    rows.extend(dict(kind="disable", target=package, value=3) for package in disabled)
    rows.extend(dict(kind="remove", target=package, value=-1) for package in args.remove_preinstall)
    if args.private_dns is not None:
        rows.append(dict(kind="dns", target="private_dns", value=dns.hostname(args.private_dns)))
    if args.disable_auto_saver:
        rows.append(dict(kind="setting", target=reporting.SAVER, value="0"))
    if args.disable_always_on_mobile_data:
        rows.append(dict(kind="setting", target=reporting.CELLULAR, value="0"))
    rows.extend(dict(kind="cache", target=package, value=None) for package in args.clear_cache)
    return rows


def read_json(path):
    return json.loads(path.read_bytes())


def execute(args):
    command = args.command
    if command == "devices":
        return devices()
    if command in {"compare-frames", "compare-standby"}:
        before, after = (read_json(path) for path in (args.before, args.after))
        if before["connection"] != after["connection"]:
            raise DeviceError("Snapshots must use the same ADB serial.")
        if command == "compare-standby":
            return reporting.standby_delta(before["standby"], after["standby"])
        if before["package"] != after["package"]:
            raise DeviceError("Frame snapshots must use the same app.")
        return reporting.frame_delta(before["graphics"], after["graphics"])
    device = Device(args.serial)
    if command == "audit":
        return reporting.audit(device)
    if command == "ads":
        return reporting.ads_report(device)
    if command == "diagnose":
        return reporting.diagnostic_report(device)
    if command == "standby":
        return {
            "connection": hashlib.sha256(device.serial.encode()).hexdigest(),
            "standby": reporting.standby(device),
        }
    if command == "frames":
        return {
            "package": args.package,
            "connection": hashlib.sha256(device.serial.encode()).hexdigest(),
            "battery_saver": device.shell("settings", "get", "global", "low_power"),
            "graphics": reporting.frame_stats(device, args.package),
        }
    if command == "plan":
        rows = operations(args)
        approval = plan.create_plan(device, rows, args.out)
        return {"plan": str(args.out), "approval_sha256": approval, **read_json(args.out)}
    if command == "apply":
        return {"journal": str(args.journal), "operations": plan.apply(device, args.plan, args.approve, args.journal)}
    if command == "restore":
        return {"operations": plan.restore(device, args.journal)}
    raise DeviceError(f"Unknown command {command}")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = execute(args)
        if args.command in {"audit", "diagnose", "standby", "ads", "frames"} and args.out:
            plan.create_json(args.out, result)
        sys.stdout.buffer.write(plan.json_bytes(result))
    except (DeviceError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. Review any local journal before retrying.", file=sys.stderr)
        return 130
    return 0
