"""Сайт: сборка генератором в копии репозитория — ссылки, разметка для поисковиков, sitemap и числа каталога."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import helpers  # noqa: F401
from helpers import ROOT

SITE = "https://vozvratapp.ru/"


class SiteBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # собираем в копии, чтобы не трогать файлы репозитория
        cls.tmp = Path(tempfile.mkdtemp(prefix="vozvrat-site-"))
        shutil.copytree(ROOT / "cite", cls.tmp / "cite")
        shutil.copytree(ROOT / "tools", cls.tmp / "tools")
        (cls.tmp / "app").mkdir()
        for name in ("catalog.json", "version.py"):
            shutil.copy(ROOT / "app" / name, cls.tmp / "app" / name)
        script = str(cls.tmp / "tools" / "build_blog.py")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}  # генератор печатает по-русски
        cls.build = staticmethod(lambda: subprocess.run([sys.executable, script], capture_output=True, text=True,
                                                        encoding="utf-8", env=env))
        out = cls.build()
        assert out.returncode == 0, out.stderr
        cls.cite = cls.tmp / "cite"
        cls.pages = sorted(cls.cite.rglob("*.html"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_no_broken_local_links(self):
        bad = []
        for page in self.pages:
            if page.name == "404.html":  # там ссылки абсолютные — от корня сайта на GitHub Pages
                continue
            for url in re.findall(r'(?:href|src)="([^"]+)"', page.read_text(encoding="utf-8")):
                if re.match(r"(https?:|mailto:|#|data:)", url):
                    continue
                target = (page.parent / url.split("#")[0]).resolve()
                if target.is_dir():
                    target = target / "index.html"
                if not target.is_file():
                    bad.append(f"{page.relative_to(self.cite)} -> {url}")
        self.assertEqual(bad, [])

    def test_links_without_index_html(self):
        for page in self.pages:
            self.assertNotRegex(page.read_text(encoding="utf-8"), r'href="[^"]*index\.html', page.name)

    def test_structured_data_parses(self):
        for page in self.pages:
            for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                                    page.read_text(encoding="utf-8"), re.S):
                json.loads(block)  # падает на ошибке синтаксиса

    def test_articles_have_dates_and_breadcrumbs(self):
        for page in (self.cite / "blog").glob("*/index.html"):
            t = page.read_text(encoding="utf-8")
            data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', t, re.S).group(1))
            kinds = {item["@type"] for item in data["@graph"]}
            self.assertEqual(kinds, {"Article", "BreadcrumbList"}, page)
            article = next(i for i in data["@graph"] if i["@type"] == "Article")
            self.assertRegex(article["dateModified"], r"^\d{4}-\d{2}-\d{2}$")

    def test_sitemap(self):
        root = ET.parse(self.cite / "sitemap.xml").getroot()
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locs = [u.find("s:loc", ns).text for u in root.findall("s:url", ns)]
        posts = [p.parent.name for p in (self.cite / "blog").glob("*/index.html")]
        self.assertEqual(len(locs), 2 + len(posts))
        self.assertIn(SITE, locs)
        for slug in posts:
            self.assertIn(f"{SITE}blog/{slug}/", locs)
        for u in root.findall("s:url", ns):
            self.assertRegex(u.find("s:lastmod", ns).text, r"^\d{4}-\d{2}-\d{2}$")

    def test_catalog_counts_on_pages(self):
        apps = json.loads((ROOT / "app" / "catalog.json").read_text(encoding="utf-8"))["apps"]
        home = (self.cite / "index.html").read_text(encoding="utf-8")
        self.assertIn(f'<span data-n="apps-num">{len(apps)}</span>', home)
        for page in self.pages:
            # неподставленные метки чисел (%APPDATA% в статьях — настоящий путь Windows, не метка)
            self.assertNotRegex(page.read_text(encoding="utf-8"), r"%(APPS|APPS-GEN|APPS-NUM|CARDS)%", page.name)

    def test_software_version_from_version_py(self):
        scope = {}
        exec((ROOT / "app" / "version.py").read_text(encoding="utf-8"), scope)
        self.assertIn(f'"softwareVersion": "{scope["VERSION"]}"', (self.cite / "index.html").read_text(encoding="utf-8"))

    def test_rebuild_changes_nothing(self):
        before = {p: p.read_bytes() for p in self.cite.rglob("*") if p.is_file()}
        self.assertEqual(self.build().returncode, 0)
        changed = [str(p.relative_to(self.cite)) for p, data in before.items() if p.read_bytes() != data]
        self.assertEqual(changed, [], "повторная сборка изменила файлы")


if __name__ == "__main__":
    unittest.main()
