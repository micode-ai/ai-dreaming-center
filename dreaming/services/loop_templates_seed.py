"""Bootstrap initial loop templates if the directory is empty."""

from __future__ import annotations

import logging
from pathlib import Path

from dreaming.services.loop_templates import LoopTemplate, list_templates, write_template

log = logging.getLogger(__name__)

_SEEDS: list[LoopTemplate] = [
    LoopTemplate(
        slug="bug-fix-with-tests",
        name="Bug fix с тестами",
        description="Failing test → fix → green. TDD-петля для починки бага.",
        engine="loop",
        max_iterations=6,
        tags=["dev", "bug-fix"],
        team="auto",
        placeholders=[
            {"key": "bug", "label": "Описание бага", "default": ""},
            {"key": "module", "label": "Модуль/файл", "default": ""},
        ],
        body=(
            "Задействуй мою команду из `.claude/agents/`.\n\n"
            "Баг: {{bug}}\n"
            "Модуль: {{module}}\n\n"
            "1. Напиши failing-тест, воспроизводящий баг.\n"
            "2. Найди корневую причину.\n"
            "3. Внеси минимальное исправление.\n"
            "4. Прогоняй тесты до зелёного, не ломая соседние."
        ),
    ),
    LoopTemplate(
        slug="forecast-tuning-segment",
        name="Forecast tuning по сегменту",
        description="Подбор параметров прогноза до целевого MAPE.",
        engine="loop",
        preset="forecast-tuning",
        max_iterations=8,
        tags=["scm", "forecast"],
        team="auto",
        placeholders=[
            {"key": "category", "label": "Категория", "default": "Молочка"},
            {"key": "stores", "label": "Магазины", "default": "5 топ"},
            {"key": "target_mape", "label": "Целевой MAPE %", "default": "12"},
        ],
        body=(
            "Задействуй мою команду из `.claude/agents/`.\n\n"
            "Подобрать параметры прогноза для категории {{category}} "
            "в магазинах {{stores}}.\n"
            "Метрика — MAPE по последним 8 неделям, threshold {{target_mape}}%."
        ),
    ),
    LoopTemplate(
        slug="oos-investigation",
        name="Расследование роста OOS",
        description="Поиск корневой причины OOS по гипотезам.",
        engine="loop",
        max_iterations=6,
        tags=["scm", "investigation"],
        team="auto",
        placeholders=[
            {"key": "category", "label": "Категория", "default": ""},
            {"key": "period", "label": "Период", "default": "последняя неделя"},
        ],
        body=(
            "Задействуй мою команду из `.claude/agents/`.\n\n"
            "Найти причину роста OOS в категории {{category}} за {{period}}.\n\n"
            "Проверить гипотезы по очереди:\n"
            "1) недопоставка, 2) задержка заказа, 3) скачок спроса,\n"
            "4) ошибка прогноза, 5) проблемы ассортимента / master-data.\n"
            "Каждую гипотезу подтвердить или опровергнуть SQL-запросом к RIM."
        ),
    ),
    LoopTemplate(
        slug="pr-self-review",
        name="Self-review перед PR",
        description="Самопроверка изменений по чек-листу.",
        engine="oneshot",
        tags=["dev", "review"],
        team="auto",
        body=(
            "Задействуй мою команду из `.claude/agents/`.\n\n"
            "Прочитай diff текущей ветки vs main и пройди по чек-листу:\n"
            "naming, обработка ошибок, security (OWASP top 10), тесты, документация.\n"
            "Выведи список замечаний приоритетно (high/medium/low) или подтверди, что всё ок."
        ),
    ),
    # ─── SCM business — внутренние и клиентские ───────────────────
    LoopTemplate(
        slug="order-params-tuning",
        name="Подбор параметров автозаказа",
        description="Симуляция параметров автозаказа на исторических данных до целевого service level.",
        engine="loop",
        preset="order-params",
        max_iterations=8,
        tags=["scm", "order"],
        team="auto",
        placeholders=[
            {"key": "scope", "label": "DC / категория", "default": ""},
            {"key": "target_sl", "label": "Целевой service level %", "default": "96"},
            {"key": "max_oos", "label": "Допустимый OOS %", "default": "3"},
        ],
        body=(
            "Задействуй мою команду из `.claude/agents/`.\n\n"
            "Подобрать параметры автозаказа (страховой запас, частоту, min/max) "
            "для {{scope}} на исторических данных так, чтобы service level ≥ {{target_sl}}% "
            "при OOS ≤ {{max_oos}}%.\n"
            "Метрика — комбинированная: SL минус штраф за избыток запаса."
        ),
    ),
    LoopTemplate(
        slug="master-data-anomalies",
        name="Аномалии в master-data RIM",
        description="Поиск битых связей и дублей в справочниках перед релизом.",
        engine="loop",
        max_iterations=6,
        tags=["scm", "investigation", "master-data"],
        team="auto",
        placeholders=[
            {"key": "scope", "label": "Что проверить (категории/магазины/SKU/all)", "default": "all"},
        ],
        body=(
            "Задействуй мою команду из `.claude/agents/`.\n\n"
            "Прогон по master-data RIM ({{scope}}). Искать:\n"
            "артикулы без категории, магазины без формата, дубли SKU, битые иерархии,\n"
            "записи с невалидными датами/нулевыми ценами.\n\n"
            "Каждую итерацию — добавлять найденные проблемы в отчёт.\n"
            "Gate: «новых аномалий за итерацию = 0»."
        ),
    ),
    LoopTemplate(
        slug="sql-optimization",
        name="SQL-оптимизация тяжёлого отчёта",
        description="Ускорение медленного SQL до целевого latency через EXPLAIN PLAN → гипотеза → правка → бенчмарк.",
        engine="loop",
        preset="sql-optimization",
        max_iterations=6,
        tags=["scm", "performance", "sql"],
        team="auto",
        placeholders=[
            {"key": "report", "label": "Название отчёта/дашборда", "default": ""},
            {"key": "current_ms", "label": "Текущее время (мс)", "default": ""},
            {"key": "target_ms", "label": "Целевое время (мс)", "default": "5000"},
        ],
        body=(
            "Задействуй мою команду из `.claude/agents/`.\n\n"
            "Ускорить отчёт «{{report}}» с {{current_ms}}мс до ≤ {{target_ms}}мс.\n\n"
            "На каждой итерации: EXPLAIN PLAN → гипотеза (индекс / переписать join /\n"
            "partition pruning / материализация) → реализация → замер.\n"
            "Gate: время выполнения ≤ цели на 3 прогонах подряд."
        ),
    ),
    LoopTemplate(
        slug="client-forecast-healthcheck",
        name="Health-check прогноза у клиента",
        description="Стартовая проверка качества данных и базового прогноза при онбординге клиента.",
        engine="loop",
        max_iterations=5,
        tags=["scm", "client", "forecast"],
        team="auto",
        placeholders=[
            {"key": "client", "label": "Клиент", "default": ""},
            {"key": "history_months", "label": "Глубина истории (месяцев)", "default": "12"},
        ],
        body=(
            "Задействуй мою команду из `.claude/agents/`.\n\n"
            "Health-check прогноза для клиента {{client}}.\n\n"
            "Проверить по очереди:\n"
            "1) качество master-data (полнота/связность),\n"
            "2) покрытие истории {{history_months}} мес,\n"
            "3) baseline-прогноз по топ-категориям (MAPE, bias),\n"
            "4) проблемные сегменты (что лечим в первую очередь).\n\n"
            "Gate: либо «всё ок, идём в обучение модели», либо собран приоритезированный\n"
            "список блокеров с владельцами."
        ),
    ),
    LoopTemplate(
        slug="client-forecast-diagnosis",
        name="Диагностика «прогноз плохой» (клиент)",
        description="Расследование тикета IntraService о деградации прогноза.",
        engine="loop",
        max_iterations=6,
        tags=["scm", "client", "investigation"],
        team="auto",
        placeholders=[
            {"key": "ticket", "label": "Номер тикета IntraService", "default": ""},
            {"key": "scope", "label": "Сегмент (категория/SKU/магазин)", "default": ""},
        ],
        body=(
            "Задействуй мою команду из `.claude/agents/`.\n\n"
            "Тикет {{ticket}}: «прогноз плохой» по сегменту {{scope}}.\n\n"
            "Проверить гипотезы:\n"
            "1) изменение структуры данных (новые/удалённые SKU, реклассификация),\n"
            "2) промо-календарь (был учтён?),\n"
            "3) праздники локали клиента,\n"
            "4) ремонт/закрытия магазинов в периоде,\n"
            "5) дрейф модели после последнего релиза.\n\n"
            "Gate: identified root cause c подтверждающими цифрами либо\n"
            "обоснованный «данных недостаточно, нужны X, Y»."
        ),
    ),
    LoopTemplate(
        slug="pre-demo-checklist",
        name="Пред-демо проверка",
        description="Прогон чек-листа перед демонстрацией клиенту.",
        engine="oneshot",
        tags=["scm", "client", "demo"],
        team="auto",
        placeholders=[
            {"key": "client", "label": "Клиент", "default": ""},
            {"key": "demo_date", "label": "Дата демо", "default": ""},
        ],
        body=(
            "Задействуй мою команду из `.claude/agents/`.\n\n"
            "Проверка перед демо для {{client}} ({{demo_date}}).\n\n"
            "Чек-лист:\n"
            "- данные свежие (последний апдейт за сутки),\n"
            "- ключевые дашборды открываются и не падают,\n"
            "- метрики прогноза в норме (нет провалов по топ-SKU),\n"
            "- сценарии демо проходят на тестовых данных,\n"
            "- pull свежей версии стенда, миграции применены.\n\n"
            "Вернуть зелёный/жёлтый/красный статус по каждому пункту."
        ),
    ),
    # ─── Dev: bug-finding ─────────────────────────────────────────
    LoopTemplate(
        slug="bug-reproduce",
        name="Воспроизвести баг по тикету",
        description="Reproduce-loop: тикет IntraService → минимальный сценарий воспроизведения.",
        engine="loop",
        max_iterations=5,
        tags=["dev", "bug-fix", "investigation"],
        team="auto",
        placeholders=[
            {"key": "ticket", "label": "ID тикета IntraService", "default": ""},
        ],
        body=(
            "Задействуй мою команду из `.claude/agents/`.\n\n"
            "Воспроизвести баг из тикета {{ticket}}.\n\n"
            "1) Прочитать тикет и собрать стек/логи/окружение.\n"
            "2) Построить минимальный сценарий воспроизведения.\n"
            "3) Прогнать локально/на стенде.\n\n"
            "Gate: баг воспроизводится локально, либо собран отчёт «нужны X, Y, Z»."
        ),
    ),
    LoopTemplate(
        slug="bug-bisect",
        name="Bisect-loop: когда сломалось",
        description="Бинарный поиск виновного коммита между working и broken.",
        engine="loop",
        max_iterations=10,
        tags=["dev", "bug-fix"],
        team="auto",
        placeholders=[
            {"key": "good_ref", "label": "Известно рабочий ref", "default": "main"},
            {"key": "bad_ref", "label": "Сломанный ref", "default": "HEAD"},
            {"key": "check", "label": "Команда-проверка (exit 0 = ok)", "default": ""},
        ],
        body=(
            "Задействуй мою команду из `.claude/agents/`.\n\n"
            "git bisect между {{good_ref}} (good) и {{bad_ref}} (bad).\n"
            "На каждом шаге: checkout → выполнить `{{check}}` → отметить good/bad.\n\n"
            "Gate: найден первый плохой коммит, проанализировать diff и"
            " вернуть гипотезу о причине."
        ),
    ),
    LoopTemplate(
        slug="flaky-test-investigation",
        name="Flaky-test расследование",
        description="Поиск причины плавающего теста через массовые прогоны.",
        engine="loop",
        max_iterations=6,
        tags=["dev", "testing"],
        team="auto",
        placeholders=[
            {"key": "test", "label": "Полный путь теста", "default": ""},
            {"key": "runs", "label": "Сколько прогонов на итерацию", "default": "20"},
        ],
        body=(
            "Задействуй мою команду из `.claude/agents/`.\n\n"
            "Тест {{test}} падает не всегда. Прогнать {{runs}} раз, собрать diff между\n"
            "успехами и провалами (порядок, время, состояние БД, race-окна).\n\n"
            "Gate: гипотеза о причине + минимальный reproducer (можно с временной задержкой)."
        ),
    ),
    # ─── Dev: testing & quality ───────────────────────────────────
    LoopTemplate(
        slug="coverage-up",
        name="Поднять покрытие модуля",
        description="Генерация тестов до целевого coverage без регрессий.",
        engine="loop",
        max_iterations=8,
        tags=["dev", "testing"],
        team="auto",
        placeholders=[
            {"key": "module", "label": "Модуль/папка", "default": ""},
            {"key": "current", "label": "Текущий coverage %", "default": ""},
            {"key": "target", "label": "Целевой coverage %", "default": "80"},
        ],
        body=(
            "Задействуй мою команду из `.claude/agents/`.\n\n"
            "Поднять покрытие модуля {{module}} с {{current}}% до {{target}}%.\n\n"
            "На каждой итерации: посмотреть отчёт coverage → выбрать самые тяжёлые\n"
            "непокрытые ветки → написать тесты → прогнать suite целиком.\n\n"
            "Gate: целевой coverage достигнут И все тесты зелёные (нет регрессий)."
        ),
    ),
    LoopTemplate(
        slug="dependency-upgrade",
        name="Обновить зависимость",
        description="Обновление пакета с починкой ломок и проверкой тестов.",
        engine="loop",
        max_iterations=6,
        tags=["dev", "maintenance"],
        team="auto",
        placeholders=[
            {"key": "package", "label": "Пакет", "default": ""},
            {"key": "from_ver", "label": "С версии", "default": ""},
            {"key": "to_ver", "label": "До версии", "default": "latest"},
        ],
        body=(
            "Задействуй мою команду из `.claude/agents/`.\n\n"
            "Обновить {{package}} c {{from_ver}} до {{to_ver}}.\n\n"
            "1) Прочитать changelog, выделить breaking changes.\n"
            "2) Обновить lock-файл и зависимые места.\n"
            "3) Чинить ломки до зелёных тестов.\n\n"
            "Gate: тесты зелёные, новых deprecation warnings ≤ 5."
        ),
    ),
    LoopTemplate(
        slug="perf-regression-fix",
        name="Устранить регрессию latency",
        description="Профилирование и устранение деградации производительности эндпоинта.",
        engine="loop",
        preset="sql-optimization",
        max_iterations=6,
        tags=["dev", "performance"],
        team="auto",
        placeholders=[
            {"key": "endpoint", "label": "Эндпоинт/функция", "default": ""},
            {"key": "baseline", "label": "Baseline latency (мс)", "default": ""},
            {"key": "current", "label": "Текущий latency (мс)", "default": ""},
        ],
        body=(
            "Задействуй мою команду из `.claude/agents/`.\n\n"
            "{{endpoint}} стал медленнее: было {{baseline}}мс, стало {{current}}мс.\n\n"
            "На каждой итерации: профайлинг → гипотеза → правка → замер.\n"
            "Gate: latency ≤ baseline на 5 прогонах подряд."
        ),
    ),
]


def seed_if_empty(templates_dir: str) -> int:
    """Seed missing templates. Returns count newly written.

    Existing templates are never overwritten — this lets the function
    safely add new seed entries on subsequent app startups.
    """
    if not templates_dir:
        return 0
    base = Path(templates_dir)
    existing_slugs = {t.slug for t in list_templates(templates_dir)} if base.exists() else set()
    written = 0
    for tpl in _SEEDS:
        if tpl.slug in existing_slugs:
            continue
        write_template(templates_dir, tpl)
        written += 1
    if written:
        log.info("Seeded %d loop templates into %s", written, templates_dir)
    return written
