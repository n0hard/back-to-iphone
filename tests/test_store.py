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

    def test_network_errors(self):
        sap = ('preparing authentication; the first login may take a few minutes | failed to initialize SAP action '
               'signer: create SAP signer: exchange SAP setup message: send SAP request: Post '
               '"https://fpinit.itunes.apple.com/v1/signSapSetup/legacy": context deadline exceeded '
               '(Client.Timeout exceeded while awaiting headers)')
        for text in (sap, "dial tcp 17.253.39.140:443: i/o timeout", "read: connection reset by peer",
                     "lookup buy.itunes.apple.com: no such host", "net/http: TLS handshake timeout"):
            e = self.err(text)
            self.assertIsInstance(e, store.NetworkError, text)
            self.assertIn("VPN", str(e))
        self.assertNotIsInstance(self.err("invalid credentials"), store.NetworkError)
        # не удалось даже подключиться — ждать бесполезно, нужен VPN, другая сеть или DNS
        dial = ('send SAP request: Post "https://fpinit.itunes.apple.com/v1/signSapSetup/legacy": dial tcp '
                '17.253.254.9:443: i/o timeout (Client.Timeout exceeded while awaiting headers)')
        self.assertEqual(str(self.err(dial)), store.CONNECT_HINT)
        self.assertIn("DNS", store.CONNECT_HINT)
        self.assertEqual(str(self.err(sap)), store.NETWORK_HINT)


class CookieLockTest(unittest.TestCase):
    """ipatool падает, если файл cookies держит другой его запуск дольше 3 секунд."""
    PANIC = ('panic: cannot load cookies: file locked for too long; giving up: cannot acquire lock: file '
             '"C:\\Users\\u\\.ipatool\\cookies.lock" already locked\n\ngoroutine 1 [running]:\n'
             'github.com/majd/ipatool/v2/pkg/util.Must[...](...)\n'
             '\t/Users/runner/work/ipatool/ipatool/pkg/util/must.go:6\n'
             'main.main()\n\t/Users/runner/work/ipatool/ipatool/main.go:10 +0x13\n')

    def test_panic_is_recognized(self):
        e = store._error([], self.PANIC)
        self.assertIsInstance(e, store.SessionBusy)
        self.assertTrue(e.at_start)
        self.assertNotIn("main.go", str(e))
        other = store._error([], "panic: runtime error: index out of range\n\ngoroutine 1\nmain.go:10 +0x13")
        self.assertIn("index out of range", str(other))

    def test_retried_until_cookies_are_free(self):
        counter = Path(tempfile.mkdtemp()) / "n"
        code = ("import json, sys, pathlib; p = pathlib.Path(sys.argv[1]); n = int(p.read_text() or 0) + 1 "
                "if p.exists() else 1; p.write_text(str(n)); "
                "(sys.stderr.write(%r), sys.exit(2)) if n < 3 else print(json.dumps({'success': True}))" % self.PANIC)
        with mock.patch.object(store, "ipatool_path", lambda: sys.executable), \
                mock.patch.object(store.random, "uniform", lambda a, b: 0):
            self.assertTrue(store._run(["-c", code, str(counter)])["success"])
        self.assertEqual(counter.read_text(), "3")

    def test_gives_up_after_attempts(self):
        code = "import sys; sys.stderr.write(%r); sys.exit(2)" % self.PANIC
        with mock.patch.object(store, "ipatool_path", lambda: sys.executable), \
                mock.patch.object(store.random, "uniform", lambda a, b: 0):
            with self.assertRaises(store.SessionBusy):
                store._run(["-c", code])


