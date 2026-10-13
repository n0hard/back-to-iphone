"""App Store через ipatool: перевод ошибок, отмена и таймаут скачивания, чтение Info.plist из IPA."""
import io
import plistlib
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401

import store


class ErrorTest(unittest.TestCase):
    def err(self, text):
        return store._error([{"error": text}], text)

    def test_messages(self):
        self.assertIsInstance(self.err("an auth code is required"), store.NeedCode)
        self.assertIn("6 цифр", str(self.err("2FA code must be 6 digits")))
        self.assertIn("Неверный Apple ID", str(self.err("invalid credentials")))
        self.assertIsInstance(self.err("failed to get account"), store.NotLoggedIn)
        self.assertIn("нет в истории покупок", str(self.err("license is required")))
        self.assertIn("Платное", str(self.err("paid app")))
        self.assertEqual(str(self.err("something new")), "something new")


class RunTest(unittest.TestCase):
    """_run с Python вместо ipatool: лишние аргументы ipatool после -c Python просто игнорирует."""

    def setUp(self):
        self.patch = mock.patch.object(store, "ipatool_path", lambda: sys.executable)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_success_json(self):
        code = 'import json; print(json.dumps({"success": True, "email": "a@b.c"}))'
        self.assertEqual(store._run(["-c", code])["email"], "a@b.c")

    def test_success_false_is_error(self):
        code = 'import json; print(json.dumps({"success": False, "error": "license is required"}))'
        with self.assertRaises(store.StoreError):
            store._run(["-c", code])

    def test_cancel_stops_quickly(self):
        cancel = threading.Event()
        threading.Timer(0.5, cancel.set).start()
        start = time.monotonic()
        with self.assertRaises(store.Canceled):
            store._run(["-c", "import time; time.sleep(30)"], timeout=60, cancel=cancel)
        self.assertLess(time.monotonic() - start, 5)

    def test_timeout(self):
        with self.assertRaises(store.StoreError) as ctx:
            store._run(["-c", "import time; time.sleep(30)"], timeout=1)
        self.assertIn("не ответил", str(ctx.exception))


class IpaTest(unittest.TestCase):
    def make_ipa(self, info):
        path = Path(tempfile.mkdtemp()) / "app.ipa"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("Payload/App.app/Info.plist", plistlib.dumps(info))
            z.writestr("Payload/App.app/Frameworks/X.framework/Info.plist", plistlib.dumps({"MinimumOSVersion": "99"}))
        return path

    def test_requirements_from_main_info_plist(self):
        ipa = self.make_ipa({"MinimumOSVersion": "15.0", "UIDeviceFamily": [1, 2], "CFBundleShortVersionString": "8.1",
                             "CFBundleIdentifier": "ru.example.app", "CFBundleDisplayName": "Пример"})
        req = store.ipa_requirements(ipa)
        self.assertEqual((req["minimumOS"], req["version"], req["bundleId"]), ("15.0", "8.1", "ru.example.app"))
        self.assertEqual(req["families"], [1, 2])

    def test_version_tuple(self):
        self.assertLess(store.version_tuple("15.8.3"), store.version_tuple("16.0"))
        self.assertEqual(store.version_tuple("abc"), (0,))


if __name__ == "__main__":
    unittest.main()
