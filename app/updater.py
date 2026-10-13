"""Обновление самой программы: проверка новой версии на GitHub, скачивание и установка в один клик.

Обновления бывают обычные и обязательные. Каждый релиз содержит update.json с номером версии
и MIN_VERSION — самой старой версией, которой ещё можно пользоваться (см. version.py):
- версия старее MIN_VERSION — обязательное обновление: программа не работает, пока её не обновят;
- версия новее MIN_VERSION, но не последняя — обычное: сверху страницы предложение обновиться.
Если проверить не удалось (нет сети, GitHub недоступен), программа не работает, пока проверка
не пройдёт: на экране кнопка «Повторить». Запуск из исходников (start.bat и т. п.) не блокируется:
там обновление делается через git.

Установка по системам:
- Windows — тихий запуск VozvratSetup.exe поверх установленной программы; инсталлятор сам
  перезапускает её (см. [Run] в installer.iss);
- macOS — новый Vozvrat.app из .dmg подменяет текущий после выхода программы;
- Linux — AppImage подменяется файлом рядом, архивная сборка — папкой рядом.
"""
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path

import requests

import store
from version import REPO, VERSION

FROZEN = getattr(sys, "frozen", False)
UPDATE_DIR = store.DATA / "update"
RECHECK = 6 * 3600  # раз в 6 часов проверяем снова, если программа долго открыта
HEADERS = {"User-Agent": f"Vozvrat/{VERSION}"}

_lock = threading.Lock()
_state = {"status": "checking", "current": VERSION, "latest": None, "progress": None, "error": None}


class UpdateError(Exception):
    pass


def state():
    with _lock:
        return dict(_state)


def allowed():
    """Можно ли пользоваться программой: последняя версия, версия с необязательным обновлением
    или запуск из исходников."""
    return state()["status"] in ("current", "available", "source")


def _set(**kw):
    with _lock:
        _state.update(kw)


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:3]) or (0,)


# ---------- какая версия последняя ----------

def latest_info():
    """(последняя версия, MIN_VERSION) из update.json последнего релиза. Файл берётся по обычной ссылке
    на скачивание — у неё нет лимита запросов, как у API GitHub (60 в час на IP, а у мобильных
    операторов один IP на многих). В релизах до 1.4.0 файла нет — тогда номер берём по тегу и считаем
    обновление обязательным, как и работали те версии."""
    try:
        r = requests.get(f"https://github.com/{REPO}/releases/latest/download/update.json", headers=HEADERS,
                         timeout=15)
        if r.ok:
            data = r.json()
            version, minimum = str(data["version"]), str(data.get("min_version") or data["version"])
            if re.fullmatch(r"\d+(\.\d+)*", version) and re.fullmatch(r"\d+(\.\d+)*", minimum):
                return version, minimum
    except (requests.RequestException, ValueError, KeyError, TypeError):
        pass
    latest = latest_version()
    return latest, latest


def latest_version():
    """Номер последнего релиза по тегу. Сначала через переадресацию страницы releases/latest (без лимита
    запросов), затем через API GitHub."""
    errors = []
    try:
        r = requests.head(f"https://github.com/{REPO}/releases/latest", headers=HEADERS, timeout=15,
                          allow_redirects=False)
        m = re.search(r"/releases/tag/v?([\d.]+)$", r.headers.get("Location", ""))
        if m:
            return m.group(1)
        errors.append(f"releases/latest: HTTP {r.status_code}")
    except requests.RequestException as e:
        errors.append(f"releases/latest: {type(e).__name__}")
    try:
        r = requests.get(f"https://api.github.com/repos/{REPO}/releases/latest", headers=HEADERS, timeout=15)
        if r.ok:
            return r.json()["tag_name"].lstrip("v")
        errors.append(f"API: HTTP {r.status_code}")
    except (requests.RequestException, ValueError, KeyError) as e:
        errors.append(f"API: {type(e).__name__}")
    raise UpdateError("Не удалось проверить обновления (" + "; ".join(errors) + ")")


def check():
    """Проверяет версию и выставляет состояние. При первой проверке ошибка блокирует программу."""
    first = state()["status"] in ("checking", "failed")
    if first:
        _set(status="checking", error=None)
    try:
        latest = minimum = None
        for attempt in range(3):  # пара повторов, чтобы не блокировать из-за мимолётного сбоя сети
            try:
                latest, minimum = latest_info()
                break
            except UpdateError:
                if attempt == 2:
                    raise
                time.sleep(2)
    except UpdateError as e:
        if not FROZEN:
            _set(status="source", error=None)
        elif first:
            _set(status="failed", error=f"{e}. Проверьте подключение к интернету и нажмите «Повторить».")
        return state()  # при повторной проверке в фоне сбой сети не мешает работать
    newer = version_tuple(latest) > version_tuple(VERSION)
    mandatory = newer and version_tuple(VERSION) < version_tuple(minimum)
    if not FROZEN:
        _set(status="source", latest=latest, mandatory=mandatory)
    elif state()["status"] not in ("downloading", "installing"):
        status = "outdated" if mandatory else "available" if newer else "current"
        _set(status=status, latest=latest, mandatory=mandatory, error=None)
    return state()


