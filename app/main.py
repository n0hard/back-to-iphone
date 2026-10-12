"""Точка входа собранной программы: окно приложения поверх локального сервера.

Windows и macOS — только своё окно (pywebview: WebView2 / WKWebView): если открыть его не удалось,
программа пробует ещё раз, а потом показывает системное сообщение с причиной — во вкладку браузера
она не уходит. Linux — вкладка браузера: встроить WebKitGTK или Qt в переносимую сборку слишком
тяжело, поэтому программа сама завершается, когда страница перестаёт выходить на связь (вкладку закрыли).
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
WINDOW_ATTEMPTS = 3  # сколько раз пробовать открыть окно, прежде чем сообщить об ошибке
WINDOW_RETRY_DELAY = 3  # сек


def relaunch_for_window(attempt):
    """Запускает программу заново, чтобы ещё раз попробовать открыть окно.

    Сразу после установки обновления .NET иногда не может загрузить свежий Python.Runtime.dll
    («Failed to resolve Python.Runtime.Loader.Initialize»), а через несколько секунд тот же файл
    загружается: видимо, его ещё держит антивирус. Повторить можно только в новом процессе —
    после неудачи pythonnet внутри процесса остаётся в нерабочем состоянии.
    """
    import subprocess

    env = dict(os.environ)
    env.pop("PYTHONNET_RUNTIME", None)  # pywebview выставляет её после неудачи — новому процессу она не нужна
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"  # новый процесс — самостоятельная программа, а не дочерний
    env["VOZVRAT_WINDOW_ATTEMPT"] = str(attempt)
    time.sleep(WINDOW_RETRY_DELAY)
    flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if sys.platform == "win32" else 0
    subprocess.Popen([sys.executable], env=env, creationflags=flags, close_fds=True,
                     start_new_session=sys.platform != "win32")
    os._exit(0)


def show_error(text):
    """Системное окно с ошибкой — когда своё окно программы открыть не удалось."""
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, "Возврат", 0x10)  # MB_ICONERROR
        elif sys.platform == "darwin":
            import subprocess
            script = 'display alert "Возврат" message (system attribute "VOZVRAT_ERROR") as critical'
            subprocess.run(["osascript", "-e", script], env={**os.environ, "VOZVRAT_ERROR": text}, timeout=600)
    except Exception:
        pass
    print(text, file=sys.stderr)


def run_in_browser():
    """Linux: своего окна нет — интерфейс открывается во вкладке браузера."""
    srv, url = server.create(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    webbrowser.open(url)
    print(f"Возврат открыт в браузере: {url}\nПрограмма завершится сама через несколько минут после закрытия вкладки.")
    while server.idle_seconds() < IDLE_EXIT:
        time.sleep(5)


def run():
    if sys.platform.startswith("linux"):
        return run_in_browser()
    # Windows и macOS — только своё окно, без запасного варианта во вкладке браузера.
    # Номер попытки забираем из окружения сразу: иначе его унаследуют дочерние процессы, в том числе
    # инсталлятор обновления, и новая версия начала бы не с первой попытки
    attempt = int(os.environ.pop("VOZVRAT_WINDOW_ATTEMPT", None) or 1)
    os.environ.pop("PYINSTALLER_RESET_ENVIRONMENT", None)
    srv, url = server.create(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        import webview
        webview.create_window("Возврат", url, width=960, height=900, min_size=(420, 600))
        webview.start()
        return
    except Exception as e:
        if getattr(sys, "frozen", False) and attempt < WINDOW_ATTEMPTS:
            relaunch_for_window(attempt + 1)
        hint = ("Установите или обновите Microsoft Edge WebView2 Runtime "
                "(https://go.microsoft.com/fwlink/p/?LinkId=2124703) и запустите программу снова."
                if sys.platform == "win32" else "Перезапустите программу. Если не поможет — создайте issue на GitHub.")
        show_error(f"Не удалось открыть окно программы.\n\n{hint}\n\nПричина: {type(e).__name__}: {e}")
        os._exit(1)


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
