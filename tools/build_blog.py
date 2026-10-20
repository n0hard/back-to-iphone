"""Собирает блог сайта: cite/blog/*, sitemap.xml, robots.txt и блок стилей блога в cite/site.css.

Статьи описаны в списке POSTS ниже. Скриншоты вставляются меткой [[имя|подпись]] или
[[имя|подпись|narrow]], где имя — файл из cite/img без .png (его размер нужно добавить в IMG).
Запуск из корня репозитория:  python tools/build_blog.py
"""
import pathlib, html, json, re


cite = pathlib.Path(__file__).resolve().parent.parent / "cite"
SITE = "https://vozvratapp.ru/"
GH = "https://github.com/n0hard/back-to-iphone"
TG = "https://t.me/vzvrt_app"  # поддержка в Telegram
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
  "app-updates": (728, 368), "download-progress": (728, 346), "update-window": (572, 387),
  "update-downloading": (572, 368), "update-banner": (728, 104), "catalog-marks": (728, 522),
  "restore-progress": (728, 259), "restore-found": (728, 461),
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
<p>Найдите приложение в каталоге (в нём %APPS%) или введите название, App Store ID либо ссылку вида <code>apps.apple.com/…/id123456789</code>. Нажмите «Установить». Не отключайте кабель и не блокируйте экран, пока идёт установка.</p>
[[step-catalog|Поиск по каталогу с подсказками при вводе и каталог по категориям. У каждой карточки — «Установить» и «Все варианты…»]]
<p>Можно нажать «Установить» у нескольких приложений сразу: они встанут в очередь. Отменить можно и ожидающие, и идущую загрузку — кнопкой «Отменить» в карточке.</p>
[[queue-cards|Очередь: первое приложение скачивается, следующие ждут своей очереди, готовое отмечено «Установлено»]]
<h2>Вернуть много приложений сразу</h2>
<p>Если вы пользовались многими банками, их не нужно ставить по одному: <a href="../vernut-vse-srazu/">«Вернуть всё сразу»</a> найдёт в истории покупок всё, чего нет на iPhone. А то, что уже стоит, в каталоге отмечено «✓ На iPhone».</p>
<h2>Дальше: обновления</h2>
<p>App Store такие приложения не обновляет, но «Возврат» умеет: <a href="../obnovleniya/">как обновлять приложения и саму программу</a>.</p>
<h2>Если что-то пошло не так</h2>
<ul><li>Нет в истории покупок — <a href="../ne-v-istorii-pokupok/">что делать</a>.</li><li>Нужна более новая iOS — <a href="../staraya-versiya-prilozheniya/">как поставить старую версию</a>.</li><li>iPhone не находится — проверьте драйвер и разрешение «Доверять этому компьютеру».</li></ul>
"""),
 dict(slug="vernut-vse-srazu", cover="restore-found", tag="Инструкция", mins=4,
  title="Как вернуть все банки и приложения на iPhone сразу",
  desc="Не нужно вспоминать, что вы когда-то скачивали: «Возврат» сам найдёт в истории покупок всё, чего нет на iPhone, и поставит одной кнопкой.",
  body="""