def start_background_checks():
    def loop():
        check()
        while True:
            time.sleep(RECHECK)
            if state()["status"] in ("current", "available"):  # вдруг вышло обязательное обновление
                check()
    threading.Thread(target=loop, daemon=True).start()


# ---------- скачивание и установка ----------

def asset_name():
    if sys.platform == "win32":
        return "VozvratSetup.exe"
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    if sys.platform == "darwin":
        return f"Vozvrat-macOS-{arch}.dmg"
    return f"Vozvrat-Linux-{arch}.AppImage" if os.environ.get("APPIMAGE") else f"Vozvrat-Linux-{arch}.tar.gz"


def _expected_sha256(tag, name):
    """SHA-256 файла релиза. Сначала из SHA256SUMS.txt в самом релизе (обычная ссылка на скачивание,
    без лимита запросов), затем из API GitHub, который считает суммы сам. Если не вышло ни то,
    ни другое — None, и целостность обеспечивает только HTTPS."""
    try:
        r = requests.get(f"https://github.com/{REPO}/releases/download/{tag}/SHA256SUMS.txt", headers=HEADERS,
                         timeout=15)
        if r.ok:
            for line in r.text.splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1].lstrip("*") == name and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
                    return parts[0].lower()
    except requests.RequestException:
        pass
    try:
        r = requests.get(f"https://api.github.com/repos/{REPO}/releases/tags/{tag}", headers=HEADERS, timeout=15)
        if not r.ok:
            return None
        for a in r.json().get("assets", []):
            if a.get("name") == name and str(a.get("digest", "")).startswith("sha256:"):
                return a["digest"].split(":", 1)[1].lower()
    except (requests.RequestException, ValueError):
        pass
    return None


