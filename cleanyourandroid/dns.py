"""Private DNS configuration for an explicitly selected DNS-over-TLS resolver."""

import re

from .adb import DeviceError

MODE = "private_dns_mode"
SPECIFIER = "private_dns_specifier"
MODES = {"null", "off", "opportunistic", "hostname"}


def hostname(value):
    if not isinstance(value, str) or len(value) > 253:
        raise DeviceError("Enter a DNS-over-TLS provider hostname.")
    labels = value.split(".")
    if (len(labels) < 2 or not re.search(r"[A-Za-z]", labels[-1]) or
            any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                for label in labels)):
        raise DeviceError("Enter a DNS-over-TLS provider hostname without a URL, IP, port, or wildcard.")
    return value.lower()


def read(device):
    return {
        "mode": device.shell("settings", "get", "global", MODE),
        "hostname": device.shell("settings", "get", "global", SPECIFIER),
    }


def desired(provider):
    return {"mode": "hostname", "hostname": provider}


def validate_state(state):
    if not isinstance(state, dict) or set(state) != {"mode", "hostname"} or state["mode"] not in MODES:
        raise DeviceError("Unexpected Private DNS mode. Use Android's network settings to review it.")
    if state["hostname"] != "null":
        hostname(state["hostname"])


def put_setting(device, key, value):
    if value == "null":
        device.shell("settings", "delete", "global", key)
    else:
        device.shell("settings", "put", "global", key, value)


def apply(device, provider):
    put_setting(device, SPECIFIER, provider)
    put_setting(device, MODE, "hostname")


def restore(device, before, provider):
    current = read(device)
    partial = {"mode": before["mode"], "hostname": provider}
    if current == before:
        return
    if current not in (desired(provider), partial):
        raise DeviceError("Private DNS changed independently. Review it on the phone first.")
    put_setting(device, MODE, before["mode"])
    put_setting(device, SPECIFIER, before["hostname"])
