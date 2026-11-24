# CleanYourAndroid

Find what is making your Android phone slow and review changes before applying them. CleanYourAndroid runs locally over an authorized ADB connection and requires no root.

```sh
git clone https://github.com/shiv-eshwar/cleanyourandroid.git
cd cleanyourandroid
python3 -m cleanyourandroid devices
python3 -m cleanyourandroid audit
```

Requires Python 3.10+ and [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools). The CLI includes performance diagnostics, an explicit tuning plan with rollback, and verified backups for supported file removals.

Inspired by [CleanYourTV](https://github.com/Gathin23/cleanyourtv).
