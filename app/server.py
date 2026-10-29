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

import catalog
import device
import store
import updater
from version import VERSION

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))  # в .exe — папка с ресурсами
IPA_DIR = store.DATA / "ipa"
INSTALLED = store.DATA / "installed.json"  # что и какой версии «Возврат» ставил на каждый iPhone
TOKEN = secrets.token_urlsafe(24)  # защищает API от запросов со сторонних сайтов

account = None  # {"email", "name"} — кэш `ipatool auth info`
jobs = {}  # id -> задача; порядок вставки = порядок добавления
queue = collections.deque()  # id задач, ждущих установки
lock = threading.Lock()
queue_ready = threading.Condition(lock)


def parse_app_id(text):
    m = re.search(r"id(\d{6,12})", str(text)) or re.fullmatch(r"\s*(\d{6,12})\s*", str(text))
    return int(m.group(1)) if m else None


def public(job):
    """Задача для отправки странице: без служебных полей (событие отмены, UDID)."""
    return {k: v for k, v in job.items() if not k.startswith("_") and k != "udid"}


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
                        "versionId": version_id, "versionLabel": version_label, "_cancel": threading.Event()}
        queue.append(job_id)
        for old in [j for j in jobs if jobs[j]["done"]][:-50]:  # не копим бесконечную историю
            del jobs[old]
        queue_ready.notify()
        return job_id


def cancel(job_id):
    """Отменяет задачу в очереди или идущее скачивание. Установку на iPhone не прерываем:
    оборванная установка может оставить приложение в непонятном состоянии."""
    with lock:
        job = jobs.get(job_id)
        if not job:
            return False
        if job_id in queue:
            queue.remove(job_id)
            job.update(stage="canceled", done=True, message="Отменено")
            return True
        if job["stage"] == "download":
            job["_cancel"].set()
            job.update(message="Отменяю…")
            return True
        return False


def snapshot():
    with lock:
        position = {job_id: i + 1 for i, job_id in enumerate(queue)}
        return [{**public(job), "position": position.get(job["id"])} for job in jobs.values()]


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


