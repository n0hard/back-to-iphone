"""Каталог: целостность catalog.json и выбор между свежей копией и встроенным каталогом."""
import json
import unittest
from unittest import mock

import helpers  # noqa: F401
from helpers import APP

import catalog
from version import VERSION


class CatalogFileTest(unittest.TestCase):
    def setUp(self):
        self.apps = json.loads((APP / "catalog.json").read_text(encoding="utf-8"))["apps"]

    def test_size_and_fields(self):
        self.assertGreaterEqual(len(self.apps), 400)
        for a in self.apps:
            self.assertIsInstance(a.get("id"), int, a)
            self.assertTrue(str(a.get("name", "")).strip(), a)
            self.assertTrue(str(a.get("category", "")).strip(), a)

    def test_ids_unique(self):
        ids = [a["id"] for a in self.apps]
        self.assertEqual(len(ids), len(set(ids)), "в каталоге повторяются App Store ID")

    def test_local_icons_exist(self):
        missing = [a["name"] for a in self.apps
                   if str(a.get("icon", "")).startswith("icons/") and not (APP / "ui" / a["icon"]).exists()]
        self.assertEqual(missing, [], "нет файлов иконок")

    def test_bundled_catalog_is_valid_for_loader(self):
        self.assertTrue(catalog._valid({"apps": self.apps}))


class LoadTest(unittest.TestCase):
    def setUp(self):
        catalog._fetched.set()  # фоновая загрузка «уже закончилась», в сеть не ходим
        self.addCleanup(lambda: catalog.CACHE.unlink(missing_ok=True))
        catalog.CACHE.parent.mkdir(parents=True, exist_ok=True)
        self.bundled = json.loads(catalog.BUNDLED.read_text(encoding="utf-8"))["apps"]

    def write_cache(self, version, apps):
        catalog.CACHE.write_text(json.dumps({"version": version, "apps": apps}), encoding="utf-8")

    def test_fresh_cache_is_used(self):
        apps = self.bundled + [{"id": 1234567890, "name": "Новое", "category": "Банки"}]
        self.write_cache(VERSION, apps)
        loaded = catalog.load(wait=0)
        self.assertEqual((loaded["source"], len(loaded["apps"])), ("remote", len(apps)))

    def test_cache_from_other_version_is_ignored(self):
        self.write_cache("0.0.1", self.bundled + [{"id": 1, "name": "x", "category": "y"}])
        self.assertEqual(catalog.load(wait=0)["source"], "bundled")

    def test_truncated_cache_is_ignored(self):
        self.write_cache(VERSION, self.bundled[:10])
        self.assertEqual(catalog.load(wait=0)["source"], "bundled")

    def test_icon_names_are_checked(self):
        self.assertIsNone(catalog.icon("../catalog.json"))
        self.assertIsNone(catalog.icon("abc.png"))
        with mock.patch.object(catalog.requests, "get") as get:
            self.assertIsNone(catalog.icon("1.png"))  # нет в каталоге — в сеть не идём
            get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
