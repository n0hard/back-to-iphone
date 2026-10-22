"""Поиск по каталогу: тот же JavaScript, что в интерфейсе, на всех приложениях каталога (нужен Node.js).

Для каждого приложения ищем по названию, названию карточки, строчными и ЗАГЛАВНЫМИ, транслитом, с опечаткой,
по App Store ID и по ссылке, а также по началу названия и слитному написанию — как при наборе.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401
from helpers import APP

HARNESS = r"""
const catalog = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8")).apps;
%(code)s
catalogGroups = makeGroups(catalog, "cat");
const L2C = {a:"а",b:"б",c:"к",d:"д",e:"е",f:"ф",g:"г",h:"х",i:"и",j:"дж",k:"к",l:"л",m:"м",n:"н",o:"о",p:"п",q:"к",
             r:"р",s:"с",t:"т",u:"у",v:"в",w:"в",x:"кс",y:"й",z:"з"};
const C2L = {а:"a",б:"b",в:"v",г:"g",д:"d",е:"e",ё:"e",ж:"zh",з:"z",и:"i",й:"y",к:"k",л:"l",м:"m",н:"n",о:"o",п:"p",
             р:"r",с:"s",т:"t",у:"u",ф:"f",х:"kh",ц:"ts",ч:"ch",ш:"sh",щ:"shch",ъ:"",ы:"y",ь:"",э:"e",ю:"yu",я:"ya"};
const tr = s => /[а-яё]/i.test(s) ? s.toLowerCase().replace(/[а-яё]/g, c => C2L[c]) : s.toLowerCase().replace(/[a-z]/g, c => L2C[c]);
const typo = s => { const w = s.split(/\s+/).sort((a, b) => b.length - a.length)[0]; if (!w || w.length < 6) return null;
                    const i = Math.floor(w.length / 2); return s.replace(w, w.slice(0, i) + w.slice(i + 1)); };
const fails = [];
for (const a of catalog) {
  const g = catalogGroups.find(x => x.apps.includes(a));
  const tests = [["name", a.name], ["title", g.title], ["lower", a.name.toLowerCase()], ["upper", a.name.toUpperCase()],
                 ["translit", tr(a.name)], ["id", String(a.id)], ["link", `https://apps.apple.com/ru/app/x/id${a.id}?l=en`]];
  const ty = typo(a.name); if (ty) tests.push(["typo", ty]);
  for (const [kind, q] of tests) {
    const res = searchCatalog(q), r = res.indexOf(g);
    if (r < 0) fails.push(`${kind}: «${q}» не нашёл ${a.name}`);
    else if (kind === "title" && r > 0) fails.push(`title: «${q}» на месте ${r + 1}`);
    else if (kind === "name" && r >= 8) fails.push(`name: «${q}» на месте ${r + 1}`);
  }
  if (a === (g.main || g.apps[0])) {
    const prefix = g.title.slice(0, Math.max(3, Math.ceil(g.title.length * 0.6)));
    const r = searchCatalog(prefix).indexOf(g);
    if (r < 0 || r >= 8) fails.push(`начало: «${prefix}» → ${g.title} на месте ${r + 1}`);
    if (/[\s-]/.test(g.title)) {
      const joined = g.title.replace(/[\s-]+/g, ""), r2 = searchCatalog(joined).indexOf(g);
      if (r2 < 0 || r2 >= 8) fails.push(`слитно: «${joined}» → ${g.title} на месте ${r2 + 1}`);
    }
  }
}
const first = q => (searchCatalog(q)[0] || {}).title || null;
const expected = {"Messenger Max": "MAX", "мессенджер макс": "MAX", "сбол": "СберБанк Онлайн", "тинькофф": "Т-Банк",
                  "вк": "ВКонтакте", "хай дай": "Hay Day", "АльфаБанк": "Альфа-Банк", "сбрбанк": "СберБанк Онлайн"};
for (const [q, want] of Object.entries(expected)) if (first(q) !== want) fails.push(`«${q}» → ${first(q)}, ожидалось ${want}`);
for (const q of ["2гис", "qwertyzzz"]) if (searchCatalog(q).length) fails.push(`«${q}» не должен ничего находить`);
// Подсказки и «Найти» показывают сам вариант, если запрос про него, а не про карточку
const firstR = q => (searchResults(q)[0] || {}).title || null;
const variants = {"синоптик+": "Синоптик+", "Синоптик": "Синоптик+", "халва синоптик": "Синоптик+",
                  "vibrogym": "VibroGym App", "совкомбанк": "Совкомбанк Халва", "т-банк": "Т-Банк"};
for (const [q, want] of Object.entries(variants)) if (firstR(q) !== want) fails.push(`вариант: «${q}» → ${firstR(q)}, ожидалось ${want}`);
for (const a of catalog) {
  const g = catalogGroups.find(x => x.apps.includes(a)), label = (a.name.match(/\(([^()]*)\)\s*$/) || [])[1];
  if (!label || a === g.main || g.apps.length < 2 || words(label).every(w => groupIndex(g).title.includes(w))) continue;
  const r = searchResults(a.name).findIndex(x => x.apps.length === 1 && x.apps[0] === a);
  if (r < 0 || r >= 8) fails.push(`вариант: «${a.name}» на месте ${r + 1}`);
}
console.log(JSON.stringify({apps: catalog.length, fails}));
"""


@unittest.skipUnless(shutil.which("node"), "нужен Node.js")
class SearchTest(unittest.TestCase):
    def test_every_catalog_app_is_found(self):
        html = (APP / "ui" / "index.html").read_text(encoding="utf-8")
        groups_code = html[html.index("const baseName"):html.index("function plural")]
        search_code = html[html.index("// Поиск только по каталогу"):html.index("let catalog = [], catalogGroups = [];")]
        code = groups_code + search_code + "\nlet catalogGroups = [];\n"
        script = Path(tempfile.mkdtemp()) / "search_test.js"
        script.write_text(HARNESS % {"code": code}, encoding="utf-8")
        out = subprocess.run(["node", str(script), str(APP / "catalog.json")], capture_output=True, text=True,
                             encoding="utf-8", timeout=600)
        self.assertEqual(out.returncode, 0, out.stderr)
        result = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertGreaterEqual(result["apps"], 400)
        self.assertEqual(result["fails"], [], "\n".join(result["fails"][:20]))


if __name__ == "__main__":
    unittest.main()
