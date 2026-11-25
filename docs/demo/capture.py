"""Capture the README evidence only on the named, disposable GitHub Actions AVD."""

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

SERIAL = "emulator-5554"
LABELS = ("Window animation scale", "Transition animation scale", "Animator duration scale")
KEYS = ("window_animation_scale", "transition_animation_scale", "animator_duration_scale")


def adb(*args):
    return subprocess.check_output(["adb", "-s", SERIAL, *args], timeout=45)


def shell(*args):
    return adb("shell", *args).decode().strip()


def capture_screen(folder, stage, expected):
    shell("am", "force-stop", "com.android.settings")
    shell("am", "start", "-W", "-a", "android.settings.APPLICATION_DEVELOPMENT_SETTINGS",
          "-p", "com.android.settings", "--es", ":settings:fragment_args_key", KEYS[0])
    last_text = []
    for _ in range(28):
        shell("uiautomator", "dump", "/data/local/tmp/cya-demo.xml")
        root = ET.fromstring(adb("shell", "cat", "/data/local/tmp/cya-demo.xml"))
        last_text = [n.get("text") for n in root.iter("node") if n.get("text")]
        titles = {n.get("text"): n for n in root.iter("node") if n.get("text") in LABELS}
        parents = {child: parent for parent in root.iter() for child in parent}
        boxes = []
        for label in LABELS:
            if label not in titles:
                break
            item = titles[label]
            summary = []
            while item in parents:
                item = parents[item]
                if sum(n.get("text") in LABELS for n in item.iter()) > 1:
                    break
                summary = [n for n in item.iter("node") if re.search(expected, n.get("text", "").lower())]
                if summary:
                    break
            if not summary:
                break
            boxes.extend(int(v) for n in (titles[label], *summary)
                         for v in re.findall(r"\d+", n.get("bounds"))[1::2])
        else:
            (folder / f"{stage}.png").write_bytes(adb("exec-out", "screencap", "-p"))
            return [0, max(0, min(boxes) - 14), 1080, min(1920, max(boxes) + 14)]
        # Slow swipes keep the three neighboring preferences together.
        if LABELS[0] in titles and LABELS[-1] not in titles:
            shell("input", "swipe", "500", "1250", "500", "950", "380")
        elif LABELS[-1] in titles and LABELS[0] not in titles:
            shell("input", "swipe", "500", "900", "500", "1200", "380")
        else:
            shell("input", "swipe", "500", "1520", "500", "760", "400")
    raise RuntimeError(f"Could not verify all three native Settings rows for {stage}: {last_text}")


def main():
    if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or adb("emu", "avd", "name").decode().splitlines()[0].strip() != "cleanandroid-ci"
            or "1" not in (shell("getprop", "ro.boot.qemu"), shell("getprop", "ro.kernel.qemu"))):
        raise SystemExit("This capture runs only on the disposable workflow emulator.")
    output = Path(os.environ["RUNNER_TEMP"]) / "readme-demo"
    output.mkdir()
    shell("wm", "size", "1080x1920")
    shell("wm", "density", "340")
    shell("settings", "put", "global", "development_settings_enabled", "1")
    time.sleep(1)
    with tempfile.TemporaryDirectory() as work:
        def cli(*args):
            return json.loads(subprocess.check_output(["cleanyourandroid", *args, "--serial", SERIAL], cwd=work))
        plan = cli("plan", "--light", "--out", "plan.json")
        if {op["target"] for op in plan["operations"]} != set(KEYS) or len(plan["operations"]) != len(KEYS):
            raise RuntimeError("Unexpected light plan; no changes applied")
        stages = []
        def record(name, rows, expected):
            current = {k: shell("settings", "get", "global", k) for k in KEYS}
            if expected == 1:
                valid = current == plan["observed"]
            else:
                valid = all(v == "0.5" for v in current.values())
            if not valid:
                raise RuntimeError(f"Unexpected state in {name}")
            # Never export device IDs, approval digests, package inventories or raw audits.
            stages.append({"stage": name, "settings": current,
                           "operations": [{k: op[k] for k in ("kind", "target", "value", "state") if k in op}
                                          for op in rows],
                           "crop": capture_screen(output, name, r"(?<![\d.])1(?:\.0)?\s*[x×]" if expected == 1 else r"0?\.5\s*[x×]")})
        record("preview", plan["operations"], 1)
        try:
            applied = cli("apply", "plan.json", "--approve", plan["approval_sha256"], "--journal", "journal.json")
            record("applied", applied["operations"], 0.5)
        finally:
            if (Path(work) / "journal.json").exists():
                restored = cli("restore", "journal.json")
        record("restored", restored["operations"], 1)
        (output / "session.json").write_text(json.dumps(stages, indent=2) + "\n")


if __name__ == "__main__":
    main()
