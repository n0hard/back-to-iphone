"""Собирает блог сайта: cite/blog/*, sitemap.xml, robots.txt и блок стилей блога в cite/site.css.

Статьи описаны в списке POSTS ниже. Скриншоты вставляются меткой [[имя|подпись]] или
[[имя|подпись|narrow]], где имя — файл из cite/img без .png (его размер нужно добавить в IMG).
Запуск из корня репозитория:  python tools/build_blog.py
"""
import pathlib, html, re

def fixlinks(t):
    # file:// не открывает index.html в папке, поэтому ссылки на папки делаем явными
    pat = r'href="((?:\.\./)+|(?:\.\./)*[a-z0-9-]+/)(#[^"]*)?"'
    t = re.sub(pat, lambda m: 'href="%sindex.html%s"' % (m.group(1), m.group(2) or ""), t)
    return t.replace('href="blog/"', 'href="blog/index.html"')

cite = pathlib.Path(__file__).resolve().parent.parent / "cite"
SITE = "https://n0hard.github.io/back-to-iphone/"
GH = "https://github.com/n0hard/back-to-iphone"
REL = GH + "/releases/latest/download/"

BLOG_CSS = """
/* BLOG */
[hidden] { display: none !important; }
.blog-hero { padding: 72px 0 40px; text-align: left; }
.blog-hero .kicker { font-size: 14px; font-weight: 600; color: var(--blue); margin: 0 0 10px; letter-spacing: .02em; text-transform: uppercase; }
.blog-hero h1 { margin: 0 0 16px; max-width: 14em; font-size: clamp(36px, 6vw, 64px); }
.blog-hero p { font-size: clamp(18px, 2vw, 24px); color: var(--ink-2); max-width: 30em; margin: 0; line-height: 1.25; }
.blog-main { background: var(--bg-alt); padding: 40px 0 100px; }
.tag { display: inline-block; font-size: 12px; font-weight: 600; color: var(--blue); background: rgba(0,113,227,.1); border-radius: 980px; padding: 3px 12px; }
.meta { font-size: 13px; color: var(--ink-2); margin-left: 8px; }
.featured { display: grid; grid-template-columns: 1.3fr 1fr; gap: 24px; background: #1d1d1f; color: #f5f5f7; border-radius: 28px; padding: 48px; margin-bottom: 20px; align-items: center; text-decoration: none; transition: transform .3s; }
.featured:hover { text-decoration: none; transform: scale(1.005); }
.featured .tag { background: rgba(10,132,255,.25); color: #64d2ff; }
.featured .meta { color: #a1a1a6; }
.featured h2 { font-size: clamp(28px, 4vw, 44px); line-height: 1.08; letter-spacing: -0.03em; margin: 14px 0 12px; font-weight: 700; color: #fff; }
.featured p { color: #a1a1a6; margin: 0 0 18px; font-size: 17px; }
.featured .go, .card .go { color: var(--link); font-weight: 500; }
.featured .go { color: #64d2ff; }
.art { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; max-width: 280px; margin-left: auto; }
.art i { aspect-ratio: 1; border-radius: 22%; display: block; }
.art i:nth-child(1){background:#30d158}.art i:nth-child(2){background:#0a84ff}.art i:nth-child(3){background:#ff453a}
.art i:nth-child(4){background:#2c2c2e;border:2px dashed #48484a}.art i:nth-child(5){background:#ffd60a}.art i:nth-child(6){background:#2c2c2e;border:2px dashed #48484a}
.cards { display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; }
.card { display: flex; flex-direction: column; background: #fff; border-radius: 28px; padding: 36px; color: var(--ink); transition: transform .3s, box-shadow .3s; }
.card:hover { text-decoration: none; transform: translateY(-3px); box-shadow: 0 14px 40px rgba(0,0,0,.08); }
.card h2 { font-size: 24px; line-height: 1.15; letter-spacing: -0.02em; margin: 14px 0 10px; font-weight: 700; }
.card p { margin: 0 0 18px; color: var(--ink-2); font-size: 16px; }
.card .go { margin-top: auto; }
.filters { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 24px; }
.filters .tab[aria-pressed="true"] { background: var(--ink); color: #fff; }
.empty { text-align: center; color: var(--ink-2); padding: 40px 0; }

/* ARTICLE */
.article { max-width: 720px; margin: 0 auto; padding: 56px 24px 80px; }
.crumbs { font-size: 14px; margin-bottom: 28px; }
.article h1 { font-size: clamp(32px, 5vw, 48px); line-height: 1.08; letter-spacing: -0.03em; margin: 14px 0 16px; font-weight: 700; max-width: none; text-align: left; }
.article .lede { font-size: 21px; line-height: 1.38; color: var(--ink-2); margin: 0 0 36px; letter-spacing: -0.01em; }
.article h2 { font-size: 28px; line-height: 1.14; letter-spacing: -0.025em; margin: 44px 0 12px; font-weight: 700; }
.article p, .article li { font-size: 18px; line-height: 1.55; letter-spacing: -0.015em; }
.article p { margin: 0 0 16px; } .article ul, .article ol { padding-left: 24px; margin: 0 0 20px; } .article li { margin: 8px 0; }
.article .code { padding-right: 90px; margin: 14px 0 20px; }
.callout { background: var(--bg-alt); border-radius: 18px; padding: 20px 24px; margin: 24px 0; }
.callout p { margin: 0; font-size: 16px; }
.callout strong { display: block; margin-bottom: 4px; }
.cta-box { background: #1d1d1f; color: #f5f5f7; border-radius: 28px; padding: 40px; margin: 48px 0 0; text-align: center; }
.cta-box h2 { color: #fff; margin: 0 0 8px; font-size: 28px; }
.cta-box p { color: #a1a1a6; margin: 0 0 20px; }
.related { margin-top: 56px; border-top: 1px solid var(--line); padding-top: 28px; }
.related h3 { font-size: 21px; margin: 0 0 12px; }
.related ul { list-style: none; padding: 0; margin: 0; }
.related li { margin: 0; border-bottom: 1px solid #ececf0; } .related li a { display: block; padding: 12px 0; font-size: 17px; }
.shot { margin: 28px 0 32px; }
.shot .frame { background: #111214; border-radius: 18px; padding: 10px; box-shadow: 0 18px 50px rgba(0,0,0,.18), 0 0 0 1px rgba(0,0,0,.06); }
.shot img { width: 100%; height: auto; border-radius: 10px; cursor: zoom-in; }
.shot.narrow .frame { max-width: 440px; margin: 0 auto; }
.shot figcaption { font-size: 14px; color: var(--ink-2); text-align: center; margin-top: 12px; line-height: 1.4; }
.card .cover { margin: -36px -36px 24px; height: 180px; background: #111214; border-radius: 28px 28px 0 0; overflow: hidden; display: flex; align-items: flex-start; justify-content: center; padding: 18px 18px 0; }
.card .cover img { width: 100%; height: auto; object-fit: cover; object-position: top; border-radius: 12px 12px 0 0; transition: transform .5s cubic-bezier(.16,1,.3,1); }
.card:hover .cover img { transform: scale(1.03); }
.featured .art.shot-art { display: block; max-width: 340px; }
.featured .shot-art img { border-radius: 14px; box-shadow: 0 20px 50px rgba(0,0,0,.5); }
.lb { position: fixed; inset: 0; z-index: 300; background: rgba(0,0,0,.85); display: flex; align-items: center; justify-content: center; padding: 24px; cursor: zoom-out; }
.lb img { max-width: 100%; max-height: 100%; border-radius: 12px; box-shadow: 0 30px 80px rgba(0,0,0,.6); }
.lb button { position: absolute; top: 16px; right: 16px; width: 40px; height: 40px; border-radius: 50%; border: 0; background: rgba(255,255,255,.15); color: #fff; font-size: 20px; }
@media (max-width: 800px) { .featured { grid-template-columns: 1fr; padding: 32px; } .art { margin: 0; max-width: 200px; } .cards { grid-template-columns: 1fr; } }
@media (max-width: 600px) { .card .cover { margin: -28px -28px 20px; border-radius: 22px 22px 0 0; height: 150px; } .shot .frame { padding: 6px; border-radius: 14px; } .article p, .article li { font-size: 17px; } .card, .cta-box { padding: 28px; border-radius: 22px; } .blog-hero { padding-top: 48px; } }
"""

