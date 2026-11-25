---
name: cleanyourandroid
description: Audit an owned Android phone over USB or wireless ADB for stutter, heat, battery drain, bloatware, app cache, unwanted ads, and preinstalled recommendations. Use when the user wants an evidence-based performance check or an approved, reversible cleanup. Requires a trusted host with access to the phone.
---

# CleanYourAndroid

Locate the `cleanyourandroid` command. If the source checkout is available, run `python -m cleanyourandroid` from its root. Otherwise follow the repository's [installation instructions](https://github.com/shiv-eshwar/cleanyourandroid#quick-start). Use the read-only MCP tools if configured.

1. Use `devices` and verify the Android model. An endpoint in the pairing dialog has a different purpose from the endpoint on the main Wireless debugging page. Use USB for standby measurements when wireless debugging might affect results. If multiple transports appear, select the trusted serial explicitly.
2. Run `audit` or `diagnose` first. Explain whether the evidence shows storage pressure, sustained load, thermal limits, or a Battery Saver policy. A CPU snapshot is brief. A requested refresh-rate limit and the active renderer can differ. For stutter, capture `frames` twice around the same gesture and use `compare-frames`. For a mode comparison, repeat the workload in each mode and capture each mode separately. Report when real low-charge behavior was not observed.
3. Present specific options and their tradeoffs. Build a `plan` only for chosen operations. Show the actions and the approval digest before applying. Preserve the rollback journal and verify the result. Use Android's **Clear cache** screen when the CLI cannot confirm cache clearing. Use `cache-settings PACKAGE` to open App info for the owner. Avoid **Clear storage** for a cache task.

For a general cleanup, offer `plan --light` as a preview. List each proposed motion change and dedicated ad service. It keeps reduced motion and leaves OEM stores in place. For battery concerns, distinguish the reported health status from capacity, and the Battery Saver schedule from hardware repair. Never promise Pixel performance or universal ad removal.

For ads and OEM bloat, run `ads` or call the read-only `audit_ads_and_preinstalls` MCP tool. Follow [the OEM guide](https://github.com/shiv-eshwar/cleanyourandroid/blob/main/docs/ads-and-preinstalls.md). Start with built-in recommendation controls. Propose disabling only an eligible package the user selects. For an eligible per-user removal, explain that the OEM APK remains on the phone and describe the restore path. If the user wants DNS filtering, ask which resolver they trust before proposing the hostname change and explain the connectivity tradeoff.

Never inspect shared storage, photos, downloads, messages, contacts or app contents. Use only the tool's package-manager cache operation for storage cleanup. Keep reports and journals local; installed app names can be private. Don't infer authorization from an audit request, override thermal protections, or disable an unfamiliar system component based on its name.