<p>Сбер, ВТБ, Альфа, Газпромбанк, Почта Банк — если вы пользовались многими приложениями, искать и ставить каждое по отдельности долго. С версии 1.4 «Возврат» делает это сам: проверяет историю покупок вашего Apple ID и показывает всё, что можно вернуть.</p>
<h2>Как вернуть всё сразу</h2>
<ol>
<li>Войдите в Apple ID и подключите iPhone, как при обычной установке.</li>
<li>В карточке «Вернуть всё сразу» выберите категорию. По умолчанию стоят «Банки», можно выбрать другую или весь каталог.</li>
<li>Нажмите «Найти мои приложения». Программа проверит каждое приложение категории, которого ещё нет на iPhone.</li>
</ol>
[[restore-progress|Проверка идёт без скачивания — по запросу к App Store на каждое приложение. Её можно остановить]]
<p>Ничего при этом не скачивается: программа только спрашивает App Store, есть ли приложение в истории покупок. Apple отвечает в среднем за несколько секунд на приложение, поэтому банки проверяются примерно за 5 минут, а весь каталог из %APPS-GEN% — за 10–15 минут. Проверку можно остановить в любой момент.</p>
<ol start="4">
<li>Когда проверка закончится, появится список найденного. Снимите галочки с того, что ставить не нужно.</li>
<li>Нажмите «Вернуть выбранные» — приложения встанут в очередь и поставятся по одному.</li>
</ol>
[[restore-found|Найденные в истории покупок приложения, которых ещё нет на iPhone]]
<h2>Что уже стоит на iPhone</h2>
<p>Приложения, которые уже есть на телефоне, проверка пропускает. В каталоге они отмечены строкой «✓ На iPhone» с установленной версией, а если стоит не основной вариант — с его названием.</p>
[[catalog-marks|СберБанк и Т-Банк уже на iPhone — у них зелёная отметка с версией]]
<h2>Если что-то не нашлось</h2>
<ul>
<li><strong>Приложения нет в списке.</strong> Значит, с этого Apple ID оно не скачивалось. Банки выходили под разными названиями — проверка смотрит все варианты, так что попробуйте другой Apple ID, если пользовались несколькими.</li>
<li><strong>«Нет в магазине вашей страны».</strong> Приложение есть в каталоге, но его нет в магазине страны вашего Apple ID (так бывает, например, с ChatGPT). С таким аккаунтом его не скачать.</li>
<li><strong>«Не удалось проверить».</strong> Сеть или App Store не ответили вовремя. Программа сама перепроверяет такие приложения в конце, а если не вышло и так — покажет причину и список. Запустите проверку ещё раз чуть позже.</li>
</ul>
<div class="callout"><p><strong>Дальше — обновления</strong>Возвращённые приложения App Store не обновляет. Как держать их свежими одной кнопкой — в <a href="../obnovleniya/">статье об обновлениях</a>.</p></div>
"""),
 dict(slug="obnovleniya", cover="app-updates", tag="Инструкция", mins=4,
  title="Как обновлять «Возврат» и установленные приложения",
  desc="Удалённые из App Store приложения сами не обновляются. Показываем, как обновить их одной кнопкой — и как обновляется сама программа.",
  body="""