IMG = {
  "step-appleid": (728, 124), "step-iphone": (728, 242), "step-catalog": (728, 554),
  "step-search": (728, 190), "modal-variants": (440, 880), "modal-versions": (440, 815),
  "queue-cards": (728, 250), "main": (780, 1100), "queue": (728, 517),
}

def figs(body, root):
    def one(m):
        parts = m.group(1).split("|")
        name, cap = parts[0], parts[1]
        narrow = len(parts) > 2
        w, h = IMG[name]
        return (f'<figure class="shot{" narrow" if narrow else ""}"><div class="frame">'
                f'<img src="{root}img/{name}.png" width="{w}" height="{h}" loading="lazy" alt="{html.escape(cap, quote=True)}" />'
                f'</div><figcaption>{cap}</figcaption></figure>')
    return re.sub(r"\[\[([^\]]+)\]\]", one, body)

def code(cmd):
    return f'<div class="code"><span>{html.escape(cmd)}</span><button class="copy" type="button">Копировать</button></div>'

POSTS = [
 dict(slug="kak-vernut-udalennye-prilozheniya", cover="main", tag="Инструкция", mins=6,
  title="Как вернуть удалённые из App Store приложения на iPhone",
  desc="Пошаговая инструкция: вход в Apple ID, подключение iPhone, выбор приложения и установка по USB.",
  body=f"""
<p>Приложение, которое когда-то скачивалось с вашего Apple ID, остаётся в истории покупок, даже если из магазина его убрали. «Возврат» берёт оригинальный IPA с подписью Apple из этой истории и ставит его на iPhone по кабелю. Джейлбрейк и переподпись сертификатами не нужны.</p>
<div class="callout"><p><strong>Важное условие</strong>Работает только для приложений, которые уже скачивались с вашего Apple ID. Если приложения в истории нет, смотрите <a href="../ne-v-istorii-pokupok/">отдельную статью</a>.</p></div>
<h2>Что понадобится</h2>
<ul><li>Компьютер с Windows 10/11, macOS 12+ или Linux x86_64.</li><li>Кабель для iPhone.</li><li>Apple ID, с которого приложение скачивалось раньше (и устройство для кода двухфакторной аутентификации).</li><li>Windows: приложение Apple Devices из Microsoft Store или iTunes. Linux: служба <code>usbmuxd</code>. На macOS драйвер встроен.</li></ul>
<h2>Шаг 1. Скачайте и запустите программу</h2>
<p>Готовые сборки лежат <a href="../../#download">в разделе «Скачать»</a>. Python ставить не нужно: он уже внутри.</p>
<h2>Шаг 2. Войдите в Apple ID</h2>
<p>Введите логин и пароль. Если включена двухфакторная аутентификация, появится поле для кода: введите код с устройства Apple и снова нажмите «Войти». Первый вход может занять 1–3 минуты.</p>
[[step-appleid|После входа в блоке «Apple ID» появится зелёная галочка и имя аккаунта]]
<h2>Шаг 3. Подключите iPhone</h2>
<p>Подключите телефон кабелем, разблокируйте его и нажмите «Доверять этому компьютеру». iPhone появится в списке. Если его нет, нажмите «Обновить список».</p>
[[step-iphone|Подключённый iPhone с моделью и версией iOS. Кнопка «Обновить список» — если телефона нет]]
<h2>Шаг 4. Выберите приложение</h2>
<p>Найдите приложение в каталоге (в нём 441 приложение) или введите название, App Store ID либо ссылку вида <code>apps.apple.com/…/id123456789</code>. Нажмите «Установить». Не отключайте кабель и не блокируйте экран, пока идёт установка.</p>
[[step-catalog|Поиск по каталогу с подсказками при вводе и каталог по категориям. У каждой карточки — «Установить» и «Все варианты…»]]
<p>Можно нажать «Установить» у нескольких приложений сразу: они встанут в очередь, а ожидающие можно отменить.</p>
[[queue-cards|Очередь: первое приложение скачивается, следующие ждут своей очереди, готовое отмечено «Установлено»]]
<h2>Если что-то пошло не так</h2>
<ul><li>Нет в истории покупок — <a href="../ne-v-istorii-pokupok/">что делать</a>.</li><li>Нужна более новая iOS — <a href="../staraya-versiya-prilozheniya/">как поставить старую версию</a>.</li><li>iPhone не находится — проверьте драйвер и разрешение «Доверять этому компьютеру».</li></ul>
"""),
 dict(slug="ne-v-istorii-pokupok", cover="modal-variants", tag="Инструкция", mins=4,
  title="«Этого приложения нет в истории покупок»: что делать",
  desc="Почему программа не находит приложение в вашем Apple ID и как это обойти.",
  body="""
<p>Это самое частое сообщение. Оно значит, что приложение никогда не скачивалось с Apple ID, под которым вы вошли. Apple отдаёт удалённые приложения только из истории покупок конкретного аккаунта.</p>
<h2>Что попробовать</h2>
<ol>
<li><strong>Другой вариант приложения.</strong> Банки выходили под разными названиями, поэтому в каталоге они собраны в одну карточку с несколькими вариантами (например, «Т-Банк · 15 вариантов»). Откройте «Все варианты…» и поставьте тот, который вы когда-то скачивали. В истории покупок есть только он.
[[modal-variants|Окно «Все варианты…»: у каждого варианта свой App Store ID и кнопки «Версии» и «Установить»|narrow]]</li>
<li><strong>Другой Apple ID.</strong> Войдите под аккаунтом, где приложение скачивалось, например под вторым своим или аккаунтом родственника, если он согласен.</li>
<li><strong>Флажок «купить, если нет в покупках».</strong> Он добавляет в историю бесплатные приложения, которые ещё доступны в App Store. Для уже удалённых приложений он не поможет.</li>
</ol>
<div class="callout"><p><strong>Пароль чужого аккаунта</strong>Вводите данные чужого Apple ID только с согласия владельца и помните, что пароль уходит напрямую на серверы Apple.</p></div>
<h2>Почему так устроено</h2>
<p>Программа не распространяет чужие приложения. Она использует штатный механизм Apple: повторную загрузку ранее приобретённого (в том числе бесплатного) приложения из вашей истории покупок.</p>
"""),
 dict(slug="staraya-versiya-prilozheniya", cover="modal-versions", tag="Инструкция", mins=4,
  title="Как поставить старую версию приложения, если не хватает iOS",
  desc="Сообщение «Нужна iOS … или новее» значит, что последняя версия вам не подходит. Выбираем более старую.",
  body="""
<p>Если на iPhone не самая свежая iOS, последняя версия приложения может её не поддерживать. Программа проверяет совместимость перед установкой и показывает сообщение «Нужна iOS … или новее».</p>
<h2>Как выбрать версию</h2>
<ol>
<li>Найдите приложение в каталоге или через поиск.</li>
<li>Нажмите «Версии» (или «Другая версия…» в окне вариантов).</li>
<li>В списке будут версии, которые хранит Apple. Выберите ту, которую поддерживает ваша iOS, и установите.</li>
</ol>
[[modal-versions|Окно версий: номер и дата выхода каждой сборки. «Показать ещё» открывает более старые|narrow]]
<p>Минимальная версия iOS и поддержка вашего iPhone проверяются перед установкой, так что несовместимую сборку программа поставить не даст.</p>
<div class="callout"><p><strong>Обновления</strong>Удалённые приложения не обновляются через App Store. Чтобы поставить более свежую версию, если она есть в истории покупок, установите приложение ещё раз.</p></div>
"""),
 dict(slug="kak-eto-rabotaet", cover="main", tag="Объяснение", mins=5,
  title="Как устроен «Возврат»: ipatool, pymobiledevice3 и локальный сервер",
  desc="Что происходит между нажатием «Установить» и иконкой на экране iPhone.",
  body="""
<p>«Возврат» состоит из локального сервера на вашем компьютере и двух готовых инструментов с открытым кодом.</p>
[[main|Интерфейс программы: три шага — Apple ID, iPhone и приложение|narrow]]
<h2>Схема</h2>
<div class="code" style="padding-right:16px"><span>Интерфейс (окно / браузер) ─► локальный сервер 127.0.0.1 ─┬─► ipatool ─────────► App Store (вход, IPA)
                                                          └─► pymobiledevice3 ─► iPhone по USB</span></div>
<h2>Зачем нужен ipatool</h2>
<p>Чтобы войти в App Store, Apple требует подпись SAP (FairPlay). Её умеет вычислять <a href="https://github.com/majd/ipatool" target="_blank" rel="noopener noreferrer">ipatool</a> (лицензия MIT): он эмулирует код Apple. Своя реализация протокола без него получает от Apple пустой ответ. Через ipatool программа входит в аккаунт и скачивает IPA вместе с <code>sinf</code> и <code>iTunesMetadata</code>.</p>
<h2>Зачем нужен pymobiledevice3</h2>
<p><a href="https://github.com/doronz88/pymobiledevice3" target="_blank" rel="noopener noreferrer">pymobiledevice3</a> (GPL-3.0) находит iPhone на USB и устанавливает на него скачанный пакет. На Windows для этого нужен драйвер Apple, на Linux — служба <code>usbmuxd</code>, на macOS всё встроено.</p>
<h2>Где хранятся данные</h2>
<p>В папке программы: <code>%APPDATA%\\vozvrat</code> на Windows, <code>~/Library/Application Support/Vozvrat</code> на macOS, <code>~/.local/share/vozvrat</code> на Linux. Там лежат ключ от хранилища ipatool и временные IPA. Общий <code>~/.ipatool</code> на Windows и Linux не используется, чтобы не мешать другим программам на ipatool.</p>
<h2>Открытый код</h2>
<p>Весь код доступен <a href="https://github.com/n0hard/back-to-iphone" target="_blank" rel="noopener noreferrer">на GitHub</a>: можно проверить, что именно делает программа, или собрать её самостоятельно.</p>
"""),
 dict(slug="bezopasnost-apple-id", cover="step-appleid", tag="Объяснение", mins=4,
  title="Безопасно ли вводить пароль Apple ID в «Возврате»",
  desc="Куда уходит пароль, как защищён локальный сервер и что делать, если вы пользовались другими ipatool-программами.",
  body="""
<h2>Куда уходит пароль</h2>
<p>Только на серверы Apple. Программа работает на вашем компьютере (127.0.0.1), а вход выполняет <code>ipatool</code>. Двухфакторная аутентификация поддерживается: код вводится в самой программе.</p>
[[step-appleid|После входа программа показывает только имя и адрес аккаунта. Кнопка «Выйти» завершает сессию]]
<h2>Как защищён локальный сервер</h2>
<p>Локальный HTTP-сервер программы защищён случайным токеном и проверкой заголовка Host, поэтому посторонние страницы в браузере не смогут им воспользоваться.</p>
<h2>Где хранится сессия</h2>
<p>На Windows и Linux — в зашифрованном <code>ipatool-home</code> внутри папки программы, на macOS — в связке ключей.</p>
<h2>Если вы пользовались IPA_Downloader и подобными</h2>
<p>Начиная с версии 1.1.0 «Возврат» хранит сессию отдельно. Если вход не работает после других программ на ipatool, просто войдите в «Возврат» ещё раз.</p>
<div class="callout"><p><strong>Проверяйте сами</strong>Исходный код открыт. Если вы не готовы доверять сборке, соберите программу из исходников: инструкция есть в README репозитория.</p></div>
"""),
 dict(slug="ustanovka-windows-macos-linux", cover="step-iphone", tag="Инструкция", mins=5,
  title="Первый запуск на Windows, macOS и Linux",
  desc="Драйверы, предупреждения SmartScreen и Gatekeeper, команды для Linux.",
  body=f"""
<h2>Windows 10/11</h2>
<ol><li>Установите <a href="https://apps.microsoft.com/detail/9np83lwlpz9k" target="_blank" rel="noopener noreferrer">Apple Devices</a> из Microsoft Store или iTunes.</li><li>Запустите <code>VozvratSetup.exe</code>. Права администратора не нужны: программа ставится в <code>%LOCALAPPDATA%\\Programs\\Vozvrat</code>.</li><li>Инсталлятор не подписан цифровой подписью, поэтому SmartScreen может показать «Неизвестный издатель». Нажмите «Подробнее», затем «Выполнить в любом случае».</li></ol>
<h2>macOS 12+</h2>
<ol><li>Откройте <code>.dmg</code> (Apple Silicon или Intel) и перетащите «Возврат» в «Программы».</li><li>Программа не подписана сертификатом Apple, поэтому первый запуск macOS заблокирует. Откройте «Системные настройки» → «Конфиденциальность и безопасность» и нажмите «Всё равно открыть» — или выполните в Терминале:</li></ol>
{code("xattr -cr /Applications/Vozvrat.app")}
<p>При первом подключении iPhone нажмите на телефоне «Доверять этому компьютеру».</p>
<h2>Проверьте, что всё работает</h2>
<p>На любой системе после запуска подключите iPhone. Если драйвер на месте, телефон появится в блоке «iPhone».</p>
[[step-iphone|iPhone найден — можно входить в Apple ID и ставить приложения]]
<h2>Linux x86_64</h2>
<p>Установите <code>usbmuxd</code> (Ubuntu/Debian):</p>
{code("sudo apt install usbmuxd")}
<p>В Fedora — <code>sudo dnf install usbmuxd</code>, в Arch — <code>sudo pacman -S usbmuxd</code>. Затем сделайте AppImage исполняемым и запустите:</p>
{code("chmod +x Vozvrat-Linux-x64.AppImage")}
{code("./Vozvrat-Linux-x64.AppImage")}
<p>Если AppImage не запускается из-за FUSE, распакуйте <code>Vozvrat-Linux-x64.tar.gz</code> и запустите <code>Vozvrat/Vozvrat</code>. На Linux интерфейс открывается во вкладке браузера, а программа сама завершается через несколько минут после закрытия вкладки, если ничего не устанавливается.</p>
"""),
 dict(slug="ne-prihodyat-push", cover="queue-cards", tag="Разбор", mins=3,
  title="Почему не приходят push-уведомления у восстановленных приложений",
  desc="Приложение работает, а пуши нет. Это ограничение Apple, а не программы.",
  body="""
<p>Часть пользователей замечает, что восстановленное приложение открывается и работает, но push-уведомления не приходят.</p>
<h2>В чём причина</h2>
<p>Для части удалённых из магазина приложений Apple отключила push-уведомления. Это ограничение на стороне Apple: программа его не создаёт и обойти не может.</p>
[[queue-cards|Если в карточке написано «Установлено», приложение поставлено корректно — отсутствие пушей с установкой не связано]]
<h2>Что можно сделать</h2>
<ul><li>Проверьте, что уведомления для приложения разрешены в настройках iPhone.</li><li>Если приложение умеет сообщать о событиях другим способом (например, SMS или письмом), включите его.</li><li>Учтите это заранее, если для вас критичны мгновенные уведомления.</li></ul>
"""),
 dict(slug="drugie-oshibki", cover="step-search", tag="Справка", mins=3,
  title="Частые ошибки и как их исправить",
  desc="iPhone не найден, драйвер Apple, поиск не находит приложение и другие сообщения.",
  body="""
<h2>«iPhone не найден» / «Не найден драйвер Apple»</h2>
<p>Windows: установите Apple Devices или iTunes. Linux: установите и запустите <code>usbmuxd</code>. Затем переподключите кабель, разблокируйте iPhone и нажмите «Обновить список».</p>
[[step-iphone|Так выглядит найденный iPhone. Если список пуст — проверьте драйвер и кабель]]
<h2>«Нажмите „Доверять этому компьютеру“»</h2>
<p>Разблокируйте iPhone и подтвердите доверие во всплывающем окне.</p>
<h2>Поиск не находит приложение</h2>
<p>Поиск идёт только по каталогу программы, а не по App Store. Он понимает транслит («max» и «макс»), разговорные названия («сбол», «тинькофф») и небольшие опечатки, а подсказки появляются прямо при вводе.</p>
<p>Если приложения в каталоге нет, введите его App Store ID или ссылку вида <code>apps.apple.com/…/id123456789</code> и нажмите «Найти»: такое приложение можно поставить напрямую.</p>
[[step-search|В поле поиска можно ввести название из каталога, App Store ID или ссылку apps.apple.com]]
<h2>macOS: «Не удаётся открыть, так как разработчик не подтверждён»</h2>
<p>Нажмите «Всё равно открыть» в «Конфиденциальности и безопасности» или выполните <code>xattr -cr /Applications/Vozvrat.app</code>.</p>
<h2>Не входит в Apple ID после IPA_Downloader</h2>
<p>Войдите в «Возврат» ещё раз: он хранит сессию отдельно.</p>
<h2>Другие вопросы</h2>
<p>Опишите проблему в <a href="https://github.com/n0hard/back-to-iphone/issues" target="_blank" rel="noopener noreferrer">Issues на GitHub</a>.</p>
"""),
]

