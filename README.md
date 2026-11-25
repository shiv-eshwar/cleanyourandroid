# CleanYourAndroid

**Find what is slowing down your Android phone. Fix what the evidence supports.**

CleanYourAndroid is a local ADB toolkit for diagnosing lag, heat, battery drain, app bloat, and storage use. It keeps your existing launcher, wallpaper, and interface. The core CLI needs Python and Android Platform-Tools. Root access and a bootloader unlock are unnecessary.

![Battery Saver settings on a Nothing Phone (2a) beside live CleanYourAndroid output showing Android 17, Battery Saver off, and 90 fps rendering](docs/images/live-diagnostic.png)

*Real USB session on a Nothing Phone (2a). The preview shows selected fields from `diagnose` alongside the phone's Battery Saver screen.*

| Start with | What you get |
| --- | --- |
| [Quick start](#quick-start) | Run your first audit over USB or Wi-Fi |
| [Diagnose lag and Battery Saver](docs/performance.md) | Measure what changes when your phone stutters |
| [Reduce OEM ads and preinstalls](docs/ads-and-preinstalls.md) | Audit OPPO, vivo, and Nothing recommendation components and configure optional DNS filtering |
| [Review and apply changes](#review-and-apply-changes) | Preview the exact actions and save a rollback journal |
| [Use a coding assistant](#use-a-coding-assistant) | Set up Claude Code, Cursor, OpenCode, Codex, or another agent |
| [Contribute](#contribute) | Share a tested finding from your phone |

## Quick start

Install Python 3.10+ and [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools). Put Platform-Tools on your PATH or point `CLEANYOURANDROID_ADB` at the full path to `adb`. The CLI also checks common SDK folders.

```sh
git clone https://github.com/shiv-eshwar/cleanyourandroid.git
cd cleanyourandroid
python3 -m cleanyourandroid devices
python3 -m cleanyourandroid audit
```

On Windows, use `py -3.12 -m cleanyourandroid` with Python 3.12 installed. To install a standalone command with [uv](https://docs.astral.sh/uv/):

```sh
uv tool install --python 3.12 "git+https://github.com/shiv-eshwar/cleanyourandroid.git"
cleanyourandroid devices
```

Use either connection below. If two transports show up for the same phone, pass the intended serial from `devices` to every device command.

```sh
cleanyourandroid audit --serial YOUR_SERIAL
cleanyourandroid diagnose --serial YOUR_SERIAL
```

### USB debugging

1. On the phone, open **Settings → About phone** and tap **Build number** seven times. It may be under **Software information**. Confirm your screen lock if prompted.
2. Open **Developer options** and enable **USB debugging**.
3. Attach a USB data cable, unlock the phone, and tap **Allow** in the debugging prompt for this computer.
4. Run `adb devices -l` and look for the state `device`. If it says `unauthorized`, accept the prompt on the phone. If the phone is missing, try a data-capable cable or another port. Windows may need the manufacturer's USB driver. Linux may need [ADB device permissions](https://developer.android.com/studio/run/device#setting-up).

### Wireless debugging

Use Android 11 or later, a recent `adb`, and a trusted Wi-Fi network shared by the phone and computer.

1. Open **Developer options → Wireless debugging → Pair device with pairing code**. Keep the pairing dialog visible.
2. Pair using the address and port in the **pairing dialog**. Enter the six-digit code at the terminal prompt.
3. Return to the main **Wireless debugging** screen. Connect using the address and port shown on **that page**.

```sh
adb pair 192.168.1.50:37123
adb connect 192.168.1.50:43657
adb devices -l
```

The two ports serve different purposes and can change. Confirm both on the phone. Reopen the pairing dialog for a fresh code if the old one expires. Run `adb mdns services` if automatic discovery fails. Android Studio also offers QR pairing under **Device Manager → Pair Devices Using Wi-Fi**. Use USB if the network blocks peer connections. Turn off debugging on the phone when you finish.

## Review and apply changes

Start with `audit`. It reports observed CPU activity, thermal state, battery policy, graphics information available on the build, free space, cached app sizes, and known optional packages. A single snapshot cannot establish which process caused a stall. Use the [performance guide](docs/performance.md) to compare repeatable workloads.

Choose an action that addresses a measured issue. For example, if Battery Saver turns on automatically and app launches feel slower:

```sh
mkdir -p .cyandroid
cleanyourandroid plan --disable-auto-saver --out .cyandroid/plan.json
```

Read the plan, including the observed values and operations. Copy its `approval_sha256` after reviewing it.

```sh
cleanyourandroid apply .cyandroid/plan.json --approve APPROVAL_SHA256 --journal .cyandroid/rollback.json
cleanyourandroid diagnose
```

| Plan option | Effect |
| --- | --- |
| `--disable-auto-saver` | Turn off the percentage-based Battery Saver trigger. Manual Battery Saver remains available. This can shorten the last stretch of battery runtime. |
| `--disable-always-on-mobile-data` | Allow the extra cellular data session to close while Wi-Fi is connected. Handoff may take longer. |
| `--disable-package PACKAGE` | Disable a verified optional preinstall for the primary user and keep its data. |
| `--remove-preinstall PACKAGE` | Remove an eligible base-image preinstall for the primary user and keep its data. The factory APK remains available for restore. |
| `--private-dns HOSTNAME` | Set a reviewed DNS-over-TLS provider. A filtering resolver can block some network ad domains. |
| `--clear-cache PACKAGE` | Clear only the cache for a listed app when Android supports the command. Use App info → Storage and cache → **Clear cache** if the result is unconfirmed. |

To undo the reversible settings and package changes:

```sh
cleanyourandroid restore .cyandroid/rollback.json
```

A cache clear cannot be reversed. After firmware updates, run a fresh audit and review any new plan. Start with `cleanyourandroid ads` for OEM recommendation controls, per-user debloat candidates, and Private DNS. [Ads and preinstalled apps](docs/ads-and-preinstalls.md)

## Use a coding assistant

Use one shared skill with Claude Code, Cursor, OpenCode, Codex, and other Agent Skills clients.

```sh
npx --yes skills add shiv-eshwar/cleanyourandroid --skill cleanyourandroid --agent claude-code cursor opencode
```

The [agent installation guide](docs/agents.md) covers native Claude Code and Codex plugins, manual skill installation, and ready-to-copy read-only MCP configurations. For any local shell-capable coding agent, open this checkout and paste [PROMPT.md](PROMPT.md).

## Compatibility and privacy

The CLI's read-only paths were verified on a **Nothing Phone (2a), Android 17**, using USB. Output and available commands vary by Android release and OEM. OPPO and vivo rules are simulator-tested. Physical-device reports are welcome. Private Space and cloned app profiles are outside the cleanup scope.

Diagnostic reports, plans, and journals stay on your computer unless you choose to send them to an assistant or another service. Put local work in `.cyandroid/`. Review anything you intend to share because it may contain app names, build identifiers or package inventories.

## Contribute

**Found something on your phone that belongs here? Open a pull request.** Device compatibility notes, verified optional packages, reproducible performance findings, and documentation improvements all help. Include your phone model, Android version, build, and what you tested. If you are still investigating, start with a [device report](https://github.com/shiv-eshwar/cleanyourandroid/issues/new?template=device-report.yml).

[Contributing guide](CONTRIBUTING.md) · [Pull requests](https://github.com/shiv-eshwar/cleanyourandroid/pulls) · [Security reporting](SECURITY.md)

Inspired by [CleanYourTV](https://github.com/Gathin23/cleanyourtv) and its inspect, review, and restore workflow. CleanYourAndroid is an independently implemented, performance-focused phone project. [MIT License](LICENSE).