class SlotTest(unittest.TestCase):
    """Windows: у одновременных запусков ipatool свои папки сессии, копии догоняют основную."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [mock.patch.object(store, "DATA", self.tmp), mock.patch.object(store.sys, "platform", "win32"),
                        mock.patch.object(store, "IPATOOL_HOME", self.tmp / "ipatool-home")]
        for p in self.patches:
            p.start()
        self.main = self.tmp / "ipatool-home" / ".ipatool"
        self.main.mkdir(parents=True)

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_copy_follows_login_and_logout(self):
        (self.main / "account").write_text("v1", encoding="utf-8")
        (self.main / "cookies").write_text("c", encoding="utf-8")
        home = store._slot_home(1)
        self.assertNotEqual(home, store.IPATOOL_HOME)
        self.assertEqual((home / ".ipatool" / "account").read_text(encoding="utf-8"), "v1")
        self.assertEqual(store._slot_home(0), store.IPATOOL_HOME)
        time.sleep(0.05)
        (self.main / "account").write_text("v2", encoding="utf-8")  # новый вход
        store._slot_home(1)
        self.assertEqual((home / ".ipatool" / "account").read_text(encoding="utf-8"), "v2")
        (self.main / "account").unlink()  # выход
        store._slot_home(1)
        self.assertFalse((home / ".ipatool" / "account").exists())

    def test_other_platforms_share_the_main_folder(self):
        with mock.patch.object(store.sys, "platform", "darwin"):
            self.assertEqual(store._slot_home(2), store.IPATOOL_HOME)

    def test_auth_waits_for_main_slot_and_others_run_in_parallel(self):
        seen, lock = [], threading.Lock()

        def run_once(args, timeout, cancel, home=None):
            with lock:
                seen.append((args[0], home))
            time.sleep(0.2)
            return {"success": True}

        with mock.patch.object(store, "_run_once", run_once):
            threads = [threading.Thread(target=store._run, args=(["list-versions"],)) for _ in range(3)]
            for th in threads:
                th.start()
            time.sleep(0.05)
            store._run(["auth", "info"])
            for th in threads:
                th.join()
        homes = {h for a, h in seen if a == "list-versions"}
        self.assertEqual(len(homes), 3)  # три одновременных запуска — три разные папки
        self.assertEqual([h for a, h in seen if a == "auth"], [store.IPATOOL_HOME])
        self.assertEqual(store._free_slots, set(range(store.SLOTS)))


class LoginTest(unittest.TestCase):
    def test_network_error_is_retried(self):
        calls = []

        def run(args, timeout=600, cancel=None):
            calls.append(args)
            if len(calls) < 3:
                raise store.NetworkError(store.NETWORK_HINT)
            return {"success": True, "email": "a@b.c", "name": "Имя"}

        with mock.patch.object(store, "_run", run), mock.patch.object(store, "LOGIN_RETRY_PAUSE", 0):
            self.assertEqual(store.login("a@b.c", "pw")["name"], "Имя")
        self.assertEqual(len(calls), 3)

    def test_gives_up_after_attempts_and_does_not_retry_other_errors(self):
        with mock.patch.object(store, "_run", side_effect=store.NetworkError("сеть")) as run, \
                mock.patch.object(store, "LOGIN_RETRY_PAUSE", 0):
            with self.assertRaises(store.NetworkError):
                store.login("a@b.c", "pw")
        self.assertEqual(run.call_count, store.LOGIN_ATTEMPTS)
        with mock.patch.object(store, "_run", side_effect=store.StoreError("Неверный Apple ID или пароль")) as run:
            with self.assertRaises(store.StoreError):
                store.login("a@b.c", "pw")
        self.assertEqual(run.call_count, 1)


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


class SessionTest(unittest.TestCase):
    """Своя папка ipatool: на Windows он берёт домашнюю папку из HOMEDRIVE+HOMEPATH, и до 1.4.1 сессия
    лежала в общем ~/.ipatool — при первом запуске она переносится, если открывается нашим ключом."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.shared = self.tmp / "user" / ".ipatool"
        self.shared.mkdir(parents=True)
        for name in store.SESSION_FILES:
            (self.shared / name).write_text(name, encoding="utf-8")
        drive, rest = __import__("os").path.splitdrive(str(self.tmp / "user"))
        self.patches = [
            mock.patch.object(store, "DATA", self.tmp / "data"),
            mock.patch.object(store, "IPATOOL_HOME", self.tmp / "data" / "ipatool-home"),
            mock.patch.object(store.sys, "platform", "win32"),
            mock.patch.dict(store.os.environ, {"HOMEDRIVE": drive, "HOMEPATH": rest}),
        ]
        for p in self.patches:
            p.start()
        self.own = self.tmp / "data" / "ipatool-home" / ".ipatool"

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_env_points_ipatool_home_everywhere(self):
        env = store._ipatool_env()
        home = str(self.tmp / "data" / "ipatool-home")
        self.assertEqual(env["HOMEDRIVE"] + env["HOMEPATH"], home)
        self.assertEqual((env["USERPROFILE"], env["HOME"]), (home, home))

    def test_own_session_is_moved(self):
        with mock.patch.object(store, "_run", return_value={"success": True}) as run:
            store._migrate_session()
        run.assert_called_once()
        self.assertEqual(sorted(p.name for p in self.own.iterdir()), sorted(store.SESSION_FILES))
        self.assertTrue((self.tmp / "data" / "session-migrated").exists())
        with mock.patch.object(store, "_run") as run:  # второй раз ничего не делает
            store._migrate_session()
        run.assert_not_called()

    def test_foreign_session_is_left_alone(self):
        with mock.patch.object(store, "_run", side_effect=store.StoreError("integrity check failed")):
            store._migrate_session()
        self.assertEqual(list(self.own.iterdir()), [])
        self.assertTrue((self.shared / "account").exists())  # чужую сессию не трогаем

    def test_other_platforms_do_nothing(self):
        with mock.patch.object(store.sys, "platform", "linux"), mock.patch.object(store, "_run") as run:
            store._migrate_session()
        run.assert_not_called()
        self.assertFalse(self.own.exists())
