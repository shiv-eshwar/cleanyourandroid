from contextlib import redirect_stderr
from io import StringIO
import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

from cleanyourandroid import adb, audit, cli, plan


class FakePhone:
    def __init__(self):
        self.settings = {audit.SAVER: "25", audit.CELLULAR: "null"}
        self.mutations = []
        self.fail_after_write = None

    def identity(self):
        return "test-hardware"

    def is_owner_active(self):
        return True

    def prop(self, key):
        return {"ro.build.fingerprint": "test/build", "ro.product.manufacturer": "Nothing"}[key]

    def shell(self, *args, **kwargs):
        words = tuple(map(str, args))
        if words[0] == "settings":
            _, action, _, key, *value = words
            if action == "get":
                return self.settings.get(key, "null")
            self.mutations.append(words)
            if action == "put":
                self.settings[key] = value[0]
                if self.fail_after_write == key:
                    raise adb.DeviceError("lost connection after writing")
            else:
                self.settings.pop(key, None)
            return ""
        if words[:3] == ("pm", "list", "packages"):
            return ""
        raise AssertionError(words)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        patcher = patch("pathlib.Path.home", return_value=self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.phone = FakePhone()

    def test_plan_approval_and_restore_after_interruption(self):
        source, journal = self.root / "plan.json", self.root / "journal.json"
        operations = [dict(kind="setting", target=k, value="0") for k in (audit.SAVER, audit.CELLULAR)]
        approved = plan.create_plan(self.phone, operations, source)
        with self.assertRaises(adb.DeviceError):
            plan.apply(self.phone, source, "wrong", journal)
        self.assertFalse(self.phone.mutations)
        self.phone.fail_after_write = audit.CELLULAR
        with self.assertRaises(adb.DeviceError):
            plan.apply(self.phone, source, approved, journal)
        self.assertEqual(self.phone.settings, {audit.SAVER: "0", audit.CELLULAR: "0"})
        self.phone.fail_after_write = None
        plan.restore(self.phone, journal)
        self.assertEqual(self.phone.settings, {audit.SAVER: "25"})
        self.assertEqual(json.loads(journal.read_text())["entries"][1]["state"], "restored")

    def test_plan_rejects_setting_change_since_preview(self):
        source, journal = self.root / "plan.json", self.root / "journal.json"
        approved = plan.create_plan(
            self.phone, [dict(kind="setting", target=audit.SAVER, value="0")], source)
        self.phone.settings[audit.SAVER] = "15"
        with self.assertRaises(adb.DeviceError):
            plan.apply(self.phone, source, approved, journal)
        self.assertFalse(journal.exists())
        self.assertFalse(self.phone.mutations)

    def test_personal_file_commands_are_rejected_before_opening_adb(self):
        for command in ("files", "backup-files", "remove-files", "restore-files"):
            with self.subTest(command=command), patch.object(cli, "Device") as device:
                with self.assertRaises(SystemExit), redirect_stderr(StringIO()):
                    cli.main([command])
                device.assert_not_called()

    def test_adb_pins_transport_and_quotes_arguments(self):
        inventory = "List of devices attached\nexample:1234 device model:Sample transport_id:7\n"
        with patch.object(adb, "run_adb", side_effect=[inventory.encode(), b"ok"]) as run:
            selected = adb.Device("example:1234")
            argument = "Example ' & $ argument"
            selected.shell("echo", argument)
            args = run.call_args.args
            self.assertEqual(args[:4], ("-t", "7", "shell", "-T"))
            self.assertEqual(shlex.split(args[4]), ["echo", argument])

    def test_frame_delta_rejects_counter_restart(self):
        before = dict(pid=1, window_ns=3, frames=100, janky_frames=2, missed_vsync=1)
        after = dict(before, frames=200, janky_frames=7, missed_vsync=4)
        self.assertEqual(audit.frame_delta(before, after)["jank_percent"], 5)
        with self.assertRaises(adb.DeviceError):
            audit.frame_delta(before, dict(after, pid=2))

    def test_standby_uses_time_and_awake_deltas_from_same_charge(self):
        before = audit.standby_counters(
            "  Time on battery screen off: 2m 5s 55ms (60%) realtime, 31s 23ms (20%) uptime\n"
            "  Start clock time: 2026-01-01-11-11-11\n"
            "  Screen off discharge: 5.0 mAh\n"
            "  Wakeup reason 524 wlan0: 30s 133ms (4 times) realtime"
        )
        self.assertEqual(before["screen_off_ms"], 125055)
        after = dict(before, screen_off_ms=425055, screen_off_awake_ms=61023, wlan_wake_count=9)
        result = audit.standby_delta(before, after)
        self.assertEqual(result["awake_percent"], 10)
        self.assertEqual(result["wlan_wakes_per_hour"], 60)
        with self.assertRaises(adb.DeviceError):
            audit.standby_delta(before, dict(after, start_clock="different"))

    def test_unavailable_or_malformed_cached_disk_stats(self):
        self.assertEqual(audit.disk_stats("Package Names: null\nApp Sizes: []\nApp Data Sizes: []\nCache Sizes: []"), [])
        rows = audit.disk_stats('Package Names: ["com.example.app"]\nApp Sizes: [5]\nApp Data Sizes: [10]\nCache Sizes: [2]')
        self.assertEqual(rows[0]["cache_bytes"], 2)


if __name__ == "__main__":
    unittest.main()
