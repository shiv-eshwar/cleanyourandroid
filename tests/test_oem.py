import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cleanyourandroid import adb, dns, oem, plan


class Phone:
    def __init__(self, brand="vivo", package="com.vivo.appstore"):
        self.brand = brand
        self.package = package
        self.code_path = "/product/app/Preload/Preload.apk"
        self.build = "factory/build"
        self.enabled = 0
        self.installed = True
        self.markers = package + ".MainActivity"
        self.home = "com.example.launcher/.Home"
        self.shared_uid = False
        self.system = True
        self.play_store = True
        self.role_holder = None
        self.settings = {dns.MODE: "opportunistic"}
        self.fail_after_write = None
        self.mutations = []

    def identity(self):
        return "test-device"

    def is_owner_active(self):
        return True

    def prop(self, name):
        return {"ro.product.manufacturer": self.brand, "ro.build.fingerprint": self.build,
                "ro.build.version.sdk": "33"}[name]

    def shell(self, *words, **kwargs):
        if words[:2] == ("settings", "--user"):
            return "null"
        if words[0] == "settings":
            _, action, _, key, *value = words
            if action == "get":
                return self.settings.get(key, "null")
            self.mutations.append(words)
            if action == "put":
                self.settings[key] = value[0]
            else:
                self.settings.pop(key, None)
            if self.fail_after_write == key:
                raise adb.DeviceError("ADB disconnected after write")
            return ""
        if words[:3] == ("cmd", "package", "resolve-activity"):
            return self.home
        if words[:3] == ("cmd", "package", "query-activities"):
            return self.package + "/.MainActivity"
        if words == ("dumpsys", "role"):
            return "ROLE STATE (dumpsys role):\n" + (f"holders={self.role_holder}" if self.role_holder else "")
        if words == ("dumpsys", "device_policy"):
            return "Current Device Policy Manager state:"
        if words[:2] == ("dumpsys", "package"):
            return f"{self.markers}\n    User 0: installed={str(self.installed).lower()} enabled={self.enabled}"
        if words[:2] == ("pm", "path"):
            return f"package:{self.code_path}"
        if words[:3] == ("pm", "list", "packages"):
            rows = []
            if self.installed and not ("-e" in words and self.enabled == 3) and not ("-s" in words and not self.system):
                rows.append((self.package, 10124))
            if self.play_store:
                rows.append(("com.android.vending", 10125))
            if self.shared_uid:
                rows.append(("com.example.other", 10124))
            if "-U" in words:
                return "\n".join(f"package:{app} uid:{uid}" for app, uid in rows)
            return "\n".join(f"package:{app}" for app, _ in rows)
        if words[:2] == ("pm", "uninstall"):
            self.mutations.append(words)
            self.installed = False
            return "Success"
        if words[:2] == ("pm", "install-existing"):
            self.mutations.append(words)
            self.installed = True
            self.enabled = 0
            if self.fail_after_write == "install-existing":
                raise adb.DeviceError("ADB disconnected after reinstall")
            return ""
        if words[0] == "pm" and words[1] in {"default-state", "enable", "disable-user"}:
            self.mutations.append(words)
            self.enabled = {"default-state": 0, "enable": 1, "disable-user": 3}[words[1]]
            return ""
        raise AssertionError(words)


class OEMTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.source, self.journal = base / "plan.json", base / "restore.json"
        patcher = patch("pathlib.Path.home", return_value=base)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_candidates_are_detected_on_matching_manufacturers(self):
        for brand, package in (
            ("OPPO", "com.heytap.market"), ("OPPO", "com.opos.ads"),
            ("vivo", "com.vivo.appstore"), ("vivo", "com.bbk.appstore"),
            ("Xiaomi", "com.miui.msa.global"), ("Redmi", "com.miui.systemAdSolution"),
            ("POCO", "com.miui.msa.global"),
        ):
            phone = Phone(brand, package)
            candidate, = oem.verified_candidates(phone)
            self.assertEqual(candidate["package"], package)
            self.assertTrue(candidate["disable_allowed"])
            self.assertTrue(candidate["remove_for_primary_user_allowed"])

    def test_xiaomi_rule_is_scoped_and_rechecked_on_apply(self):
        phone = Phone("Xiaomi", "com.miui.msa.global")
        self.assertTrue(oem.report(phone)["recommendation_controls_to_check"])
        op = dict(kind="disable", target=phone.package, value=3)
        approval = plan.create_plan(phone, [op], self.source)
        phone.role_holder = phone.package
        with self.assertRaises(adb.DeviceError):
            plan.apply(phone, self.source, approval, self.journal)
        self.assertFalse(phone.mutations)
        phone.role_holder = None
        phone.brand = "OPPO"
        self.assertFalse(oem.verified_candidates(phone))

    def test_truncated_uid_listing_is_not_evidence_of_an_unshared_uid(self):
        phone = Phone()
        shell = phone.shell
        def partial(*words):
            if "-U" in words:
                return f"package:{phone.package} uid:10124\npackage:com.example.other uid:"
            return shell(*words)
        with patch.object(phone, "shell", side_effect=partial):
            self.assertEqual(oem.verified_candidates(phone), [])
            with self.assertRaises(adb.DeviceError):
                oem.verified_candidates(phone, strict=True)

    def test_optional_preinstall_works_on_other_brands_without_targeting_user_apps(self):
        phone = Phone("other", "com.netflix.mediaclient")
        candidate, = oem.verified_candidates(phone)
        self.assertTrue(candidate["disable_allowed"])
        self.assertTrue(candidate["remove_for_primary_user_allowed"])
        phone.system = False
        self.assertEqual(oem.verified_candidates(phone), [])
        self.assertFalse(phone.mutations)

    def test_rule_refuses_protected_and_uncorroborated_packages(self):
        for field, value in (
            ("brand", "unknown"), ("shared_uid", True), ("system", False),
            ("home", "com.vivo.appstore/.Home"), ("role_holder", "com.vivo.appstore"),
            ("markers", "unrecognized"),
        ):
            with self.subTest(field=field):
                phone = Phone()
                setattr(phone, field, value)
                self.assertEqual(oem.verified_candidates(phone), [])
                with self.assertRaises(adb.DeviceError):
                    plan.create_plan(phone, [dict(kind="disable", target=phone.package, value=3)], self.source)
                self.assertFalse(phone.mutations)

    def test_keeps_only_store_available(self):
        phone = Phone()
        phone.play_store = False
        candidate, = oem.verified_candidates(phone)
        self.assertFalse(candidate["disable_allowed"])
        self.assertFalse(candidate["remove_for_primary_user_allowed"])
        self.assertIn("Google Play Store", candidate["blocked_reason"])
        for kind, value in (("disable", 3), ("remove", -1)):
            with self.assertRaises(adb.DeviceError):
                plan.create_plan(phone, [dict(kind=kind, target=phone.package, value=value)], self.source)
        self.assertFalse(phone.mutations)

    def test_light_preset_protects_reduced_motion_and_only_disables_ad_services(self):
        phone = Phone("Xiaomi", "com.miui.msa.global")
        phone.settings.update(window_animation_scale="0", animator_duration_scale="0.25",
                              transition_animation_scale="1.5")
        digest = plan.create_plan(phone, [], self.source, light=True)
        self.assertFalse(phone.mutations)
        self.assertEqual(json.loads(self.source.read_bytes())["operations"], [
            dict(kind="setting", target="transition_animation_scale", value="0.5"),
            dict(kind="disable", target=phone.package, value=3)])
        earlier = dict(phone.settings)
        plan.apply(phone, self.source, digest, self.journal)
        self.assertEqual(phone.enabled, 3)
        plan.restore(phone, self.journal)
        self.assertEqual(phone.settings, earlier)
        self.assertEqual(phone.enabled, 0)

    def test_light_preset_with_no_work_keeps_store_and_does_not_create_empty_plan(self):
        for brand, app in (("vivo", "com.vivo.appstore"), ("Other", "com.netflix.mediaclient")):
            phone = Phone(brand, app)
            phone.settings.update(window_animation_scale="0", animator_duration_scale="0.5",
                                  transition_animation_scale="unknown")
            with self.assertRaisesRegex(adb.DeviceError, "No eligible changes"):
                plan.create_plan(phone, [], self.source, light=True)
            self.assertFalse(self.source.exists())
            self.assertFalse(phone.mutations)

    def test_updated_preinstall_can_be_disabled_but_not_removed(self):
        phone = Phone()
        phone.code_path = "/data/app/update/base.apk"
        candidate, = oem.verified_candidates(phone)
        self.assertTrue(candidate["disable_allowed"])
        self.assertFalse(candidate["remove_for_primary_user_allowed"])
        with self.assertRaises(adb.DeviceError):
            plan.create_plan(phone, [dict(kind="remove", target=phone.package, value=-1)], self.source)
        approval = plan.create_plan(phone, [dict(kind="disable", target=phone.package, value=3)], self.source)
        plan.apply(phone, self.source, approval, self.journal)
        self.assertEqual(phone.enabled, 3)
        plan.restore(phone, self.journal)
        self.assertEqual(phone.enabled, 0)

    def test_per_user_removal_preserves_data_and_resumes_restore(self):
        phone = Phone()
        phone.enabled = 3
        operations = [dict(kind="remove", target=phone.package, value=-1)]
        approval = plan.create_plan(phone, operations, self.source)
        self.assertFalse(phone.mutations)
        plan.apply(phone, self.source, approval, self.journal)
        self.assertIn(("pm", "uninstall", "-k", "--user", "0", phone.package), phone.mutations)
        self.assertFalse(phone.installed)
        phone.build = "changed/build"
        with self.assertRaises(adb.DeviceError):
            plan.restore(phone, self.journal)
        self.assertFalse(phone.installed)
        phone.build = "factory/build"
        phone.fail_after_write = "install-existing"
        with self.assertRaises(adb.DeviceError):
            plan.restore(phone, self.journal)
        self.assertEqual(json.loads(self.journal.read_bytes())["entries"][0]["state"], "restoring")
        phone.fail_after_write = None
        plan.restore(phone, self.journal)
        self.assertTrue(phone.installed)
        self.assertEqual(phone.enabled, 3)

    def test_dns_restores_partial_setting_after_transport_loss(self):
        phone = Phone()
        approval = plan.create_plan(
            phone, [dict(kind="dns", target="private_dns", value="dns.example.com")], self.source)
        phone.fail_after_write = dns.SPECIFIER
        with self.assertRaises(adb.DeviceError):
            plan.apply(phone, self.source, approval, self.journal)
        self.assertEqual(phone.settings, {dns.MODE: "opportunistic", dns.SPECIFIER: "dns.example.com"})
        phone.fail_after_write = None
        plan.restore(phone, self.journal)
        self.assertEqual(phone.settings, {dns.MODE: "opportunistic"})

    def test_dns_restores_existing_provider(self):
        phone = Phone()
        phone.settings = {dns.MODE: "hostname", dns.SPECIFIER: "family.example.com"}
        approval = plan.create_plan(
            phone, [dict(kind="dns", target="private_dns", value="dns.example.com")], self.source)
        plan.apply(phone, self.source, approval, self.journal)
        self.assertEqual(phone.settings[dns.SPECIFIER], "dns.example.com")
        plan.restore(phone, self.journal)
        self.assertEqual(phone.settings[dns.SPECIFIER], "family.example.com")

    def test_restore_handles_dns_even_if_another_action_conflicts(self):
        phone = Phone()
        phone.settings["low_power_trigger_level"] = "25"
        approval = plan.create_plan(phone, [
            dict(kind="dns", target="private_dns", value="dns.example.com"),
            dict(kind="setting", target="low_power_trigger_level", value="0"),
        ], self.source)
        plan.apply(phone, self.source, approval, self.journal)
        phone.settings["low_power_trigger_level"] = "15"
        with self.assertRaises(adb.DeviceError):
            plan.restore(phone, self.journal)
        self.assertEqual(phone.settings, {dns.MODE: "opportunistic", "low_power_trigger_level": "15"})

    def test_dns_rejects_urls_ip_addresses_and_invalid_labels(self):
        for value in ("https://dns.example.com", "1.1.1.1", "dns.example.com:853", "*.example.com",
                      "dns..example.com", "invalid", "-dns.example.com", "dns.example.com\n"):
            with self.subTest(value=value), self.assertRaises(adb.DeviceError):
                dns.hostname(value)
        self.assertEqual(dns.hostname("DNS.Example.COM"), "dns.example.com")


if __name__ == "__main__":
    unittest.main()
