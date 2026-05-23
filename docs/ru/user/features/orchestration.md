# Orchestration — запуск Романа

`/p/{slug}/orchestration` — список orchestration runs и форма запуска нового. Detail-страница на `/{run_id}` показывает дерево nodes (Roman + sub-agents) и поток сообщений.

## Содержание

- [Что такое Roman](#что-такое-roman)
- [Список runs](#список-runs)
- [Запуск нового run'а](#запуск-нового-run-а)
- [Detail page](#detail-page)
- [Polling и обновления](#polling-и-обновления)
- [Mark completed (manual)](#mark-completed-manual)
- [Resume](#resume)
- [One-Roman-per-project](#one-roman-per-project)
- [Bulk queue — массовый запуск](#bulk-queue--массовый-запуск)
- [Авто-скролл чата и позиционирование сайдбара](#авто-скролл-чата-и-позиционирование-сайдбара)

## Что такое Roman

Roman — это root-агент-оркестратор. В коде `agent_name="roman"`, `role="orchestrator"`. Запускается через `claude` CLI с твоей `goal` как prompt'ом, и Claude использует Task tool для делегирования под-агентам (sub-agents).

Концептуально:
```
[user goal]
     |
     v
+---------+
|  Roman  |  decomposes goal, picks sub-agents
+---------+
   /  |  \
  v   v   v
[A] [B] [C]   <- sub-agents (Task tool spawns)
```

Каждый sub-agent — отдельный `claude` subprocess. Roman передаёт им чёткие задачи, собирает результаты, агрегирует ответ.

В DC ты видишь:
- Один **run** в orchestrator_runs (root = Roman).
- Несколько **nodes** в orchestrator_nodes (по одной на каждого агента, включая Roman'а как root).
- Несколько **messages** в orchestrator_messages (текст из stdout каждого агента).

## Список runs

Открой `/p/{slug}/orchestration`. Сверху — белая карточка с формой:
- Input «Цель Roman-сессии (например: «декомпозируй фичу X»)» (обязательное).
- Синяя кнопка `Start Roman`.

Под формой — таблица runs (если есть):
- `run_id` — короткий UUID (первые 8 символов + многоточие). Кликабельная ссылка на detail.
- `goal` — обрезанная (80 символов) цель.
- `status` — цветной моноширинный: amber `running`, green `completed`, red `failed`.
- `started` — timestamp.
- `finished` — timestamp или `—`.

Сортировка — newest first.

Если нет runs — текст «Нет orchestration runs пока. Запусти Roman через форму выше.»

## Запуск нового run-а

В форме введи цель и нажми `Start Roman`.

Что происходит:
1. POST на `/p/{slug}/orchestration/start`.
2. DC создаёт `orchestrator_runs` row: id (UUID), project_id, goal, status='running', started_at=now.
3. Создаёт `orchestrator_nodes` row для root: agent_name='roman', role='orchestrator', status='running'.
4. Спавнит `claude` с goal как prompt и `cwd={working_dir}`.
5. Поднимает `ClaudeSessionTail` (читает stdout JSONL и пишет в orchestrator_events / orchestrator_messages).
6. Поднимает `SubagentWatcher` (мониторит filesystem-каталог `subagents/` под session-dir; когда появляется новый JSONL — создаёт node и подписывает второй tail).
7. Редиректит браузер на `/p/{slug}/orchestration/{run_id}`.

Дальше — наблюдаешь run на detail-странице.

## Detail page

`/p/{slug}/orchestration/{run_id}`.

Сверху — header:
- Хлебная крошка `← к списку runs`.
- Заголовок: цель run'а (полностью).
- Метаданные: full UUID моноширинно, status (цветной), started, finished, session UUID Claude'а (если уже есть).
- Кнопки в зависимости от статуса:
  - Если `running`: `Mark completed`.
  - Если finished с external_id: `Resume` + input «Что дальше? (опц.)».
  - Если finished без external_id: ничего.

Дальше — секция **Nodes**:
- Заголовок «Nodes (N)» где N — количество.
- Таблица: `agent`, `role`, `status`, `started`.
- Если нет nodes — «Нет nodes пока. Watcher активен — подождём ещё пару секунд…» (если status running).

Дальше — секция **Messages**:
- Заголовок «Messages (N)».
- Список белых карточек, по одной на сообщение. На карточке: автор, kind (assistant_message / tool_use / tool_result / etc.), timestamp, и `<pre>` с whitespace-pre-wrap'ом — текст сообщения.
- Если нет — «Нет messages пока.»

## Polling и обновления

Detail-страница использует AJAX-polling каждые 2 секунды (пока status `running`):
- Шлёт GET `/p/{slug}/orchestration/{run_id}/refresh`.
- Получает JSON: `{status, node_count, message_count}`.
- Если node_count или message_count изменились — `location.reload()` (полная перезагрузка страницы).
- Если status вышел из `running` — тоже reload.
- Если pending error — повтор через 5 секунд.

Поэтому ты видишь, как новые nodes и messages «появляются» примерно в real-time (с задержкой до 2 секунд + перезагрузка страницы).

После того как run в `completed` или `failed` — polling останавливается. Для дальнейших обновлений — ручной refresh.

## Mark completed (manual)

Кнопка `Mark completed` (только для running):
- POST на `/p/{slug}/orchestration/{run_id}/finish`.
- DC помечает run как `completed`, finished_at=now.
- Subprocess Claude'а **не убивается** автоматически — продолжит писать в JSONL до естественного завершения.
- Polling остановится.

Используй когда:
- Run вечно висит в running, хотя ты знаешь что Claude уже закончил (callback не пришёл).
- Нужно «закрыть» run, чтобы запустить новый (one-Roman-per-project).
- Ты сделал Kill процесса вручную (через Task Manager / `kill -9`) и DB row висит.

После Mark completed можно нажать Resume чтобы продолжить с того же session_id.

## Resume

Кнопка `Resume` (только для finished с `external_id`):
- В input'е «Что дальше? (опц.)» можешь ввести follow-up prompt или оставить пустым (тогда Claude продолжит без новых инструкций).
- POST на `/p/{slug}/orchestration/{run_id}/resume`.
- DC спавнит новый claude-subprocess с `--resume {external_id}` и переданным prompt'ом.
- Создаётся новый run или обновляется существующий (зависит от реализации) — в любом случае, ты получаешь продолжение работы.
- Редирект на detail page.

Используй когда:
- Roman завершил первую часть задачи, ты прочитал результат, и хочешь дать ему дополнительные инструкции.
- Run упал на середине (`failed`), но `external_id` есть — можешь попробовать продолжить.

## One-Roman-per-project

Только один orchestration run на проект может быть в статусе `running`. Если ты пытаешься стартовать второй (нажимаешь `Start Roman` на проекте, где уже есть running run) — DC редиректит тебя на existing run вместо создания нового.

Это сделано чтобы:
- Не плодить parallel-Roman'ы (они будут спавнить одинаковых sub-agents и confusing).
- Сохранить чистоту orchestration-treees.

Если хочешь parallel work:
- Закрой existing (Mark completed или жди завершения).
- Тогда новый запустится.

Или используй другой проект — там свой Roman независим.

## Bulk queue — массовый запуск

Когда нужно прогнать через Orchestrator сразу пачку tech-debt'ов, продуктовых идей или эволюций — на каждой из таблиц `/findings`, `/ideas`, `/evolutions` есть колонка чекбоксов и кнопка **«Запустить (N)»**.

### Как пользоваться

1. Чекбокс в заголовке таблицы — toggle для всех **видимых** строк (отфильтрованные не трогаются; если выбрано не всё — indeterminate).
2. Кнопка «Запустить (N)» под счётчиком записей. Дизейблится, пока N=0; после клика — модалка подтверждения: «Поставить в очередь N элементов? Будут запущены последовательно — Orchestrator принимает один run за раз.»
3. После подтверждения — flash-сообщение «N элементов в очереди оркестрации», редирект обратно на исходную страницу. Фоновая задача начинает диспатчить.

### Очередь на `/p/{slug}/orchestration`

Сверху страницы — баннер «Очередь»:
- **N в ожидании** (амбер, пульс) — сколько элементов ещё не отправлено;
- **очередь пуста** — все дошли до диспатча;
- Список чипов: иконка (🐛 finding, 💡 idea, 🧬 evolution) + укороченный идентификатор + статус (`pending` / `dispatched` / `failed`). У уже отправленных — кликабельная ссылка на конкретный run.
- Для failed — текст ошибки выводится inline (не только в тултипе).

### Диагностика диспатчера

Рядом со счётчиком pending — второй бейдж описывает, чем диспатчер сейчас занят:

| Бейдж | Что значит |
|---|---|
| ⚡ **обрабатывает** | Слот свободен, идёт диспатч |
| ⏳ **ждёт run abc12345…** | Слот занят живым Orchestrator-run'ом; очередь продолжится после его завершения |
| ⏸ **диспатчер остановлен** | Есть pending, но фон-задача упала — нажми «разбудить диспатчер» |
| ⚠ **ошибка проверки слота** | Внутренняя ошибка проверки; тултип содержит текст исключения. Диспатчер всё равно продолжит работу — slot-check fail-open |

### Кнопки управления очередью

- **разбудить диспатчер** — рестартит фоновую задачу. Безопасно: если уже работает, no-op.
- **повторить failed (N)** — флипает все failed обратно в pending. Для эволюций с conflict-gate бесполезно (упадут снова) — для них используй кнопку справа.
- **повторить с force (N)** (красная, с подтверждением) — то же + ставит `force=1` на элементах. Эволюции с conflict теперь пройдут гейт. Кнопка OK в модалке называется «Повторить (force)», не «Удалить» (хоть variant и danger).
- **скрыть выполненные** — убирает `dispatched`/`failed` карточки, оставляя только pending.
- **очистить очередь** (с подтверждением) — обнуляет панель полностью. Уже запущенные runs продолжают жить в БД — это чисто косметика.
- **скрыть** — мгновенное скрытие, когда в очереди только dispatched (закончилось).

### Особенности

- Очередь **in-memory**, теряется при рестарте сервера. Уже отправленные runs живут в БД — теряются только pending. По смыслу нормально: диспатчер просто переустанавливается на старте.
- **Auto-cancel зомби**: если slot-check находит DB-row `status='running'` без живого PM-процесса, диспатчер сам помечает run как `cancelled` (`error_message="auto-cancelled by bulk dispatcher (no live process)"`) — таким образом очередь не зависает на «мёртвых» runs после kill процесса.
- **Идемпотентность**: если у элемента уже привязан жив run, повторный запуск переиспользует его (не плодит дубли).
- **Conflict-gate эволюций**: если ≥2 открытых evolution-предложения нацелены на одного агента, dispatch без force падает с понятным `ValueError`. Решение — либо архивировать конфликтующие, либо «повторить с force».

### На дашборде

На тайле «Оркестрация» рядом с счётчиком running показывается синий бейдж **+N в очереди** (тултип: «Элементы поставлены в очередь для последовательного запуска через Orchestrator»). Появляется только когда `pending > 0`.

## Авто-скролл чата и позиционирование сайдбара

**Сообщения в чате** — sticky-скролл:
- При новом `message_added` через SSE, если ты был у дна (последние 80px) — страница плавно докручивается вниз;
- Если отмотал вверх читать старое — НЕ дёргает: новые сообщения копятся внизу, кнопка прокрутки/инструменты браузера в твоём распоряжении.
- **При первом открытии run'а** страница автоматически прокручивается к последнему сообщению (после `requestAnimationFrame`, чтобы layout успел встать). То есть открываешь run — сразу видишь хвост чата, а не goal-заголовок.

**Левый сайдбар со списком runs**: при загрузке страницы выбранная карточка (`?run_id=...`) автоматически прокручивается в середину сайдбара — больше не теряется под фолдом, когда runs много. Скролл идёт внутри сайдбара, страница в целом не сдвигается.

---

См. также:
- [`cascade.md`](cascade.md) — структурированные multi-stage runs.
- [`live-log.md`](live-log.md) — для self-study runs (другой механизм).
- [`analytics-extras.md`](analytics-extras.md) — Cascade Costs.
- Технически: [`../../features/orchestration.md`](../../features/orchestration.md), [`../../api.md#orchestration`](../../api.md), [`../../schema.md`](../../schema.md).
