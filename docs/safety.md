# Approval and recovery

Read-only commands operate on an already authorized ADB connection. The CLI automatically selects a device only when one online transport exists. Apply and restore commands require the primary Android user and use a fingerprint derived from the phone's hardware serial to detect a different phone. A new build requires a fresh plan for new changes.

## Settings and packages

The plan shows current values and requested changes. Its SHA-256 approval binds the exact local file. Read it before copying the digest. Each apply saves the journal before making changes. The journal records which work was attempted even if ADB disconnects before a result arrives.

To recover an interrupted settings run, reconnect the same phone and run `cleanyourandroid restore JOURNAL`. If a value changed independently, the tool stops so you can resolve it on the phone. Cache-only clears do not support rollback. If Android does not confirm one, check **App info → Storage and cache → Clear cache**. A cache-only plan must match Android's package-manager help and the shell's internal cache permission. Some builds silently ignore the older permission. See the Android 16 sources for [the clear command](https://github.com/aosp-mirror/platform_frameworks_base/blob/android-16.0.0_r1/services/core/java/com/android/server/pm/PackageManagerShellCommand.java) and [the permission check](https://github.com/aosp-mirror/platform_frameworks_base/blob/android-16.0.0_r1/services/core/java/com/android/server/pm/PackageManagerService.java).

If a process was killed and a stale lock remains under `~/.cyandroid/`, first confirm there is no cleanup still running. Read the journal, then remove only the stale lock identified in the error.

## Existing 0.2 file backups

The current CLI has no commands to list, copy, or delete phone files. Existing backups on your computer are untouched. If you need to recover an old backup, keep its `files.json` and `payload/` together. Use the [v0.2.0 recovery instructions](https://github.com/shiv-eshwar/cleanyourandroid/blob/v0.2.0/docs/safety.md) with that version in a separate checkout. Use an absolute manifest path. No migration or rescan is needed.
