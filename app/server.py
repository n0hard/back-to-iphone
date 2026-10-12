"""Локальный сервер: интерфейс в браузере на 127.0.0.1, всё работает только на вашем компьютере."""
import collections
import json
import os
import re
import secrets
import shutil
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import device
import store

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))  # в .exe — папка с ресурсами
IPA_DIR = store.DATA / "ipa"
TOKEN = secrets.token_urlsafe(24)  # защищает API от запросов со сторонних сайтов

account = None  # {"email", "name"} — кэш `ipatool auth info`
jobs = {}  # id -> задача; порядок вставки = порядок добавления
queue = collections.deque()  # id задач, ждущих установки
lock = threading.Lock()
queue_ready = threading.Condition(lock)


def parse_app_id(text):
    m = re.search(r"id(\d{6,12})", str(text)) or re.fullmatch(r"\s*(\d{6,12})\s*", str(text))
    return int(m.group(1)) if m else None


# ---------- очередь установок ----------

ACTIVE = ("queued", "download", "install")


def enqueue(app_id, name, udid, allow_purchase, keep_ipa, version_id=None, version_label=None):
    with lock:
        for job in jobs.values():  # повторное нажатие не ставит приложение в очередь дважды
            if job["appId"] == app_id and job["stage"] in ACTIVE:
                return job["id"]
        job_id = uuid.uuid4().hex
        jobs[job_id] = {"id": job_id, "appId": app_id, "name": name, "stage": "queued", "message": "В очереди",
                        "progress": None, "done": False, "udid": udid, "purchase": allow_purchase, "keepIpa": keep_ipa,
                        "versionId": version_id, "versionLabel": version_label}
        queue.append(job_id)
        for old in [j for j in jobs if jobs[j]["done"]][:-50]:  # не копим бесконечную историю
            del jobs[old]
        queue_ready.notify()
        return job_id


def cancel(job_id):
    with lock:
        job = jobs.get(job_id)
        if not job or job_id not in queue:
            return False
        queue.remove(job_id)
        job.update(stage="canceled", done=True, message="Отменено")
        return True


def snapshot():
    with lock:
        position = {job_id: i + 1 for i, job_id in enumerate(queue)}
        return [{k: v for k, v in {**job, "position": position.get(job["id"])}.items() if k != "udid"}
                for job in jobs.values()]


def worker():
    while True:
        with lock:
            while not queue:
                queue_ready.wait()
            job = jobs[queue.popleft()]
        run_job(job)


def check_compatible(ipa, udid):
    """Не ставим то, что iPhone всё равно отклонит: понятная ошибка вместо ошибки installd."""
    req = store.ipa_requirements(ipa)
    if req.get("families") and 1 not in req["families"]:
        raise device.DeviceError("Эта версия приложения только для iPad")
    dev = next((d for d in device.list_devices() if d["udid"] == udid), None) if udid else None
    if dev and req.get("minimumOS") and store.version_tuple(dev["ios"]) < store.version_tuple(req["minimumOS"]):
        raise device.DeviceError(f"Версии {req.get('version') or ''} нужна iOS {req['minimumOS']} или новее, "
                                 f"а на iPhone iOS {dev['ios']}. Выберите более старую версию приложения")
    return req


