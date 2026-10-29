"""App Store: вход в Apple ID и скачивание IPA из истории покупок через ipatool.

Apple требует для входа подпись SAP (FairPlay), которую умеет вычислять только ipatool
(github.com/majd/ipatool, open source). Бинарник лежит в ../bin, его ставит setup_tools.py.
Сессия Apple хранится в зашифрованном хранилище ipatool; пароль нужен ipatool для
автоматического перелогина при истечении токена и хранится там же, а не в этом приложении.
Хранилище лежит в своей папке (IPATOOL_HOME), а не в общем ~/.ipatool: туда же пишут другие
программы на ipatool (например, IPA_Downloader) своим ключом, и сессии портили бы друг друга.
На Windows ipatool берёт домашнюю папку из HOMEDRIVE+HOMEPATH (не USERPROFILE), поэтому до 1.4.1
сессия всё равно лежала в общем ~/.ipatool — при первом запуске она переносится (_migrate_session).
"""
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import zipfile
import plistlib
from pathlib import Path, PurePosixPath

import requests

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))  # в .exe bin/ лежит внутри


def _data_dir():
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home()) / "vozvrat"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Vozvrat"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "vozvrat"


DATA = _data_dir()
IPATOOL_HOME = DATA / "ipatool-home"  # ipatool кладёт состояние в <домашняя папка>/.ipatool
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# iTunes Search API отвечает 403 на User-Agent python-requests
WEB_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/130.0 Safari/537.36"}


class StoreError(Exception):
    pass


class NotLoggedIn(StoreError):
    pass


class NeedCode(StoreError):
    """Apple требует код двухфакторной аутентификации."""


class NetworkError(StoreError):
    """Сервер Apple не ответил или соединение оборвалось: дело в сети, а не в Apple ID — стоит повторить."""


NETWORK_HINT = ("Сервер Apple не ответил вовремя — это проблема сети, а не Apple ID. Повторите через минуту. "
                "Если не поможет: выключите VPN или прокси (а если их нет — попробуйте с VPN), отключите на время "
                "антивирус или подключитесь к другой сети, например раздайте интернет с телефона")
# ipatool (Go) пишет сетевые сбои так: «context deadline exceeded (Client.Timeout exceeded while awaiting
# headers)», «dial tcp …: i/o timeout», «connection reset by peer», «no such host», «TLS handshake timeout»
NETWORK_MARKERS = ("deadline exceeded", "client.timeout", "i/o timeout", "handshake timeout", "connection reset",
                   "connection refused", "no such host", "network is unreachable", "unexpected eof",
                   "server misbehaving", "dial tcp")


class Canceled(StoreError):
    """Пользователь отменил скачивание."""


def ipatool_path():
    exe = ROOT / "bin" / ("ipatool.exe" if sys.platform == "win32" else "ipatool")
    if not exe.exists():
        raise StoreError("Не найден ipatool. Запустите start.bat (или python app/setup_tools.py)")
    return str(exe)


def _passphrase():
    """Ключ для файлового хранилища ipatool (на Windows нет системной связки ключей)."""
    key = DATA / "keychain.key"
    if not key.exists():
        DATA.mkdir(parents=True, exist_ok=True)
        key.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    return key.read_text(encoding="utf-8").strip()


def _ipatool_env(home=None):
    """Окружение для ipatool: его домашняя папка — IPATOOL_HOME (или home), а не общая папка пользователя."""
    home = Path(home or IPATOOL_HOME)
    home.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    # На macOS сессия ipatool лежит в системной связке ключей, а не в общем файле, и HOME трогать нельзя:
    # от него зависит доступ к связке. На Windows и Linux — файловое хранилище в своей папке.
    if sys.platform == "win32":
        drive, rest = os.path.splitdrive(str(home))
        # ipatool на Windows смотрит только на HOMEDRIVE+HOMEPATH; USERPROFILE/HOME — для остальных программ
        env.update(HOMEDRIVE=drive, HOMEPATH=rest, USERPROFILE=str(home), HOME=str(home))
    elif sys.platform != "darwin":
        env["HOME"] = str(home)
    return env


SESSION_FILES = ("account", "cookies", "kbsync-v1")


