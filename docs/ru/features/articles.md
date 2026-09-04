# Article pipeline

Конвейер статей: центр предлагает тему (сам или по чужой подсказке), человек
согласует, агент проекта пишет черновик, человек смотрит и либо отправляет на
доработку, либо публикует коммитом в репозиторий проекта. Два человеческих
гейта — Approve и Publish — единственные места, где что-то реально происходит
без явного клика.

Ключевое архитектурное решение волны A, из которого следует почти всё
остальное: **центр не знает формата статьи**. У лендинга проза лежит записями
в `blog-posts.json`, у `accounting-ai-agent` — markdown по локалям со строгим
фронтматтером, у `legalka-kb` — своя структура. Поэтому центр владеет только
предложением (тема, evidence, статус), а форму статьи всегда решает площадка
(venue) — её существующие посты и её агент-писатель, если он есть. Агент-писатель
есть только в 3 из 11 подключённых проектов; для остальных писателем выступает
сама сессия `write-article` (`writer_agent = 'self'`), и это нормальный исход,
а не деградация.

## Содержание

- [Subject и venue](#subject-и-venue)
- [Жизненный цикл предложения](#жизненный-цикл-предложения)
- [Таблица `article_proposals`](#таблица-article_proposals)
- [Кто подаёт предложения](#кто-подаёт-предложения)
- [Approve: диспетчеризация писателя](#approve-диспетчеризация-писателя)
- [Резолюция площадки и корня статьи](#резолюция-площадки-и-корня-статьи)
- [Write-back API и канал вопросов](#write-back-api-и-канал-вопросов)
- [Preview](#preview)
- [Revise — доработка черновика](#revise--доработка-черновика)
- [Publish: коммит](#publish-коммит)
- [Reconcile: зависшие попытки](#reconcile-зависшие-попытки)
- [Настройки](#настройки)
- [Четыре скилла](#четыре-скилла)
- [Cross-references](#cross-references)

## Subject и venue

Каждое предложение имеет два проекта, которые почти всегда совпадают, но не
обязаны:

- **subject** — проект, о котором статья ("подана из" — `article_proposals.project_id`).
  Владеет карточкой, строкой очереди, вопросами писателя и логами сессии.
- **venue** — проект, в чей репозиторий статья попадёт. Владеет форматом:
  `article_blog_dir`, `article_writer_agent`, `article_verify_cmd`,
  `article_publish_mode` и всё остальное со страницы настроек читаются с venue,
  а не с subject.

Venue резолвится чистой функцией
[`articles.resolve_venue_id`](../../../dreaming/services/articles.py) (Wave B):
per-row override (`target_project_id`) важнее настройки `article_venue_project`
subject'а, та — важнее самого subject'а. Значение, не называющее ни один включённый
проект, откатывается назад к subject'у, а не отказывает. Без override и без
настройки `article_venue_project` venue == subject, что побайтово воспроизводит
поведение волны A — так устроены сейчас все проекты, кроме `budlog`, у которого
`article_venue_project=test` (кросс-проектная демонстрация из волны B).

Venue **фиксируется** ("pinned") в момент успешного диспетча
(`db.pin_article_proposal_venue`, вызывается из `articles_approve` сразу после
`pm.start_command`, но до `start_article_attempt`) — не раньше и не позже.
Публикация читает зафиксированное значение, а не пересчитывает его заново:
иначе строка могла бы разъехаться, если `article_venue_project` изменится между
approve и publish.

## Жизненный цикл предложения

```
proposed --(approve)--> writing --(written, verify_ok или нет)--> drafted --(publish)--> published
   |                        ^                                        |
   |                        |________________(revise / retry)________|
   |
   +--(reject)--> rejected --(restore)--> proposed
   +--(done)----> done -----(restore)--> proposed

writing --(written, error_message)--> failed --(approve/retry)--> writing
writing --(cancel, вручную)---------> failed
writing --(reconcile-крон, сессия мертва)--> failed
failed  --(done)--------------------> done
failed  --(draft-ready, вручную)----> drafted
```

Два выхода из `failed` не взаимозаменяемы. `done` («уже сделано») закрывает
строку и ничего не коммитит — статья существует вне этого конвейера; он
отделён от `rejected` намеренно: отказ означает «тема не годится», `done` —
«тема верна, работа уже сделана». На дедуп это не влияет (уникальный индекс
`(project_id, slug_hint)` не даёт скану предложить слаг заново при любом из
двух исходов), но месяц спустя очередь читается честнее. Достижим из
`proposed` и `failed`, обратим тем же `restore`, что и `rejected`; из
`writing` запрещён (`409`) — там ещё работает сессия.

`draft-ready` — восстановление, а не решение: черновик лежит на диске, но
отчёт о нём не дошёл (сессию убили, хост перезапустился, строку уронил
reconcile под работающим писателем — см. ниже). Роут ставит строку туда, куда
её поставил бы `/written`, так что снова доступен обычный гейт публикации и
коммит за ним; повторный прогон писателя (ещё одна оплаченная сессия ради
файлов, которые уже есть) не нужен. Пути проверяются тем же кодом, что и при
публикации (`article_publish.validate_draft_paths`), до любой записи. Метка
верификации у такой строки — `manual`, никогда не `verified`: центр сборку не
запускал, за неё ручается человек, и коммит-сообщение говорит, что именно из
двух произошло. Принимается только из `failed` — строку в `writing` сначала
нужно отменить, чтобы ничего не записывалось за спиной у живой сессии.

Статус пишется в столбец `status`; проверка не CHECK-констрейнт, а код
(`_ORDER` в шаблоне и `_DISPATCHABLE_STATUSES` в роуте) — строка с любым другим
значением всё равно рендерится, в отдельной группе "other".

`approved` формально входит в `_DISPATCHABLE_STATUSES` и в порядок статусов, но
это **сегодня недостижимое состояние**: ни один код-путь его не выставляет —
`articles_approve` диспетчит писателя и сразу переводит строку в `writing`,
минуя промежуточный `approved`. Комментарий в
[`db.py:1506`](../../../dreaming/services/db.py) называет его прямым текстом:
"the first approve ('proposed', and the unreachable-today 'approved')" —
задел на будущий двухшаговый approve, а не текущее поведение.

`published` — терминальный статус: повторный approve/retry на уже
опубликованную строку отклоняется 409 ещё до диспетча (проверка в
[`project_articles.py:428`](../../../dreaming/routes/project_articles.py), до
`start_article_attempt`, а не только внутри него — иначе уже потраченная
CLI-сессия оказалась бы ни на что не записанной строкой).

## Таблица `article_proposals`

Не задокументирована в [`schema.md`](../schema.md) — таблица появилась после
среза на 16 таблиц. Ключевые столбцы:

| Столбец | Смысл |
|---|---|
| `project_id` | subject |
| `target_project_id` | venue override / pin (nullable, Wave B) |
| `source` | `project_scan` \| `radar` \| `center` \| `manual` |
| `evidence` | обязателен, непусто проверяется в `add_article_proposal`, не только на HTTP-границе |
| `slug_hint` | seed для писателя; `UNIQUE(project_id, slug_hint)` — дедуп трёх фидеров на один сюжет |
| `funnel_level` | `top` \| `product` |
| `locales`, `tags_json`, `related_product` | бриф |
| `status` | см. жизненный цикл выше |
| `writer_agent`, `draft_ref`, `verify_output`, `verify_ok`, `verify_label` | что вернул write-back |
| `commit_ref`, `session_id`, `error_message` | результат publish / диспетча |
| `revision_notes` | непусто только между revise и следующим write-back |

`verify_label` — что карточка и commit-message **вправе заявить**
(`articles.publish_label`): `"unverified"`, если `article_verify_cmd` пуст,
иначе `"verified"`/`"failed"` по факту `verify_ok`. Персистится в момент
write-back, а не пересчитывается заново при рендере или publish — иначе смена
`article_verify_cmd` задним числом перекрашивала бы уже написанные карточки.

## Кто подаёт предложения

Четыре источника, различаются только `source`:

| Источник | `source` | Как | Где |
|---|---|---|---|
| Слэш-команда `/article-ideas-scan` | `project_scan` | Сессия сканит `git log`, спеки, `docs/seo/ai-visibility/REPORT.md`, шлёт `POST /api/p/{slug}/articles/ingest` | вручную кнопкой "Предложить темы" или еженедельным `weekly_article_ideas_scan_{slug}` (по умолчанию выключен) |
| AI Radar | `radar` | `POST /ai-radar/{finding_id}/propose-article` — evidence собирается из самой находки (источник, заголовок, дата), без LLM-сессии | кнопка на карточке finding |
| Product Ideas | `center` | `POST /p/{slug}/ideas/{item_id}/propose-article` — evidence это путь к md-файлу идеи | кнопка на карточке idea |
| Человек | `manual` | `POST /p/{slug}/articles/add` — evidence честно говорит "requested by hand on `<дата>`" | форма на самой странице `/articles` |

`_ARTICLE_SOURCES` в [`api.py`](../../../dreaming/routes/api.py) — общий белый
список для HTTP-границы ingest; `add_article_proposal` сам отказывает пустому
`evidence` (не только роут), так что правило держится структурно для любого
будущего фидера.

Ручная форма (`articles_add`) — единственное место, где slug строится не
`articles.slugify` (которая роняет кириллицу), а хэшем нормализованной темы
(`"manual-" + sha1(...)[:10]`), если `slugify` вернула пусто: тема по-русски —
основной случай для этой формы, а не краевой, и фолбэк на времени коллизировал
бы разные темы в одну секунду и не дедуплицировал бы одну тему секундами позже.

## Approve: диспетчеризация писателя

`POST /p/{slug}/articles/{id}/approve`
([`project_articles.py:408`](../../../dreaming/routes/project_articles.py)):

1. 404, если строка не найдена или принадлежит другому проекту.
2. 409, если `status` не в `_DISPATCHABLE_STATUSES = (proposed, approved, failed, drafted)`.
3. Резолвит venue (`_venue_for`) и `article_blog_dir` — 400, если пусто.
4. Резолвит корень репозитория, который реально владеет блогом
   (`articles.resolve_article_root`) — не всегда `venue.working_dir`: у
   `micode-landing-page`-подобных площадок блог лежит во вложенном репозитории
   со своим `.git`.
5. Проверяет, что `write-article` установлен **в этом корне**, а не в
   `venue.working_dir` — иначе проверка проходит по чужому `.claude/commands/`,
   пока сессия реально стартует во вложенном репозитории без команды.
6. Резолвит писателя (`articles.resolve_writer`) и стартует `pm.start_command`
   с `working_dir=root`, промптом `/write-article {proposal_id}` и env:
   `DREAMING_PROJECT_SLUG` (subject, не venue — сюда должны прийти write-back
   и вопросы), `DREAMING_API_URL`, `DC_ARTICLE_WRITER`, `DC_ARTICLE_BLOG_DIR`
   (пересчитан относительно `root`, см. `session_blog_dir`),
   `DC_ARTICLE_VERIFY_CMD`, `DC_ARTICLE_LOCALES`, `DC_ARTICLE_SUBJECT_DIR`,
   `DC_ARTICLE_SUBJECT_SLUG`, `DC_ARTICLE_REVISION_NOTES`, `DC_ARTICLE_DRAFT_REF`
   (два последних непусты только при повторной доработке), `DC_ARTICLE_BRIEF`
   (уточнение оператора, введённое на самом запуске; живёт на заявке и
   переживает все попытки).
7. Пинит venue, затем `db.start_article_attempt` — переводит строку в
   `writing`, стирает `draft_ref`/`verify_output`/`writer_agent`/`error_message`
   от прошлой попытки (иначе retry показывал бы старый "сборка прошла" рядом с
   новой ошибкой).
8. Сбрасывает висящие вопросы прошлой попытки (`dismiss_article_proposal_questions`)
   — иначе retry читал бы ответ на вопрос чужой, уже мёртвой попытки.

`bypassPermissions` обязателен (см. [`self-study.md`](self-study.md) — то же
решение, что для self-study): с `--allowedTools` сессия тихо теряет право
писать в репозиторий.

`articles_revise` (доработка) — **тот же код-путь**: пишет `revision_notes`,
затем вызывает `articles_approve` напрямую, так что venue, писатель, cwd и
лимиты доработки никогда не могут разъехаться с тем, что решил первый write.

## Резолюция площадки и корня статьи

`articles.resolve_article_root(working_dir, blog_dir)` — git-репозиторий,
который реально владеет блогом, не всегда `working_dir`. Falls back к
`working_dir` без изменений, если: `blog_dir` пуст; выходит за пределы
`working_dir` (абсолютный путь или `..`); каталога ещё нет на диске; каталог не
внутри git-репозитория; либо `git rev-parse --show-toplevel` для него
оказывается **предком** `working_dir` (проект зарегистрирован на подкаталоге
большего чекаута — реальный git-репозиторий, но не свой). Следование такому
предку закоммитило бы публикацию выше по дереву, чем сам проект — поэтому
функция гарантирует: `root` либо равен `working_dir`, либо является его
потомком, никогда не предком и не посторонним деревом.

`articles.session_blog_dir(working_dir, blog_dir, root)` — пересчитывает
`DC_ARTICLE_BLOG_DIR` относительно `root`, только если `root` реально
отличается от `working_dir` (случай вложенного репозитория).

## Write-back API и канал вопросов

`/write-article` читает бриф через `GET /api/articles/{id}`
([`api.py:646`](../../../dreaming/routes/api.py)) и отчитывается через
`POST /api/articles/{id}/written` ([`api.py:655`](../../../dreaming/routes/api.py)):

- 409, если строка уже не `writing`.
- Успех: `{draft_ref, verify_output, writer_agent, verify_ok}` →
  `mark_article_written` переводит в `drafted`, персистит `verify_label`
  (посчитанный с venue, а не subject — `target_project_id` строки уже несёт
  зафиксированный venue), очищает `revision_notes`.
- Неудача: `{error_message}` → `failed`, снимает висящие вопросы.
- `draft_ref` по умолчанию `""` — иначе честный отчёт о провале
  (`{"error_message": "..."}`, без `draft_ref`) сам получил бы 422 от
  pydantic до того, как обработчик вообще запустится.

Канал вопросов (`POST /api/questions/create`, `GET /api/questions/{id}/poll`,
общая инфраструктура с self-study, таблица `orchestrator_questions`) — писатель
использует его, когда факт нельзя подтвердить ни в subject, ни в venue.
Вопрос постится с `run_id = <proposal_id>` **на слаг subject'а**, даже если cwd
сессии — venue: страница показывает "писатель ждёт ответа" на карточке
предложения, сопоставляя `run_id` пендинг-вопроса с id строки, и это
единственный способ не подсветить чужую карточку (self-study/rotation/другое
предложение того же проекта). Пока вопрос pending, watchdog `ProcessManager` не
засчитывает молчание сессии как зависание (`process_manager.py:561`) — но не
продлевает `article_max_turns`.

## Preview

`GET /p/{slug}/articles/{id}/preview?lang=&file=`
([`project_articles.py:660`](../../../dreaming/routes/project_articles.py)) —
показывает рабочее дерево, не коммит: для опубликованной строки это файл, как
он выглядит сейчас, что может уже разойтись с закоммиченной версией.

Каждый путь из `draft_ref` проходит через `article_publish._validate_paths` —
тот же валидатор, что и publish, так что preview физически не может показать
то, что publish не смог бы закоммитить. Путь, не прошедший проверку, попадает
в список "problems" вместо падения всей страницы.

Язык варианта определяется по фронтматтеру (`lang:`/`locale:` в первых
`---`-строках) либо по сегменту пути, совпадающему с одной из `locales` строки.
Для площадок, хранящих прозу как данные (`micode-landing-page`: одна запись
JSON-массива с полями `titlePl`/`bodyPl` и т.д.) —
`articles.data_entry_variants` находит запись по `slug_hint` или сегментам
`draft_ref` и достаёт языки из полей `body<Lang>`. Файл при этом остаётся
доступен отдельно ("others") — для отладки.

Файлы длиннее 200 000 символов обрезаются с пометкой (реестр или план статьи
может быть куда больше самой статьи).

Для `status == 'drafted'` считаются `draft_findings` (см. ниже) — что
подставить в форму доработки предзаполненными галочками.

## Revise — доработка черновика

Проверки, вычислимые без знания инструментария площадки
(`articles.draft_findings`), обе per-venue и обе опциональны, потому что ни у
одной нет разумного дефолта:

- `article_min_chars` — вариант короче этого числа символов помечается `short`.
- `article_required_markers` — маркер (например `[[diagram:`), отсутствующий
  хотя бы в одном языке, помечается `marker`.

Без обеих настроек форма доработки — просто текстовое поле. `POST
/p/{slug}/articles/{id}/revise` объединяет отмеченные находки и текст в
`revision_notes`, отказывает пустому запросу (400) и вызывает `articles_approve`
— тот же путь диспетча, что и первый write.

## Publish: коммит

`POST /p/{slug}/articles/{id}/publish`
([`project_articles.py:812`](../../../dreaming/routes/project_articles.py)) →
[`article_publish.publish`](../../../dreaming/services/article_publish.py) —
общий модуль с creatives (см. [`features/creatives.md`](creatives.md), не
дублируется здесь).

Гейт `articles.can_publish(row, verify_cmd, publish_mode)`:

- `article_publish_mode == 'off'` → отказ (`mode_off`).
- `status != 'drafted'` → отказ (`not_drafted`).
- `verify_cmd` задан и `verify_ok` ложен → отказ (`verify_failed`).
- Иначе разрешено; если `verify_cmd` пуст — публикация разрешена, но и
  карточка, и commit-message честно говорят "unverified". Запрет этого случая
  сделал бы фичу бесполезной для `accounting-ai-agent`, чей markdown-блог не
  имеет шага сборки вовсе.

Публикуются только пути из `draft_ref` (self-reported писателем) плюс, если
задано, `article_publish_extra_paths` — построчный/через-запятую список,
**может называть каталоги** (в отличие от `draft_ref`): предназначен для
committed build output вроде `ai-budget-assistant`, где `docs/marketing/seo/site/blog`
собирается генератором и коммитится целиком (Wave C). Комментарий к
`article_verify_cmd` в [`config.py`](../../../dreaming/config.py) фиксирует урок
первой живой публикации: verify обязан пересобрать **всё**, что увозит деплой,
а не только ближайший к статье генератор — иначе гейт проходит на
наполовину собранном сайте.

`PushFailed` (коммит прошёл, `git push` — нет) отдельно от `PublishError`:
строка помечается `published` с `commit_ref`, а `error_message` говорит, что
нужен ручной push — иначе retry увидел бы "nothing to publish" навечно, а sha
потерялся бы.

## Reconcile: зависшие попытки

Глобальный крон каждые 5 минут (`scheduler._reconcile_job`) вызывает
`db.reconcile_stranded_article_proposals(active_session_ids)` — переводит в
`failed` любую строку в `writing`, чей `session_id` не входит в множество
живых `cmd:*`-процессов `ProcessManager`. Единственный сигнал живости —
процесс, не столбец `agent_learning_sessions.status` (после `_cleanup`
сбоя он может годами показывать `running`). Это закрывает случай, когда
write-article-сессию убил watchdog или процесс дерева хоста, и она никогда не
вызвала `/written`.

Ручная кнопка "Отменить" (`POST /p/{slug}/articles/{id}/cancel`) делает то же
самое немедленно, по нажатию — переводит `writing → failed`, не убивая сам
процесс (об этом сказано в докстринге роута прямым текстом).

### Чужие сессии: один файл БД, несколько серверов

Приложение нигде не является single-instance: второй `uvicorn` на другом порту
спокойно открывает тот же `data/dreaming.db` и крутит тот же пятиминутный
крон. А множество живых процессов у него — своё, так что без дополнительной
проверки каждый инстанс читает живые сессии другого как мёртвые и роняет
работу под ними. Это не гипотеза: так 25.08.2026 умерло предложение 514 —
писатель работал 21 минуту, забытый сервер с кодом от 23.08 уронил строку на
пятой, и собственный `/written` писателя был потом отвергнут как
out-of-status.

Поэтому каждый инстанс при старте регистрируется в `app_instances`
(`main.lifespan` → `db.register_instance`) и раз в минуту обновляет
`last_seen` (`scheduler._heartbeat_job`), а `create_session` пишет владельца в
`agent_learning_sessions.owner_instance`. Перед всеми тремя свипами
`_reconcile_job` добавляет в множество живых
`db.sessions_owned_by_live_instances()` — незавершённые сессии тех инстансов,
чей heartbeat моложе `db.INSTANCE_STALE_AFTER_SEC` (180 с, три пропущенных
удара). Сессия чужого живого инстанса считается работающей, потому что она
работает, а решать её судьбу будет её собственный владелец.

Самоисцеление при этом не теряется: инстанс, убитый жёстко, перестаёт стучать,
через staleness-окно его строки снова становятся подметаемыми; при чистом
выключении `db.unregister_instance()` снимает строку сразу. Строки с пустым
`owner_instance` (всё, что было до этого столбца) ведут себя ровно как раньше.
`_heartbeat_job` пишет `warning` в лог, когда рядом появляется другой живой
инстанс, — забытый сервер невидим ровно до того момента, когда что-нибудь
съест.

## Настройки

Группа "Articles" в [`configuration.md`](../configuration.md) /
[`features/settings.md`](settings.md):

| Ключ | Смысл |
|---|---|
| `article_writer_agent` | override автодетекта |
| `article_blog_dir` | относительно venue.working_dir |
| `article_locales` | если пусто — берётся `row.locales` (догадка скана) |
| `article_verify_cmd` | сборка/проверка, запускается **сессией**, не веб-запросом |
| `article_publish_mode` | `off` \| `commit` \| `commit+push` |
| `article_publish_extra_paths` | Wave C, может называть каталоги |
| `article_min_chars`, `article_required_markers` | опциональные проверки доработки |
| `article_max_turns`, `article_timeout_minutes` | отдельные от self-study лимиты — 50/20 глобальных исчерпываются первым языком трёхъязычной статьи |
| `article_venue_project` | дефолтная площадка (Wave B) |

Плюс `weekly_article_ideas_scan_cron` / `_enabled` в группе "Scheduling —
weekly" — по умолчанию выключен, единственный крон-джоб этого конвейера.

## Четыре скилла

Все четыре живут в `templates/starter-kit/commands/*.md` (эталон) и копируются
в `{working_dir}/.claude/commands/` инсталлятором starter-kit; два из них
относятся к статьям:

- **`article-ideas-scan`** — read-only. Никогда не пишет, не коммитит, не
  вызывает писателя. Постит через `POST .../articles/ingest`, пропуская то,
  что уже есть в `GET .../articles/list`.
- **`write-article`** — `/write-article <id>`. Читает бриф, отличает первую
  запись от доработки по `$DC_ARTICLE_REVISION_NOTES`, копирует форму двух-трёх
  соседних постов **venue**, а не subject'а, для площадок с одним огромным
  JSON-файлом-реестром явно предписано не читать файл целиком (пример из
  документа: 778 КБ, сессия умерла на 11 минуте без единой строки), задаёт
  вопрос через API вместо того чтобы выдумать факт, никогда не коммитит и не
  пушит — это отдельный, согласуемый человеком шаг.

Обе команды детально прокомментированы построчно в самих файлах — см.
[`templates/starter-kit/commands/article-ideas-scan.md`](../../../templates/starter-kit/commands/article-ideas-scan.md)
и
[`templates/starter-kit/commands/write-article.md`](../../../templates/starter-kit/commands/write-article.md).

Установленная копия может **разойтись** с шаблоном (не то же самое, что
отсутствовать) — центр это обнаруживает (`starter_kit.command_stale`,
сравнение с нормализацией переводов строк) и показывает баннер на `/articles`
с диффом, но не блокирует сессию: слишком старая копия просто выполняет более
старые инструкции молча.

## Cross-references

- Публикация коммитом (общий модуль с creatives) — [`features/creatives.md`](creatives.md).
- Пользовательский гайд — [`user/features/articles.md`](../user/features/articles.md).
- Инвентарь маршрутов — [`routes.md`](../routes.md).
- История волн A/B/C — [`waves.md`](../waves.md#wave-a--article-pipeline).
- Self-study и `bypassPermissions` — [`features/self-study.md`](self-study.md).