<p>Приложения, которые вернули на iPhone через «Возврат», App Store не обновляет: в магазине их больше нет. Начиная с версии 1.3.0 программа делает это сама — и сама же обновляется, когда выходит её новая версия.</p>
<h2>Обновить приложения на iPhone</h2>
<ol>
<li>Войдите в Apple ID и подключите iPhone, как при обычной установке.</li>
<li>В блоке «Обновления приложений» нажмите «Проверить обновления». Проверка занимает до минуты: программа сравнивает версии на iPhone с последними версиями в истории покупок вашего Apple ID.</li>
<li>Нажмите «Обновить» у нужного приложения или «Обновить все».</li>
</ol>
[[app-updates|Для каждого приложения видно, какая версия стоит и какая доступна]]
<p>Обновления встают в общую очередь установок, прогресс виден в карточке приложения. Данные приложения при обновлении сохраняются: новая версия ставится поверх старой.</p>
[[download-progress|Скачивание с процентами и кнопкой «Отменить»; следующее приложение ждёт в очереди]]
<div class="callout"><p><strong>Если последняя версия не подходит</strong>Новая версия может требовать iOS новее, чем на вашем iPhone. Тогда программа скажет об этом перед установкой — откройте «Версии» и выберите подходящую, как описано в <a href="../staraya-versiya-prilozheniya/">статье про старые версии</a>.</p></div>
<h2>Какие приложения проверяются</h2>
<p>Программа проверяет приложения из своего каталога и те, что ставила сама. Остальные приложения на iPhone она не трогает — их обновляет App Store.</p>
<h2>Как обновляется сама программа</h2>
<p>При каждом запуске «Возврат» проверяет, не вышла ли новая версия. Нажмите «Обновить» — программа скачает файл для вашей системы, проверит его контрольную сумму, установит и откроется заново. Заходить на сайт или GitHub не нужно.</p>
<p>Обновления бывают двух видов:</p>
<ul>
<li><strong>Обычное</strong> — сверху появляется плашка «Доступна новая версия». Программой можно пользоваться дальше, а обновиться — когда удобно, или отложить кнопкой «Позже».</li>
<li><strong>Обязательное</strong> — с важными исправлениями. Программа показывает окно новой версии и не работает, пока вы не обновитесь.</li>
</ul>
[[update-banner|Обычное обновление: плашка сверху, работать можно дальше]]
[[update-window|Обязательное обновление: окно новой версии|narrow]]
[[update-downloading|Обновление скачивается — займёт около минуты|narrow]]
<div class="callout"><p><strong>Если у вас 1.2.1 или старше</strong>Автообновление появилось в версии 1.3.0, поэтому один раз установите новую версию вручную со <a href="../../#download">страницы загрузки</a>. Дальше обновления будут ставиться кнопкой.</p></div>
<h2>Если обновиться не получается</h2>
<ul>
<li><strong>«Не удалось проверить обновления».</strong> Программе нужен доступ к GitHub. Проверьте интернет и нажмите «Повторить».</li>
<li><strong>Обычное обновление не установилось.</strong> Программа продолжит работать, а причина будет видна на плашке — нажмите «Обновить» ещё раз позже.</li>
<li><strong>«Нет прав на запись в папку».</strong> На macOS перенесите «Возврат» в «Программы», на Linux — в папку, куда у вас есть права на запись. Затем повторите.</li>
<li><strong>«Файлы новой версии ещё загружаются».</strong> Версия только что вышла — подождите пару минут и повторите.</li>
</ul>
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
<div class="callout"><p><strong>Обновления</strong>Удалённые приложения не обновляются через App Store, но «Возврат» находит для них версии новее в истории покупок и ставит одной кнопкой — <a href="../obnovleniya/">подробнее</a>.</p></div>
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
<p>«Возврат» хранит сессию отдельно от других программ на ipatool: на macOS и Linux — начиная с версии 1.1.0, на Windows — с версии 1.4.1 (до неё на Windows сессия лежала в общей папке <code>.ipatool</code>, и 1.4.1 при первом запуске переносит её к себе). Если вход не работает после других программ на ipatool, просто войдите в «Возврат» ещё раз.</p>
<div class="callout"><p><strong>Проверяйте сами</strong>Исходный код открыт. Если вы не готовы доверять сборке, соберите программу из исходников: инструкция есть в README репозитория.</p></div>
"""),
 dict(slug="ustanovka-windows-macos-linux", cover="step-iphone", tag="Инструкция", mins=5,
  title="Первый запуск на Windows, macOS и Linux",
  desc="Драйверы, предупреждения SmartScreen и Gatekeeper, команды для Linux.",
  body=f"""
