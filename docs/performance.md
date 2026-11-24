# Diagnose Android performance

Start with `cleanyourandroid diagnose` in the condition where the problem occurs. Capture a second report after the phone cools or while in a different power mode.

```sh
cleanyourandroid diagnose --out .cyandroid/symptom.json
```

| Field | How to interpret it |
| --- | --- |
| `recent_cpu` | A recent Android sample. Percentages are relative to one CPU core. Repeat before calling an app a persistent hog. |
| `thermal_status` | Android's reported policy level. Values can lag the latest physical temperature. Compare runs at similar temperatures. |
| `battery_saver` | Android's reported mode. Some OEMs expose fewer fields, in which case the value can be missing. |
| `low_power_render_limit_fps` and `active_render_fps` | The requested policy limit and the active renderer are separate readings. If they disagree, report both. |
| `memory_available_bytes` and `volume.free_bytes` | A live snapshot of available RAM and data-partition space. A large app cache does not on its own explain stutter. |

## Measure stutter

Open the app or interface that stutters. Capture counters immediately before and after repeating the same gesture several times. Use `com.android.systemui` for Quick Settings on devices where that package exposes frame statistics.

```sh
cleanyourandroid frames com.android.systemui --out .cyandroid/before.json
# Repeat the same gesture several times on the phone.
cleanyourandroid frames com.android.systemui --out .cyandroid/after.json
cleanyourandroid compare-frames .cyandroid/before.json .cyandroid/after.json
```

The result is the delta in frames, janky frames, and missed VSYNC within the same process and statistics window. Treat small samples as directional. Compare similar interactions, process state, temperature, screen orientation, charge and power source. The counters are not an end-to-end input-latency measurement.

## Check Battery Saver

Test two short runs on a cool phone, one with Battery Saver off and one with it on. Toggle it in Android's Battery settings and collect a **separate pair** of frame snapshots in each mode. USB charging may make the switch unavailable. In that case, use paired wireless ADB on battery power for the screen-on test.

Some Android builds reduce the app-launch boost or request a lower render rate in Battery Saver. A 25% trigger shows when the policy changes. It does not establish that an app or that policy caused every stall. A test at 80% cannot confirm behavior at a real 4% charge. To investigate that complaint, capture a report during the actual symptom with the currently selected power mode.

For standby drain, use comparable periods on battery power with the screen off. Wireless debugging traffic, cellular signal, app notifications, and media playback can change the result. Take readings before and after the interval to avoid polling a phone you expect to sleep. Preserve Android's battery history and thermal safeguards while investigating.