def run_job(job):
    job_id, app_id, udid = job["id"], job["appId"], job["udid"]
    allow_purchase, keep_ipa = job["purchase"], job["keepIpa"]
    work = IPA_DIR / job_id

    def update(**kw):
        with lock:
            job.update(kw)

    def on_progress(size):
        update(message=f"Скачивание из App Store… {size / 1048576:.0f} МБ")

    try:
        update(stage="download", message="Запрос к App Store…")
        path = Path(store.download(app_id, work, on_progress, allow_purchase, job.get("versionId")))
        update(message="Проверка совместимости с iPhone…")
        req = check_compatible(path, udid)
        update(stage="install", message="Установка на iPhone… Не отключайте кабель и не блокируйте экран")
        device.install(udid, str(path))
        if keep_ipa:
            os.replace(path, IPA_DIR / path.name)
        update(stage="done", done=True, progress=1, message=f"Готово: {path.stem} установлено на iPhone"
               + f"\nВерсия {req.get('version') or '?'}"
               + (f", IPA сохранён: {IPA_DIR / path.name}" if keep_ipa else ""))
    except store.NotLoggedIn as e:
        global account
        account = None
        update(stage="error", done=True, error=str(e), relogin=True)
    except (store.StoreError, device.DeviceError) as e:
        update(stage="error", done=True, error=str(e))
    except Exception as e:
        traceback.print_exc()
        update(stage="error", done=True, error=f"{type(e).__name__}: {e}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------- версии приложений ----------

version_ids = {}  # app_id -> [externalVersionId], от новых к старым
version_meta = {}  # (app_id, version_id) -> {"id", "version", "date"}


def versions(app_id, offset, limit):
    if not app_id:
        raise store.StoreError("Некорректный App Store ID")
    if app_id not in version_ids:
        version_ids[app_id] = store.list_versions(app_id)
    ids = version_ids[app_id][offset:offset + limit]
    missing = [v for v in ids if (app_id, v) not in version_meta]
    with ThreadPoolExecutor(4) as pool:  # каждая версия — отдельный запрос к Apple
        for v, meta in zip(missing, pool.map(lambda v: _safe_meta(app_id, v), missing)):
            version_meta[(app_id, v)] = meta
    return {"total": len(version_ids[app_id]), "offset": offset,
            "versions": [version_meta[(app_id, v)] for v in ids]}


def _safe_meta(app_id, version_id):
    try:
        return store.version_metadata(app_id, version_id)
    except store.StoreError:
        return {"id": version_id, "version": "?", "date": ""}


# ---------- HTTP ----------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        global last_seen
        if self.headers.get("X-Token") != TOKEN:
            self.send_json({"error": "forbidden"}, 403)
            return False
        last_seen = time.monotonic()
        return True

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}

        if self.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
            return self.send_json({"error": "forbidden"}, 403)  # защита от DNS rebinding
        if url.path == "/":
            html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN)
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        icon = re.fullmatch(r"/icons/(\d+\.png)", url.path)
        if icon and (ROOT / "ui" / "icons" / icon.group(1)).exists():
            body = (ROOT / "ui" / "icons" / icon.group(1)).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png" if body[:4] == b"\x89PNG" else "image/jpeg")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            self.wfile.write(body)
            return
        if not self.authorized():
            return
        try:
            if url.path == "/api/state":
                self.send_json({"account": account, "platform": sys.platform})
            elif url.path == "/api/devices":
                self.send_json({"devices": device.list_devices()})
            elif url.path == "/api/catalog":
                self.send_json(json.loads((ROOT / "catalog.json").read_text(encoding="utf-8")))
            elif url.path == "/api/search":
                term = q.get("q", "")
                app_id = parse_app_id(term)
                if app_id:
                    found = store.lookup(app_id)
                    self.send_json({"results": [found] if found else [{"id": app_id, "name": f"Приложение id{app_id}",
                                                                       "removed": True}]})
                else:
                    self.send_json({"results": store.search(term)})
            elif url.path == "/api/versions":
                self.send_json(versions(parse_app_id(q.get("id")), int(q.get("offset", 0)), int(q.get("limit", 15))))
            elif url.path == "/api/jobs":
                self.send_json({"jobs": snapshot()})
            elif url.path.startswith("/api/job/"):
                with lock:
                    self.send_json(dict(jobs.get(url.path.rsplit("/", 1)[1], {"error": "нет задачи", "done": True})))
            else:
                self.send_json({"error": "not found"}, 404)
        except (device.DeviceError, store.StoreError) as e:
            self.send_json({"error": str(e)}, 400)
        except Exception as e:
            self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self):
        global account
        if not self.authorized():
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        path = urlparse(self.path).path
        try:
            if path == "/api/login":
                account = store.login(body["email"].strip(), body["password"], body.get("code", "").strip())
                self.send_json({"account": account})
            elif path == "/api/logout":
                store.logout()
                account = None
                self.send_json({"account": None})
            elif path == "/api/install":
                if not account:
                    return self.send_json({"error": "Сначала войдите в Apple ID"}, 400)
                app_id = parse_app_id(body.get("appId"))
                if not app_id:
                    return self.send_json({"error": "Некорректный App Store ID"}, 400)
                job_id = enqueue(app_id, str(body.get("name") or f"id{app_id}"), body.get("udid"),
                                 bool(body.get("purchase")), bool(body.get("keepIpa")),
                                 body.get("versionId"), body.get("versionLabel"))
                self.send_json({"job": job_id})
            elif path == "/api/cancel":
                if not cancel(body.get("job")):
                    return self.send_json({"error": "Задача уже выполняется или завершена"}, 400)
                self.send_json({"ok": True})
            else:
                self.send_json({"error": "not found"}, 404)
        except store.NeedCode as e:
            self.send_json({"needCode": True, "error": str(e)}, 401)
        except store.StoreError as e:
            self.send_json({"error": str(e)}, 400)
        except Exception as e:
            traceback.print_exc()
            self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)


last_seen = time.monotonic()  # время последнего запроса страницы: она опрашивает сервер каждые несколько секунд


def idle_seconds():
    """Сколько секунд страница не выходила на связь; пока что-то ставится, программа не простаивает."""
    with lock:
        busy = any(job["stage"] in ACTIVE for job in jobs.values())
    return 0 if busy else time.monotonic() - last_seen


def create(port):
    """Создаёт сервер (port=0 — любой свободный) и возвращает (server, url)."""
    global account
    account = store.account_info()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=worker, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/"


def main():
    server, url = create(next((int(a) for a in sys.argv[1:] if a.isdigit()), 8765))
    print(f"Возврат запущен: {url}  (закройте это окно, чтобы остановить)")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