<h2>Windows 10/11</h2>
<ol><li>Установите <a href="https://apps.microsoft.com/detail/9np83lwlpz9k" target="_blank" rel="noopener noreferrer">Apple Devices</a> из Microsoft Store или iTunes.</li><li>Запустите <code>VozvratSetup.exe</code>. Права администратора не нужны: программа ставится в <code>%LOCALAPPDATA%\\Programs\\Vozvrat</code>.</li><li>Инсталлятор не подписан цифровой подписью, поэтому SmartScreen может показать «Неизвестный издатель». Нажмите «Подробнее», затем «Выполнить в любом случае».</li></ol>
<p>Окно программы работает на Microsoft Edge WebView2 — в Windows 10 и 11 он обычно уже есть. Если вместо программы появилось сообщение «Не удалось открыть окно программы», установите или обновите <a href="https://go.microsoft.com/fwlink/p/?LinkId=2124703" target="_blank" rel="noopener noreferrer">WebView2 Runtime</a>.</p>
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
<h2>Обновления программы</h2>
<p>Ставить новые версии вручную больше не нужно: при выходе новой версии «Возврат» покажет окно с кнопкой «Обновить» и обновится сам. Для этого на macOS программа должна лежать в «Программах», а на Linux — в папке, куда у вас есть права на запись. <a href="../obnovleniya/">Подробнее об обновлениях</a>.</p>
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
<h2>«Не удалось проверить обновления»</h2>
<p>При запуске «Возврат» проверяет обновления на GitHub — в том числе обязательные, без которых старой версией пользоваться нельзя. Проверьте подключение к интернету и нажмите «Повторить».</p>
<h2>«Не удалось открыть окно программы» (Windows)</h2>
<p>Окно программы работает на Microsoft Edge WebView2. Установите или обновите <a href="https://go.microsoft.com/fwlink/p/?LinkId=2124703" target="_blank" rel="noopener noreferrer">WebView2 Runtime</a> и запустите «Возврат» снова. Сразу после обновления программа сама пробует открыть окно ещё раз, так что это сообщение означает именно отсутствие WebView2.</p>
<h2>«Вернуть всё сразу»: «не удалось проверить» или «нет в магазине вашей страны»</h2>
<p>«Нет в магазине вашей страны» — приложения нет в магазине страны вашего Apple ID, с таким аккаунтом его не скачать. «Не удалось проверить» — App Store или сеть не ответили вовремя: программа перепроверяет такие приложения сама, а если не вышло — запустите проверку позже. Подробнее — в <a href="../vernut-vse-srazu/">статье «Вернуть всё сразу»</a>.</p>
<h2>«Нет прав на запись в папку» при обновлении</h2>
<p>Программа не может заменить сама себя. На macOS перенесите «Возврат» из «Загрузок» в «Программы», на Linux — в папку, куда у вас есть права на запись, и повторите. Подробнее — в <a href="../obnovleniya/">статье об обновлениях</a>.</p>
<h2>Не входит в Apple ID после IPA_Downloader</h2>
<p>Войдите в «Возврат» ещё раз: он хранит сессию отдельно.</p>
<h2>Не нашли ответа?</h2>
<p>Напишите в поддержку в Telegram — <a href="https://t.me/vzvrt_app" target="_blank" rel="noopener noreferrer">@vzvrt_app</a>. Приложите текст ошибки, версию «Возврата» (видна рядом с названием в окне программы), систему компьютера и модель iPhone с версией iOS.</p>
<p>Ошибку в программе можно описать и в <a href="https://github.com/n0hard/back-to-iphone/issues" target="_blank" rel="noopener noreferrer">Issues на GitHub</a>.</p>
"""),
]

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

# ---------- даты статей (для читателей, разметки Article и sitemap) ----------
# (опубликовано, обновлено). При правке статьи обновите вторую дату.
DATES = {
    "kak-vernut-udalennye-prilozheniya": ("2026-10-12", "2026-10-14"),
    "vernut-vse-srazu": ("2026-10-14", "2026-10-19"),
    "obnovleniya": ("2026-10-13", "2026-10-14"),
    "ne-v-istorii-pokupok": ("2026-10-12", "2026-10-12"),
    "staraya-versiya-prilozheniya": ("2026-10-12", "2026-10-14"),
    "kak-eto-rabotaet": ("2026-10-12", "2026-10-12"),
    "bezopasnost-apple-id": ("2026-10-12", "2026-10-19"),
    "ustanovka-windows-macos-linux": ("2026-10-12", "2026-10-14"),
    "ne-prihodyat-push": ("2026-10-12", "2026-10-12"),
    "drugie-oshibki": ("2026-10-12", "2026-10-19"),
}
for p in POSTS:
    p["date"], p["updated"] = DATES[p["slug"]]
SITE_UPDATED = max(p["updated"] for p in POSTS)
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября",
          "декабря"]


def human_date(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} {MONTHS[m - 1]} {y}"


# ---------- числа каталога: берутся из app/catalog.json при каждой сборке ----------
def plural(n, one, few, many):
    if n % 10 == 1 and n % 100 != 11:
        return one
    return few if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else many


_apps = json.loads((cite.parent / "app" / "catalog.json").read_text(encoding="utf-8"))["apps"]
_base = lambda n: re.sub(r"\s*\([^()]*\)\s*$", "", n).strip() or n
N_APPS = len(_apps)
N_CARDS = len({(a.get("category"), _base(a["name"])) for a in _apps})
COUNTS = {  # <span data-n="ключ">…</span> на страницах и %КЛЮЧ% в текстах статей
    "apps-num": str(N_APPS),
    "apps": f"{N_APPS} {plural(N_APPS, 'приложение', 'приложения', 'приложений')}",
    "apps-gen": f"{N_APPS} {plural(N_APPS, 'приложения', 'приложений', 'приложений')}",
    "cards": f"{N_CARDS} {plural(N_CARDS, 'карточку', 'карточки', 'карточек')}",
}


def counts(t):
    t = re.sub(r'(<span data-n="([a-z-]+)">)[^<]*(</span>)', lambda m: m.group(1) + COUNTS[m.group(2)] + m.group(3), t)
    return re.sub(r"%([A-Z-]+)%", lambda m: COUNTS.get(m.group(1).lower(), m.group(0)), t)


def cleanlinks(t):
    """Ссылки без index.html — те же адреса, что в canonical и sitemap (GitHub Pages открывает папку сам)."""
    t = re.sub(r'href="((?:\.\./)*(?:[a-z0-9-]+/)*)index\.html(#[^"]*)?"',
               lambda m: f'href="{m.group(1) or "./"}{m.group(2) or ""}"', t)
    return t


# ---------- коды подтверждения для Google Search Console и Яндекс.Вебмастера ----------
# Вставьте значение content из выданного мета-тега — и пересоберите сайт.
GOOGLE_VERIFICATION = ""
YANDEX_VERIFICATION = ""


def icons(root):
    verify = ""
    if GOOGLE_VERIFICATION:
        verify += f'\n  <meta name="google-site-verification" content="{GOOGLE_VERIFICATION}" />'
    if YANDEX_VERIFICATION:
        verify += f'\n  <meta name="yandex-verification" content="{YANDEX_VERIFICATION}" />'
    return (f'  <link rel="icon" type="image/png" sizes="32x32" href="{root}favicon-32.png" />\n'
            f'  <link rel="icon" type="image/png" sizes="192x192" href="{root}favicon-192.png" />\n'
            f'  <link rel="apple-touch-icon" href="{root}apple-touch-icon.png" />{verify}')


NAV = lambda root, blog_active: f"""
  <header class="nav">
    <div class="wrap">
      <a class="brand" href="{root or './'}" aria-label="Возврат — на главную"><span class="brand-ico" aria-hidden="true">↺</span>Возврат</a>
      <ul class="menu" id="menu">
        <li><a href="{root}#features">Возможности</a></li>
        <li><a href="{root}#screens">Интерфейс</a></li>
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

