# Ads and preinstalled apps

Start with a read-only audit. Each Android build can ship different packages and settings, even within the same model family.

```sh
cleanyourandroid ads
```

The report shows the recommendation controls to check, the current Private DNS setting, and verified package candidates. The launchable preinstalled-app inventory is for manual review. Critical apps can appear there. The tool checks each writable target against the device manufacturer, installed package metadata, shared UIDs, Home, app roles, device administrators, accessibility, keyboards, and always-on VPN.

| Phone | Initial candidate | What to check first |
| --- | --- | --- |
| OPPO ColorOS | OPPO App Market `com.heytap.market`; advertising component `com.opos.ads` | Look for **Ads & recommendations** in App Market privacy settings. Some builds also offer **App Content** in Security & Privacy and a separate recommendations toggle in Phone Manager. |
| vivo Funtouch OS | V-Appstore `com.vivo.appstore` or `com.bbk.appstore` | Check V-Appstore settings for **Hot Apps** and **Hot Games**. Review lock-screen and launcher suggestions separately where available. |
| Xiaomi MIUI / HyperOS (including Redmi and POCO) | System Ads: `com.miui.msa.global` or `com.miui.systemAdSolution` | Search Settings for **Authorization & revocation → msa**. Check **Receive recommendations** in Security, Themes and GetApps. Menus vary by region; changing ad personalization alone does not remove ads. |
| Nothing OS | Aura `com.aura.oobe.solutions` | Check the app or notification channel responsible for recommendations. |
| Other Android builds | Verified Netflix, Amazon Shopping, and Booking.com system preinstalls | Review each optional app you use. Android settings and Private DNS can address other recommendations and some network ads. |

The cross-brand rules only qualify these apps when they arrived as system preinstalls. Apps installed by the user stay outside the debloat list. OPPO and vivo app-store changes require an enabled Google Play Store. Open it and verify you can get the app updates you need before disabling the OEM store. A vendor store can still provide updates that Google Play doesn't offer. Hardware verification for these OPPO, vivo and Xiaomi rules is pending. The initial rules and rollback behavior are covered by simulated-device tests. Please [contribute a tested device report or pull request](../CONTRIBUTING.md).

Package identities were cross-checked against the [Universal Android Debloater community catalog](https://github.com/Universal-Debloater-Alliance/universal-android-debloater-next-generation/blob/main/resources/assets/uad_lists.json). A catalog entry alone never authorizes a change.

[OPPO App Market](https://developers.oppomobile.com/) · [ColorOS community guide](https://community.oppo.com/thread/1799696188740468741) · [vivo V-Appstore support](https://www.vivo.com/en/support/questionList?categoryId=55879)

## Disable a verified package

Disabling is the first option. It stops the app for the primary Android user and keeps its data and APK. For example, run this on an OPPO phone only if the audit lists the exact package as eligible.

```sh
mkdir -p .cyandroid
cleanyourandroid plan --disable-package com.heytap.market --out .cyandroid/preinstall.json
cleanyourandroid apply .cyandroid/preinstall.json --approve APPROVAL_SHA256 --journal .cyandroid/preinstall-rollback.json
cleanyourandroid ads
```

Copy the SHA-256 digest after you review the package, current state, and expected impact. Check the affected feature and updates after applying. Restore with the journal if you need the app back.

```sh
cleanyourandroid restore .cyandroid/preinstall-rollback.json
```

## Remove an eligible preinstall for the primary user

For a base-image preinstall marked `remove_for_primary_user_allowed`, use `--remove-preinstall PACKAGE` in a separate plan. This runs Android's per-user uninstall with `-k` to retain app data and cache. The factory APK stays on the system partition, so removing a preinstall this way may reclaim little space. Restore reinstalls that existing APK for the primary user and restores the prior enabled state.

Updated system apps are eligible for disabling only when they pass the other checks. A firmware change can prevent per-user restore, so keep your journal and restore before updating if you still need the app. Keep a separate backup of important app data.

## Filter network ads with Private DNS

Android 9 or later supports a Private DNS provider hostname. Select a DNS-over-TLS provider you trust that filters the ad and tracker domains you want blocked. The example uses AdGuard's public filtering resolver. Review its terms and privacy information before using it. [AdGuard Android setup](https://adguard-dns.io/kb/private-dns/connect-devices/mobile-and-desktop/android/)

```sh
cleanyourandroid plan --private-dns dns.adguard-dns.com --out .cyandroid/dns.json
cleanyourandroid apply .cyandroid/dns.json --approve APPROVAL_SHA256 --journal .cyandroid/dns-rollback.json
```

Use a USB connection so you can restore even if the phone loses Internet access. The tool verifies the Android setting. Check browsing, app sign-in, and any VPN or captive portal you use. If service breaks, run `cleanyourandroid restore .cyandroid/dns-rollback.json` or switch **Private DNS** back in Android Settings. The chosen resolver can see the DNS queries it handles.

DNS filtering works on domains. Ads delivered through the same domains as the content, many video ads, OEM interface suggestions, and apps that bypass Android DNS may still appear. Turn off advertising personalization separately if you want fewer personalized recommendations. [Android ads privacy controls](https://support.google.com/android/answer/13720755?hl=en)

Disabling unused components and recommendations can reduce background activity on some phones. Use the [performance guide](performance.md) to measure the effect. The changes run on the original firmware with the existing launcher and OEM update system.
