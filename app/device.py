"""Работа с iPhone по USB через pymobiledevice3 (нужен драйвер Apple: iTunes или «Apple Devices»)."""
import json
import os
import subprocess
import sys

ENV = {**os.environ, "PYTHONWARNINGS": "ignore", "NO_COLOR": "1", "PYTHONIOENCODING": "utf-8"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# в собранном .exe pymobiledevice3 вызывается через сам exe (см. main.py)
PMD3 = [sys.executable, "--pmd3"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "pymobiledevice3"]


class DeviceError(Exception):
    pass


def _run(args, timeout):
    p = subprocess.run(
        [*PMD3, "--no-color", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=ENV, timeout=timeout, creationflags=NO_WINDOW,
    )
    return p.returncode, p.stdout, p.stderr


def list_devices():
    code, out, err = _run(["usbmux", "list", "--usb"], timeout=30)
    if code != 0:
        raise DeviceError(_explain(err or out))
    start = out.find("[")
    try:
        items = json.loads(out[start:]) if start >= 0 else []
    except json.JSONDecodeError:
        items = []
    return [{
        "udid": d.get("UniqueDeviceID") or d.get("Identifier") or d.get("SerialNumber"),
        "name": d.get("DeviceName") or "iPhone",
        "model": d.get("ProductType", ""),
        "ios": d.get("ProductVersion", ""),
    } for d in items]


def install(udid, ipa_path):
    args = ["apps", "install", ipa_path]
    if udid:
        args += ["--udid", udid]
    code, out, err = _run(args, timeout=1800)
    if code != 0:
        raise DeviceError(_explain(err or out))


def _explain(text):
    t = text.lower()
    if "pairing" in t or "not paired" in t or "passwordprotected" in t or "user denied" in t:
        return "Разблокируйте iPhone и нажмите «Доверять этому компьютеру», затем повторите"
    if "usbmux" in t and ("connect" in t or "refused" in t):
        return "Не найден драйвер Apple. Установите «Apple Devices» из Microsoft Store или iTunes"
    if "applicationverificationfailed" in t:
        return "iPhone отклонил приложение: подпись не прошла проверку (вероятно, IPA скачан с другим Apple ID)"
    if "devicefamily" in t or "minimumosversion" in t or "requires a newer" in t:
        return "Приложение не поддерживает эту модель или версию iOS"
    lines = [l for l in text.strip().splitlines() if l.strip()]
    return lines[-1] if lines else "Неизвестная ошибка устройства"
