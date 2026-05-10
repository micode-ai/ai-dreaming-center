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

---

См. также:
- [`cascade.md`](cascade.md) — структурированные multi-stage runs.
- [`live-log.md`](live-log.md) — для self-study runs (другой механизм).
- [`analytics-extras.md`](analytics-extras.md) — Cascade Costs.
- Технически: [`../../features/orchestration.md`](../../features/orchestration.md), [`../../api.md#orchestration`](../../api.md), [`../../schema.md`](../../schema.md).
