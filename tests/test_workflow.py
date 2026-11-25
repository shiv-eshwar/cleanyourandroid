from contextlib import redirect_stderr
from io import StringIO
import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import Mock, patch

from cleanyourandroid import adb, audit, cli, plan


class FakePhone:
    def __init__(self):
        self.settings = {audit.SAVER: "25", audit.CELLULAR: "null"}
        self.mutations = []
        self.fail_after_write = None
        self.cache_help = "  clear [--user USER_ID] [--cache-only] PACKAGE"
        self.installed = {"com.example.fixture"}
        self.cache_reply = "Success"
        self.cache_permission = "android.permission.INTERNAL_DELETE_CACHE_FILES: granted=true"

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
            return "\n".join("package:" + package for package in self.installed)
        if words == ("pm", "help"):
            return self.cache_help
        if words == ("dumpsys", "package", "com.android.shell"):
            return self.cache_permission
        if words[:2] == ("pm", "clear"):
            self.mutations.append(words)
            return self.cache_reply
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

    def test_animation_and_battery_plan_restores_mixed_original_values(self):
        window, transition, animator = audit.ANIMATIONS
        self.phone.settings.update({window: "1.25", transition: "0.50"})
        source, journal = self.root / "plan", self.root / "journal"
        args = cli.parser().parse_args(["plan", "--animation-scale", "0.5", "--battery-saver-at", "20",
                                        "--out", str(source)])
        digest = plan.create_plan(self.phone, cli.operations(args, self.phone), source)
        self.assertFalse(self.phone.mutations)
        results = plan.apply(self.phone, source, digest, journal)
        self.assertEqual([r["target"] for r in results if r["state"] == "unchanged"], [transition])
        self.assertEqual(self.phone.settings[audit.SAVER], "20")
        self.assertEqual(self.phone.settings[animator], "0.5")
        self.phone.settings[window] = "0.50"  # equivalent OEM formatting
        plan.restore(self.phone, journal)
        self.assertNotIn(animator, self.phone.settings)
        self.assertEqual(self.phone.settings[window], "1.25")
        self.assertEqual(self.phone.settings[transition], "0.50")
        self.assertEqual(self.phone.settings[audit.SAVER], "25")

    def test_unsupported_settings_or_schedule_do_not_create_a_plan(self):
        source = self.root / "plan"
        self.phone.settings["automatic_power_save_mode"] = "1"
        for target, value in ((audit.SAVER, "15"), (audit.SAVER, "101"), (audit.CELLULAR, "15"),
                              (audit.ANIMATIONS[0], "-1"), ("unknown_key", "0")):
            with self.subTest(target=target, value=value), self.assertRaises(adb.DeviceError):
                plan.create_plan(self.phone, [dict(kind="setting", target=target, value=value)], source)
        self.assertFalse(source.exists())
        self.assertFalse(self.phone.mutations)

    def test_cache_requires_clear_specific_help_and_explicit_installed_target(self):
        source, journal = self.root / "plan", self.root / "journal"
        package = "com.example.fixture"
        op = dict(kind="cache", target=package, value=None)
        digest = plan.create_plan(self.phone, [op], source)
        self.phone.cache_help = "clear [--user USER_ID] PACKAGE\nother [--cache-only]"
        with self.assertRaises(adb.DeviceError):
            plan.apply(self.phone, source, digest, journal)
        self.phone.cache_help = "clear [--cache-only] [--user USER_ID] PACKAGE"
        grant = self.phone.cache_permission
        self.phone.cache_permission = "android.permission.DELETE_CACHE_FILES: granted=true"
        with self.assertRaises(adb.DeviceError):
            plan.apply(self.phone, source, digest, journal)
        self.phone.cache_permission = grant
        self.phone.installed.clear()
        with self.assertRaises(adb.DeviceError):
            plan.apply(self.phone, source, digest, journal)
        self.assertFalse(journal.exists())
        self.assertFalse(self.phone.mutations)
        self.phone.installed.add(package)
        self.phone.cache_reply = "Failed"
        with self.assertRaises(adb.DeviceError):
            plan.apply(self.phone, source, digest, journal)
        self.assertEqual(json.loads(journal.read_bytes())["entries"][0]["state"], "started")
        plan.restore(self.phone, journal)
        self.assertEqual(self.phone.mutations, [("pm", "clear", "--user", "0", "--cache-only", package)])
        with self.assertRaises(adb.DeviceError):
            plan.check_operations([dict(op, target="--user")])

    def test_cache_settings_opens_app_info_without_a_clear_operation(self):
        args = cli.parser().parse_args(["cache-settings", "com.example.fixture"])
        phone = Mock()
        phone.shell.side_effect = ["package:com.example.fixture", "Status: ok\nComplete"]
        with patch.object(cli, "Device", return_value=phone):
            self.assertIn("Clear cache", cli.execute(args)["next"])
        self.assertEqual([call.args for call in phone.shell.call_args_list], [
            ("pm", "list", "packages", "--user", "0"),
            ("am", "start", "-W", "--user", "0", "-p", "com.android.settings", "-a", "android.settings.APPLICATION_DETAILS_SETTINGS",
             "-d", "package:com.example.fixture")])

    def test_scan_screen_does_not_inspect_location_or_write_radio_settings(self):
        args = cli.parser().parse_args(["scan-settings"])
        phone = Mock()
        phone.shell.side_effect = ["Status: ok", "Error: unable to resolve Intent"]
        with patch.object(cli, "Device", return_value=phone):
            self.assertIn("No switch was changed", cli.execute(args)["next"])
            with self.assertRaisesRegex(adb.DeviceError, "Location services"):
                cli.execute(args)
            phone.is_owner_active.return_value = False
            with self.assertRaisesRegex(adb.DeviceError, "primary Android user"):
                cli.execute(args)
        self.assertEqual([call.args for call in phone.shell.call_args_list],
                         [("am", "start", "-W", "--user", "0", "-p", "com.android.settings", "-a",
                           "android.settings.LOCATION_SCANNING_SETTINGS")] * 2)

    def test_cache_threshold_freezes_an_exact_list_and_excludes_other_apps(self):
        source = self.root / "plan"
        args = cli.parser().parse_args(["plan", "--clear-cache-above-mib", "4", "--out", str(source)])
        size = 4 * 1024**2
        stats = ('Package Names: ["com.other.profile", "com.example.fixture", "com.example.small"]\n'
                 'App Sizes: [1,1,1]\nApp Data Sizes: [1,1,1]\n'
                 f'Cache Sizes: [{size*2},{size},{size-1}]')
        def fixture(*words, **kwargs):
            if words == ("dumpsys", "diskstats"):
                return stats
            if words == ("pm", "list", "packages", "--user", "0", "-3"):
                return "package:com.example.fixture\npackage:com.example.small"
            return self.phone.shell(*words, **kwargs)
        ops = cli.operations(args, Mock(shell=fixture))
        self.assertEqual(ops, [dict(kind="cache", target="com.example.fixture", value=None)])
        digest = plan.create_plan(self.phone, ops, source)
        self.phone.installed.add("com.other.profile")
        plan.apply(self.phone, source, digest, self.root / "journal")
        self.assertEqual(self.phone.mutations, [("pm", "clear", "--user", "0", "--cache-only", "com.example.fixture")])

    def test_health_is_condition_not_capacity_and_unknown_values_are_preserved(self):
        source = {("dumpsys", "battery"): "  health: 3\n  temperature: -20"}
        device = Mock(shell=lambda *words: source.get(words, ""))
        result = audit.core_snapshot(device)
        self.assertEqual(result["battery_health_status"], "overheat")
        self.assertEqual(result["battery_celsius"], -2)
        source[("dumpsys", "battery")] = "health: 99"
        self.assertEqual(audit.core_snapshot(device)["battery_health_status"], "unknown")
        source.clear()
        self.assertIsNone(audit.core_snapshot(device)["battery_health_status"])
        self.assertIsNone(audit.data_volume(""))

    def test_missing_oem_services_do_not_hide_available_readings(self):
        def limited(*words):
            if words == ("dumpsys", "battery"):
                return "level: 82\nUSB powered: false"
            raise adb.DeviceError("service unavailable")
        report = audit.core_snapshot(Mock(shell=limited))
        self.assertEqual(report["battery_level"], 82)
        self.assertIs(report["external_power"], False)
        self.assertIsNone(report["thermal_status"])
        self.assertIsNone(report["settings"][audit.SAVER])

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
