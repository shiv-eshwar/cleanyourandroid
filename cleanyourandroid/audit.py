"""Summarize what Android reports without collecting raw bug reports."""

from datetime import datetime, timezone
import json
import re

from .adb import DeviceError, package_name
from . import dns, oem
from .oem import packages

SAVER = "low_power_trigger_level"
CELLULAR = "mobile_data_always_on"
ANIMATIONS = ("window_animation_scale", "transition_animation_scale", "animator_duration_scale")
SCALES = ("0", "0.5", "1")
SAVER_LEVELS = ("15", "20", "25")
SETTINGS = {
    SAVER: "Battery Saver percentage trigger. Earlier activation may extend runtime and reduce performance; 0 disables this trigger.",
    CELLULAR: "Keep a cellular data session active on Wi-Fi. A value of 0 allows it to close.",
    **dict.fromkeys(ANIMATIONS, "Device-wide animation duration: 0 turns motion off, 0.5 shortens it, 1 is standard."),
}
HEALTH = {1: "unknown", 2: "good", 3: "overheat", 4: "dead", 5: "over_voltage",
          6: "unspecified_failure", 7: "cold"}


def cache_only_supported(device):
    # Require both flags on the clear command itself, not somewhere else in pm help.
    try:
        advertised = any(re.fullmatch(r"\s*clear (?:\[--user USER_ID\] \[--cache-only\]|"
                                      r"\[--cache-only\] \[--user USER_ID\]) PACKAGE\s*", line)
                         for line in device.shell("pm", "help").splitlines())
        # AOSP silently ignores the older DELETE_CACHE_FILES permission; the
        # command may hang even on builds whose help advertises --cache-only.
        return advertised and bool(re.search(
            r"^\s*android\.permission\.INTERNAL_DELETE_CACHE_FILES: granted=true\b",
            device.shell("dumpsys", "package", "com.android.shell"), re.M))
    except DeviceError:
        return False


def disk_stats(raw):
    columns = {}
    for line in raw.splitlines():
        field, _, value = line.partition(":")
        if field in {"Package Names", "App Sizes", "App Data Sizes", "Cache Sizes"}:
            try:
                columns[field] = json.loads(value)
            except ValueError:
                return []
    fields = ["Package Names", "App Sizes", "App Data Sizes", "Cache Sizes"]
    if (len(columns) != len(fields) or any(not isinstance(columns[field], list) for field in fields)
            or len({len(columns[field]) for field in fields}) != 1):
        return []
    rows = [
        dict(package=name, app_bytes=code, data_bytes=data, cache_bytes=cache)
        for name, code, data, cache in zip(*(columns[field] for field in fields))
        if isinstance(name, str) and all(type(n) is int and n >= 0 for n in (code, data, cache))
    ]
    return sorted(rows, key=lambda row: row["cache_bytes"], reverse=True)


def data_volume(raw):
    for line in reversed(raw.splitlines()):
        fields = line.split()
        if len(fields) >= 4 and fields[1].isdecimal() and fields[3].isdecimal():
            return dict(total_bytes=int(fields[1]) * 1024, free_bytes=int(fields[3]) * 1024)
    return None


def large_caches(device, min_mib):
    if min_mib < 1:
        raise DeviceError("The cache threshold must be at least 1 MiB.")
    installed = packages(device, "-3")
    stats = disk_stats(device.shell("dumpsys", "diskstats", timeout=45))
    selected = sorted({row["package"] for row in stats if row["package"] in installed
                       and row["cache_bytes"] >= min_mib * 1024**2})
    if not selected:
        raise DeviceError("No matching third-party cache estimate. Review audit or name an installed app explicitly.")
    return selected


def core_snapshot(device):
    battery = device.shell("dumpsys", "battery")
    thermal = device.shell("dumpsys", "thermalservice")
    mem = device.shell("cat", "/proc/meminfo")
    power = device.shell("dumpsys", "power")
    display = device.shell("dumpsys", "display")
    temp = re.search(r"^\s*temperature: (-?\d+)", battery, re.M)
    health = re.search(r"^\s*health: (\d+)\s*$", battery, re.M)
    level = re.search(r"^\s*level: (\d+)", battery, re.M)
    status = re.search(r"^Thermal Status: (\d+)", thermal, re.M)
    memory = re.search(r"^MemAvailable:\s+(\d+) kB", mem, re.M)
    render = re.search(r"mActiveRenderFrameRate=(\d+(?:\.\d+)?)", display)
    cap = re.search(r"PRIORITY_LOW_POWER_MODE_RENDER_RATE[^\n]*mMaxRefreshRate=(\d+(?:\.\d+)?)", display)
    effective = power.partition("Policy 'effective'")[2].partition("Battery saver state machine:")[0]
    launch = re.search(r"^\s*disable_launch_boost=(true|false)\s*$", effective, re.M)
    return {
        "battery_level": int(level[1]) if level else None,
        "battery_celsius": int(temp[1]) / 10 if temp else None,
        "battery_health_status": HEALTH.get(int(health[1]), "unknown") if health else None,
        "thermal_status": int(status[1]) if status else None,
        "memory_available_bytes": int(memory[1]) * 1024 if memory else None,
        "external_power": bool(re.search(r"^\s*(?:AC|USB|Wireless|Dock) powered: true", battery, re.M)),
        "battery_saver": next((line.partition(": ")[2] for line in power.splitlines()
                               if "Battery Saver is currently:" in line), None),
        "low_power_render_limit_fps": float(cap[1]) if cap else None,
        "active_render_fps": float(render[1]) if render else None,
        "launch_boost_disabled": launch[1] == "true" if launch else None,
        "settings": {key: device.shell("settings", "get", "global", key) for key in SETTINGS},
    }


