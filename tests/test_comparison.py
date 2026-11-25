import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from cleanyourandroid import cli, comparison
from cleanyourandroid.adb import DeviceError


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.before = {
            "comparison_key": "c" * 64, "captured_at": "2026-05-01T10:00:00+00:00",
            "volume": {"free_bytes": 512 * 1024**2}, "memory_available_bytes": None,
            "package_counts": {"disabled": 0, "system": 250, "third_party": 20},
            "recent_cpu": [{"process": "private.example.app"}],
            "device": {"model": "private model", "serial": "private serial"},
        }
        self.after = dict(self.before, captured_at="2026-05-01T10:30:00+00:00",
                          volume={"free_bytes": 484 * 1024**2}, memory_available_bytes=100,
                          package_counts={"disabled": 3, "system": 250, "third_party": 20})

    def test_offline_report_has_signed_deltas_and_cannot_overwrite_a_snapshot(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(cli, "Device") as adb:
            start, end, report = (Path(folder) / f for f in ("before.json", "after.json", "report.html"))
            start.write_text(json.dumps(self.before))
            end.write_text(json.dumps(self.after))
            args = cli.parser().parse_args(["compare-audits", str(start), str(end), "--html", str(report)])
            data = cli.execute(args)
            rows = {row["metric"]: row for row in data["measurements"]}
            self.assertEqual(rows["Free storage"]["change"], -28 * 1024**2)
            self.assertEqual(rows["Disabled packages"]["change"], 3)
            self.assertIsNone(rows["Available memory"]["change"])
            html = report.read_text(encoding="utf-8")
            self.assertIn("-28.00 MiB", html)
            self.assertIn("+3", html)
            for private in ("private", self.before["comparison_key"]):
                self.assertNotIn(private, json.dumps(data) + html)
            args.html = start
            with self.assertRaises(FileExistsError):
                cli.execute(args)
            self.assertEqual(json.loads(start.read_bytes()), self.before)
            adb.assert_not_called()

    def test_rejects_old_mismatched_reversed_and_malformed_audits(self):
        for other in (dict(self.after, comparison_key=None), dict(self.after, comparison_key="d" * 64),
                      dict(self.after, captured_at=self.before["captured_at"]),
                      dict(self.after, captured_at="wrong"), dict(self.after, captured_at="2000-01-01T00:00:00"),
                      dict(self.after, volume={"free_bytes": -9})):
            with self.subTest(other=other), self.assertRaises(DeviceError):
                comparison.compare(self.before, other)
        with self.assertRaises(DeviceError):
            comparison.compare(self.after, self.before)

    def test_key_depends_on_hardware_and_build_but_does_not_require_them_to_audit(self):
        phone = Mock()
        phone.identity.return_value = "device one"
        phone.prop.return_value = "build one"
        first = comparison.capture_key(phone)
        self.assertRegex(first, r"^[a-f0-9]{64}$")
        phone.prop.return_value = "build two"
        self.assertNotEqual(comparison.capture_key(phone), first)
        phone.prop.return_value = "build one"
        phone.identity.return_value = "device two"
        self.assertNotEqual(comparison.capture_key(phone), first)
        phone.identity.side_effect = DeviceError("serial unavailable")
        self.assertIsNone(comparison.capture_key(phone))
