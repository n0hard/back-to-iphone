"""Точка входа .exe: окно приложения поверх локального сервера."""
import sys

if len(sys.argv) > 1 and sys.argv[1] == "--pmd3":
    # режим CLI pymobiledevice3 — device.py запускает exe так, чтобы не требовать Python на машине
    sys.argv = ["pymobiledevice3", *sys.argv[2:]]
    from pymobiledevice3.__main__ import main
    sys.exit(main())

import threading

import server


def run():
    srv, url = server.create(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        import webview
        webview.create_window("Возврат", url, width=960, height=900, min_size=(420, 600))
        webview.start()
    except Exception:
        import webbrowser
        webbrowser.open(url)
        threading.Event().wait()


if __name__ == "__main__":
    run()
