# Changelog

## 0.3.0 (on main)

- Added a reviewable light preset, a control for the three animation scales, battery condition reporting, and a configurable Battery Saver percentage trigger.
- Added Xiaomi System Ads variants, the OPPO ad service, and an alternate vivo store rule. OEM checks refuse unverified packages. Physical-device validation for these manufacturers is pending.
- Added cache-only plans for named apps and preview by size. Unsupported builds can open Android's App info screen without clearing any data.
- Removed personal-file scanning, backup, removal, and restore commands from the current CLI. Existing backups are untouched. See [recovery instructions](docs/safety.md#existing-02-file-backups) if you have a 0.2 backup.
- Added a disposable Android emulator check alongside the Linux, macOS, and Windows test matrix.

## 0.2.0

Added OEM preinstall checks, per-user removal with data retention, and optional Private DNS plans. [Source at v0.2.0](https://github.com/shiv-eshwar/cleanyourandroid/tree/v0.2.0).