NAV = lambda root, blog_active: f"""
  <header class="nav">
    <div class="wrap">
      <a class="brand" href="{root}" aria-label="Возврат — на главную"><span class="brand-ico" aria-hidden="true">↺</span>Возврат</a>
      <ul class="menu" id="menu">
        <li><a href="{root}#features">Возможности</a></li>
        <li><a href="{root}#how">Как это работает</a></li>
        <li><a href="{root}#download">Скачать</a></li>
        <li><a href="{root}blog/"{' class="active"' if blog_active else ''}>Блог</a></li>
        <li><a href="{root}#faq">Вопросы</a></li>
        <li><a href="{GH}" target="_blank" rel="noopener noreferrer">GitHub</a></li>
      </ul>
      <div class="nav-cta">
        <a class="btn sm" href="{root}#download">Скачать</a>
        <button class="burger" id="burger" aria-label="Меню" aria-expanded="false" aria-controls="menu"><span></span><span></span></button>
      </div>
    </div>
  </header>"""

FOOT = lambda root: f"""
  <footer>
    <div class="wrap">
      <div>
        <p>Проект для личного использования. Он не связан с Apple и не распространяет чужие приложения: всё скачивается с серверов Apple под вашим Apple ID и только из вашей истории покупок.</p>
        <p>Используются ipatool (MIT) и pymobiledevice3 (GPL-3.0). &copy; 2026 n0hard.</p>
      </div>
      <div class="foot-links"><a href="{GH}" target="_blank" rel="noopener noreferrer">GitHub</a><a href="{root}blog/">Блог</a><a href="#top">Наверх</a></div>
    </div>
  </footer>"""

