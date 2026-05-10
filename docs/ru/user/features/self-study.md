# Self-study

Self-study — это автоматический режим, в котором Claude перечитывает свой агент-файл и пишет конспект-обновление по своей зоне ответственности. Аналог «agent grokking»: модель идёт на 20 минут «изучать» свою роль и кодовую базу.

## Содержание

- [Что делает self-study](#что-делает-self-study)
- [Как запустить вручную](#как-запустить-вручную)
- [Как запускается автоматически](#как-запускается-автоматически)
- [Жизненный цикл сессии](#жизненный-цикл-сессии)
- [Где смотреть результаты](#где-смотреть-результаты)
- [Когда сессия падает](#когда-сессия-падает)
- [Кастомизация](#кастомизация)

## Что делает self-study

Когда ты говоришь DC «запусти self-study для агента `vera`», DC спавнит Claude CLI с такой командой:

```
claude /self-study vera
```

Где `/self-study` — slash-команда, заранее установленная в `~/.claude/commands/self-study.md` (через agent-team-starter-kit или вручную). Она инструктирует Claude:
1. Прочитать `.claude/agents/vera.md` (где описана зона ответственности).
2. Прочитать релевантные части кодовой базы.
3. Подмешать активные `custom_topics` (если есть, для этого агента) — DC их подкидывает через шаблонные переменные.
4. Написать markdown-конспект в `learning_notes_dir` (по дефолту `.claude/agents/learning-notes/{date}-{agent}.md`).
5. Опционально — обновить какие-то tech-debt items, написать новые ideas, обновить wiki.

Конкретное поведение зависит от того, как написан `/self-study` в твоём starter-kit'е.

## Как запустить вручную

1. Открой `/p/{slug}/rotation`.
2. Найди нужного агента в таблице.
3. Если рядом с ним кнопка `Start session` (синяя) — нажми. Если там написано `running…` — сессия уже идёт.
4. Тебя редиректнёт на `/p/{slug}/live` со streaming-логом.

Для ручного запуска не нужно, чтобы у агента был `enabled=true` — `Start session` работает в любом случае.

## Как запускается автоматически

Каждую ночь cron-job `nightly_learning_{slug}` (по умолчанию в 03:00) делает:
1. Берёт из rotation всех агентов проекта где `enabled=true`.
2. Сортирует по `last_studied_at ASC` (oldest first), tiebreak по `tier ASC`.
3. Берёт top-N (`agents_per_night`, default 3).
4. Запускает их подряд, ожидая `wait_between_sec` (default 30) между сессиями.

Если глобальный `max_concurrent` > 1 — могут идти параллельно. По дефолту = 1.

Чтобы:
- **Поменять время cron'а**: `/settings` или `/p/{slug}/settings` → группа «Scheduling — nightly» → `cron_expression`.
- **Поменять количество агентов за ночь**: `agents_per_night` там же.
- **Временно отключить**: `cron_enabled = false` (на global или per-project уровне).

Подробнее — [`../workflows/nightly-cron.md`](../workflows/nightly-cron.md).

## Жизненный цикл сессии

```
[user clicks Start session]
        |
        v
+------------------+
| pre-create row   |  status='running', started_at=now
| in DB            |
+------------------+
        |
        v
+------------------+
| spawn claude     |  asyncio.create_subprocess_exec
| CLI subprocess   |
+------------------+
        |
        v
+------------------+
| stream stdout    |  ring-buffer + SSE fan-out + watchdog
| watchdog ticks   |
+------------------+
        |
   normal exit?       timeout?           crash?
        |                |                  |
        v                v                  v
   POST /api/         status=             status=
   session/finish     'timeout'           'failed'
   (callback from    (watchdog kills)    (subprocess
    Claude after                           exits != 0)
    /self-study
    finishes)
        |
        v
+------------------+
| status='success' |  finished_at=now, note_path set
+------------------+
```

Если callback не пришёл (claude умер не дав финиш) — reconcile job через 5 минут проверит, есть ли процесс, и закроет row как `failed`.

## Где смотреть результаты

После завершения сессии:

- **Dashboard проекта** (`/p/{slug}/`) — самые свежие 10–20 строк в «Последние сессии» с статусом и временем старта.
- **Live** (`/p/{slug}/live`) — пока сессия running, тут её stdout. После окончания убирается.
- **Конспекты** (`/p/{slug}/notes`) — список md-файлов, которые агенты накладывали. Если `note_path` записан — клик откроет raw-content.
- **AI Usage** (`/p/{slug}/ai-usage`) — токены / cost этой сессии (через 5 минут после ingest cron'а).
- **Aggregated `/`** — incremented success/failed/timeout counters.

## Когда сессия падает

Возможные статусы:

- `success` — claude вернул exit-code 0 и (опционально) DC получил finish callback.
- `failed` — claude вернул exit != 0. В `error_message` запишется stderr или последние строки stdout.
- `timeout` — watchdog убил процесс через `timeout_minutes` минут. В `error_message`: «timeout after N min».
- `running` (зависший) — процесс мёртв, callback не пришёл, reconcile ещё не сработал. Через 5 минут перейдёт в `failed`.

Что делать:

- Открой `/p/{slug}/` → recent sessions → клик на failed-сессию (если есть detail-link) → читай `error_message`.
- Если `error_message` пустой — открой `/p/{slug}/live` (если ещё running) или JSONL claude'а в `~/.claude/projects/<workdir>/<session>.jsonl`.
- Часто причины: модель не нашла агент-файл (имя опечатано), нет API key, slash-команда `/self-study` не установлена, Claude CLI выдал rate-limit.

## Кастомизация

Все ключи доступны на global level (`/settings`) и на per-project level (`/p/{slug}/settings`):

- `self_study_command` — slash-команда, которую дёргает DC. Default: `/self-study`. Меняй если ты переименовал свою команду.
- `self_study_max_turns` — max turns для одной сессии (default 50). Уменьшай для коротких review, увеличивай для глубоких research-задач.
- `self_study_model` — модель Claude (default берётся из агент-файла или fallback). Перебивает per-агентский setting.
- `timeout_minutes` — watchdog (default 20).
- `agents_per_night` — сколько за ночь.
- `wait_between_sec` — пауза между сессиями.
- `max_concurrent` — глобальный потолок параллелизма.

Изменения в settings вступают в силу после Save. Рестарт uvicorn не нужен.

---

См. также:
- [`rotation.md`](rotation.md) — управление списком агентов.
- [`live-log.md`](live-log.md) — наблюдение за running-сессией.
- [`notes.md`](notes.md) — где читать конспекты.
- Технически: [`../../features/self-study.md`](../../features/self-study.md), [`../../api.md#sessions`](../../api.md), [`../../architecture.md`](../../architecture.md).