FOOT_GUIDES = ["kak-vernut-udalennye-prilozheniya", "vernut-vse-srazu", "obnovleniya", "staraya-versiya-prilozheniya"]


def FOOT(root):
    guides = "".join(f'<a href="{root}blog/{s}/">{html.escape(next(p["title"] for p in POSTS if p["slug"] == s))}</a>'
                     for s in FOOT_GUIDES)
    ext = 'target="_blank" rel="noopener noreferrer"'
    return f"""
  <footer>
    <div class="wrap">
      <div class="foot-cols">
        <div class="foot-col"><h4>Возврат</h4>
          <a href="{root}#features">Возможности</a><a href="{root}#download">Скачать</a>
          <a href="{GH}/releases" {ext}>Все версии</a><a href="{GH}" {ext}>Исходный код</a></div>
        <div class="foot-col wide"><h4>Инструкции</h4>{guides}<a href="{root}blog/">Все статьи блога</a></div>
        <div class="foot-col"><h4>Помощь</h4>
          <a href="{root}#faq">Вопросы и ответы</a><a href="{root}blog/drugie-oshibki/">Частые ошибки</a>
          <a href="{TG}" {ext}>Поддержка в Telegram</a><a href="{GH}/issues" {ext}>Сообщить о проблеме на GitHub</a></div>
      </div>
      <div class="foot-legal">
        <p>Проект для личного использования. Он не связан с Apple и не распространяет чужие приложения: всё скачивается с серверов Apple под вашим Apple ID и только из вашей истории покупок. Используйте на свой страх и риск и соблюдайте условия Apple.</p>
        <p>Лицензия <a href="{GH}/blob/main/LICENSE" {ext}>GPL-3.0</a>. Используются <a href="https://github.com/majd/ipatool" {ext}>ipatool</a> (MIT) и <a href="https://github.com/doronz88/pymobiledevice3" {ext}>pymobiledevice3</a> (GPL-3.0). &copy; 2026 n0hard.</p>
      </div>
    </div>
  </footer>"""


def ld(data):
    return '\n  <script type="application/ld+json">\n  ' + json.dumps(data, ensure_ascii=False) + "\n  </script>"


