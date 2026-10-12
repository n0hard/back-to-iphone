"""Работа с iPhone по USB через pymobiledevice3.

Нужна служба usbmuxd: на Windows её ставит «Apple Devices» или iTunes, на macOS она встроена,
на Linux это пакет usbmuxd.

Список устройств и установленных приложений берётся прямо в этом процессе: страница опрашивает
iPhone каждые 8 секунд, и запуск отдельного процесса на каждый опрос (в сборке — копии всей
программы) зря грузил процессор. Установка по-прежнему идёт отдельным процессом: она долгая,
и её сбой не должен ронять программу.
"""
import asyncio
import os
import plistlib
import subprocess
import sys

ENV = {**os.environ, "PYTHONWARNINGS": "ignore", "NO_COLOR": "1", "PYTHONIOENCODING": "utf-8"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# в собранной программе pymobiledevice3 вызывается через её же исполняемый файл (см. main.py)
PMD3 = [sys.executable, "--pmd3"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "pymobiledevice3"]


DRIVER_HINT = {
    "win32": "Не найден драйвер Apple. Установите «Apple Devices» из Microsoft Store или iTunes",
    "darwin": "macOS не видит iPhone. Переподключите кабель и разблокируйте iPhone",
}.get(sys.platform, "Не запущена служба usbmuxd. Установите её (sudo apt install usbmuxd или аналог "
                   "для вашего дистрибутива) и переподключите iPhone")
TRUST_HINT = "Разблокируйте iPhone и нажмите «Доверять этому компьютеру», затем повторите"


class DeviceError(Exception):
    pass


def _run(args, timeout):
    p = subprocess.run(
        [*PMD3, "--no-color", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=ENV, timeout=timeout, creationflags=NO_WINDOW,
    )
    return p.returncode, p.stdout, p.stderr


def _call(coro_fn, *args):
    """Выполняет асинхронную функцию pymobiledevice3 и переводит её ошибки в понятные."""
    try:
        return asyncio.run(coro_fn(*args))
    except (DeviceError, ImportError):  # ImportError — неполная сборка, её должна поймать самопроверка
        raise
    except Exception as e:
        raise DeviceError(_explain(f"{type(e).__name__}: {e}")) from e


# ---------- список устройств ----------

async def _list_devices():
    from pymobiledevice3 import usbmux
    from pymobiledevice3.lockdown import create_using_usbmux

    found = []
    for dev in await usbmux.list_devices():
        if not dev.is_usb:
            continue
        # то же, что `pymobiledevice3 usbmux list --usb`; соединение закрываем сразу
        async with await create_using_usbmux(dev.serial, autopair=False, connection_type=dev.connection_type) as ld:
            found.append(ld.short_info)
    return found


def list_devices():
    items = _call(_list_devices)
    return [{
        "udid": d.get("UniqueDeviceID") or d.get("Identifier"),
        "name": d.get("DeviceName") or "iPhone",
        "model": d.get("ProductType") or "",
        "ios": d.get("ProductVersion") or "",
    } for d in items]


# ---------- установленные приложения ----------

APP_ATTRIBUTES = ["CFBundleIdentifier", "CFBundleShortVersionString", "CFBundleDisplayName", "CFBundleName",
                  "iTunesMetadata"]


async def _installed_apps(udid):
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.installation_proxy import InstallationProxyService

    async with await create_using_usbmux(udid, autopair=False, connection_type="USB") as ld:
        async with InstallationProxyService(lockdown=ld) as proxy:
            return await proxy.lookup({"ApplicationType": "User", "ReturnAttributes": APP_ATTRIBUTES}) or {}


def installed_apps(udid):
    """{bundleId: {"version", "name", "appId"}} для приложений пользователя. appId (App Store ID) берётся
    из iTunesMetadata, если iPhone её отдал; иначе None — тогда его знает только журнал установок."""
    result = {}
    for bundle_id, info in _call(_installed_apps, udid).items():
        app_id = None
        meta = info.get("iTunesMetadata")
        if isinstance(meta, (bytes, bytearray)):
            try:
                app_id = int(plistlib.loads(bytes(meta)).get("itemId") or 0) or None
            except Exception:
                app_id = None
        elif isinstance(meta, dict):
            app_id = int(meta.get("itemId") or 0) or None
        result[bundle_id] = {"version": str(info.get("CFBundleShortVersionString") or ""),
                             "name": info.get("CFBundleDisplayName") or info.get("CFBundleName") or bundle_id,
                             "appId": app_id}
    return result


# ---------- установка ----------

def install(udid, ipa_path):
    args = ["apps", "install", ipa_path]
    if udid:
        args += ["--udid", udid]
    code, out, err = _run(args, timeout=1800)
    if code != 0:
        raise DeviceError(_explain(err or out))


def _explain(text):
    t = text.lower()
    if any(k in t for k in ("pairing", "not paired", "notpaired", "passwordprotected", "passwordrequired",
                            "user denied", "nottrusted")):
        return TRUST_HINT
    if "usbmux" in t and ("connect" in t or "refused" in t):
        return DRIVER_HINT
    if "applicationverificationfailed" in t:
        return "iPhone отклонил приложение: подпись не прошла проверку (вероятно, IPA скачан с другим Apple ID)"
    if "devicefamily" in t or "minimumosversion" in t or "requires a newer" in t:
        return "Приложение не поддерживает эту модель или версию iOS"
    lines = [l for l in text.strip().splitlines() if l.strip()]
    return lines[-1] if lines else "Неизвестная ошибка устройства"
