# Contribute to CleanYourAndroid

Tested results from different phones make this project better. If you find a performance issue, an optional preinstalled app, or a cleanup step that works on your phone, **open a pull request with the evidence**. Compatibility notes, reproduction steps, and documentation fixes are welcome. An [issue][device-report] is a good starting point when the behavior still needs investigation.

## Report what you found

1. Run `cleanyourandroid diagnose` or `cleanyourandroid audit` on a phone you own or are authorized to maintain.
2. Record the manufacturer, model, Android version, build, and whether you used USB or wireless ADB. For Battery Saver or standby reports, include charge level, power mode, whether it was plugged in, and the measurement window.
3. For a potential debloat rule, include the full package name, what it does, how you verified that on your device, and which phone features could depend on it. Preserve the package's data and verify the restore path for any reversible change. For an OEM store or ad surface, include the firmware region, how you verified the package identity, which recommendation toggle was available, and whether app updates still worked after the change.
4. For a performance claim, repeat the same workload and report the before-and-after measurements. For a storage claim, distinguish reclaimed space, cache estimates, and the size of a file.
5. Share only the relevant values or a sanitized excerpt. Remove serial numbers, IP addresses, Wi-Fi names, pairing codes, account details, personal filenames, and notification contents from logs and screenshots.

An unfamiliar package name or a large cache alone is insufficient evidence for a removal rule. Keep OEM rules scoped to the manufacturer and builds you can verify. If a device behaves differently, document that result too.

## Open a pull request

1. [Fork the project][fork], clone your fork, and create a branch with `git switch -c describe-your-change`.
2. Keep changes focused. Update the affected documentation and add a regression test when the change could break parsing, device selection, approval, backup, or rollback.
3. Run the checks below. For write flows, use fake devices and synthetic files before trying them on a phone. If you tested on hardware, give the model and build and summarize how you verified the outcome.
4. Push the branch to your fork and [open a pull request][pulls] against `main`. Describe what changed, what you tested, and what remains unverified. Link an existing issue when there is one.

```sh
python -m pip install -e ".[mcp]"
python -m unittest discover -s tests -v
git diff --check
```

When changing the CLI, keep audit commands read-only and use the existing approval, verified backup, and rollback flows. Keep the MCP tools read-only. If platform-specific behavior prevents verification, report the limit instead of guessing.

Report vulnerabilities privately. [Security reporting](SECURITY.md)

[device-report]: https://github.com/shiv-eshwar/cleanyourandroid/issues/new?template=device-report.yml
[fork]: https://github.com/shiv-eshwar/cleanyourandroid/fork
[pulls]: https://github.com/shiv-eshwar/cleanyourandroid/pulls
