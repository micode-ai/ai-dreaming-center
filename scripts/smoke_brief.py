"""Smoke-тест уточняющего брифа на запуске сборки/написания.

Оператор может дописать направление в момент запуска — «Собрать» у кампании
и «Согласовать и написать» у статьи. Текст доезжает до сессии ТОЛЬКО через
окружение (`DC_CREATIVE_BRIEF` / `DC_ARTICLE_BRIEF`); промпт остаётся чистой
слэш-командой, потому что дописанный в промпт текст уводит спавн в отказ от
записи (см. `_build_self_study_prompt` и историю ротации).

Покрывает:
  - бриф из формы сохраняется на заявке и доезжает до env сессии;
  - промпт при этом остаётся ровно `/<команда> <id>`;
  - пустое поле не перетирает уже сохранённый бриф (повторный запуск);
  - бриф и замечания к доработке — РАЗНЫЕ каналы: доработка не затирает бриф
    и не выдаёт себя за него;
  - `revise`, который вызывает approve прямым питоновским вызовом, не роняется
    на дефолте `Form("")`.

Выход 0 — всё ок; ненулевой код + диагностика в stderr — что упало.
"""
from __future__ import annotations
import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Как и остальные смоки: поднимаем настоящее приложение TestClient-ом, поэтому
# берём документированный opt-out на общую БД (стартап иначе откажется
# делить путь с живым сервером разработчика).
os.environ.setdefault("DC_ALLOW_MULTI_INSTANCE", "1")

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

from dreaming.services.db import SqliteDB  # noqa: E402
from dreaming.services.projects import ProjectsService  # noqa: E402


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


