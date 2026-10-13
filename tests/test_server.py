"""Локальный сервер: установленные приложения, «Вернуть всё сразу», обновления приложений, очередь и API."""
import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

import helpers  # noqa: F401

import catalog
import device
import server
import store
import updater

CATALOG = {"apps": [
    {"id": 492224193, "name": "СберБанк Онлайн", "category": "Банки"},
    {"id": 1001, "name": "Т-Банк", "category": "Банки"},
    {"id": 1002, "name": "Т-Банк (VibroGym App)", "category": "Банки"},
    {"id": 6739530834, "name": "MAX", "category": "Соцсети и мессенджеры"},
    {"id": 564177498, "name": "ВКонтакте", "category": "Соцсети и мессенджеры"},
], "source": "bundled"}

ON_PHONE = {  # bundleId -> то, что отдаёт iPhone
    "ru.sberbank.app": {"version": "15.1", "name": "СберБанк", "appId": 492224193},
    "com.vk.app": {"version": "9.0", "name": "VK", "appId": 564177498},
    "com.max.app": {"version": "1.0", "name": "MAX", "appId": None},          # ID знает только журнал
    "com.other.app": {"version": "1.0", "name": "Чужое", "appId": 111111111},  # не из каталога
}


class InstalledTest(unittest.TestCase):
    def setUp(self):
        server.INSTALLED.parent.mkdir(parents=True, exist_ok=True)
        server.INSTALLED.write_text(json.dumps({"UDID": {"com.max.app": {"appId": 6739530834}}}), encoding="utf-8")
        self.addCleanup(lambda: server.INSTALLED.unlink(missing_ok=True))
        self.patches =[mock.patch.object(device, "installed_apps", lambda udid: ON_PHONE),
                        mock.patch.object(catalog, "load", lambda wait=5: CATALOG)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_installed_known(self):
        apps = server.installed_known("UDID")
        self.assertEqual(set(apps), {492224193, 564177498, 6739530834})
        self.assertEqual(apps[492224193]["version"], "15.1")

    def test_requires_device(self):
        with self.assertRaises(device.DeviceError):
            server.installed_known(None)

    def test_app_updates(self):
        latest = {492224193: "16.0", 564177498: "9.0", 6739530834: "1.2"}
        with mock.patch.object(server, "latest_app_version", lambda app_id: latest[app_id]):
            r = server.app_updates("UDID")
        self.assertEqual(r["checked"], 3)
        self.assertEqual([u["appId"] for u in r["updates"]], [6739530834, 492224193])

    def test_record_install_journal(self):
        server.record_install("UDID2", {"bundleId": "com.x", "version": "2.0"}, 123456789, "X")
        journal = json.loads(server.INSTALLED.read_text(encoding="utf-8"))
        self.assertEqual(journal["UDID2"]["com.x"]["appId"], 123456789)
        self.assertIn("UDID", journal)


class RestoreScanTest(unittest.TestCase):
    """«Вернуть всё сразу»: какие приложения каталога есть в покупках и ещё не стоят на iPhone."""

    def run_scan(self, list_versions, category=None, installed=()):
        with mock.patch.object(catalog, "load", lambda wait=5: CATALOG), \
                mock.patch.object(server, "installed_known", lambda udid: {i: {} for i in installed}), \
                mock.patch.object(store, "list_versions", list_versions):
            server.start_scan("UDID", category)
            for _ in range(200):
                if not server.scan_snapshot()["running"]:
                    break
                time.sleep(0.02)
        return server.scan_snapshot()

    def test_finds_owned_and_skips_installed(self):
        owned = {492224193, 1002, 6739530834}

        def list_versions(app_id):
            if app_id in owned:
                return ["v1"]
            raise store.StoreError("Этого приложения нет в истории покупок этого Apple ID")

        s = self.run_scan(list_versions, installed=[492224193])
        self.assertEqual(s["total"], 4)  # СберБанк уже на iPhone — не проверяем
        self.assertEqual(sorted(a["id"] for a in s["found"]), [1002, 6739530834])
        self.assertEqual((s["checked"], s["failed"], s["error"]), (4, 0, None))

    def test_category_filter(self):
        s = self.run_scan(lambda app_id: ["v1"], category="Банки")
        self.assertEqual(s["total"], 3)
        self.assertTrue(all(a["category"] == "Банки" for a in s["found"]))

    def test_other_errors_are_counted(self):
        def list_versions(app_id):
            raise store.StoreError("App Store не ответил вовремя")
        s = self.run_scan(list_versions)
        self.assertEqual((s["failed"], s["found"]), (5, []))

    def test_logged_out_stops_with_message(self):
        def list_versions(app_id):
            raise store.NotLoggedIn("Сначала войдите в Apple ID")
        s = self.run_scan(list_versions)
        self.assertEqual(s["error"], "Сначала войдите в Apple ID")
        self.assertFalse(s["running"])


class QueueTest(unittest.TestCase):
    def test_parse_app_id(self):
        self.assertEqual(server.parse_app_id("https://apps.apple.com/ru/app/vk/id564177498?l=en"), 564177498)
        self.assertEqual(server.parse_app_id(" 564177498 "), 564177498)
        self.assertIsNone(server.parse_app_id("вконтакте"))

    def test_cancel_queued_and_downloading_but_not_installing(self):
        job = server.enqueue(1234567, "Тест", "UDID", False, False)
        self.assertTrue(all("_cancel" not in j and "udid" not in j for j in server.snapshot()))
        json.dumps(server.snapshot())
        self.assertTrue(server.cancel(job))
        self.assertEqual(server.jobs[job]["stage"], "canceled")
        job2 = server.enqueue(7654321, "Тест2", "UDID", False, False)
        server.queue.remove(job2)
        server.jobs[job2]["stage"] = "download"
        self.assertTrue(server.cancel(job2) and server.jobs[job2]["_cancel"].is_set())
        server.jobs[job2]["stage"] = "install"
        self.assertFalse(server.cancel(job2))

    def test_stale_downloads_removed_saved_ipa_kept(self):
        (server.IPA_DIR / ("a" * 32)).mkdir(parents=True, exist_ok=True)
        (server.IPA_DIR / "keep.ipa").write_bytes(b"x")
        server.clean_stale_downloads()
        self.assertFalse((server.IPA_DIR / ("a" * 32)).exists())
        self.assertTrue((server.IPA_DIR / "keep.ipa").exists())


class HttpTest(unittest.TestCase):
    """Настоящий HTTP-сервер программы: токен, проверка Host, блокировка до обязательного обновления."""

    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def request(self, path, token=True, body=None, host=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Token"] = server.TOKEN
        if host:
            headers["Host"] = host
        req = urllib.request.Request(self.base + path, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read() or b"{}")

    def set_update(self, status):
        updater._state.update(status=status, current="1.3.2", latest="1.4.0", mandatory=status == "outdated")

    def test_token_and_host_required(self):
        self.assertEqual(self.request("/api/state", token=False)[0], 403)
        self.assertEqual(self.request("/api/state", host="evil.example")[0], 403)

    def test_mandatory_update_blocks_actions(self):
        self.set_update("outdated")
        with mock.patch.object(device, "list_devices", lambda: []):
            self.assertEqual(self.request("/api/devices")[0], 423)
            self.assertEqual(self.request("/api/login", body={"email": "a", "password": "b"})[0], 423)
            self.assertEqual(self.request("/api/installed?udid=X")[0], 423)
            self.assertEqual(self.request("/api/state")[0], 200)  # состояние и обновление — доступны

    def test_optional_update_does_not_block(self):
        self.set_update("available")
        with mock.patch.object(device, "list_devices", lambda: []):
            self.assertEqual(self.request("/api/devices"), (200, {"devices": []}))

    def test_installed_endpoint(self):
        self.set_update("current")
        with mock.patch.object(server, "installed_known", lambda udid: {492224193: {"version": "15.1", "name": "С"}}):
            status, data = self.request("/api/installed?udid=UDID")
        self.assertEqual((status, data["apps"]["492224193"]["version"]), (200, "15.1"))


if __name__ == "__main__":
    unittest.main()
