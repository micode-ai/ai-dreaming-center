# Настройка nightly cron

Каждую ночь DC автоматически запускает self-study для top-N агентов каждого включённого проекта. Здесь — как сконфигурировать это поведение.

## Содержание

- [Как cron выбирает агентов](#как-cron-выбирает-агентов)
- [Ключевые настройки](#ключевые-настройки)
- [Изменение времени](#изменение-времени)
- [Per-project расписание](#per-project-расписание)
- [Временно отключить](#временно-отключить)
- [Проверить, что cron реально зарегистрирован](#проверить-что-cron-реально-зарегистрирован)

## Как cron выбирает агентов

Алгоритм nightly_learning_{slug}:

1. SELECT из `agent_learning_rotation` для текущего project_id где `enabled=true`.
2. ORDER BY:
   - `last_studied_at ASC NULLS FIRST` — вообще не учившиеся первыми, потом самые давно не учившиеся.
   - `tier ASC` — при tie P1 раньше P2 раньше P3.
3. LIMIT `agents_per_night` (default 3).
4. Запуск этих агентов по одному (или параллельно если `max_concurrent > 1`):
   - Спавн `claude` с prompt'ом `{self_study_command} {agent}`.
   - Custom topics для project_id и target_agents — подмешиваются в env vars / args.
   - Watchdog по `timeout_minutes`.
   - Между запусками — `wait_between_sec` (default 30) пауза.
5. После завершения каждой сессии — обновляет `last_studied_at = now()` для агента.

Эффект: со временем все агенты получают примерно равное внимание, но P1-агенты чаще вытаскиваются вперед при сходных last_studied_at.

## Ключевые настройки

Все доступны на `/settings` (global) и `/p/{slug}/settings` (per-project override).

Группа **Scheduling — nightly**:

- **`cron_enabled`** (bool, default `true`) — мастер-выключатель. Если false — cron-job не регистрируется.
- **`cron_expression`** (str, default `0 3 * * *`) — стандартный 5-частный cron. По дефолту — каждый день в 3:00.
- **`agents_per_night`** (int, default 3) — сколько top-агентов брать.
- **`wait_between_sec`** (int, default 30) — пауза между сессиями.
- **`nightly_max_concurrent`** (int, default следует global `max_concurrent`) — потолок параллелизма для ночного cron'а специально.

Также релевантны (группа Self-study):
- **`self_study_command`** (str, default `/self-study`) — slash-команда, которую дёргает.
- **`self_study_max_turns`** (int, default 50).
- **`self_study_model`** (str) — override модели.
- **`timeout_minutes`** (int, default 20).

## Изменение времени

Cron expression — стандарт:
```
* * * * *
| | | | |
| | | | +-- день недели (0–6, sunday=0)
| | | +---- месяц (1–12)
| | +------ день месяца (1–31)
| +-------- час (0–23)
+---------- минута (0–59)
```

Примеры:
- `0 3 * * *` — каждый день в 3:00.
- `0 4 * * 1-5` — будни в 4:00.
- `0 2,14 * * *` — каждый день в 2:00 и 14:00.
- `30 23 * * 0` — воскресенье 23:30.

Чтобы изменить:
1. `/settings` → группа Scheduling — nightly → ключ `cron_expression`.
2. Впиши новое значение.
3. Save.

DC перезарегистрирует все cron-jobs (один на проект) с новым expression. Изменения видны со следующего тика scheduler'а (обычно через несколько секунд после Save).

**Внимание:** часовой пояс — local time машины DC. Не UTC.

## Per-project расписание

Если хочешь чтобы один проект учился в одно время, второй — в другое:

1. На `/p/{slug-A}/settings` → `cron_expression` → Override → впиши `0 2 * * *`.
2. На `/p/{slug-B}/settings` → `cron_expression` → Override → впиши `0 4 * * *`.
3. Save обе.

Job ID'ы у обоих разные (`nightly_learning_slug-A`, `nightly_learning_slug-B`), поэтому APScheduler триггерит их независимо.

Аналогично можно override'нуть `agents_per_night` (один проект учит 5 агентов, другой — только 1):
- Project A: `agents_per_night = 5`.
- Project B: `agents_per_night = 1`.

## Временно отключить

Способ 1 — глобально для всех:
- `/settings` → `cron_enabled` → uncheck → Save.
- Все nightly_learning_* jobs unregister'ятся.

Способ 2 — per-project:
- `/p/{slug}/settings` → `cron_enabled` → Override → uncheck → Save.
- Только этот проект перестанет получать cron'ы.

Способ 3 — disable весь проект:
- `/projects` → кнопка `Disable` рядом с проектом.
- Cron-job unregister'ится. Проект пропадёт из dropdown'а в шапке.

Способ 4 — disable агента:
- На `/p/{slug}/rotation` toggle `enabled` у конкретного агента в `—`.
- Cron-job ещё работает, но этот агент не в выборке.

Способ 5 — снять с tier:
- Поставь tier P3 — будет браться последним.
- Не отключение, а deprioritisation.

## Проверить, что cron реально зарегистрирован

В UI пока нет страницы со списком jobs (TODO будущей волны).

**Метод 1 — uvicorn-логи на старте** (если запускал с `--log-level debug`):
- В логе при lifespan startup APScheduler пишет: `Adding job tentatively -- it will be properly scheduled when the scheduler starts`. Потом `Added job nightly_learning_my-app to job store ... cron(... )`.

**Метод 2 — ждать**:
- В время `cron_expression` зайди в `/p/{slug}/`. Должна появиться запись session со статусом `running`.

**Метод 3 — interactive REPL** (если разбираешься в коде):
- Открой Python в venv'е DC.
- Импортируй и enuminate jobs scheduler'а через app.state. См. [`../../troubleshooting.md`](../../troubleshooting.md) — там есть snippet.

**Метод 4 — APScheduler jobstore**:
- DC использует MemoryJobStore по дефолту (jobs живут только пока процесс жив). При рестарте всё пересоздаётся.
- Если переключил на SQLAlchemyJobStore (custom) — посмотри в БД.

Если на cron-time не запускается — типичные причины:
- `cron_enabled = false` (global или per-project).
- Проект `enabled = false`.
- В rotation все агенты с `enabled = false` (нет кандидатов).
- DC сервер был выключен в момент cron'а.
- Часовой пояс машины не тот, который ты ожидал.

---

См. также:
- [`../features/self-study.md`](../features/self-study.md) — что вообще делает self-study.
- [`../features/rotation.md`](../features/rotation.md) — управление списком агентов.
- [`../features/settings.md`](../features/settings.md) — где менять настройки.
- [`weekly-scanners.md`](weekly-scanners.md) — opt-in weekly scan'еры.
- Технически: [`../../features/self-study.md`](../../features/self-study.md), [`../../services.md#scheduler`](../../services.md).