def frame_stats(device, package):
    raw = device.shell("dumpsys", "gfxinfo", package_name(package))
    patterns = {
        "window_ns": r"Stats since: (\d+)ns",
        "frames": r"^Total frames rendered: (\d+)",
        "janky_frames": r"^Janky frames: (\d+)",
        "missed_vsync": r"^Number Missed Vsync: (\d+)",
    }
    first_process = raw.split("** Graphics info for pid ", 2)
    if len(first_process) >= 2 and (pid := re.match(r"(\d+)", first_process[1])):
        result = {"pid": int(pid[1])}
        for key, pattern in patterns.items():
            if match := re.search(pattern, first_process[1], re.M):
                result[key] = int(match[1])
        if all(key in result for key in patterns):
            return result
    raise DeviceError(f"No comparable graphics statistics for {package}. Open it on the phone first.")


def frame_delta(before, after):
    if not all(before[key] == after[key] for key in ("pid", "window_ns")):
        raise DeviceError("The process or graphics counter window changed. Capture both samples again.")
    delta = {key: after[key] - before[key] for key in ("frames", "janky_frames", "missed_vsync")}
    if min(delta.values()) < 0 or delta["frames"] <= 0:
        raise DeviceError("There were no comparable new frames. Repeat the same interaction between samples.")
    return {**delta, "jank_percent": round(100 * delta["janky_frames"] / delta["frames"], 2)}


def cpu_processes(raw):
    rows = []
    for line in raw.splitlines():
        if match := re.match(r"\s*(\d+(?:\.\d+)?)%\s+\d+/([^: ]+(?::[^: ]+)?):\s", line):
            rows.append(dict(process=match[2], percent_of_one_core=float(match[1])))
    return rows[:12]


def diagnostic_report(device):
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "device": {key: device.prop(prop) for key, prop in {
            "manufacturer": "ro.product.manufacturer", "model": "ro.product.model",
            "android": "ro.build.version.release", "build": "ro.build.display.id",
        }.items()},
        "volume": data_volume(device.shell("df", "-k", "/data")),
        **core_snapshot(device),
        "recent_cpu": cpu_processes(device.shell("dumpsys", "cpuinfo")),
    }


def audit(device):
    disabled = packages(device, "-d")
    system = packages(device, "-s")
    user = packages(device, "-3")
    stats = disk_stats(device.shell("dumpsys", "diskstats", timeout=45))
    return {
        **diagnostic_report(device),
        "profile": "Primary user (0)",
        "package_counts": {"third_party": len(user), "system": len(system), "disabled": len(disabled)},
        "cache_estimates": [
            {**row, "system": row["package"] in system, "disabled": row["package"] in disabled}
            for row in stats if row["package"] in system | user
        ][:15],
        "cache_note": "Android's cached estimates. Data bytes include cache. Profile attribution can vary by build.",
        "cache_only_supported": cache_only_supported(device),
        "disable_candidates": [row for row in oem.verified_candidates(device) if row["disable_allowed"]],
    }


def duration_ms(value):
    units = {"d": 86_400_000, "h": 3_600_000, "m": 60_000, "s": 1_000, "ms": 1}
    fields = re.findall(r"(\d+)(ms|[dhms])\b", value)
    if fields and " ".join(number + unit for number, unit in fields) == " ".join(value.split()):
        return sum(int(number) * units[unit] for number, unit in fields)
    return None


def standby_counters(raw):
    start = re.search(r"^\s*Start clock time: (.+)$", raw, re.M)
    off = re.search(r"^\s*Time on battery screen off: (.*?) \([^\n]+?\) realtime, "
                    r"(.*?) \([^\n]+?\) uptime", raw, re.M)
    charge = re.search(r"^\s*Screen off discharge: (\d+(?:\.\d+)?) mAh", raw, re.M)
    wlan = re.search(r"^\s*Wakeup reason .*?\bwlan\d+: .*?\((\d+) times?\)", raw, re.M)
    return {
        "start_clock": start[1].strip() if start else None,
        "screen_off_ms": duration_ms(off[1]) if off else None,
        "screen_off_awake_ms": duration_ms(off[2]) if off else None,
        "screen_off_discharge_mah": float(charge[1]) if charge else None,
        "wlan_wake_count": int(wlan[1]) if wlan else None,
    }


def standby(device):
    # --charged reads the current stats. --checkin can consume an archived report.
    return standby_counters(device.shell("dumpsys", "batterystats", "--charged", timeout=45))


def standby_delta(before, after):
    if not before["start_clock"] or before["start_clock"] != after["start_clock"]:
        raise DeviceError("The charge statistics window changed or is unavailable.")
    keys = ("screen_off_ms", "screen_off_awake_ms", "screen_off_discharge_mah", "wlan_wake_count")
    delta = {key: after[key] - before[key] if None not in (before[key], after[key]) else None for key in keys}
    if any(value < 0 for value in delta.values() if value is not None):
        raise DeviceError("Standby counters decreased. Capture both samples again.")
    interval = delta["screen_off_ms"]
    if not interval:
        raise DeviceError("The phone accumulated no screen-off time on battery power.")
    awake = delta["screen_off_awake_ms"]
    wakes = delta["wlan_wake_count"]
    return {**delta, "awake_percent": round(100 * awake / interval, 2) if awake is not None else None,
            "wlan_wakes_per_hour": round(3_600_000 * wakes / interval, 2) if wakes is not None else None}



def ads_report(device):
    return {
        "model": device.prop("ro.product.model"),
        "build": device.prop("ro.build.display.id"),
        **oem.report(device),
        "private_dns": dns.read(device),
        "private_dns_note": "Choose a DNS-over-TLS provider you trust. DNS filtering cannot block every ad.",
    }
