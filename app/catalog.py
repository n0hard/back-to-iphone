"""Каталог приложений: свежий из репозитория, без выпуска новой версии программы.

При запуске программа скачивает app/catalog.json из ветки main и кладёт копию в папку данных.
Если сети нет — берётся сохранённая копия, а если её нет или она от другой версии программы —
каталог, встроенный в сборку. Иконки новых приложений, которых нет в сборке, скачиваются оттуда же
при первом показе и тоже сохраняются.
"""
import json
import re
import sys
import threading
from pathlib import Path

import requests

import store
from version import REPO, VERSION

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
BUNDLED = ROOT / "catalog.json"
CACHE = store.DATA / "catalog.json"
ICON_CACHE = store.DATA / "icons"
RAW = f"https://raw.githubusercontent.com/{REPO}/main/app"
HEADERS = {"User-Agent": f"Vozvrat/{VERSION}"}
MIN_APPS = 100  # защита от обрезанного или пустого ответа

_fetched = threading.Event()
_missing = set()  # иконки, которых нет и в репозитории: не спрашиваем снова


def _valid(data):
    apps = data.get("apps") if isinstance(data, dict) else None
    return (isinstance(apps, list) and len(apps) >= MIN_APPS
            and all(isinstance(a, dict) and isinstance(a.get("id"), int) and isinstance(a.get("name"), str)
                    for a in apps))


def refresh():
    """Скачивает свежий каталог в фоне; /api/catalog ждёт этого не дольше нескольких секунд."""
    def run():
        try:
            r = requests.get(f"{RAW}/catalog.json", headers=HEADERS, timeout=10)
            data = r.json() if r.ok else None
            if _valid(data):
                CACHE.parent.mkdir(parents=True, exist_ok=True)
                tmp = CACHE.with_suffix(".tmp")
                tmp.write_text(json.dumps({"version": VERSION, "apps": data["apps"]}, ensure_ascii=False),
                               encoding="utf-8")
                tmp.replace(CACHE)
        except (requests.RequestException, ValueError, OSError):
            pass
        finally:
            _fetched.set()
    threading.Thread(target=run, daemon=True).start()


def load(wait=5):
    _fetched.wait(wait)
    try:
        cached = json.loads(CACHE.read_text(encoding="utf-8"))
        # копия от другой версии программы могла устареть сильнее встроенного каталога
        if cached.get("version") == VERSION and _valid(cached):
            return {"apps": cached["apps"], "source": "remote"}
    except (OSError, ValueError, AttributeError):
        pass
    return {"apps": json.loads(BUNDLED.read_text(encoding="utf-8"))["apps"], "source": "bundled"}


def icon(name):
    """Байты иконки icons/<id>.png: из сборки, из кэша или из репозитория (и в кэш)."""
    if not re.fullmatch(r"\d+\.png", name):
        return None
    for path in (ROOT / "ui" / "icons" / name, ICON_CACHE / name):
        if path.exists():
            return path.read_bytes()
    app_id = int(name.split(".")[0])
    if name in _missing:
        return None
    if not any(a.get("id") == app_id for a in load(wait=0)["apps"]):
        return None  # качаем только иконки приложений из каталога
    try:
        r = requests.get(f"{RAW}/ui/icons/{name}", headers=HEADERS, timeout=10)
    except requests.RequestException:
        return None
    if not r.ok or not (r.content[:4] == b"\x89PNG" or r.content[:3] == b"\xff\xd8\xff"):
        _missing.add(name)
        return None
    ICON_CACHE.mkdir(parents=True, exist_ok=True)
    (ICON_CACHE / name).write_bytes(r.content)
    return r.content
