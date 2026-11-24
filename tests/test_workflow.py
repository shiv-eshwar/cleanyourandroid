from contextlib import redirect_stderr
import hashlib
from io import StringIO
import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

from cleanyourandroid import adb, audit, files, plan


class FakePhone:
    def __init__(self):
        self.settings = {audit.SAVER: "25", audit.CELLULAR: "null"}
        self.phone_files = {}
        self.mutations = []
        self.fail_after_write = None
        self.change_on_move = None

    def identity(self):
        return "test-hardware"

    def is_owner_active(self):
        return True

    def prop(self, key):
        return {"ro.build.fingerprint": "test/build", "ro.product.manufacturer": "Nothing"}[key]

    def pull(self, remote, local):
        local.write_bytes(self.phone_files[str(remote)][0])

    def push(self, local, remote):
        self.phone_files[str(remote)] = local.read_bytes(), 42

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
        if words[0] == "realpath":
            return words[-1]
        if words[0] in {"stat", "sha256sum"}:
            data, inode = self.phone_files[words[-1]]
            if words[0] == "sha256sum":
                return hashlib.sha256(data).hexdigest() + "  " + words[-1]
            if words[2] == "%f %s %d:%i %h":
                return f"81f8 {len(data)} 1:{inode} 2"
            return f"1:{inode}:{len(data)}:timestamp"
        if words[0] == "sh":
            if words[2].startswith("if [ -e"):
                return "yes" if words[-1] in self.phone_files else "no"
            self.mutations.append(words)
            self.phone_files.pop(words[4])
            return ""
        if words[0] == "mv":
            *_, source, destination = words
            if destination not in self.phone_files:
                data, inode = self.phone_files.pop(source)
                if self.change_on_move and source == self.change_on_move:
                    data = b"newer content"
                    self.change_on_move = None
                self.phone_files[destination] = data, inode
            return ""
        if words[0] == "rm":
            self.phone_files.pop(words[-1], None)
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

    def make_file_backup(self):
        source = str(files.SENT / "DOC-1234.")
        retained = str(files.CAMERA / "Video.mp4")
        self.phone.phone_files = {source: (b"identical video", 1), retained: (b"identical video", 2)}
        folder = self.root / "backup"
        manifest, approval = files.backup(self.phone, folder, [], [(source, retained)])
        return source, retained, folder, manifest, approval

    def test_backup_remove_retry_and_restore(self):
        source, retained, _, manifest, approval = self.make_file_backup()
        with redirect_stderr(StringIO()):
            self.assertEqual(files.remove(self.phone, manifest, approval)["removed"], [source])
            self.assertEqual(files.remove(self.phone, manifest, approval)["already_absent"], 1)
        self.assertIn(retained, self.phone.phone_files)
        files.restore(self.phone, manifest, json.loads(manifest.read_text()))
        self.assertEqual(self.phone.phone_files[source][0], self.phone.phone_files[retained][0])

    def test_changed_source_is_put_back_instead_of_deleted(self):
        source, _, _, manifest, approval = self.make_file_backup()
        self.phone.change_on_move = source
        with self.assertRaises(adb.DeviceError):
            files.remove(self.phone, manifest, approval)
        self.assertEqual(self.phone.phone_files[source][0], b"newer content")
        self.assertFalse(self.phone.mutations)

    def test_bad_backup_or_changed_original_prevents_removal(self):
        source, retained, folder, manifest, approval = self.make_file_backup()
        entry, = json.loads(manifest.read_text())["entries"]
        local = folder / entry["backup"]
        local.write_bytes(b"x" * len(local.read_bytes()))
        with self.assertRaises(adb.DeviceError):
            files.remove(self.phone, manifest, approval)
        local.write_bytes(b"identical video")
        self.phone.phone_files[retained] = b"unrelated data!", 2
        with self.assertRaises(adb.DeviceError):
            files.remove(self.phone, manifest, approval)
        self.assertIn(source, self.phone.phone_files)
        self.assertFalse(self.phone.mutations)

    def test_backup_filename_is_portable_and_noninterpretable(self):
        source = files.DOWNLOAD / r"C:\CON:alt.apk"
        relative = files.backup_path(source)
        self.assertEqual(relative.parts[0], "payload")
        self.assertRegex(relative.name, r"^[a-f0-9]{64}-[a-zA-Z0-9._-]+$")
        self.assertNotIn("\\", str(relative))
        self.assertNotIn(":", str(relative))

    def test_adb_pins_transport_and_quotes_path(self):
        inventory = "List of devices attached\nexample:1234 device model:Sample transport_id:7\n"
        with patch.object(adb, "run_adb", side_effect=[inventory.encode(), b"ok"]) as run:
            selected = adb.Device("example:1234")
            argument = "/storage/emulated/0/Download/Foo ' & $.apk"
            selected.shell("stat", "--", argument)
            args = run.call_args.args
            self.assertEqual(args[:4], ("-t", "7", "shell", "-T"))
            self.assertEqual(shlex.split(args[4]), ["stat", "--", argument])

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
