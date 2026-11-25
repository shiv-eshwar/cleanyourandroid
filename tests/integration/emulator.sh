#!/usr/bin/env bash
# Run only in CI on the disposable AVD created by the workflow.
set -euo pipefail
serial=emulator-5554
device() { adb -s "$serial" "$@"; }
cli() { local command=$1; shift; python -m cleanyourandroid "$command" --serial "$serial" "$@"; }
[[ ${GITHUB_ACTIONS:-} == true ]]
[[ $(device shell getprop ro.boot.qemu) == 1 || $(device shell getprop ro.kernel.qemu) == 1 ]]
[[ $(device emu avd name | tr -d '\r' | head -1) == cleanandroid-ci ]]

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
cli audit --out "$work/audit.json" > /dev/null
jq -e '.volume.total_bytes > 0 and (.settings | has("window_animation_scale"))' "$work/audit.json"
cli ads > "$work/ads.json"
jq -e '.candidates | type == "array"' "$work/ads.json"
cli scan-settings

# Round-trip four independent settings using a single reviewed plan.
keys=(window_animation_scale transition_animation_scale animator_duration_scale low_power_trigger_level)
for key in "${keys[@]}"; do device shell settings get global "$key" > "$work/$key"; done
digest=$(cli plan --animation-scale 0.5 --battery-saver-at 20 --out "$work/plan" | jq -er '.approval_sha256')
cli apply "$work/plan" --approve "$digest" --journal "$work/journal"
for key in "${keys[@]:0:3}"; do [[ $(device shell settings get global "$key") == 0.5 ]]; done
[[ $(device shell settings get global low_power_trigger_level) == 20 ]]
cli restore "$work/journal"
for key in "${keys[@]}"; do device shell settings get global "$key" | diff - "$work/$key"; done
cli audit --out "$work/after.json" > /dev/null
python -m cleanyourandroid compare-audits "$work/audit.json" "$work/after.json" --html "$work/report.html" |
  jq -e '.measurements[] | select(.metric == "Free storage") | (.change | type) == "number"'
test -s "$work/report.html"

# Install a fresh no-code app. The two markers belong only to this fixture.
pkg=org.example.cleanyourandroidfixture
build_tools="$ANDROID_HOME/build-tools/36.0.0"
cat > "$work/AndroidManifest.xml" <<XML
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="$pkg">
    <application android:hasCode="false" android:debuggable="true" android:label="Cache fixture"/>
</manifest>
XML
"$build_tools/aapt2" link -I "$ANDROID_HOME/platforms/android-36/android.jar" \
  --manifest "$work/AndroidManifest.xml" --min-sdk-version 24 --target-sdk-version 36 -o "$work/raw.apk"
keytool -genkeypair -keystore "$work/fixture.p12" -alias fixture -storepass fixture123 \
  -keypass fixture123 -keyalg RSA -keysize 2048 -dname CN=Test -validity 1
"$build_tools/apksigner" sign --ks "$work/fixture.p12" --ks-pass pass:fixture123 \
  --out "$work/fixture.apk" "$work/raw.apk"
device install "$work/fixture.apk"
device shell "run-as $pkg sh -c 'mkdir -p cache files && echo temporary > cache/marker && echo retained > files/marker'"

# Test against the image's actual permission, independently of the CLI verdict.
device shell pm help > "$work/pm-help"
device shell dumpsys package com.android.shell > "$work/shell-package"
if grep -Fq 'clear [--user USER_ID] [--cache-only] PACKAGE' "$work/pm-help" &&
   grep -Eq '^[[:space:]]*android\.permission\.INTERNAL_DELETE_CACHE_FILES: granted=true' "$work/shell-package"; then
  digest=$(cli plan --clear-cache "$pkg" --out "$work/cache-plan" | jq -er '.approval_sha256')
  cli apply "$work/cache-plan" --approve "$digest" --journal "$work/cache-journal"
  device shell run-as "$pkg" test ! -e cache/marker
else
  if cli plan --clear-cache "$pkg" --out "$work/cache-plan" 2>"$work/error"; then exit 1; fi
  grep -Fq 'cache-only' "$work/error"
  [[ ! -e "$work/cache-plan" ]]
  cli cache-settings "$pkg"
  [[ $(device shell run-as "$pkg" cat cache/marker) == temporary ]]
fi
[[ $(device shell run-as "$pkg" cat files/marker) == retained ]]
