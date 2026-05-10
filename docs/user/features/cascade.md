# Cascade — структурированный конвейер

Cascade — это orchestration с фиксированной последовательностью фаз и gate-verdict'ами между ними. Используется когда нужны formal quality gates (review-фаза должна approve'нуть design'у прежде чем идёт implementation).

## Содержание

- [Концептуальная модель](#концептуальная-модель)
- [Default stages](#default-stages)
- [Gate verdict](#gate-verdict)
- [Iteration counter](#iteration-counter)
- [Artifacts с дедупом](#artifacts-с-дедупом)
- [Состояние UI в Wave 3.9](#состояние-ui-в-wave-39)
- [Когда полезно использовать cascade](#когда-полезно-использовать-cascade)

## Концептуальная модель

Обычный Roman-run — свободно-формулированная цель, Roman сам решает, как декомпозировать. Cascade — то же самое, но:
1. Заранее определены **stages** (фазы): contract, design, implementation, review, qa.
2. Между stages — **gate** (агент-judge), который оценивает результат фазы и решает: approve, return-to-stage (повторить), reject.
3. Если return-to-stage — счётчик `iteration` инкрементится для этой фазы.
4. Каждый stage может иметь несколько nodes (один stage — один или несколько agent run'ов).

```
contract --[gate]--> design --[gate]--> implementation --[gate]--> review --[gate]--> qa
              |                |                  |                  |
            return           return             return             return
              |                |                  |                  |
              v                v                  v                  v
          new iter         new iter          new iter            new iter
```

Если gate возвращает `approve` — двигаемся дальше. Если `return-to-stage` — текущий stage запускается ещё раз с фидбеком от gate'а. Если `reject` — run завершается failed.

## Default stages

В коде заданы 5 фаз (stages):

1. **contract** — формализация требований. Agent читает goal, артефакты входа, и пишет формальный контракт: что должно получиться, какие constraints, какие acceptance criteria.
2. **design** — техническое решение. Agent читает контракт и предлагает архитектуру, выбор технологий, breakdown в модули.
3. **implementation** — собственно код. Agent (или несколько) кодит согласно design'у.
4. **review** — code review. Agent (vera/svetlana/silent-failure-hunter) ревьюит implementation'у, ищет проблемы.
5. **qa** — финальная проверка. Run tests, validate acceptance criteria, smoke-tests.

Имена и количество stages — конфигурируемы (через настройки проекта или harness adapter), но default — эти 5.

## Gate verdict

Gate — отдельный агент, который запускается **между** stages. Он читает:
- Артефакты предыдущего stage'а (что нагенерировал прошлый агент).
- Acceptance criteria (из contract'а).
- Goal/контекст всего run'а.

И возвращает структурированный JSON:
```
{
  "verdict": "approve" | "return-to-stage" | "reject",
  "stage_name": "design",
  "comment": "Spec-блок неполный: не покрывает edge case X",
  "items": [...]  // список конкретных issues если return/reject
}
```

DC парсит этот JSON и решает:
- `approve` → следующий stage.
- `return-to-stage` → текущий stage запускается заново с iteration+1, передаётся `gate_comment`.
- `reject` → run помечается failed.

Gate-агент конфигурируется per-stage через harness adapter. Имена обычно вида `gate-design`, `gate-implementation`.

## Iteration counter

Каждый stage имеет `iteration` (default 1). Если gate говорит `return-to-stage` — iteration становится 2, потом 3, и т.д.

Есть `max_iterations` (default 3). Если уперлись в потолок и gate всё ещё не одобряет — run автоматически помечается failed с причиной «max iterations reached at stage X».

В DB:
- `orchestrator_nodes.iteration` — для каждой node.
- `orchestrator_runs.current_stage` — где run сейчас.

## Artifacts с дедупом

Каждая фаза может писать **artifacts** — структурированные результаты (например, набор «правил» которые review нашёл, набор tasks которые design предложил).

Artifact identifies by `rule_id` или подобным ключом. Дедуп: если на iteration 1 уже было `rule:auth-session-leak`, и на iteration 2 review снова нашёл то же самое — DC не дублирует, а помечает как повторно найденный.

Это нужно чтобы:
- Не разрастался список «issues» на каждой итерации.
- Можно было tracking — сколько раз rule всплывал.

Artifacts хранятся в `cascade_artifacts` таблице.

## Состояние UI в Wave 3.9

**Важно:** в текущей версии (Wave 3.9) **отдельной cascade-страницы в UI нет**. Cascade runs появляются в общем списке `/p/{slug}/orchestration` вместе с обычными Roman'ами. Различить можно только по data:
- У cascade run в `metadata` (или подобном поле) флаг `kind=cascade`.
- В nodes больше иерархии: stages + sub-nodes per stage.
- В messages — gate verdicts видны как сообщения с особым `kind=gate_verdict`.

Визуализация stages с прогрессом, артефактами, iteration counter'ами — TODO для будущих волн.

Что **есть** в UI сейчас:
- В `/p/{slug}/cascade-costs` — список runs с total cost, includes cascade runs (если они были).
- В `/p/{slug}/orchestration/{id}` — обычная list-view nodes/messages, можешь руками понять последовательность по timestamp'ам.

## Когда полезно использовать cascade

- **Сложные фичи с чёткими acceptance criteria** — где нужно `Spec` artefact чтобы все были на одной странице.
- **High-stakes изменения** — security review, payment-flow refactor — где нужен formal review-gate.
- **Команды агентов с разделением ответственности** — кто-то проектирует, кто-то реализует, кто-то ревьюит.
- **Когда нужна repeatability** — повторяемый flow для типичных задач.

Когда **не** полезно:
- Маленькие задачи (overhead на 5 stages не оправдан).
- Research / exploration (нет чётких acceptance criteria).
- Quick fixes (просто стартани обычного Roman'а).

Cascade runs дороже обычных runs (больше LLM-calls, больше токенов). Используй адекватно scope'у задачи.

---

См. также:
- [`orchestration.md`](orchestration.md) — обычные Roman runs.
- [`analytics-extras.md`](analytics-extras.md) — Cascade Costs аналитика.
- Технически: [`../../features/cascade.md`](../../features/cascade.md), [`../../schema.md#cascade_artifacts`](../../schema.md), [`../../api.md`](../../api.md).
