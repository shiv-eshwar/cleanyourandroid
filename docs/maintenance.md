# Choose individual changes

Use the options below with `cleanyourandroid plan … --out .cyandroid/NAME.json`, then [review and apply the plan](../README.md#try-the-light-preset). Each option is independent.

| Goal | Option | What changes |
| --- | --- | --- |
| Hide bloatware | `--disable-package PACKAGE` | Stops an eligible system preinstall for the primary user. Its APK and app data stay on the phone. Start here if you may want it back. |
| Remove a preinstall | `--remove-preinstall PACKAGE` | For an eligible factory APK, Android removes it for user 0 and keeps its data. The system APK remains, so this can reclaim little space. |
| Reduce network ads | `--private-dns HOSTNAME` | On Android 9+, use a DNS-over-TLS resolver you choose. A filtering resolver sees DNS queries and can affect connectivity. [Provider example and rollback](ads-and-preinstalls.md#filter-network-ads-with-private-dns). |
| Adjust motion | `--animation-scale 0.5` | Sets window, transition, and animator duration. Choose `0` for off or `1` for standard. Shorter animations do not increase frame rate. |
| Extend battery runtime | `--battery-saver-at 20` | Requests Battery Saver at 15%, 20%, or 25% on a percentage schedule. Check the OEM Battery settings. `--disable-auto-saver` turns that trigger off. |
| Reduce cellular standby use | `--disable-always-on-mobile-data` | Allows cellular data to idle on Wi-Fi; switching back to cellular may take longer. |
| Reclaim temporary space | `--clear-cache PACKAGE` | Requests cache-only clearing for a named installed app; repeat for multiple apps. Cleared cache cannot be restored. |
| Review large caches together | `--clear-cache-above-mib 128` | Lists installed third-party apps whose cached estimate is at least 128 MiB. The exact list is frozen in the plan. Android's estimates may be stale. |

**When cache clearing is unavailable:** check `cache_only_supported` in the audit. Some phones advertise cache clearing but deny ADB the required permission. Run `cleanyourandroid cache-settings PACKAGE` to open that app's info screen, then choose **Storage → Clear cache** yourself. **Clear storage / Clear data** erases app data. The CLI never uses it as a fallback. Apps can rebuild cache, use network data, and load more slowly after clearing; target storage pressure rather than clearing on a schedule.

For a standby-drain investigation, `cleanyourandroid scan-settings` opens Android's Wi-Fi and Bluetooth scanning controls. You can review each switch on the phone without sharing your location or nearby networks. Turning scanning off may reduce location accuracy; the CLI does not change either switch.

## Measure the result

Save one audit before maintenance and another afterward, on the same phone and firmware. Run the comparison after disconnecting if you like:

```sh
cleanyourandroid audit --out .cyandroid/before.json
# Apply your reviewed changes and repeat the activity you want to measure.
cleanyourandroid audit --out .cyandroid/after.json
cleanyourandroid compare-audits .cyandroid/before.json .cyandroid/after.json --html .cyandroid/report.html
```

The comparison prints JSON and can write a local HTML table. It exports only timestamps, free storage, available memory, and package counts; it omits app names, device identifiers, and network settings. Missing readings are `null` in JSON and appear as a dash in HTML. These snapshots cannot prove faster launches or longer battery life. For those questions, use the frame and standby comparisons in the [performance guide](performance.md).
