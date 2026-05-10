# Первый день: расширенный onboarding

Шаг-за-шагом от `git clone` до настроенного nightly-расписания. Расширение [`getting-started.md`](../getting-started.md) с дополнительными деталями про подготовку проекта к DC.

## Содержание

- [День 0: предусловия](#день-0-предусловия)
- [Установка Claude CLI](#установка-claude-cli)
- [Настройка `.claude/agents/` в проекте](#настройка-claudeagents-в-проекте)
- [Установка DC](#установка-dc)
- [Первая сессия](#первая-сессия)
- [Первый custom topic](#первый-custom-topic)
- [Первый JSONL через AI Usage](#первый-jsonl-через-ai-usage)
- [День 2: enable weekly scanners](#день-2-enable-weekly-scanners)

## День 0: предусловия

У тебя должно быть:
- Python 3.10+.
- Git.
- Хотя бы один проект на машине (репозиторий, который ты захочешь использовать с DC).
- Anthropic API key или активный Claude Pro/Team plan.
- Желательно — Obsidian для чтения конспектов в красивом виде.

## Установка Claude CLI

DC спавнит `claude` CLI как subprocess. Без него ничего не работает.

**На Windows:**
1. Установи Node.js (если ещё нет): https://nodejs.org/
2. `npm install -g @anthropic-ai/claude-code` — глобальная установка.
3. Проверь: `claude --version` в PowerShell. Должна показаться версия.
4. На Windows shutil.which найдёт `claude.cmd` (а не голый `claude` — это bash-script). DC это умеет.

**На macOS:**
1. `brew install claude` или через npm.
2. Проверь `claude --version`.

**На Linux:**
1. Через npm или package manager твоего дистра.

После установки авторизуйся: `claude` (без аргументов) откроет браузер для login. Или установи API key: `claude config set apiKey <your-key>`.

Это всё нужно сделать **до** первого запуска DC, иначе сессии будут падать с auth-error.

## Настройка `.claude/agents/` в проекте

DC ожидает что у твоего проекта есть `.claude/agents/` папка с md-файлами агентов. Если у тебя нет — создай хотя бы один.

Минимальный пример:

1. `cd D:\Work\micode\my-app`
2. `mkdir .claude\agents`
3. Создай файл `.claude/agents/test-agent.md` с содержимым:
   ```
   ---
   name: test-agent
   description: Test agent для проверки DC.
   ---

   # Test agent

   Я просто читаю файлы проекта и пишу summary в `learning-notes/`.

   ## Задача

   1. Прочитай README.md и pyproject.toml (или package.json).
   2. Напиши конспект-обзор в `.claude/agents/learning-notes/{date}-test-agent.md`.
   3. Заверши.
   ```

Это минимальный агент. Реальные агенты будут более structured — посмотри agent-team-starter-kit.

Если у тебя есть starter-kit:
```
git clone https://github.com/RsCloud2022/agent-team-starter-kit.git temp-kit
xcopy /E /Y temp-kit\.claude D:\Work\micode\my-app\.claude
rmdir /S /Q temp-kit
```

Это даст тебе готовый набор: roman, vera, svetlana, silent-failure-hunter, и slash-команды (`/self-study`, `/wiki-bootstrap`, etc.).

## Установка DC

Теперь — DC.

1. `git clone <repo-url> ai-dreaming-center`
2. `cd ai-dreaming-center`
3. `python -m venv .venv`
4. `.\.venv\Scripts\Activate.ps1` (PowerShell) или `source .venv/Scripts/activate` (bash)
5. `pip install -e .`
6. `python -m uvicorn dreaming.main:app --port 8086`

Открой http://localhost:8086 — попадёшь на `/setup`.

В setup wizard:
- `claude_path` — оставь `claude` (DC сам подхватит `.cmd` на Windows).
- `projects_root` — впиши `D:\Work\micode` (или где у тебя проекты).
- `default_locale` — выбери русский или английский.
- Нажми «Просканировать projects_root».
- В таблице найдёшь `my-app` (галочка `✓` в колонке `.claude` если ты создал агентов выше).
- Сними чекбоксы у проектов, которые сейчас не нужны.
- Выбери default radio для одного проекта.
- Нажми «Сохранить и импортировать».

Готово, DC настроен.

## Первая сессия

1. На `/` увидишь карточку проекта.
2. Кликни → попадёшь на `/p/my-app/`.
3. Переключись на вкладку `Ротация`.
4. Увидишь `test-agent` (или roman/vera/svetlana/etc если starter-kit) с tier P2, enabled ✓, last_studied —.
5. Нажми синюю `Start session`.
6. Тебя редиректит на `/p/my-app/live`. Видишь, как Claude поднимается:
   - JSONL `session_start` event.
   - Reads README.md, package.json, etc.
   - Пишет конспект.
   - Final `result` event.
7. Через несколько минут — `[stream ended]`. Сессия закончилась.
8. Возвращайся на `/p/my-app/` — должна появиться запись `success` в recent sessions.
9. Загляни в `/p/my-app/notes` — увидишь созданный конспект.

## Первый custom topic

Допустим, ты хочешь чтобы агент следующий раз изучал что-то конкретное.

1. Открой `/p/my-app/kanban`.
2. В форме сверху:
   - Title: «Что делает функция X в модуле Y?»
   - Module: оставь пусто (или впиши `auth`).
   - Агенты: оставь пусто (= всем).
   - Что именно изучить: «Как `auth.login()` обрабатывает 2FA? Какие edge case'ы?»
   - Почему важно: «Через 2 недели рефакторинг auth-flow.»
3. Нажми `Добавить`.

Topic появился в таблице. Когда следующий раз агент пойдёт в self-study — этот topic будет включён в его prompt.

## Первый JSONL через AI Usage

После пары сессий иди на `/p/my-app/ai-usage`. Сразу может быть пусто — ai_usage_ingest cron работает с интервалом 5 минут.

Подожди 5–10 минут, обнови страницу:
- Карточки сверху: `Last 7d input/output/cache` — заполнены.
- Таблица `By model` — будет одна строка с `claude-sonnet-4-5` (или какой моделью ты используешь).

Если через 15 минут всё пусто — открой `/ai-usage` (global). Если там тоже пусто:
1. Проверь, что `~/.claude/projects/` существует и в нём есть JSONL'ы.
2. Проверь `claude_projects_dir` в `/settings` (default = `~/.claude/projects/`).
3. Перезапусти uvicorn — ingest job сработает на старте.

Если на global есть, а на per-project пусто — проблема в mapping'е (`cwd` в JSONL не совпадает с `working_dir` в registry). См. [`../features/ai-usage.md`](../features/ai-usage.md).

## День 2: enable weekly scanners

После первого дня знакомства можно подключить «помощников».

1. **Tech-debt scanner**: на `/p/my-app/settings` найди `weekly_tech_debt_scan_enabled` → Override → checkbox true → Save. Также убедись что `tech_debt_dir` прописан (например `D:\Work\micode\my-app\docs\tech-debt\`). Создай папку если нет.

2. **Product ideas scanner**: то же для `weekly_product_ideas_scan_enabled` и `product_ideas_dir`.

3. **Wiki linter**: то же для `weekly_wiki_lint_enabled` и `wiki_dir`.

После Save scheduler перерегистрирует cron-jobs (на следующем тике, обычно сразу). По cron-expression (default `0 4 * * 0` — воскресенье 4 утра) scanner запустится. Через неделю на `/findings` и `/ideas` увидишь artifact'ы.

Если хочешь раньше — пройди в `/p/my-app/wiki` и нажми `Run /wiki-bootstrap`. Это запустит Claude'а сейчас (вне cron'а).

Подробнее: [`weekly-scanners.md`](weekly-scanners.md).

---

См. также:
- [`daily.md`](daily.md) — типичный день после onboarding'а.
- [`new-project.md`](new-project.md) — добавить второй проект.
- [`jira-integration.md`](jira-integration.md) — настройка Jira.
- [`nightly-cron.md`](nightly-cron.md) — детально про nightly.
- [`../features/`](../features/) — feature-guides.
