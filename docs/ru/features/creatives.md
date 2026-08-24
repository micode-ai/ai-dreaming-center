# Creative pipeline (промо-креативы)

Тот же цикл, что у статей — предложение, согласование, сборка агентом
площадки, просмотр, доработка по замечаниям, публикация — но для рекламных
креативов: рендеров (картинка/видео) под несколько форматов и локалей плюс
текста поста. Волна E (после трёх волн статей) сознательно **переиспользует
дисциплину, а не схему**: своя таблица `creative_proposals`, но общий модуль
git-публикации, общая венью-резолюция, общая нормализация publish-режима —
всё это импортировано из [`articles`](../../../dreaming/services/articles.py),
а не скопировано. Этот документ описывает только то, чем creatives отличаются;
за общей механикой — в [`features/articles.md`](articles.md).

Публикация — это коммит, не постинг через API соцсетей (осознанное решение,
принятое до дизайна: единственное необратимое действие в конвейере не должно
зависеть от токенов каждой площадки). Видео — часть первой волны, не
последующая доработка: рилсы — то, как контент сейчас потребляют.

## Содержание

- [Чем creatives отличаются от articles](#чем-creatives-отличаются-от-articles)
- [Жизненный цикл кампании](#жизненный-цикл-кампании)
- [Таблица `creative_proposals`](#таблица-creative_proposals)
- [Слаг кампании и вложения](#слаг-кампании-и-вложения)
- [Кто подаёт предложения](#кто-подаёт-предложения-1)
- [Approve: диспетчеризация сборщика](#approve-диспетчеризация-сборщика)
- [Write-back API](#write-back-api)
- [Preview и роут медиа](#preview-и-роут-медиа)
- [Revise — доработка кампании](#revise--доработка-кампании)
- [Publish: коммит](#publish-коммит-1)
- [Известный пробел: reconcile не подключён](#известный-пробел-reconcile-не-подключён)
- [Что отложено с волны E](#что-отложено-с-волны-e)
- [Настройки](#настройки-1)
- [Два скилла](#два-скилла)
- [Cross-references](#cross-references-1)

## Чем creatives отличаются от articles

Три площадки уже делают рекламу руками, и центр в этом не участвовал:
`accounting-ai-agent` (77 файлов — HTML-шаблон на формат/локаль, `assets/`,
`build.mjs`, `build-reel.mjs`, `renders/pl/`, тексты в `creatives/captions/`),
`ai-budget-assistant` (249 файлов — исходные скриншоты, `renders/`, тексты в
`docs/marketing/copy/`), лендинг (310 файлов — `<slug>/src/`, `<slug>/renders/`).
Тот же урок, что дали волны статей: **форму владеет площадка**, центр не
должен знать ни одну из них.

Своя таблица, а не флаг `kind` на статье: у креатива есть форматы, вложения и
бинарные результаты, которых у статьи нет, а четыре nullable-колонки на каждой
статье заставили бы каждый запрос по статьям объясняться.

Отличия от articles по существу:

- **Вложения.** Человек прикрепляет исходный материал (скриншоты, скринкасты)
  **до** запуска сборщика — этого у статей нет вовсе.
- **Слаг фиксируется при создании предложения**, не выбирается сборщиком (у
  статей — наоборот, `slug_hint` лишь seed, финальный слаг решает писатель).
- **Роут выдачи медиа** — рекламу нельзя согласовать не увидев; у статей
  такого роута нет, превью текстовое.
- Статус сборки называется `making`, не `writing`; кнопка — "Собрать", не
  "Согласовать и написать".

## Жизненный цикл кампании

```
proposed --(approve)--> making --(made, verify_ok или нет)--> drafted --(publish)--> published
   |                        ^                                     |
   |                        |_______________(revise / retry)______|
   |
   +--(reject)--> rejected --(restore)--> proposed
   +--(done)----> done -----(restore)--> proposed

making --(made, error_message)--> failed --(approve/retry)--> making
making --(cancel, вручную)-------> failed
failed  --(done)----------------> done
```

Тот же граф, что у статей, с переименованным `writing → making`, плюс
терминальный `done` («уже реализовано»), которого у статей нет. Он отделён от
`rejected` намеренно: отказ означает, что идея не годится, `done` — что она
верна, а работа уже сделана вручную. На дедуп это не влияет — уникальный
индекс `(project_id, slug_hint)` не даёт сканеру предложить слаг заново при
любом из двух исходов, — но месяц спустя очередь читается честнее. Достижим
из `proposed` и `failed`, обратим тем же `restore`, что и `rejected`; из
`making` запрещён (`409`) — там ещё работает сессия.
`approved` — так же формально объявлен дисптчеруемым
(`_CREATIVE_DISPATCHABLE`), но так же недостижим на практике: approve сразу
переводит `proposed → making`.

## Таблица `creative_proposals`

Тоже не задокументирована в [`schema.md`](../schema.md). Столбцы, которых нет
у `article_proposals`:

| Столбец | Смысл |
|---|---|
| `formats` | форматы кампании (переопределяет `creative_formats` площадки) |
| `maker_agent` | аналог `writer_agent` |
| `made_at` | аналог `written_at` |

Остальное — `project_id`, `target_project_id`, `source`, `source_ref`,
`evidence`, `title`, `angle`, `slug_hint`, `locales`, `tags_json`,
`related_product`, `status`, `draft_ref`, `verify_output`, `verify_ok`,
`verify_label`, `commit_ref`, `session_id`, `error_message`,
`revision_notes` — один в один со статьями, включая
`UNIQUE(project_id, slug_hint)`.

`draft_ref` здесь — **и рендеры, и текст поста вперемешку**: превью различает
их по расширению (`creatives.media_type` / `creatives.is_copy`), а не по
отдельной колонке, которая могла бы разойтись с этой.

## Слаг кампании и вложения

`creatives.campaign_slug(title)` — **не** `articles.slugify`. Та роняет
кириллицу нарочно (slug_hint у статей — только seed для писателя); слаг
кампании — имя каталога, в который вложения лягут **до** запуска сборщика, и
он никогда не меняется. Поэтому кириллица транслитерируется
(`Дашборды и отчёты` → `dashbordy-i-otchety`), а не отбрасывается: пустой слаг
свёл бы разные кампании в один каталог по уникальному индексу — молча, как
"дубликат", которым это не является.

Вложения пишутся в `<creative_dir>/<slug>/src/`
(`_store_attachments` в [`project_creatives.py:107`](../../../dreaming/routes/project_creatives.py),
общая функция для формы добавления и отдельного роута attach). Исходит из
того, что вызывающий небрежен, и отказывает в любом случае:

- Только basename выживает (`creatives.safe_upload_name`) — путь
  **сокращается**, а не отвергается, потому что браузер с `<input type=file>`
  честно присылает путь.
- Имя нормализуется до `[a-z0-9._-]`, расширение — по белому списку
  (`UPLOAD_EXTS`: png/jpg/jpeg/gif/webp/mp4/mov/webm — **без svg**: svg
  выполнился бы как скрипт при отдаче роутом медиа с origin центра и куками
  оператора).
- Размер ограничивается **по ходу потока** (64 МБ), не после — файл,
  превысивший лимит, стирается немедленно.
- Путь затем проверяется тем же валидатором, что publish
  (`article_publish._validate_paths`) — роут не может записать туда, откуда
  публикация не смогла бы закоммитить.

Прикреплять можно, пока кампания в `proposed` / `approved` / `failed` /
`drafted` (`_CREATIVE_ATTACHABLE`) — не во время `making`: сборщик уже
залистил каталог, и файл, приехавший под ним, — гонка без выигрыша.

## Кто подаёт предложения

Два источника вместо четырёх у статей — `_ARTICLE_SOURCES` (общий белый список
в [`api.py`](../../../dreaming/routes/api.py)) допускает все четыре значения
(`project_scan`, `radar`, `center`, `manual`) и для creatives тоже, но
**ни один роут сегодня не производит `radar` или `center`** — ни у AI Radar,
ни у Product Ideas нет кнопки "Предложить кампанию" (в отличие от статей).
Реально работают:

| Источник | `source` | Как |
|---|---|---|
| Слэш-команда `/creative-ideas-scan` | `project_scan` | `POST /api/p/{slug}/creatives/ingest`, дедуп через `GET .../creatives/list` |
| Человек | `manual` | `POST /p/{slug}/creatives/add` — тема, вводный промпт, площадка **и вложения одним шагом** |

Ручная форма креативов, в отличие от статей, принимает файлы прямо здесь
(`enctype="multipart/form-data"`, форма `_creative_add`,
[`project_creatives.py:304`](../../../dreaming/routes/project_creatives.py)):
кампания, которую предлагает оператор, обычно существует именно потому, что у
него есть материал, и заставлять искать карточку заново, чтобы его передать —
шаг, который обязательно будет пропущен.

## Approve: диспетчеризация сборщика

`POST /p/{slug}/creatives/{id}/approve`
([`project_creatives.py:450`](../../../dreaming/routes/project_creatives.py)):
почти дословно `articles_approve`, с той же причиной для
`bypassPermissions`. Отличия:

- Резолвит не только venue, но и **корень репозитория + каталог кампании**
  (`_campaign`) — `<creative_dir>/<slug>` относительно того же
  `resolve_repo_root` (=`articles.resolve_article_root` под другим именем),
  что обрабатывает вложенные репозитории (например у лендинга).
- env содержит `DC_CREATIVE_AGENT` (аналог `DC_ARTICLE_WRITER`, резолвится
  `creatives.resolve_agent` — отдельный список хинтов: `creative`, `designer`,
  `design`, `marketing`, `copywriter`, `social`, `brand`, **намеренно без
  голого `"writer"`**: автодетект однажды подобрал `blog-writer` для лендинга,
  подсунув прозаический агент под сборку рилсов), `DC_CREATIVE_DIR` (каталог
  кампании), `DC_CREATIVE_SLUG` (фиксированный), `DC_CREATIVE_FORMATS`,
  `DC_CREATIVE_LOCALES`, `DC_CREATIVE_VERIFY_CMD`, `DC_CREATIVE_SUBJECT_DIR`,
  `DC_CREATIVE_SUBJECT_SLUG`, `DC_CREATIVE_REVISION_NOTES`,
  `DC_CREATIVE_DRAFT_REF`.
- Нет отдельного `article_blog_dir`-подобного 400 на старте: отсутствие
  `creative_dir` отсекается раньше, `_require_dir`, тем же кодом, что не даёт
  прикреплять вложения без каталога.

## Write-back API

`GET /api/creatives/{id}` (бриф) и `POST /api/creatives/{id}/made`
([`api.py:565`](../../../dreaming/routes/api.py),
[`api.py:574`](../../../dreaming/routes/api.py)) — зеркало
`GET .../articles/{id}` / `POST .../articles/{id}/written`: 409 если строка не
`making`, `{error_message}` → `failed`, успех `{draft_ref, verify_output,
maker_agent, verify_ok}` → `mark_creative_made` переводит в `drafted`,
`verify_label` считается с venue (не subject — тот же приём "read from the
pinned target", что у статей).

Канал вопросов у сборщика есть — заведён после того, как выяснилось, что
его нет. Писать факт, который нельзя подтвердить, `make-creative.md` прямо
запрещает ("Never invent a number, a customer, a testimonial..."), и до
появления шага 4a альтернативы кроме честного отчёта о провале команда не
предлагала: кампания погибала из-за одной цифры, которую человек назвал бы
за секунды.

Шаг 4a повторяет устройство `write-article.md`: `POST /api/questions/create`
на слаг **субъекта**, `run_id` равен id заявки, затем цикл опроса **внутри
одного** вызова Bash — чтобы ожидание стоило один ход, а не по ходу на каждый
`curl`. Именно `run_id` позволяет карточке кампании показать строку ожидания:
`project_creatives.py` сверяет `run_id` висящего вопроса с id строки, поэтому
вопрос от другой кампании или вовсе без `run_id` не зажигает ничего. При
`dismissed` или отсутствии ответа правило прежнее — провалиться и назвать
вопрос, но не обходить его.

## Preview и роут медиа

`GET /p/{slug}/creatives/{id}/preview?fmt=&loc=`
([`project_creatives.py:587`](../../../dreaming/routes/project_creatives.py))
группирует пути из `draft_ref` по `(формат, локаль)`
(`creatives.classify_render` читает суффикс имени файла —
`<...>-<формат>-<локаль>.<ext>`, самый длинный формат первым, чтобы `reel-4x5`
не читался как `reel` с локалью `4x5`). Рендеры показываются вкладками,
текст поста — сразу под ними как markdown, что не подошло ни под один формат —
отдельным списком "outside the formats".

Рендеры не инлайнятся в HTML — каждый отдаётся отдельным запросом на
`GET /p/{slug}/creatives/{id}/media?path=`
([`project_creatives.py:668`](../../../dreaming/routes/project_creatives.py)),
которого у статей нет вовсе (текст можно вставить прямо в страницу,
изображение и видео — нет). Три независимых проверки:

1. Путь обязан быть тем, что **эта же строка сама сообщила** в `draft_ref`,
   либо файлом из её собственных вложений (`creatives.list_attachments`) —
   параметр выбирает из готового списка, никогда не открывает произвольное.
2. Проходит `article_publish._validate_paths` относительно корня кампании.
3. Расширение входит в `creatives.MEDIA_TYPES` — **без `.svg`**, по той же
   причине, что и в списке вложений: SVG — контейнер для скрипта, отданный с
   origin центра и куками оператора.

## Revise — доработка кампании

`creatives.draft_findings` — свой набор проверок, не пересекающийся с
`articles.draft_findings`, потому что предметная область другая:

- `format_missing` — формат из `creative_formats` площадки, для которого нет
  ни одного рендера.
- `locale_missing` — локаль без рендеров.
- `wrong_size` — рендер, чьи пиксели (читаются из заголовка PNG/JPEG/GIF,
  `creatives.image_size`, без библиотек изображений) не совпадают с
  объявленным размером формата (`FORMAT_SIZES`: `post-4x5`/`reel-4x5` —
  1080×1350, `story`/`reel` — 1080×1920). Видео не измеряется вовсе —
  сообщается только наличие/отсутствие, никогда не угадывается размер.
- `copy_missing` — рендеры есть, текста поста нет.

`POST /p/{slug}/creatives/{id}/revise` — тот же паттерн, что у статей: находки
+ свободный текст → `revision_notes`, отказ на пустой запрос, вызов
`creatives_approve` тем же кодом, что первая сборка.

## Publish: коммит

`POST /p/{slug}/creatives/{id}/publish`
([`project_creatives.py:742`](../../../dreaming/routes/project_creatives.py))
использует **тот же** [`article_publish.publish`](../../../dreaming/services/article_publish.py),
что и статьи — не отдельную копию. Гейт `creatives.can_publish` — импорт
`articles.can_publish` без изменений. `creative_publish_extra_paths` — то же,
что `article_publish_extra_paths` у статей (может называть каталоги, для
построенного вывода). Отказ, если `draft_ref` пуст ("кампания не сообщила ни
одного файла") — у статей эта проверка неявная (пустой `draft_ref` не пройдёт
`_validate_paths`), у creatives — явный 409 перед вызовом publish.

## Известный пробел: reconcile не подключён

`db.reconcile_stranded_creative_proposals` существует в
[`db.py:2000`](../../../dreaming/services/db.py) и дословно копирует контракт
`reconcile_stranded_article_proposals` (тот же сигнал живости — множество
`cmd:*`-сессий `ProcessManager`, не столбец `agent_learning_sessions.status`)
— но **не вызывается нигде**: `scheduler._reconcile_job` зовёт только версию
для статей. Кампания, застрявшая в `making` после смерти сборщика (watchdog,
падение хоста), не восстанавливается автоматически — только вручную, кнопкой
"Отменить". `waves.md` про этот пробел не упоминает вовсе; обнаружено при
чтении кода для этого документа, не задокументировано больше нигде.

## Что отложено с волны E

Прямым текстом в [`waves.md`](../waves.md#wave-e--creative-pipeline):

- Постинг в соцсети через API — решение оператора, не пробел.
- Кросс-проектная очередь `/creatives` (аналог `/articles` для статей) и
  плановый `weekly_creative_ideas_scan` — не реализованы; отсюда и отсутствие
  крон-джоба в `_PER_PROJECT_JOBS` (у статей `weekly_article_ideas_scan`
  есть, у creatives — нет).
- Живой прогон сборки не состоялся ни разу: конвейер собран и проверен
  smoke-тестами, но ни одна кампания через него не прошла на момент волны.

## Настройки

Группа "Creatives" (аналогична "Articles", но короче — нет `_min_chars` /
`_required_markers`, у creatives их роль играют формат/локаль/size-проверки):

| Ключ | Смысл |
|---|---|
| `creative_dir` | пусто по умолчанию = фича выключена, каждый роут отказывает с сообщением про этот ключ |
| `creative_agent` | override автодетекта |
| `creative_formats` | дефолт `post-4x5,story,reel-4x5,reel` |
| `creative_locales` | если пусто — берётся `row.locales` |
| `creative_verify_cmd` | сборка (рилсы — минуты; поэтому в сессии, никогда не в веб-запросе) |
| `creative_publish_mode` | `off` \| `commit` \| `commit+push` |
| `creative_publish_extra_paths` | как у статей |
| `creative_venue_project` | дефолтная площадка |
| `creative_max_turns`, `creative_timeout_minutes` | отдельные лимиты, дефолт 300/120 — те же значения, что у статей |

## Два скилла

- **`creative-ideas-scan`** — read-only, три-семь предложений за прогон,
  каждое с `evidence`. Никогда не создаёт файлы/каталоги/ветки, не запускает
  сборщика.
- **`make-creative`** — `/make-creative <id>`. Смотрит `$DC_CREATIVE_DIR/src/`
  на человеческие вложения **прежде всего остального**; копирует форму
  соседних кампаний (где лежат шаблоны, куда идут рендеры, как имя файла
  кодирует формат и локаль); пишет текст поста — "рендеры без текста — это
  половина кампании"; для реестра предписан тот же приём, что у статей — не
  читать большой файл целиком, мутировать скриптом. Никогда не коммитит и не
  пушит, никогда не переименовывает и не двигает каталог кампании (вложения
  уже там), никогда не удаляет человеческое вложение.

См. дословно:
[`templates/starter-kit/commands/creative-ideas-scan.md`](../../../templates/starter-kit/commands/creative-ideas-scan.md),
[`templates/starter-kit/commands/make-creative.md`](../../../templates/starter-kit/commands/make-creative.md).

## Cross-references

- Общая механика (venue-резолюция, git-публикация, статус-машина) —
  [`features/articles.md`](articles.md).
- Пользовательский гайд — [`user/features/creatives.md`](../user/features/creatives.md).
- Инвентарь маршрутов — [`routes.md`](../routes.md).
- История волны E — [`waves.md`](../waves.md#wave-e--creative-pipeline).
