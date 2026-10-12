"""Точка входа собранной программы: окно приложения поверх локального сервера.

Windows и macOS — своё окно (pywebview: WebView2 / WKWebView). Linux — вкладка браузера: встроить
WebKitGTK или Qt в переносимую сборку слишком тяжело, поэтому программа сама завершается, когда
страница перестаёт выходить на связь (вкладку закрыли).
"""
import sys

if len(sys.argv) > 1 and sys.argv[1] == "--pmd3":
    # режим CLI pymobiledevice3 — device.py запускает программу так, чтобы не требовать Python на машине
    sys.argv = ["pymobiledevice3", *sys.argv[2:]]
    from pymobiledevice3.__main__ import main
    sys.exit(main())

import os
import threading
import time
import webbrowser

import server

IDLE_EXIT = 300  # сек; фоновые вкладки браузер будит не чаще раза в минуту, поэтому запас большой


def run():
    srv, url = server.create(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    if sys.platform != "linux" and os.environ.get("VOZVRAT_BROWSER") != "1":
        try:
            import webview
            webview.create_window("Возврат", url, width=960, height=900, min_size=(420, 600))
            webview.start()
            return
        except Exception:
            pass  # нет WebView — работаем через браузер
    webbrowser.open(url)
    print(f"Возврат открыт в браузере: {url}\nПрограмма завершится сама через несколько минут после закрытия вкладки.")
    while server.idle_seconds() < IDLE_EXIT:
        time.sleep(5)


def smoke():
    """Проверка сборки в CI: сервер отдаёт страницу и каталог, внутри есть рабочие ipatool и pymobiledevice3."""
    import json
    import subprocess
    import urllib.request

    import device
    import store

    srv, url = server.create(0, check_updates=False)  # в CI проверка обновлений не нужна
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    page = urllib.request.urlopen(url).read().decode()
    assert server.TOKEN in page, "страница без токена"
    req = urllib.request.Request(url + "api/catalog", headers={"X-Token": server.TOKEN})
    apps = json.loads(urllib.request.urlopen(req).read())["apps"]
    assert len(apps) > 100, "каталог пуст"
    ipatool = subprocess.run([store.ipatool_path(), "--version"], capture_output=True, text=True, timeout=60)
    assert ipatool.returncode == 0, ipatool.stderr
    for cmd in (["usbmux", "list"], ["apps", "install"]):  # ровно те команды pymobiledevice3, что вызывает device.py
        pmd3 = subprocess.run([*device.PMD3, "--no-color", *cmd, "--help"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=device.ENV, timeout=120)
        assert pmd3.returncode == 0 and "Usage" in pmd3.stdout, f"{' '.join(cmd)}: {pmd3.stderr[-500:]}"
    # список iPhone теперь берётся внутри программы: модули pymobiledevice3 должны быть в сборке.
    # iPhone на машине сборки нет, а службы usbmuxd может не быть — ошибка устройства здесь нормальна,
    # а вот ImportError означает, что сборка неполная
    try:
        device.list_devices()
    except device.DeviceError:
        pass
    from pymobiledevice3.services.installation_proxy import InstallationProxyService  # noqa: F401
    import updater
    assert updater.asset_name(), "не определён файл обновления"
    print(f"smoke ok: {sys.platform}, {len(apps)} apps, {ipatool.stdout.strip()}, update asset {updater.asset_name()}")


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        try:
            smoke()
        except BaseException as e:  # без этого оконная сборка на Windows покажет диалог с ошибкой и CI зависнет
            print(f"smoke failed: {type(e).__name__}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        run()