def _download(latest):
    name, tag = asset_name(), f"v{latest}"
    shutil.rmtree(UPDATE_DIR, ignore_errors=True)
    UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    path = UPDATE_DIR / name
    expected = _expected_sha256(tag, name)
    url = f"https://github.com/{REPO}/releases/download/{tag}/{name}"
    try:
        with requests.get(url, headers=HEADERS, stream=True, timeout=60) as r:
            if r.status_code == 404:
                raise UpdateError("Файлы новой версии ещё загружаются на GitHub. Повторите через пару минут")
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or 0)
            done, sha = 0, hashlib.sha256()
            with open(path, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
                    sha.update(chunk)
                    done += len(chunk)
                    _set(progress=done / total if total else None,
                         error=None, detail=f"{done / 1048576:.0f} из {total / 1048576:.0f} МБ" if total else
                         f"{done / 1048576:.0f} МБ")
    except requests.RequestException as e:
        raise UpdateError(f"Не удалось скачать обновление: {type(e).__name__}. Проверьте интернет и повторите")
    if total and done != total:
        raise UpdateError("Обновление скачалось не полностью. Повторите")
    if expected and sha.hexdigest() != expected:
        path.unlink(missing_ok=True)
        raise UpdateError("Файл обновления повреждён (не совпала контрольная сумма). Повторите")
    return path


def _clean_env():
    """Окружение для новой версии: без служебных переменных этого процесса, чтобы она стартовала
    как самостоятельная программа, а не как дочерний процесс старой."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("_PYI_") and k not in ("PYTHONNET_RUNTIME", "VOZVRAT_WINDOW_ATTEMPT")}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def _spawn_detached(cmd):
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(cmd, creationflags=flags, close_fds=True, env=_clean_env())
    else:
        subprocess.Popen(cmd, start_new_session=True, close_fds=True, env=_clean_env(),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _install_windows(path):
    # Инсталлятор помнит папку и ярлыки прошлой установки. /CLOSEAPPLICATIONS — на случай, если
    # программа ещё не успела закрыться; /FORCECLOSEAPPLICATIONS — закрыть её принудительно, если
    # вежливо не вышло: иначе тихий инсталлятор молча завершается, ничего не поставив.
    # После тихой установки он сам запускает новую версию.
    _spawn_detached([str(path), "/SILENT", "/SP-", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                     "/FORCECLOSEAPPLICATIONS"])


def _install_macos(dmg):
    app = Path(sys.executable).resolve().parents[2]  # …/Vozvrat.app/Contents/MacOS/Vozvrat
    if app.suffix != ".app":
        raise UpdateError("Не удалось найти Vozvrat.app")
    if not os.access(app.parent, os.W_OK):
        raise UpdateError(f"Нет прав на запись в папку «{app.parent}». Скачайте новую версию вручную или "
                          "переместите программу в «Программы»")
    mount = Path(tempfile.mkdtemp(prefix="vozvrat-dmg-"))
    staged = UPDATE_DIR / "Vozvrat.app"
    try:
        subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", str(mount),
                        str(dmg)], check=True, capture_output=True, timeout=300)
        try:
            shutil.rmtree(staged, ignore_errors=True)
            subprocess.run(["ditto", str(mount / "Vozvrat.app"), str(staged)], check=True, capture_output=True,
                           timeout=600)
        finally:
            subprocess.run(["hdiutil", "detach", str(mount), "-force"], capture_output=True, timeout=120)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        raise UpdateError(f"Не удалось распаковать обновление: {type(e).__name__}")
    # Подмена — уже после выхода программы: работающий бандл заменять нельзя. Если что-то пошло
    # не так, возвращаем старую версию на место.
    script = (f'while kill -0 {os.getpid()} 2>/dev/null; do sleep 0.3; done; '
              f'APP="{app}"; rm -rf "$APP.old"; mv "$APP" "$APP.old" && '
              f'{{ mv "{staged}" "$APP" || mv "$APP.old" "$APP"; }}; rm -rf "$APP.old"; '
              f'xattr -cr "$APP" 2>/dev/null; open "$APP"')
    _spawn_detached(["/bin/sh", "-c", script])


def _install_linux(path):
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        target = Path(appimage)
        if not os.access(target.parent, os.W_OK):
            raise UpdateError(f"Нет прав на запись в папку «{target.parent}»")
        new = target.with_name(target.name + ".new")
        shutil.move(str(path), new)
        new.chmod(0o755)
        os.replace(new, target)  # работающий AppImage заменять можно: старый файл живёт, пока открыт
        _spawn_detached([str(target)])
        return
    appdir = Path(sys.executable).resolve().parent  # …/Vozvrat/Vozvrat
    parent = appdir.parent
    if not os.access(parent, os.W_OK):
        raise UpdateError(f"Нет прав на запись в папку «{parent}»")
    stage, old = parent / ".vozvrat-update", parent / ".vozvrat-old"
    shutil.rmtree(stage, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)
    with tarfile.open(path) as tar:
        try:
            tar.extractall(stage, filter="data")  # безопасная распаковка: без путей наружу и ссылок за пределы
        except TypeError:  # Python без параметра filter (до 3.11.4)
            for m in tar.getmembers():
                if m.name.startswith(("/", "..")) or ".." in Path(m.name).parts:
                    raise UpdateError("Архив обновления повреждён")
            tar.extractall(stage)
    os.rename(appdir, old)  # работающую папку на Linux переименовывать можно
    try:
        os.rename(stage / "Vozvrat", appdir)
    except OSError:
        os.rename(old, appdir)
        raise UpdateError("Не удалось заменить папку программы")
    _spawn_detached([str(appdir / "Vozvrat")])


def _failed(message):
    # необязательное обновление не удалось — программа продолжает работать, ошибка видна на плашке;
    # обязательное — экран обновления остаётся с кнопкой «Повторить»
    _set(status="error" if state().get("mandatory", True) else "available", error=message, progress=None)


def _apply(latest):
    try:
        _set(status="downloading", progress=0, error=None, detail="")
        path = _download(latest)
        _set(status="installing", progress=None, detail="")
        {"win32": _install_windows, "darwin": _install_macos}.get(sys.platform, _install_linux)(path)
    except UpdateError as e:
        _failed(str(e))
        return
    except Exception as e:
        _failed(f"Не удалось обновить: {type(e).__name__}: {e}")
        return
    _set(status="restarting")
    time.sleep(1.5)  # даём странице получить ответ «перезапуск»
    os._exit(0)


def start_update():
    st = state()
    if not FROZEN:
        raise UpdateError("Программа запущена из исходников: обновите её через git pull")
    if st["status"] not in ("outdated", "available", "error") or not st["latest"]:
        raise UpdateError("Обновление не требуется")
    threading.Thread(target=_apply, args=(st["latest"],), daemon=True).start()


def cleanup():
    """Убирает остатки прошлого обновления (скачанный инсталлятор, старую папку на Linux)."""
    shutil.rmtree(UPDATE_DIR, ignore_errors=True)
    if FROZEN and sys.platform.startswith("linux") and not os.environ.get("APPIMAGE"):
        parent = Path(sys.executable).resolve().parent.parent
        for name in (".vozvrat-old", ".vozvrat-update"):
            shutil.rmtree(parent / name, ignore_errors=True)