def _migrate_session():
    """Windows, до 1.4.1: сессия «Возврата» лежала в общем ~/.ipatool. Переносим её в свою папку, если она
    открывается нашим ключом; чужую (другой программы) не трогаем — тогда «Возврат» попросит войти."""
    marker = DATA / "session-migrated"
    if sys.platform != "win32" or marker.exists():
        return
    shared = Path(os.environ.get("HOMEDRIVE", "") + os.environ.get("HOMEPATH", "")) / ".ipatool"
    own = IPATOOL_HOME / ".ipatool"
    try:
        if (shared / "account").exists() and not (own / "account").exists() and shared != own:
            own.mkdir(parents=True, exist_ok=True)
            for name in SESSION_FILES:
                if (shared / name).exists():
                    shutil.copy2(shared / name, own / name)
            try:
                _run(["auth", "info"], timeout=60)
            except StoreError:  # не наш ключ — сессия чужая
                for name in SESSION_FILES:
                    (own / name).unlink(missing_ok=True)
    finally:
        DATA.mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="utf-8")


def _run(args, timeout=600, cancel=None):
    cmd =[ipatool_path(), *args, "--format", "json", "--non-interactive", "--keychain-passphrase", _passphrase()]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                         errors="replace", creationflags=NO_WINDOW, env=_ipatool_env())
    deadline = time.monotonic() + timeout
    while True:  # ждём кусками, чтобы скачивание можно было прервать кнопкой «Отменить»
        try:
            stdout, stderr = p.communicate(timeout=0.5)
            break
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_set():
                p.kill()
                p.communicate()
                raise Canceled("Отменено")
            if time.monotonic() > deadline:
                p.kill()
                p.communicate()
                raise StoreError("App Store не ответил вовремя, попробуйте ещё раз")
    events = []
    for line in (stdout + "\n" + stderr).splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
    result = next((e for e in reversed(events) if "success" in e), {})
    # при нужном 2FA ipatool завершается с кодом 0 и лишь пишет сообщение — успех только при success: true
    if p.returncode != 0 or result.get("success") is not True:
        raise _error(events, stdout + stderr)
    return result


def _error(events, raw):
    text = " | ".join(str(e.get("error") or e.get("message") or "") for e in events) or raw
    t = text.lower()
    if "auth code is required" in t or "2fa code is required" in t:
        return NeedCode("Введите код подтверждения, который пришёл на ваши устройства Apple")
    if "2fa code must" in t:
        return NeedCode("Код должен состоять из 6 цифр")
    if "invalid credentials" in t or "-5000" in t or "badlogin" in t:
        return StoreError("Неверный Apple ID или пароль")
    if "account is disabled" in t:
        return StoreError("Apple ID заблокирован")
    if "not logged in" in t or "failed to get account" in t:
        return NotLoggedIn("Сначала войдите в Apple ID")
    if "license is required" in t or "license required" in t or "9610" in t:
        return StoreError("Этого приложения нет в истории покупок этого Apple ID")
    if "paid app" in t:
        return StoreError("Платное приложение: его можно установить, только если оно уже куплено")
    if "temporarily unavailable" in t or "2059" in t:
        return StoreError("Приложение недоступно для этого Apple ID (регион или удаление)")
    if any(m in t for m in NETWORK_MARKERS):
        return NetworkError(NETWORK_HINT)
    lines = [l for l in text.strip().splitlines() if l.strip()]
    return StoreError(lines[-1][:500] if lines else "Неизвестная ошибка App Store")


# ---------- аккаунт ----------

def account_info():
    _migrate_session()
    try:
        r = _run(["auth", "info"], timeout=60)
    except StoreError:
        return None
    return {"email": r.get("email", ""), "name": (r.get("name") or "").strip()}


LOGIN_ATTEMPTS = 3
LOGIN_RETRY_PAUSE = 5  # сек


def login(email, password, code=""):
    args = ["auth", "login", "--email", email, "--password", password]
    if code:
        args += ["--auth-code", code]
    for attempt in range(LOGIN_ATTEMPTS):  # сетевой сбой у Apple часто проходит за секунды — повторяем сами
        try:
            r = _run(args, timeout=900)  # первый вход ipatool готовит эмулятор — может занять пару минут
            break
        except NetworkError:
            if attempt == LOGIN_ATTEMPTS - 1:
                raise
            time.sleep(LOGIN_RETRY_PAUSE)
    return {"email": r.get("email", email), "name": (r.get("name") or "").strip()}


def logout():
    try:
        _run(["auth", "revoke"], timeout=60)
    except StoreError:
        pass


# ---------- скачивание ----------