JS = """
  <script>
  (function () {
    var burger = document.getElementById('burger'), menu = document.getElementById('menu');
    function setMenu(o) { menu.classList.toggle('open', o); burger.setAttribute('aria-expanded', String(o)); }
    burger.addEventListener('click', function () { setMenu(!menu.classList.contains('open')); });
    Array.prototype.forEach.call(menu.querySelectorAll('a'), function (a) { a.addEventListener('click', function () { setMenu(false); }); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') setMenu(false); });
    Array.prototype.forEach.call(document.querySelectorAll('.code'), function (box) {
      var btn = box.querySelector('.copy'); if (!btn) return;
      var txt = box.querySelector('span').textContent.trim();
      btn.addEventListener('click', function () {
        function ok() { btn.textContent = 'Скопировано'; btn.classList.add('done'); setTimeout(function () { btn.textContent = 'Копировать'; btn.classList.remove('done'); }, 1600); }
        function fb() { var ta = document.createElement('textarea'); ta.value = txt; ta.style.position = 'fixed'; ta.style.opacity = '0'; document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); ok(); } catch (e) { btn.textContent = 'Ошибка'; } document.body.removeChild(ta); }
        if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(txt).then(ok, fb); else fb();
      });
    });
    Array.prototype.forEach.call(document.querySelectorAll('.shot img'), function (img) {
      img.addEventListener('click', function () {
        var lb = document.createElement('div'); lb.className = 'lb'; lb.setAttribute('role', 'dialog'); lb.setAttribute('aria-label', img.alt);
        lb.innerHTML = '<img alt=""><button type="button" aria-label="Закрыть">✕</button>';
        lb.querySelector('img').src = img.src;
        function close() { document.removeEventListener('keydown', esc); lb.remove(); img.focus(); }
        function esc(e) { if (e.key === 'Escape') close(); }
        lb.addEventListener('click', close); document.addEventListener('keydown', esc);
        document.body.appendChild(lb); lb.querySelector('button').focus();
      });
    });
    var f = document.querySelectorAll('.filters [data-f]');
    if (f.length) {
      var items = document.querySelectorAll('[data-tag]'), empty = document.getElementById('empty');
      Array.prototype.forEach.call(f, function (b) {
        b.addEventListener('click', function () {
          Array.prototype.forEach.call(f, function (x) { x.setAttribute('aria-pressed', String(x === b)); });
          var v = b.getAttribute('data-f'), n = 0;
          Array.prototype.forEach.call(items, function (it) { var show = v === 'all' || it.getAttribute('data-tag') === v; it.hidden = !show; if (show) n++; });
          empty.hidden = n > 0;
        });
      });
    }
  })();
  </script>"""