def head(title, desc, url, root, extra="", og_type="article"):
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(desc, quote=True)}" />
  <meta name="robots" content="index, follow, max-image-preview:large" />
  <meta name="theme-color" content="#ffffff" />
  <link rel="canonical" href="{SITE}{url}" />
{icons(root)}
  <meta property="og:type" content="{og_type}" />
  <meta property="og:locale" content="ru_RU" />
  <meta property="og:site_name" content="Возврат" />
  <meta property="og:title" content="{html.escape(title, quote=True)}" />
  <meta property="og:description" content="{html.escape(desc, quote=True)}" />
  <meta property="og:url" content="{SITE}{url}" />
  <meta property="og:image" content="{SITE}og-cover.jpg" />
  <meta property="og:image:width" content="1200" />
  <meta property="og:image:height" content="630" />
  <meta name="twitter:card" content="summary_large_image" />
  <link rel="stylesheet" href="{root}site.css" />{extra}
</head>
<body id="top">"""


def breadcrumbs(items):
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": name, "item": url} for i, (name, url) in enumerate(items)]}


def finish(t):
    return counts(cleanlinks(t))


# append blog css to site.css once
css_path = cite / "site.css"
css = css_path.read_text(encoding="utf-8")
if "/* BLOG */" in css:
    css = css[:css.index("/* BLOG */")].rstrip() + "\n"
css_path.write_text(css + BLOG_CSS, encoding="utf-8")

AUTHOR = {"@type": "Person", "name": "n0hard", "url": "https://github.com/n0hard"}

# article pages
for i, p in enumerate(POSTS):
    d = cite / "blog" / p["slug"]
    d.mkdir(parents=True, exist_ok=True)
    others = [q for q in POSTS if q is not p][:4]
    rel = "".join(f'<li><a href="../{q["slug"]}/">{html.escape(q["title"])}</a></li>' for q in others)
    url = f'{SITE}blog/{p["slug"]}/'
    images = [f"{SITE}img/{m}.png" for m in re.findall(r"\[\[([a-z0-9-]+)\|", p["body"])] or [f"{SITE}img/{p['cover']}.png"]
    data = {"@context": "https://schema.org", "@graph": [
        {"@type": "Article", "headline": p["title"], "description": p["desc"], "inLanguage": "ru",
         "datePublished": p["date"], "dateModified": p["updated"], "author": AUTHOR, "publisher": AUTHOR,
         "image": images, "mainEntityOfPage": url},
        breadcrumbs([("Возврат", SITE), ("Блог", SITE + "blog/"), (p["title"], url)])]}
    dates = (f'Опубликовано {human_date(p["date"])}' if p["date"] == p["updated"]
             else f'Обновлено {human_date(p["updated"])}')
    page = head(p["title"] + " — Возврат", p["desc"], f'blog/{p["slug"]}/', "../../", ld(data)) + NAV("../../", True) + f"""
  <main>
    <article class="article">
      <nav class="crumbs" aria-label="Навигация"><a href="../../">Главная</a> <span aria-hidden="true">›</span> <a href="../">Блог</a></nav>
      <span class="tag">{p["tag"]}</span><span class="meta">{p["mins"]} мин · <time datetime="{p["updated"]}">{dates}</time></span>
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
    (d / "index.html").write_text(finish(page), encoding="utf-8")

# blog index
f = POSTS[0]
cards = "".join(f"""
        <a class="card" href="{q["slug"]}/" data-tag="{q["tag"]}">
          <div class="cover"><img src="../img/{q["cover"]}.png" width="{IMG[q["cover"]][0]}" height="{IMG[q["cover"]][1]}" loading="lazy" alt="" /></div>
          <div><span class="tag">{q["tag"]}</span><span class="meta">{q["mins"]} мин · {human_date(q["updated"])}</span></div>
          <h2>{html.escape(q["title"])}</h2>
          <p>{html.escape(q["desc"])}</p>
          <span class="go">Читать →</span>
        </a>""" for q in POSTS[1:])
tags = sorted({q["tag"] for q in POSTS})
filters = '<button class="tab" type="button" data-f="all" aria-pressed="true">Все</button>' + "".join(
    f'<button class="tab" type="button" data-f="{t}" aria-pressed="false">{t}</button>' for t in tags)
blog_ld = {"@context": "https://schema.org", "@graph": [
    {"@type": "Blog", "name": "Блог «Возврата»", "url": SITE + "blog/", "inLanguage": "ru",
     "blogPost": [{"@type": "BlogPosting", "headline": q["title"], "url": f'{SITE}blog/{q["slug"]}/',
                   "datePublished": q["date"], "dateModified": q["updated"]} for q in POSTS]},
    breadcrumbs([("Возврат", SITE), ("Блог", SITE + "blog/")])]}