def record_install(udid, req, app_id, name):
    """Запоминает, какое приложение под каким App Store ID поставлено: по этому журналу программа
    находит обновления, если iPhone не сообщает ID приложения сам."""
    if not udid or not req.get("bundleId"):
        return
    with lock:
        try:
            data = json.loads(INSTALLED.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data.setdefault(udid, {})[req["bundleId"]] = {"appId": app_id, "name": name, "version": req.get("version")}
        INSTALLED.parent.mkdir(parents=True, exist_ok=True)
        INSTALLED.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def run_job(job):
    job_id, app_id, udid = job["id"], job["appId"], job["udid"]
    allow_purchase, keep_ipa = job["purchase"], job["keepIpa"]
    work = IPA_DIR / job_id

    def update(**kw):
        with lock:
            job.update(kw)

    try:
        update(stage="download", message="Запрос к App Store…")
        # размер известен только для последней версии и только если приложение есть хоть в одном магазине
        total = None if job.get("versionId") else store.download_size(app_id)

        def on_progress(size):
            if job["_cancel"].is_set():
                return
            if total:
                share = min(size / total, 0.99)
                update(progress=share, message=f"Скачивание из App Store… {size / 1048576:.0f} из "
                                               f"{total / 1048576:.0f} МБ ({share * 100:.0f}%)")
            else:
                update(message=f"Скачивание из App Store… {size / 1048576:.0f} МБ")

        path = Path(store.download(app_id, work, on_progress, allow_purchase, job.get("versionId"), job["_cancel"]))
        update(progress=None, message="Проверка совместимости с iPhone…")
        req = check_compatible(path, udid)
        update(stage="install", message="Установка на iPhone… Не отключайте кабель и не блокируйте экран")
        device.install(udid, str(path))
        record_install(udid, req, app_id, job["name"])
        if keep_ipa:
            os.replace(path, IPA_DIR / path.name)
        update(stage="done", done=True, progress=1, message=f"Готово: {path.stem} установлено на iPhone"
               + f"\nВерсия {req.get('version') or '?'}"
               + (f", IPA сохранён: {IPA_DIR / path.name}" if keep_ipa else ""))
    except store.Canceled:
        update(stage="canceled", done=True, progress=None, message="Отменено")
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


def clean_stale_downloads():
    """Папки незавершённых скачиваний (имя — id задачи) остаются, если программу закрыли посреди
    загрузки, и занимают сотни мегабайт. При запуске задач ещё нет — всё такое можно удалить.
    Сохранённые по желанию пользователя .ipa лежат прямо в IPA_DIR и не трогаются."""
    if IPA_DIR.exists():
        for d in IPA_DIR.iterdir():
            if d.is_dir() and re.fullmatch(r"[0-9a-f]{32}", d.name):
                shutil.rmtree(d, ignore_errors=True)


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


# ---------- обновления приложений на iPhone ----------

latest_cache = {}  # app_id -> (время, номер последней версии); список версий у Apple меняется нечасто
LATEST_TTL = 3600


def latest_app_version(app_id):
    cached = latest_cache.get(app_id)
    if cached and time.monotonic() - cached[0] < LATEST_TTL:
        return cached[1]
    ids = store.list_versions(app_id)  # свежий список, а не кэш окна «Версии»
    version_ids[app_id] = ids
    latest = store.version_metadata(app_id, ids[0])["version"] if ids else None
    latest_cache[app_id] = (time.monotonic(), latest)
    return latest


def installed_known(udid):
    """{App Store ID: {"version", "name"}} — приложения на iPhone, которые есть в каталоге или которые ставил
    «Возврат» (их ID знает журнал установок). Остальные приложения на телефоне не трогаем."""
    if not udid:
        raise device.DeviceError("Подключите iPhone (шаг 2)")
    installed = device.installed_apps(udid)
    try:
        journal = json.loads(INSTALLED.read_text(encoding="utf-8")).get(udid, {})
    except (OSError, ValueError):
        journal = {}
    known = {a["id"]: a["name"] for a in catalog.load(wait=0)["apps"]}
    result = {}
    for bundle_id, info in installed.items():
        app_id = info["appId"] or (journal.get(bundle_id) or {}).get("appId")
        if app_id and (app_id in known or bundle_id in journal):
            result[app_id] = {"version": info["version"], "name": known.get(app_id) or info["name"]}
    return result


def app_updates(udid):
    """Приложения из каталога и из журнала установок, для которых у Apple есть версия новее, чем на iPhone."""
    candidates = [(app_id, info["name"], info["version"]) for app_id, info in installed_known(udid).items()]

    def check(c):
        app_id, name, current = c
        try:
            latest = latest_app_version(app_id)
        except store.StoreError:
            return None  # нет в истории покупок этого Apple ID или Apple не ответил — пропускаем
        if latest and current and store.version_tuple(latest) > store.version_tuple(current):
            return {"appId": app_id, "name": name, "installed": current, "latest": latest}
        return None

    with ThreadPoolExecutor(4) as pool:
        found = [r for r in pool.map(check, candidates) if r]
    return {"checked": len(candidates), "updates": sorted(found, key=lambda r: r["name"].lower())}


# ---------- «Вернуть всё сразу»: какие приложения каталога есть в истории покупок ----------

# Есть ли приложение в покупках, узнаём запросом списка версий: он не скачивает IPA, а для приложения
# не из истории покупок Apple отвечает «нужна лицензия». Запросы идут по одному на приложение,
# поэтому параллельно немного — чтобы не упереться в ограничения App Store. Временные сбои (сеть,
# медленный ответ Apple, занятый файл сессии) не должны прятать купленные приложения: такие
# приложения в конце перепроверяются по одному, с паузой.
SCAN_WORKERS = 3
SCAN_RETRY_ROUNDS = 2
SCAN_RETRY_PAUSE = 3  # сек между приложениями при перепроверке
scan = {"running": False, "phase": "", "checked": 0, "total": 0, "found": [], "failed": 0,
        "unavailable": 0, "reasons": {}, "failedApps": [], "error": None}
scan_stop = threading.Event()

NOT_OWNED = "нет в истории покупок"


def scan_reason(error):
    """(тип, понятная причина): тип — "not_owned", "unavailable" (нет в магазине вашей страны) или "failed"."""
    t = str(error).lower()
    if NOT_OWNED in t:
        return "not_owned", ""
    # ipatool ищет версию в магазине страны Apple ID; приложения, которых там нет (ChatGPT, V2Box…),
    # из этого магазина не скачать, даже если они куплены в другой стране
    if "storefront" in t or "недоступно для этого apple id" in t:
        return "unavailable", "нет в магазине вашей страны"
    if "не ответил вовремя" in t or "timeout" in t or "deadline" in t:
        return "failed", "Apple не ответила вовремя"
    if any(k in t for k in ("lock", "занят", "being used by another process", "access is denied")):
        return "failed", "файл сессии был занят"
    if any(k in t for k in ("connection", "dial tcp", "eof", "no such host", "tls", "network", "reset by peer")):
        return "failed", "сетевая ошибка"
    if "429" in t or "too many requests" in t or "rate limit" in t:
        return "failed", "Apple ограничила частоту запросов"
    return "failed", str(error).strip().splitlines()[-1][:120] if str(error).strip() else "неизвестная ошибка"


def scan_snapshot():
    with lock:
        return {**scan, "found": list(scan["found"]), "reasons": dict(scan["reasons"]),
                "failedApps": list(scan["failedApps"])}


def start_scan(udid, category):
    """Проверяет приложения каталога (одной категории или все), которых ещё нет на iPhone."""
    with lock:
        if scan["running"]:
            raise store.StoreError("Проверка уже идёт")
    skip = set(installed_known(udid)) if udid else set()
    apps = [a for a in catalog.load(wait=0)["apps"]
            if (not category or a.get("category") == category) and a["id"] not in skip]
    scan_stop.clear()
    failed = {}  # id -> (app, причина) — то, что ещё предстоит перепроверить
    with lock:
        scan.update(running=True, phase="check", checked=0, total=len(apps), found=[], failed=0, unavailable=0,
                    reasons={}, failedApps=[], error=None)

    def publish():  # вызывается под lock
        reasons = {}
        for _, reason in failed.values():
            reasons[reason] = reasons.get(reason, 0) + 1
        scan["failed"] = len(failed)
        scan["reasons"] = reasons
        scan["failedApps"] = [{"id": app["id"], "name": app["name"], "reason": reason}
                              for app, reason in failed.values()]

    def check(app, first=True):
        if scan_stop.is_set():
            return
        kind, reason, owned = "failed", "", False
        try:
            ids = store.list_versions(app["id"])
            version_ids[app["id"]] = ids  # пригодится окну «Версии»
            owned, kind = bool(ids), "owned"
        except store.NotLoggedIn as e:
            scan_stop.set()
            with lock:
                scan["error"] = str(e)
            return
        except store.StoreError as e:
            kind, reason = scan_reason(e)
        with lock:
            if first:
                scan["checked"] += 1
            failed.pop(app["id"], None)
            if kind == "failed":
                failed[app["id"]] = (app, reason)
            elif kind == "unavailable":
                scan["unavailable"] += 1
            if owned:
                scan["found"].append({"id": app["id"], "name": app["name"], "category": app.get("category")})
            publish()

    def run():
        try:
            with ThreadPoolExecutor(SCAN_WORKERS) as pool:
                list(pool.map(check, apps))
            for _ in range(SCAN_RETRY_ROUNDS):  # перепроверка сбойных — по одному и не спеша
                with lock:
                    retry = [app for app, _ in failed.values()]
                if not retry or scan_stop.is_set():
                    break
                with lock:
                    scan["phase"] = "retry"
                for app in retry:
                    if scan_stop.wait(SCAN_RETRY_PAUSE):
                        break
                    check(app, first=False)
        finally:
            with lock:
                scan["running"] = False
                scan["phase"] = ""
                scan["found"].sort(key=lambda a: a["name"].lower())

    threading.Thread(target=run, daemon=True).start()
    return scan_snapshot()


# ---------- HTTP ----------

GATED_GET = ("/api/devices", "/api/search", "/api/versions", "/api/app-updates", "/api/installed")
GATED_POST = ("/api/login", "/api/install", "/api/restore-scan")


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

    def send_bytes(self, body, ctype, cache=None):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if cache:
            self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        global last_seen
        if self.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
            self.send_json({"error": "forbidden"}, 403)  # защита от DNS rebinding
            return False
        if self.headers.get("X-Token") != TOKEN:
            self.send_json({"error": "forbidden"}, 403)
            return False
        last_seen = time.monotonic()
        return True

    def gate(self, path, gated):
        """Устаревшая версия не работает: действия отклоняются, пока программа не обновится."""
        if path in gated and not updater.allowed():
            self.send_json({"error": "Нужно обновить программу", "update": updater.state()}, 423)
            return False
        return True

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}

        if self.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
            return self.send_json({"error": "forbidden"}, 403)  # защита от DNS rebinding
        if url.path == "/":
            html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN)
            return self.send_bytes(html.encode(), "text/html; charset=utf-8")
        icon = re.fullmatch(r"/icons/(\d+\.png)", url.path)
        if icon:
            body = catalog.icon(icon.group(1))
            if body is None:
                return self.send_json({"error": "not found"}, 404)
            return self.send_bytes(body, "image/png" if body[:4] == b"\x89PNG" else "image/jpeg", "max-age=86400")
        if not self.authorized() or not self.gate(url.path, GATED_GET):
            return
        try:
            if url.path == "/api/state":
                self.send_json({"account": account, "platform": sys.platform, "version": VERSION,
                                "update": updater.state()})
            elif url.path == "/api/update":
                self.send_json(updater.state())
            elif url.path == "/api/devices":
                self.send_json({"devices": device.list_devices()})
            elif url.path == "/api/catalog":
                self.send_json(catalog.load())
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
            elif url.path == "/api/installed":
                apps = installed_known(q.get("udid"))
                self.send_json({"apps": {str(k): v for k, v in apps.items()}})
            elif url.path == "/api/restore-scan":
                self.send_json(scan_snapshot())
            elif url.path == "/api/app-updates":
                if not account:
                    return self.send_json({"error": "Сначала войдите в Apple ID"}, 400)
                self.send_json(app_updates(q.get("udid")))
            elif url.path == "/api/jobs":
                self.send_json({"jobs": snapshot()})
            elif url.path.startswith("/api/job/"):
                with lock:
                    job = jobs.get(url.path.rsplit("/", 1)[1])
                    self.send_json(public(job) if job else {"error": "нет задачи", "done": True})
            else:
                self.send_json({"error": "not found"}, 404)
        except (device.DeviceError, store.StoreError) as e:
            self.send_json({"error": str(e)}, 400)
        except Exception as e:
            self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self):
        global account
        path = urlparse(self.path).path
        if not self.authorized() or not self.gate(path, GATED_POST):
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
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
                    return self.send_json({"error": "Установку на iPhone прервать нельзя, дождитесь окончания"}, 400)
                self.send_json({"ok": True})
            elif path == "/api/restore-scan":
                if not account:
                    return self.send_json({"error": "Сначала войдите в Apple ID"}, 400)
                self.send_json(start_scan(body.get("udid"), body.get("category") or None))
            elif path == "/api/restore-scan/stop":
                scan_stop.set()
                self.send_json(scan_snapshot())
            elif path == "/api/update/check":
                self.send_json(updater.check())
            elif path == "/api/update/start":
                updater.start_update()
                self.send_json(updater.state())
            else:
                self.send_json({"error": "not found"}, 404)
        except store.NeedCode as e:
            self.send_json({"needCode": True, "error": str(e)}, 401)
        except (store.StoreError, updater.UpdateError) as e:
            self.send_json({"error": str(e)}, 400)
        except Exception as e:
            traceback.print_exc()
            self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)


last_seen = time.monotonic()  # время последнего запроса страницы: она опрашивает сервер каждые несколько секунд


def idle_seconds():
    """Сколько секунд страница не выходила на связь; пока что-то ставится, программа не простаивает."""
    with lock:
        busy = any(job["stage"] in ACTIVE for job in jobs.values())
    if updater.state()["status"] in ("downloading", "installing", "restarting"):
        busy = True
    return 0 if busy else time.monotonic() - last_seen


def create(port, check_updates=True):
    """Создаёт сервер (port=0 — любой свободный) и возвращает (server, url)."""
    global account
    updater.cleanup()
    clean_stale_downloads()
    catalog.refresh()
    if check_updates:
        updater.start_background_checks()
    account = store.account_info()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=worker, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/"


def main():
    server, url = create(next((int(a) for a in sys.argv[1:] if a.isdigit()), 8765))
    print(f"Возврат {VERSION} запущен: {url}  (закройте это окно, чтобы остановить)")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
