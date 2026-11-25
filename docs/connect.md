# Connect a phone with ADB

## USB debugging

1. On the phone, open **Settings → About phone** and tap **Build number** seven times. It may be under **Software information**. Confirm your screen lock if prompted.
2. Open **Developer options** and enable **USB debugging**.
3. Attach a USB data cable, unlock the phone, and tap **Allow** in the debugging prompt for this computer.
4. Run `adb devices -l` and look for the state `device`. If it says `unauthorized`, accept the prompt on the phone. If the phone is missing, try a data-capable cable or another port. Windows may need the manufacturer's USB driver. Linux may need [ADB device permissions](https://developer.android.com/studio/run/device#setting-up).

## Wireless debugging

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