class Dispatches:
    """Перехватчик pm.start_command: запоминает промпт и окружение спавна.

    Настоящий CLI в смоке запускать нечем и незачем — проверяемое поведение
    целиком в том, ЧТО роут передаёт в спавн.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def install(self, pm) -> None:
        async def start_command(project, **kw):
            self.calls.append(kw)
            return f"sess-{len(self.calls)}"
        pm.start_command = start_command

    @property
    def last(self) -> dict:
        return self.calls[-1]

    def env(self, key: str) -> str:
        return (self.last.get("env_overrides") or {}).get(key, "")


def install_command(root: Path, name: str) -> None:
    """Слэш-команда должна лежать там, где будет cwd сессии, иначе роут
    откажется диспатчить ещё до спавна."""
    d = root / ".claude" / "commands"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text("# stub\n", encoding="utf-8")


async def main() -> int:  # noqa: C901
    from starlette.testclient import TestClient
    from dreaming.main import app

    prior_db = os.environ.get("DC_DB_PATH")
    db_dir = Path(tempfile.mkdtemp(prefix="dc_smoke_brief_db_"))
    repo = Path(tempfile.mkdtemp(prefix="dc_smoke_brief_repo_"))
    (repo / "docs" / "marketing" / "creatives").mkdir(parents=True)
    (repo / "blog").mkdir(parents=True)
    install_command(repo, "make-creative")
    install_command(repo, "write-article")
    os.environ["DC_DB_PATH"] = str(db_dir / "t.db")

    try:
        with TestClient(app) as client:
            db = app.state.db
            svc = ProjectsService(db)
            proj = await svc.create(
                slug="brief", label="Brief", working_dir=str(repo))
            await svc.set_setting(
                proj.id, "creative_dir", "docs/marketing/creatives")
            await svc.set_setting(proj.id, "article_blog_dir", "blog")

            taps = Dispatches()
            taps.install(app.state.process_manager)

            # ---- креативы ------------------------------------------------
            cid = await db.add_creative_proposal(
                proj.id, source="manual", source_ref="", evidence="checked",
                title="Voice", angle="", slug_hint="voice",
                formats="post-4x5", locales="pl")

            r = client.post(f"/p/brief/creatives/{cid}/approve",
                            data={"brief": "  делай упор на офлайн-режим  "})
            if r.status_code not in (200, 303):
                fail(f"creative approve с брифом: {r.status_code} {r.text[:300]}")
                return 1
            if not taps.calls:
                fail("creative approve не дошёл до спавна")
                return 1
            if taps.env("DC_CREATIVE_BRIEF") != "делай упор на офлайн-режим":
                fail("бриф не доехал до окружения сессии кампании (обрезанным "
                     f"по краям): {taps.env('DC_CREATIVE_BRIEF')!r}")
                return 1
            if taps.last.get("prompt") != f"/make-creative {cid}":
                fail("промпт кампании перестал быть чистой слэш-командой: "
                     f"{taps.last.get('prompt')!r}")
                return 1
            row = await db.get_creative_proposal(cid)
            if (row.get("brief") or "") != "делай упор на офлайн-режим":
                fail(f"бриф не сохранился на заявке: {row.get('brief')!r}")
                return 1
            print("ok: бриф кампании сохранён, обрезан и доехал до env; "
                  "промпт остался чистой слэш-командой")

            # Повторный запуск с пустым полем: бриф не должен обнулиться —
            # иначе retry молча теряет направление оператора.
            await db.set_creative_proposal_status(cid, "failed")
            r = client.post(f"/p/brief/creatives/{cid}/approve",
                            data={"brief": ""})
            if r.status_code not in (200, 303):
                fail(f"повторный creative approve: {r.status_code}")
                return 1
            if taps.env("DC_CREATIVE_BRIEF") != "делай упор на офлайн-режим":
                fail("пустое поле перетёрло сохранённый бриф кампании: "
                     f"{taps.env('DC_CREATIVE_BRIEF')!r}")
                return 1
            print("ok: пустое поле не перетирает сохранённый бриф кампании")

            # Доработка — отдельный канал. Бриф остаётся, замечания приходят
            # своей переменной, и одно не выдаёт себя за другое.
            await db.mark_creative_made(
                cid, draft_ref="voice/post-4x5.png", verify_output="",
                maker_agent="aba-designer", verify_ok=True, verify_label="ok")
            r = client.post(f"/p/brief/creatives/{cid}/revise",
                            data={"notes": "первый кадр слабый"})
            if r.status_code not in (200, 303):
                fail(f"creative revise: {r.status_code} {r.text[:300]}")
                return 1
            if taps.env("DC_CREATIVE_REVISION_NOTES") != "первый кадр слабый":
                fail("замечания доработки не доехали: "
                     f"{taps.env('DC_CREATIVE_REVISION_NOTES')!r}")
                return 1
            if taps.env("DC_CREATIVE_BRIEF") != "делай упор на офлайн-режим":
                fail("доработка потеряла бриф кампании: "
                     f"{taps.env('DC_CREATIVE_BRIEF')!r}")
                return 1
            print("ok: доработка кампании не трогает бриф и едет своим каналом")

            # ---- статьи --------------------------------------------------
            aid = await db.add_article_proposal(
                proj.id, source="manual", source_ref="", evidence="checked",
                title="Offline", angle="", slug_hint="offline")

            r = client.post(f"/p/brief/articles/{aid}/approve",
                            data={"brief": "  без сравнений с конкурентами  "})
            if r.status_code not in (200, 303):
                fail(f"article approve с брифом: {r.status_code} {r.text[:300]}")
                return 1
            if taps.env("DC_ARTICLE_BRIEF") != "без сравнений с конкурентами":
                fail("бриф не доехал до окружения сессии статьи: "
                     f"{taps.env('DC_ARTICLE_BRIEF')!r}")
                return 1
            if taps.last.get("prompt") != f"/write-article {aid}":
                fail("промпт статьи перестал быть чистой слэш-командой: "
                     f"{taps.last.get('prompt')!r}")
                return 1
            arow = await db.get_article_proposal(aid)
            if (arow.get("brief") or "") != "без сравнений с конкурентами":
                fail(f"бриф не сохранился на заявке статьи: {arow.get('brief')!r}")
                return 1
            print("ok: бриф статьи сохранён и доехал до env; промпт чистый")

            await db.set_article_proposal_status(aid, "failed")
            r = client.post(f"/p/brief/articles/{aid}/approve", data={})
            if r.status_code not in (200, 303):
                fail(f"повторный article approve без поля: {r.status_code}")
                return 1
            if taps.env("DC_ARTICLE_BRIEF") != "без сравнений с конкурентами":
                fail("отсутствующее поле перетёрло бриф статьи: "
                     f"{taps.env('DC_ARTICLE_BRIEF')!r}")
                return 1
            print("ok: отсутствующее поле не перетирает бриф статьи")

            # ---- формы на карточках --------------------------------------
            # Сейчас обе заявки в работе ('making' / 'writing'): сессия уже
            # запущена, дописывать ей направление некуда, поэтому поля быть
            # не должно — иначе оператор печатает в пустоту.
            page = client.get("/p/brief/creatives").text
            if 'name="brief"' in page:
                fail("поле brief показано у кампании, которая уже собирается")
                return 1
            page = client.get("/p/brief/articles").text
            if 'name="brief"' in page:
                fail("поле brief показано у статьи, которая уже пишется")
                return 1
            print("ok: у запущенной заявки поля brief нет")

            # А на заявке, которую можно (пере)запустить, поле есть и
            # предзаполнено — иначе повторный запуск не показывает, с каким
            # направлением он поедет.
            await db.set_creative_proposal_status(cid, "failed")
            await db.set_article_proposal_status(aid, "failed")
            page = client.get("/p/brief/creatives").text
            if 'name="brief"' not in page:
                fail("на странице кампаний нет поля brief")
                return 1
            if "делай упор на офлайн-режим" not in page:
                fail("поле brief на странице кампаний не предзаполнено "
                     "сохранённым брифом")
                return 1
            if 'form="creative-make-%d"' % cid not in page:
                fail("поле brief не привязано к форме запуска кампании")
                return 1
            page = client.get("/p/brief/articles").text
            if 'name="brief"' not in page:
                fail("на странице статей нет поля brief")
                return 1
            if "без сравнений с конкурентами" not in page:
                fail("поле brief на странице статей не предзаполнено "
                     "сохранённым брифом")
                return 1
            if 'form="article-write-%d"' % aid not in page:
                fail("поле brief не привязано к форме запуска статьи")
                return 1
            print("ok: поле brief есть на обеих страницах, предзаполнено и "
                  "привязано к своей форме запуска")

        # ---- порядок колонок ----------------------------------------
        # `brief` добавлен ALTER TABLE ADD COLUMN, а он умеет только
        # дописывать в конец. Значит в CREATE TABLE он тоже должен стоять
        # последним, иначе свежая база и миграция молча расходятся в порядке
        # колонок. Тот же пин, что у article_proposals в smoke_articles, —
        # для таблицы, которую этот же коммит и мигрирует.
        order_tmp = Path(tempfile.mkdtemp(prefix="dc_smoke_brief_order_"))
        order_db = SqliteDB(str(order_tmp / "order.db"))
        await order_db.connect()
        try:
            async with order_db._conn.execute(
                "PRAGMA table_info(creative_proposals)"
            ) as cur:
                fresh = [row[1] for row in await cur.fetchall()]
        finally:
            await order_db.close()
        if fresh[-1] != "brief":
            fail("в свежей базе creative_proposals.brief не последняя "
                 f"колонка, а миграция допишет её в конец: {fresh}")
            return 1
        print("ok: creative_proposals.brief стоит последней и в свежей базе")

        print("\nALL OK")
        return 0
    finally:
        if prior_db is None:
            os.environ.pop("DC_DB_PATH", None)
        else:
            os.environ["DC_DB_PATH"] = prior_db


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
