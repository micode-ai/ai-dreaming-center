# Live-лог сессий

`/p/{slug}/live` — здесь видно stdout всех running-сессий проекта в реальном времени. Используй для:
- Наблюдения за стартующей сессией (понять, что Claude действительно начал работать).
- Дебага, если сессия залипла.
- Ручной остановки (кнопка `Kill`).

## Содержание

- [Что показывает страница](#что-показывает-страница)
- [Как читать stream](#как-читать-stream)
- [Кнопка Kill](#кнопка-kill)
- [Если ничего не запущено](#если-ничего-не-запущено)
- [Auto-scroll и stream end](#auto-scroll-и-stream-end)

## Что показывает страница

Открой `/p/{slug}/live`. Если в этом проекте есть running-сессии — увидишь по одному блоку на каждую:

- Заголовок с именем агента (моноширинный) и slug-key (`{slug}:{agent}`).
- Кнопка `Kill` справа в углу — красным текстом, в обычной рамке.
- Чёрный `<pre>`-блок с прокруткой, max-height 96 (Tailwind units). Туда потоково льётся stdout.

Если сессий несколько — блоки идут вертикально, каждая со своим streamer'ом.

## Как читать stream

Claude CLI выдаёт stdout в JSONL-формате (один JSON-объект на строку). DC показывает их **as-is** — без парсинга, raw текст. Это даёт максимальную прозрачность, но требует понимания формата.

Типичные строки:

- `{"type":"session_start","model":"claude-sonnet-4-5","cwd":"..."}` — Claude стартанул.
- `{"type":"assistant_message","content":"..."}` — модель сгенерировала текст.
- `{"type":"tool_use","name":"Read","input":{"file_path":"..."}}` — модель решила использовать tool. Тут — Read (читать файл).
- `{"type":"tool_result","content":"...","is_error":false}` — результат tool'а.
- `{"type":"assistant_message","content":"..."}` — followup-ответ модели.
- ... повторяется ...
- `{"type":"result","subtype":"success","total_cost_usd":0.42,"num_turns":15}` — сессия закончилась успешно.
- `{"type":"result","subtype":"error_max_turns"}` — закончилась max_turns'ами.

Что искать:
- Слово `is_error":true` — tool вернул ошибку.
- `subtype` в финальном `result` — success / error_max_turns / error / etc.
- `cost_usd` — сколько стоила сессия.
- Долгое отсутствие новых строк — claude думает (модель отвечает) или завис.

## Кнопка Kill

Кнопка `Kill` (красный текст, кликабельна для running-сессии) — POST на `/p/{slug}/live/kill/{agent}`.

Что происходит:
1. DC находит subprocess по ключу `{slug}:{agent}` в таблице running.
2. Шлёт `process.terminate()` (SIGTERM на Unix, terminate на Windows).
3. Ждёт до 5 секунд graceful shutdown'а.
4. Если процесс жив — `process.kill()` (SIGKILL / forceful).
5. DB row помечается `status='failed'`, `error_message='killed by user'`.
6. Страница `/live` перезагружается.
7. `KeepAwake` (на Windows) если это была последняя сессия — пускает машину в sleep.

Нажимай Kill когда:
- Модель явно зациклилась (одни и те же строки повторяются).
- Сессия слишком долго стоит на одном месте (a tool вызвал что-то очень медленное).
- Тебе нужно срочно освободить slot для другой сессии.

После Kill JSONL claude'а в `~/.claude/projects/<workdir>/<session>.jsonl` остаётся — можешь посмотреть post-mortem.

## Если ничего не запущено

Если на странице нет running-сессий — увидишь только текст «Ничего не запущено». Никаких pre-блоков.

Чтобы что-то запустить — иди в [`rotation.md`](rotation.md), нажми `Start session` рядом с агентом, и тебя редиректнёт сюда.

## Auto-scroll и stream end

Логика streamer'а:
- Каждая новая строка добавляется в `<pre>` через JS event listener.
- `target.scrollTop = target.scrollHeight` — pre всегда прокручивается вниз.
- Когда сервер шлёт SSE-event `end` — JS закрывает EventSource и добавляет в pre строку `[stream ended]`.
- Если ты к этому моменту прокрутил вверх руками — auto-scroll всё равно прыгнёт вниз. (К сожалению, без save-scroll-position.)

Технически `/live/stream/{agent}` — это SSE endpoint (Server-Sent Events) через `sse-starlette`. Каждая stdout-строка одного процесса fan-out'ится во все подписки одного агента: можешь открыть `/live` в нескольких вкладках — все увидят одно и то же.

После `[stream ended]` страница не перезагрузится сама. Обнови, чтобы блок исчез из списка.

---

См. также:
- [`self-study.md`](self-study.md) — что вообще запускается.
- [`rotation.md`](rotation.md) — кнопка Start session.
- [`orchestration.md`](orchestration.md) — для Roman'овских run'ов есть свой live-механизм (polling, не SSE).
- Технически: [`../../api.md`](../../api.md), [`../../routes.md`](../../routes.md), [`../../services.md`](../../services.md).
