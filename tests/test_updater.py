"""Обновление программы: обычное и обязательное, контрольные суммы, ошибки — без сети."""
import unittest
from unittest import mock

import helpers  # noqa: F401  (папка данных и путь к app)
from helpers import FakeResponse

import updater


def update_json(version, minimum):
    return lambda url, **kw: FakeResponse(json_data={"version": version, "min_version": minimum})


class VersionTupleTest(unittest.TestCase):
    def test_compare(self):
        self.assertGreater(updater.version_tuple("1.10.0"), updater.version_tuple("1.9.9"))
        self.assertEqual(updater.version_tuple("v1.3.0"), (1, 3, 0))
        self.assertEqual(updater.version_tuple(""), (0,))


class LatestInfoTest(unittest.TestCase):
    def test_from_update_json(self):
        with mock.patch.object(updater.requests, "get", update_json("1.4.0", "1.3.2")):
            self.assertEqual(updater.latest_info(), ("1.4.0", "1.3.2"))

    def test_old_release_without_update_json_is_mandatory(self):
        # релизы до 1.4.0 без update.json: номер по тегу, обновление обязательное (как работали те версии)
        with mock.patch.object(updater.requests, "get", lambda url, **kw: FakeResponse(404)), \
                mock.patch.object(updater, "latest_version", lambda: "1.3.2"):
            self.assertEqual(updater.latest_info(), ("1.3.2", "1.3.2"))

    def test_garbage_update_json_falls_back_to_tag(self):
        bad = lambda url, **kw: FakeResponse(json_data={"version": "<script>", "min_version": "1"})
        with mock.patch.object(updater.requests, "get", bad), mock.patch.object(updater, "latest_version", lambda: "2.0.0"):
            self.assertEqual(updater.latest_info(), ("2.0.0", "2.0.0"))

    def test_latest_version_from_redirect(self):
        head = lambda url, **kw: FakeResponse(302, headers={"Location": "https://github.com/x/y/releases/tag/v1.5.1"})
        with mock.patch.object(updater.requests, "head", head):
            self.assertEqual(updater.latest_version(), "1.5.1")


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.patches = [mock.patch.object(updater, "FROZEN", True), mock.patch.object(updater, "VERSION", "1.3.2"),
                        mock.patch.object(updater.time, "sleep", lambda s: None)]
        for p in self.patches:
            p.start()
        updater._state.clear()
        updater._state.update(status="checking", current="1.3.2", latest=None, progress=None, error=None)

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def check(self, latest, minimum):
        with mock.patch.object(updater, "latest_info", lambda: (latest, minimum)):
            return updater.check()

    def test_current(self):
        self.assertEqual(self.check("1.3.2", "1.3.2")["status"], "current")
        self.assertTrue(updater.allowed())

    def test_optional_update_does_not_block(self):
        st = self.check("1.4.0", "1.3.0")
        self.assertEqual((st["status"], st["mandatory"]), ("available", False))
        self.assertTrue(updater.allowed())

    def test_min_version_equal_to_current_is_optional(self):
        self.assertEqual(self.check("1.4.0", "1.3.2")["status"], "available")

    def test_mandatory_update_blocks(self):
        st = self.check("1.4.0", "1.4.0")
        self.assertEqual((st["status"], st["mandatory"]), ("outdated", True))
        self.assertFalse(updater.allowed())

    def test_first_check_failure_blocks(self):
        def fail():
            raise updater.UpdateError("нет сети")
        with mock.patch.object(updater, "latest_info", fail):
            st = updater.check()
        self.assertEqual(st["status"], "failed")
        self.assertFalse(updater.allowed())

    def test_background_failure_keeps_working(self):
        self.check("1.3.2", "1.3.2")

        def fail():
            raise updater.UpdateError("нет сети")
        with mock.patch.object(updater, "latest_info", fail):
            self.assertEqual(updater.check()["status"], "current")

    def test_source_run_never_blocks(self):
        with mock.patch.object(updater, "FROZEN", False):
            self.assertEqual(self.check("9.0.0", "9.0.0")["status"], "source")
            self.assertTrue(updater.allowed())

    def test_failed_optional_update_returns_to_banner(self):
        self.check("1.4.0", "1.3.0")
        updater._failed("Не удалось скачать")
        st = updater.state()
        self.assertEqual((st["status"], st["error"]), ("available", "Не удалось скачать"))
        self.assertTrue(updater.allowed())

    def test_failed_mandatory_update_stays_blocked(self):
        self.check("1.4.0", "1.4.0")
        updater._failed("Не удалось скачать")
        self.assertEqual(updater.state()["status"], "error")
        self.assertFalse(updater.allowed())

    def test_start_update_requires_newer_version(self):
        self.check("1.3.2", "1.3.2")
        with self.assertRaises(updater.UpdateError):
            updater.start_update()