def download(app_id, dest_dir, progress=None, allow_purchase=False, version_id=None, cancel=None):
    """Скачивает IPA (уже с sinf и iTunesMetadata). Возвращает путь к файлу.
    version_id — externalVersionId из list_versions; без него берётся последняя версия."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    args = ["download", "--app-id", str(app_id), "--output", str(dest), "--platform", "iphone"]
    if version_id:
        args += ["--external-version-id", str(version_id)]
    if allow_purchase:
        args.append("--purchase")

    stop = threading.Event()

    def watch():  # ipatool не печатает прогресс в неинтерактивном режиме — смотрим на размер файла
        while not stop.wait(0.7):
            files = [f for f in dest.iterdir() if f.is_file()]
            if files and progress:
                progress(max(f.stat().st_size for f in files))

    t = threading.Thread(target=watch, daemon=True)
    t.start()
    try:
        r = _run(args, timeout=3600, cancel=cancel)
    finally:
        stop.set()
        t.join()
    path = r.get("output")
    if not path or not Path(path).exists():
        ipas = sorted(dest.glob("*.ipa"), key=lambda f: f.stat().st_mtime)
        if not ipas:
            raise StoreError("ipatool не сообщил, куда сохранил файл")
        path = str(ipas[-1])
    return path


# ---------- версии ----------

def list_versions(app_id):
    """externalVersionId всех версий, от новых к старым."""
    r = _run(["list-versions", "--app-id", str(app_id), "--platform", "iphone"], timeout=300)
    ids = [str(v) for v in r.get("externalVersionIdentifiers") or []]
    return ids[::-1]  # Apple отдаёт от старых к новым


def version_metadata(app_id, version_id):
    r = _run(["get-version-metadata", "--app-id", str(app_id), "--external-version-id", str(version_id),
              "--platform", "iphone"], timeout=300)
    return {"id": str(version_id), "version": r.get("displayVersion") or "?", "date": (r.get("releaseDate") or "")[:10]}


def ipa_requirements(path):
    """Минимальная iOS и поддерживаемые устройства из Info.plist внутри IPA."""
    with zipfile.ZipFile(path) as z:
        name = next((n for n in z.namelist() if len(PurePosixPath(n).parts) == 3
                     and n.startswith("Payload/") and n.endswith(".app/Info.plist")), None)
        if not name:
            return {}
        info = plistlib.loads(z.read(name))
    return {"minimumOS": str(info.get("MinimumOSVersion") or ""), "families": info.get("UIDeviceFamily") or [],
            "version": str(info.get("CFBundleShortVersionString") or ""), "name": info.get("CFBundleDisplayName")
            or info.get("CFBundleName") or "", "bundleId": str(info.get("CFBundleIdentifier") or "")}


def version_tuple(v):
    return tuple(int(x) for x in str(v).split(".")[:3] if x.isdigit()) or (0,)


# ---------- публичный поиск (iTunes Search API) ----------

def search(term, limit=20):
    # Поиск по российской витрине Apple сейчас отвечает 403 — тогда ищем в других
    for country in ("ru", "kz", "us"):
        r = requests.get("https://itunes.apple.com/search", headers=WEB_HEADERS, timeout=20, params={
            "term": term, "entity": "software", "country": country, "limit": limit})
        if r.ok:
            return [_short(x) for x in _json(r).get("results", [])]
    raise StoreError("Поиск App Store временно недоступен, попробуйте через минуту или введите ID")


def download_size(app_id):
    """Размер IPA последней версии по данным App Store — для процентов скачивания. Удалённые приложения
    часто остались в магазинах других стран; если нигде нет — None, тогда прогресс только в мегабайтах."""
    for country in ("ru", "us", "kz"):
        try:
            r = requests.get("https://itunes.apple.com/lookup", headers=WEB_HEADERS, timeout=10,
                             params={"id": app_id, "country": country})
            res = r.json().get("results", []) if r.ok else []
        except (requests.RequestException, ValueError):
            continue
        if res and res[0].get("fileSizeBytes"):
            return int(res[0]["fileSizeBytes"])
    return None


def lookup(app_id, country="ru"):
    r = requests.get("https://itunes.apple.com/lookup", headers=WEB_HEADERS, params={"id": app_id, "country": country}, timeout=20)
    res = _json(r).get("results", [])
    return _short(res[0]) if res else None


def _json(r):
    try:
        return r.json()
    except ValueError:
        raise StoreError("Поиск App Store временно недоступен, попробуйте через минуту или введите ID")


def _short(x):
    return {
        "id": x.get("trackId"),
        "name": x.get("trackName"),
        "bundleId": x.get("bundleId"),
        "icon": x.get("artworkUrl100"),
        "seller": x.get("sellerName"),
        "version": x.get("version"),
        "price": x.get("price", 0),
    }
