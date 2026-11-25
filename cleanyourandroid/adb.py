"""ADB transport shared by the CLI and the read-only MCP server."""

import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess


class DeviceError(RuntimeError):
    pass


def adb_binary():
    candidates = [
        os.getenv("CLEANYOURANDROID_ADB"),
        shutil.which("adb"),
        *(Path(value) / "platform-tools" / "adb" for key in ("ANDROID_HOME", "ANDROID_SDK_ROOT")
          if (value := os.getenv(key))),
        Path.home() / "Library/Android/sdk/platform-tools/adb",
        Path.home() / "Android/Sdk/platform-tools/adb",
    ]
    if local_app_data := os.getenv("LOCALAPPDATA"):
        candidates.append(Path(local_app_data) / "Android/Sdk/platform-tools/adb.exe")
    for candidate in filter(None, candidates):
        if executable := shutil.which(candidate):
            return executable
    raise DeviceError("ADB was not found. Install Android SDK Platform-Tools or set CLEANYOURANDROID_ADB.")


def run_adb(*args, timeout=30):
    try:
        result = subprocess.run(
            [adb_binary(), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeviceError(f"ADB {args[0]} failed or timed out after {timeout}s: {exc.__class__.__name__}") from exc
    if result.returncode:
        message = (result.stderr or result.stdout).decode(errors="replace").strip()
        raise DeviceError(message or f"ADB returned exit code {result.returncode}")
    return result.stdout


def devices():
    raw = run_adb("devices", "-l").decode(errors="replace")
    rows = []
    for line in raw.splitlines():
        if not line or line.startswith(("List of devices", "*")):
            continue
        fields = line.split()
        if len(fields) >= 2:
            details = dict(field.split(":", 1) for field in fields[2:] if ":" in field)
            rows.append(dict(serial=fields[0], state=fields[1], model=details.get("model"),
                             transport_id=details.get("transport_id")))
    return rows


class Device:
    def __init__(self, serial=None):
        online = {row["serial"]: row for row in devices() if row["state"] == "device"}
        if serial is None and len(online) == 1:
            serial = next(iter(online))
        if not serial or serial not in online:
            raise DeviceError("Select one authorized online device with --serial from the devices command.")
        self.serial = serial
        transport = online[serial]["transport_id"]
        self.selector = ("-t", transport) if transport and transport.isdecimal() else ("-s", serial)

    def shell_bytes(self, *words, timeout=30):
        command = " ".join(shlex.quote(str(word)) for word in words)
        return run_adb(*self.selector, "shell", "-T", command, timeout=timeout)

    def shell(self, *words, timeout=30):
        return self.shell_bytes(*words, timeout=timeout).decode(errors="replace").strip()

    def prop(self, name):
        return self.shell("getprop", name)

    def identity(self):
        serial = self.prop("ro.serialno")
        if serial.lower() in {"", "unknown", "null"}:
            raise DeviceError("The phone did not expose a hardware serial. Device writes are disabled.")
        return hashlib.sha256(serial.encode()).hexdigest()

    def is_owner_active(self):
        return self.shell("am", "get-current-user") == "0"


def package_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", value):
        raise DeviceError("Enter a full Android package name.")
    return value