def head(title, desc, url, root, extra=""):
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(desc, quote=True)}" />
  <meta name="theme-color" content="#ffffff" />
  <link rel="canonical" href="{SITE}{url}" />
  <meta property="og:type" content="article" />
  <meta property="og:locale" content="ru_RU" />
  <meta property="og:site_name" content="Возврат" />
  <meta property="og:title" content="{html.escape(title, quote=True)}" />
  <meta property="og:description" content="{html.escape(desc, quote=True)}" />
  <meta property="og:url" content="{SITE}{url}" />
  <meta property="og:image" content="{SITE}og-image.jpg" />
  <meta name="twitter:card" content="summary_large_image" />
  <link rel="stylesheet" href="{root}site.css" />{extra}
</head>
<body id="top">"""

# append blog css to site.css once
css_path = cite / "site.css"
css = css_path.read_text(encoding="utf-8")
if "/* BLOG */" in css:
    css = css[:css.index("/* BLOG */")].rstrip() + "\n"
css_path.write_text(css + BLOG_CSS, encoding="utf-8")

# article pages
for i, p in enumerate(POSTS):
    d = cite / "blog" / p["slug"]
    d.mkdir(parents=True, exist_ok=True)
    others = [q for q in POSTS if q is not p][:4]
    rel = "".join(f'<li><a href="../{q["slug"]}/">{html.escape(q["title"])}</a></li>' for q in others)
    page = head(p["title"] + " — Возврат", p["desc"], f'blog/{p["slug"]}/', "../../") + NAV("../../", True) + f"""
  <main>
    <article class="article">
      <p class="crumbs"><a href="../">← Блог</a></p>
      <span class="tag">{p["tag"]}</span><span class="meta">{p["mins"]} мин</span>
      <h1>{html.escape(p["title"])}</h1>
      <p class="lede">{html.escape(p["desc"])}</p>
      {figs(p["body"], "../../")}
      <div class="cta-box">
        <h2>Вернуть приложение на iPhone</h2>
        <p>Бесплатно, с открытым исходным кодом, для Windows, macOS и Linux.</p>
        <a class="btn" href="../../#download">Скачать «Возврат»</a>
      </div>
      <div class="related"><h3>Читайте также</h3><ul>{rel}</ul></div>
    </article>
  </main>""" + FOOT("../../") + JS + "\n</body>\n</html>\n"
    (d / "index.html").write_text(fixlinks(page), encoding="utf-8")

# blog index
f = POSTS[0]
cards = "".join(f"""
        <a class="card" href="{q["slug"]}/" data-tag="{q["tag"]}">
          <div class="cover"><img src="../img/{q["cover"]}.png" width="{IMG[q["cover"]][0]}" height="{IMG[q["cover"]][1]}" loading="lazy" alt="" /></div>
          <div><span class="tag">{q["tag"]}</span><span class="meta">{q["mins"]} мин</span></div>
          <h2>{html.escape(q["title"])}</h2>
          <p>{html.escape(q["desc"])}</p>
          <span class="go">Читать →</span>
        </a>""" for q in POSTS[1:])
tags = sorted({q["tag"] for q in POSTS})
filters = '<button class="tab" type="button" data-f="all" aria-pressed="true">Все</button>' + "".join(
    f'<button class="tab" type="button" data-f="{t}" aria-pressed="false">{t}</button>' for t in tags)
idx = head("Блог — Возврат", "Как вернуть удалённые из App Store приложения на iPhone: инструкции, разборы и ответы на частые вопросы.", "blog/", "../") + NAV("../", True) + f"""
  <main>
    <section class="blog-hero"><div class="wrap">
      <p class="kicker">Блог</p>
      <h1>Удалённые приложения — и как их вернуть</h1>
      <p>Разбираем, как восстановить приложения из истории покупок Apple ID и что делать, если что-то не получается.</p>
    </div></section>
    <div class="blog-main"><div class="wrap">
      <a class="featured" href="{f["slug"]}/" data-tag="{f["tag"]}">
        <div>
          <span class="tag">{f["tag"]}</span><span class="meta">{f["mins"]} мин</span>
          <h2>{html.escape(f["title"])}</h2>
          <p>{html.escape(f["desc"])}</p>
          <span class="go">Читать →</span>
        </div>
        <div class="art shot-art" aria-hidden="true"><img src="../img/queue-cards.png" width="728" height="250" alt="" /></div>
      </a>
      <div class="filters" role="group" aria-label="Фильтр по рубрикам">{filters}</div>
      <div class="cards">{cards}
      </div>
      <p class="empty" id="empty" hidden>В этой рубрике пока нет статей.</p>
    </div></div>
  </main>""" + FOOT("../") + JS + "\n</body>\n</html>\n"
(cite / "blog").mkdir(exist_ok=True)
(cite / "blog" / "index.html").write_text(fixlinks(idx), encoding="utf-8")
ip = cite / "index.html"; ip.write_text(fixlinks(ip.read_text(encoding="utf-8")), encoding="utf-8")

# sitemap + robots
urls = [SITE, SITE + "blog/"] + [f"{SITE}blog/{p['slug']}/" for p in POSTS]
(cite / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")
(cite / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE}sitemap.xml\n", encoding="utf-8")
print("ok", len(POSTS))
