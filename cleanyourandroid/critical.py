"""Packages excluded from debloat even if a future OEM rule names them.

Identifiers and patterns adapted from Shibakaa/cleanyourdroid at 6234b0b.
Copyright (c) 2026 cleanyourdroid contributors; see LICENSES/cleanyourdroid-MIT.txt.
"""

from fnmatch import fnmatchcase


PACKAGES = frozenset({
    # global
    "android",
    "com.android.dialer",
    "com.android.inputmethod.latin",
    "com.android.keychain",
    "com.android.launcher3",
    "com.android.packageinstaller",
    "com.android.phone",
    "com.android.providers.downloads",
    "com.android.providers.media",
    "com.android.providers.telephony",
    "com.android.server.telecom",
    "com.android.settings",
    "com.android.settings.intelligence",
    "com.android.systemui",
    "com.android.vending",
    "com.google.android.gms",
    "com.google.android.gsf",
    "com.google.android.inputmethod.latin",
    "com.google.android.packageinstaller",
    "com.google.android.permissioncontroller",
    "com.google.android.providers.media.module",
    "com.touchtype.swiftkey",
    # xiaomi_hyperos
    "com.mi.android.globallauncher",
    "com.miui.core",
    "com.miui.guardprovider",
    "com.miui.home",
    "com.miui.powerkeeper",
    "com.miui.securityadd",
    "com.miui.securitycenter",
    "com.miui.systemui.carriers.overlay",
    "com.xiaomi.account",
    "com.xiaomi.finddevice",
    "com.xiaomi.xmsf",
    # samsung_oneui
    "com.samsung.android.SettingsReceiver",
    "com.samsung.android.biometrics.service",
    "com.samsung.android.honeyboard",
    "com.samsung.android.incallui",
    "com.samsung.android.knox.containercore",
    "com.samsung.android.spay",
    "com.sec.android.app.SecSetupWizard",
    "com.sec.android.app.launcher",
    # bbk_coloros
    "com.coloros.safecenter",
    "com.coloros.wirelesssettings",
    "com.oplus.athena",
    "com.oplus.battery",
    "com.oplus.securitypermission",
    "com.oppo.launcher",
    # google_pixel
    "com.google.android.apps.nexuslauncher",
    "com.google.android.apps.turbo",
    "com.google.android.as",
    "com.google.android.dialer",
    "com.google.android.settings.intelligence",
    # Additional vivo and Xiaomi launcher, security, and power services.
    "com.bbk.launcher2",
    "com.iqoo.secure",
    "com.vivo.permissionmanager",
    "com.xiaomi.joyose",
})

PATTERNS = (
    "com.google.android.gms.*",
    "com.google.android.gsf*",
    "com.android.*.overlay",
    "com.miui.*.overlay",
    "com.samsung.android.knox.*",
    "android.*",
)


def protected(package):
    return package in PACKAGES or any(fnmatchcase(package, pattern) for pattern in PATTERNS)
