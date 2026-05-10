# AI Dreaming Center — Documentation

Available in two languages — choose one:

## English

- [English documentation index](en/README.md) — full tech + user guides
- Quickstart: [en/user/getting-started.md](en/user/getting-started.md)
- Tech reference: [en/architecture.md](en/architecture.md), [en/api.md](en/api.md), [en/schema.md](en/schema.md), [en/configuration.md](en/configuration.md)

## Русский / Russian

- [Русский указатель](ru/README.md) — полная техническая + пользовательская документация
- Quickstart: [ru/user/getting-started.md](ru/user/getting-started.md)
- Tech reference: [ru/architecture.md](ru/architecture.md), [ru/api.md](ru/api.md), [ru/schema.md](ru/schema.md), [ru/configuration.md](ru/configuration.md)

## Language-agnostic

- [smoke-tests.md](smoke-tests.md) — manual smoke verification scripts
- [superpowers/specs/](superpowers/specs/) — design specs
- [superpowers/plans/](superpowers/plans/) — wave implementation plans

## Structure

```
docs/
+-- README.md                # this file (multilingual index)
+-- smoke-tests.md           # mixed RU/EN reference
+-- superpowers/             # design history (RU+EN mixed)
+-- ru/                      # Russian docs
|   +-- README.md            # Russian index
|   +-- (tech docs in RU)
|   +-- user/                # user-facing docs in RU
+-- en/                      # English docs (parallel structure to ru/)
    +-- README.md            # English index
    +-- (tech docs in EN)
    +-- user/                # user-facing docs in EN
```
