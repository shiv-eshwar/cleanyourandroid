---
name: cleanyourandroid
description: Audit an owned Android phone over USB or wireless ADB for stutter, heat, battery drain, bloatware, app cache, and large files. Use when the user wants an evidence-based performance check or an approved, reversible cleanup. Requires a trusted host with access to the phone.
---

# CleanYourAndroid

Locate the `cleanyourandroid` command. If the source checkout is available, run `python -m cleanyourandroid` from its root. Otherwise follow the repository's [installation instructions](https://github.com/shiv-eshwar/cleanyourandroid#quick-start). Use the read-only MCP tools if configured.

1. Use `devices` and verify the Android model. An endpoint in the pairing dialog has a different purpose from the endpoint on the main Wireless debugging page. Use USB for standby measurements when wireless debugging might affect results. If multiple transports appear, select the trusted serial explicitly.
2. Run `audit` or `diagnose` first. Explain whether the evidence shows storage pressure, sustained load, thermal limits, or a Battery Saver policy. A CPU snapshot is brief. A requested refresh-rate limit and the active renderer can differ. For stutter, capture `frames` twice around the same gesture and use `compare-frames`. For a mode comparison, repeat the workload in each mode and capture each mode separately. Report when real low-charge behavior was not observed.
3. Present specific options and their tradeoffs. Build a `plan` only for chosen operations. Show the actions and the approval digest before applying. Preserve the rollback journal and verify the result. Use Android's **Clear cache** screen when the CLI cannot confirm cache clearing. Avoid **Clear storage** for a cache task.
4. For storage cleanup, use `files --duplicates` to validate candidate copies, and `backup-files` for the explicitly chosen paths. Keep the external copy of each WhatsApp video. Tell the user that removing a Sent copy can break access from that chat. Apply `remove-files` only for a reviewed manifest. For local app drafts, use the phone's built-in app archive option if available.

Keep reports and backups on the user's computer. Package names and file paths can be private. Don't infer authorization from an audit request, override thermal protections, or disable an unfamiliar system component based on its name.
