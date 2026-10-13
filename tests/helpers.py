"""Общая подготовка тестов: временная папка данных вместо настоящей и путь к модулям программы.

Импортируйте этот модуль раньше модулей программы: папка данных вычисляется при импорте store.py.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
DATA_ROOT = Path(tempfile.mkdtemp(prefix="vozvrat-tests-"))

# store.DATA: Windows — %APPDATA%, macOS — ~/Library/…, Linux — $XDG_DATA_HOME
os.environ["APPDATA"] = str(DATA_ROOT)
os.environ["XDG_DATA_HOME"] = str(DATA_ROOT)
if sys.platform == "darwin":
    os.environ["HOME"] = str(DATA_ROOT)

if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))


class FakeResponse:
    """Ответ requests для подмены сетевых запросов."""

    def __init__(self, status=200, json_data=None, text="", headers=None, content=b""):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._json = json_data
        self.text = text
        self.headers = headers or {}
        self.content = content

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json
