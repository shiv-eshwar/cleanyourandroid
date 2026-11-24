# Approval, backup, and recovery

Read-only commands operate on an already authorized ADB connection. The CLI automatically selects a device only when one online transport exists. Apply and restore commands require the primary Android user and use a fingerprint derived from the phone's hardware serial to detect a different phone. A new build requires a fresh plan for new changes.

## Settings and packages

The plan shows current values and requested changes. Its SHA-256 approval binds the exact local file. Read it before copying the digest. Each apply saves the journal before making changes. The journal records which work was attempted even if ADB disconnects before a result arrives.

To recover an interrupted settings run, reconnect the same phone and run `cleanyourandroid restore JOURNAL`. If a value changed independently, the tool stops so you can resolve it on the phone. Cache-only clears do not support rollback. If Android does not confirm one, check **App info → Storage and cache → Clear cache**. To preserve drafts when reducing an installed app's footprint, use Android's **Archive** option where available.

## Files

The backup command copies selected files to a new local directory, computes SHA-256 on the phone and computer, and records the original paths in `files.json`. The payload files have portable local names. Keep the manifest and payload directory together. Their contents remain private unless you share them.

Before a deletion, the CLI checks the corresponding backup and, for WhatsApp Sent duplicates, checks the retained copy. It moves the removal candidate to a temporary name in the same folder, re-checks the bytes, and removes that verified copy. If a disconnect interrupts the move, reconnect the phone and rerun `remove-files` with the same manifest and approval digest. If the CLI reports both an original and staged file, review the named paths before acting so a newer copy is kept.

Use `restore-files` with the same manifest to restore the backed-up bytes into available original folders. Changes made by messaging apps to their own indexes fall outside this operation.

If a process was killed and a stale lock remains under `~/.cyandroid/`, first confirm there is no cleanup still running. Read the journal or manifest, then remove only the stale lock identified in the error.
