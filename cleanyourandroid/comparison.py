"""Compare two saved audits offline without publishing the underlying inventory."""

from datetime import datetime, timezone
import hashlib
from html import escape
import re

from .adb import DeviceError

# Restrict exported fields: app names, device IDs, CPU processes and DNS hosts
# from a private audit must never be copied wholesale to a shareable report.
METRICS = (
    ("Free storage", ("volume", "free_bytes"), "bytes"),
    ("Available memory", ("memory_available_bytes",), "bytes"),
    ("Installed system packages", ("package_counts", "system"), "packages"),
    ("Installed third-party packages", ("package_counts", "third_party"), "packages"),
    ("Disabled packages", ("package_counts", "disabled"), "packages"),
)
NOTE = ("These are two observations. Free storage and available memory also change with background activity. "
        "A difference does not measure speed, battery life, or space reclaimed by the cleaner.")


def capture_key(device):
    try:
        hardware = device.identity()
        firmware = device.prop("ro.build.fingerprint")
    except DeviceError:
        return None
    if not firmware or firmware.lower() in {"unknown", "null"}:
        return None
    return hashlib.sha256(f"cyandroid-audit-v1\0{hardware}\0{firmware}".encode()).hexdigest()


def capture_time(report):
    try:
        instant = datetime.fromisoformat(report["captured_at"])
        if instant.utcoffset() is None:
            raise ValueError
        return instant.astimezone(timezone.utc)
    except (KeyError, TypeError, ValueError) as exc:
        raise DeviceError("Audit needs a valid capture timestamp with a time zone.") from exc


def counter(report, path):
    value = report
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    if value is None:
        return None
    if type(value) is not int or not 0 <= value < 2**63:
        raise DeviceError(f"Invalid audit measurement: {'.'.join(path)}.")
    return value


def compare(before, after):
    if not all(isinstance(r, dict) and isinstance(r.get("comparison_key"), str)
               and re.fullmatch(r"[0-9a-f]{64}", r["comparison_key"]) for r in (before, after)):
        raise DeviceError("Use two saved audit --out reports with a readable hardware identity and firmware.")
    if before["comparison_key"] != after["comparison_key"]:
        raise DeviceError("These audits are from different devices or firmware builds.")
    start, end = capture_time(before), capture_time(after)
    if end <= start:
        raise DeviceError("The after audit must be newer than the before audit.")
    rows = []
    for label, path, unit in METRICS:
        old, new = counter(before, path), counter(after, path)
        rows.append({"metric": label, "unit": unit, "before": old, "after": new,
                     "change": new - old if old is not None and new is not None else None})
    return {"from": start.isoformat(), "to": end.isoformat(), "measurements": rows, "note": NOTE}


def display(value, unit, signed=False):
    if value is None:
        return "—"
    sign = "+" if signed and value > 0 else ""
    return sign + (f"{value / 1024**2:,.2f} MiB" if unit == "bytes" else f"{value:,}")


def html_report(result):
    rows = []
    for row in result["measurements"]:
        cells = "".join(f'<td>{escape(display(row[k], row["unit"], k == "change"))}</td>'
                        for k in ("before", "after", "change"))
        rows.append(f'<tr><th scope="row">{escape(row["metric"])}</th>{cells}</tr>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Android maintenance comparison</title>
<style>
body{{font:1rem/1.5 system-ui,sans-serif;color:#182d31;background:#fbfbf7;margin:3rem auto;padding:0 1rem;max-width:52rem}}
h1{{line-height:1.15}} small{{color:#385d63}} table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}
th,td{{padding:.6rem .35rem;border-bottom:1px solid #b4c2be;text-align:right}}
th:first-child{{text-align:left}} thead{{background:#e7efea}} section{{overflow-x:auto}}
</style></head><body><main><small>CleanYourAndroid</small><h1>Before and after maintenance</h1>
<p>From {escape(result['from'])} to {escape(result['to'])}.</p>
<section><table><thead><tr><th scope="col">Measurement</th><th scope="col">Before</th>
<th scope="col">After</th><th scope="col">Change</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>
<p>{escape(result['note'])} A dash means Android did not report a value.</p></main></body></html>
"""