idx = head("Блог — Возврат", "Как вернуть удалённые из App Store приложения на iPhone: инструкции, разборы и ответы на частые вопросы.",
           "blog/", "../", ld(blog_ld), og_type="website") + NAV("../", True) + f"""
  <main>
    <section class="blog-hero"><div class="wrap">
      <p class="kicker">Блог</p>
      <h1>Удалённые приложения — и как их вернуть</h1>
      <p>Разбираем, как восстановить приложения из истории покупок Apple ID и что делать, если что-то не получается.</p>
    </div></section>
    <div class="blog-main"><div class="wrap">
      <a class="featured" href="{f["slug"]}/" data-tag="{f["tag"]}">
        <div>
          <span class="tag">{f["tag"]}</span><span class="meta">{f["mins"]} мин · {human_date(f["updated"])}</span>
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
(cite / "blog" / "index.html").write_text(finish(idx), encoding="utf-8")

# главная: общий подвал, значки, коды подтверждения и числа каталога
ip = cite / "index.html"
home = ip.read_text(encoding="utf-8")
home = re.sub(r"\n  <footer>.*?</footer>", lambda m: FOOT(""), home, count=1, flags=re.S)
home = re.sub(r"  <!-- icons -->\n.*?  <!-- /icons -->", lambda m: "  <!-- icons -->\n" + icons("") + "\n  <!-- /icons -->",
              home, count=1, flags=re.S)
_ver = {}
exec((cite.parent / "app" / "version.py").read_text(encoding="utf-8"), _ver)
home = re.sub(r'"softwareVersion": "[^"]*"', f'"softwareVersion": "{_ver["VERSION"]}"', home)
home = re.sub(r'(<span data-v="version">)[^<]*(</span>)', lambda m: m.group(1) + _ver["VERSION"] + m.group(2), home)
ip.write_text(finish(home), encoding="utf-8")

# страница 404: GitHub Pages показывает её для любого несуществующего адреса — ссылки только абсолютные
ROOT_PATH = "/"
nf = head("Страница не найдена — Возврат", "Такой страницы нет на сайте «Возврата».", "404.html", ROOT_PATH) \
    .replace('<meta name="robots" content="index, follow, max-image-preview:large" />', '<meta name="robots" content="noindex" />') \
    + NAV(ROOT_PATH, False) + f"""
  <main>
    <section class="blog-hero"><div class="wrap">
      <p class="kicker">Ошибка 404</p>
      <h1>Такой страницы нет</h1>
      <p>Возможно, ссылка устарела. Начните с главной страницы или загляните в блог.</p>
      <p style="margin-top:28px"><a class="btn" href="{ROOT_PATH}">На главную</a> <a class="btn ghost" href="{ROOT_PATH}blog/">Блог</a></p>
    </div></section>
  </main>""" + FOOT(ROOT_PATH) + JS + "\n</body>\n</html>\n"
(cite / "404.html").write_text(counts(nf), encoding="utf-8")

# sitemap: адреса, даты изменения и скриншоты статей + robots
SCREENS_HOME = ["main", "catalog-marks", "restore-found", "app-updates", "update-banner", "variants", "versions"]


def sm_url(loc, lastmod, imgs=()):
    images = "".join(f"\n    <image:image><image:loc>{SITE}img/{m}.png</image:loc></image:image>" for m in imgs)
    return f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>{lastmod}</lastmod>{images}\n  </url>\n"


sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
           'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n'
           + sm_url(SITE, SITE_UPDATED, SCREENS_HOME) + sm_url(SITE + "blog/", SITE_UPDATED)
           + "".join(sm_url(f"{SITE}blog/{p['slug']}/", p["updated"],
                            dict.fromkeys(re.findall(r"\[\[([a-z0-9-]+)\|", p["body"]))) for p in POSTS)
           + "</urlset>\n")
(cite / "sitemap.xml").write_text(sitemap, encoding="utf-8")
(cite / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE}sitemap.xml\n", encoding="utf-8")
print("ok", len(POSTS), "статей;", COUNTS["apps"], "в", COUNTS["cards"])
