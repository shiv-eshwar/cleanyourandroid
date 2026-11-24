"""Conservative rules for optional OEM preinstalls."""

from collections import Counter
from dataclasses import dataclass
import re

from .adb import DeviceError

AURA = "com.aura.oobe.solutions"
IMAGE_PREFIXES = ("/system/", "/system_ext/", "/product/", "/vendor/", "/odm/")


@dataclass(frozen=True)
class Rule:
    manufacturer: str
    label: str
    purpose: str
    impact: str
    markers: tuple[str, ...]


RULES = {
    AURA: Rule("nothing", "Aura recommendations", "Preloaded app recommendations and delivery.",
               "Stops this recommendation app. Setup and suggested installs can change.",
               ("com.ironsource.aura.", "com.ironsource.appmanager.")),
    "com.heytap.market": Rule(
        "oppo", "OPPO App Market", "OEM app store and recommendations.",
        "Use the in-app recommendation controls first if you rely on App Market or its updates.",
        ("com.heytap.market.", "com.oppo.market.", "/AppMarket", "/HeytapMarket")),
    "com.vivo.appstore": Rule(
        "vivo", "vivo V-Appstore", "OEM app store that may provide Hot Apps and Hot Games.",
        "This can stop an OEM store or updater you use. Try turning off Hot Apps and Hot Games inside the store first.",
        ("com.vivo.appstore.", "/VivoAppStore", "/AppStore")),
}


OEM_AD_CONTROLS = {
    "oppo": [
        "In App Market, open the account/profile settings and look for recommendations or personalized recommendations.",
        "Check the Browser, Theme Store, and lock-screen content settings for separate recommendations and notifications.",
    ],
    "vivo": [
        "In V-Appstore settings, turn off Hot Apps and Hot Games if that switch is available.",
        "Check launcher app suggestions and lock-screen content separately. Names vary by build and region.",
    ],
    "nothing": [
        "Check the app or notification channel responsible for unwanted recommendations before disabling a component.",
    ],
}


def packages(device, *options):
    output = device.shell("pm", "list", "packages", "--user", "0", *options)
    return {line.removeprefix("package:") for line in output.splitlines() if line.startswith("package:")}


def manufacturer(device):
    return device.prop("ro.product.manufacturer").strip().casefold()


def package_state(device, package):
    dump = device.shell("dumpsys", "package", package)
    match = re.search(r"^[ \t]*User 0: [^\n]*\binstalled=(true|false)[^\n]*\benabled=([0-4])\b", dump, re.M)
    if not match:
        raise DeviceError(f"Cannot verify the primary user's package state for {package}.")
    return int(match[2]) if match[1] == "true" else -1


def protected_packages(device):
    home = device.shell("cmd", "package", "resolve-activity", "--brief", "--user", "0",
                        "-a", "android.intent.action.MAIN", "-c", "android.intent.category.HOME")
    resolved = re.findall(r"(?m)^([A-Za-z][\w.]+)/[A-Za-z.][\w.$]*$", home)
    role = device.shell("dumpsys", "role")
    admins = device.shell("dumpsys", "device_policy")
    if len(resolved) != 1 or resolved[0] == "android" or not role.startswith("ROLE STATE") or not admins.startswith("Current Device Policy Manager state"):
        raise DeviceError("Cannot verify the current Home, app roles, and device administrator state.")
    protected = set(resolved)
    protected.update(re.findall(r"\b[A-Za-z][\w]*(?:\.[\w]+)+\b", role + "\n" + admins))
    for key in ("default_input_method", "enabled_input_methods", "enabled_accessibility_services", "always_on_vpn_app"):
        value = device.shell("settings", "--user", "0", "get", "secure", key)
        protected.update(re.findall(r"\b[A-Za-z][\w]*(?:\.[\w]+)+\b", value))
    return protected


def verified_candidates(device, *, strict=False):
    brand = manufacturer(device)
    candidates = {name for name, rule in RULES.items() if rule.manufacturer == brand}
    present = candidates & packages(device, "-s")
    if not present:
        return []
    try:
        protected = protected_packages(device)
        raw = device.shell("pm", "list", "packages", "--user", "0", "-U", "-u")
        uid_map = {name: int(uid) for name, uid in re.findall(r"(?m)^package:([^\s]+)\s+uid:(\d+)\s*$", raw)}
    except DeviceError:
        if strict:
            raise
        return []
    counts = Counter(uid_map.values())
    enabled = packages(device, "-e")
    rows = []
    for name in sorted(present):
        uid = uid_map.get(name, 0)
        if name in protected or not 10000 <= uid < 20000 or counts[uid] != 1:
            continue
        rule = RULES[name]
        dump = device.shell("dumpsys", "package", name)
        paths = device.shell("pm", "path", "--user", "0", name)
        if re.search(r"(?im)^\s*sharedUser(?:Id)?\s*=\s*(?!null\s*$|0\s*$)\S", dump):
            continue
        code_paths = [line.removeprefix("package:") for line in paths.splitlines() if line.startswith("package:")]
        if not code_paths or not any(marker in dump or marker in paths for marker in rule.markers):
            continue
        # Per-user removal can reliably retain the same version only for an APK on the system image.
        remove_allowed = all(path.startswith(IMAGE_PREFIXES) for path in code_paths) and "UPDATED_SYSTEM_APP" not in dump
        rows.append({
            "package": name, "label": rule.label, "reason": rule.purpose, "impact": rule.impact,
            "disable_allowed": name in enabled, "remove_for_primary_user_allowed": remove_allowed,
        })
    return rows


def review_apps(device, known):
    try:
        output = device.shell("cmd", "package", "query-activities", "--components", "--user", "0",
                              "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER")
    except DeviceError:
        return None
    launchable = set(re.findall(r"(?m)^([A-Za-z][\w.]+)/[A-Za-z.][\w.$]*$", output))
    return sorted(launchable & packages(device, "-s") - known)


def report(device):
    brand = manufacturer(device)
    verified = verified_candidates(device)
    return {
        "manufacturer": brand,
        "candidates": verified,
        "declared_preinstalled_apps_for_manual_review": review_apps(device, {row["package"] for row in verified}),
        "manual_review_note": "Inventory only. System apps can be essential or provide updates.",
        "recommendation_controls_to_check": OEM_AD_CONTROLS.get(brand, []),
    }