class ChecksumTest(unittest.TestCase):
    SUMS = ("1111111111111111111111111111111111111111111111111111111111111111  Vozvrat-Linux-x64.AppImage\n"
            "AAAAaaaa22222222222222222222222222222222222222222222222222222222 *VozvratSetup.exe\n"
            "garbage line\n")

    def fake_get(self, sums_ok):
        def get(url, **kw):
            if url.endswith("SHA256SUMS.txt"):
                return FakeResponse(200 if sums_ok else 404, text=self.SUMS)
            return FakeResponse(json_data={"assets": [{"name": "VozvratSetup.exe", "digest": "sha256:" + "3" * 64}]})
        return get

    def test_from_sums_file(self):
        with mock.patch.object(updater.requests, "get", self.fake_get(True)):
            self.assertEqual(updater._expected_sha256("v9", "VozvratSetup.exe"), "aaaaaaaa" + "2" * 56)
            self.assertEqual(updater._expected_sha256("v9", "Vozvrat-Linux-x64.AppImage"), "1" * 64)
            self.assertIsNone(updater._expected_sha256("v9", "Vozvrat-macOS-arm64.dmg"))

    def test_falls_back_to_api_digest(self):
        with mock.patch.object(updater.requests, "get", self.fake_get(False)):
            self.assertEqual(updater._expected_sha256("v9", "VozvratSetup.exe"), "3" * 64)


class EnvironmentTest(unittest.TestCase):
    def test_clean_env_for_new_version(self):
        dirty = {"PATH": "x", "_PYI_ARCHIVE_FILE": "a", "_PYI_PARENT_PROCESS_LEVEL": "1",
                 "PYTHONNET_RUNTIME": "coreclr", "VOZVRAT_WINDOW_ATTEMPT": "2"}
        with mock.patch.dict(updater.os.environ, dirty, clear=True):
            env = updater._clean_env()
        self.assertEqual(env, {"PATH": "x", "PYINSTALLER_RESET_ENVIRONMENT": "1"})

    def test_asset_names(self):
        cases = [("win32", "AMD64", {}, "VozvratSetup.exe"),
                 ("darwin", "arm64", {}, "Vozvrat-macOS-arm64.dmg"),
                 ("darwin", "x86_64", {}, "Vozvrat-macOS-x64.dmg"),
                 ("linux", "x86_64", {"APPIMAGE": "/a/V.AppImage"}, "Vozvrat-Linux-x64.AppImage"),
                 ("linux", "x86_64", {}, "Vozvrat-Linux-x64.tar.gz")]
        for plat, machine, env, expected in cases:
            with mock.patch.object(updater.sys, "platform", plat), \
                    mock.patch.object(updater.platform, "machine", lambda m=machine: m), \
                    mock.patch.dict(updater.os.environ, env, clear=False):
                if "APPIMAGE" not in env:
                    updater.os.environ.pop("APPIMAGE", None)
                self.assertEqual(updater.asset_name(), expected, plat)


if __name__ == "__main__":
    unittest.main()
