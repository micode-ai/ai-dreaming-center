"""Seed AI Radar — данные для ручной проверки UI до того, как заработает реальный сканер.

Создаёт sources.yaml с базовым watchlist-ом (Karpathy, Anthropic, OpenAI, HF,
arXiv) и вставляет 5 фиктивных findings в data/dreaming.db. Идемпотентен:
UNIQUE(source_key, url) защищает от дублей при повторном запуске.

    python scripts/seed_ai_radar.py
"""
from __future__ import annotations
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dreaming.services.db import SqliteDB  # noqa: E402
from dreaming.services import ai_radar  # noqa: E402


SOURCES_YAML = """\
# AI Radar — watchlist по умолчанию. Идея: пользователь почти ничего не
# добавляет руками — приложение шипается с этим набором, юзер лишь правит.
# Все строковые поля помимо key/name/tags считаются URL-ами (X/blog/rss/...).

people:
  - key: karpathy
    name: "Andrej Karpathy"
    x: "https://x.com/karpathy"
    blog: "https://karpathy.github.io/"
    youtube: "https://www.youtube.com/@AndrejKarpathy"
    tags: [education, agents, llm-internals]

  - key: sutskever
    name: "Ilya Sutskever"
    org_url: "https://ssi.inc/"
    tags: [safety, frontier]

  - key: jimfan
    name: "Jim Fan"
    x: "https://x.com/DrJimFan"
    tags: [agents, robotics, embodied]

  - key: chris_olah
    name: "Chris Olah"
    x: "https://x.com/ch402"
    blog: "https://colah.github.io/"
    tags: [interpretability]

  - key: nathan_lambert
    name: "Nathan Lambert"
    blog: "https://www.interconnects.ai/"
    x: "https://x.com/natolambert"
    tags: [post-training, rlhf]

  - key: simonw
    name: "Simon Willison"
    blog: "https://simonwillison.net/"
    x: "https://x.com/simonw"
    tags: [tooling, practical, agents]

  - key: chollet
    name: "François Chollet"
    blog: "https://fchollet.com/"
    x: "https://x.com/fchollet"
    tags: [reasoning, arc]

  - key: tri_dao
    name: "Tri Dao"
    blog: "https://tridao.me/"
    x: "https://x.com/tri_dao"
    tags: [architectures, efficiency]

  - key: raschka
    name: "Sebastian Raschka"
    blog: "https://magazine.sebastianraschka.com/"
    x: "https://x.com/rasbt"
    tags: [education, llm-engineering]

  - key: lilian_weng
    name: "Lilian Weng"
    blog: "https://lilianweng.github.io/"
    tags: [surveys, agents]

orgs:
  - key: anthropic
    name: "Anthropic"
    news: "https://www.anthropic.com/news"
    research: "https://www.anthropic.com/research"
    tags: [claude, safety, interpretability]

  - key: openai
    name: "OpenAI"
    blog: "https://openai.com/blog"
    tags: [gpt, agents]

  - key: deepmind
    name: "Google DeepMind"
    blog: "https://deepmind.google/discover/blog/"
    tags: [gemini, science]

  - key: meta_fair
    name: "Meta AI (FAIR)"
    blog: "https://ai.meta.com/blog/"
    tags: [llama, open-weights, research]

  - key: mistral
    name: "Mistral AI"
    news: "https://mistral.ai/news/"
    tags: [open-weights, efficiency]

  - key: qwen
    name: "Qwen (Alibaba)"
    blog: "https://qwenlm.github.io/blog/"
    tags: [open-weights, multilingual]

  - key: deepseek
    name: "DeepSeek"
    blog: "https://www.deepseek.com/"
    tags: [open-weights, reasoning]

  - key: ai2
    name: "Allen Institute for AI (AI2)"
    blog: "https://allenai.org/blog"
    tags: [olmo, open-science]

  - key: xai
    name: "xAI"
    news: "https://x.ai/news"
    tags: [grok, frontier]

  - key: cohere
    name: "Cohere"
    blog: "https://cohere.com/blog"
    tags: [enterprise, rag]

  - key: huggingface
    name: "Hugging Face"
    blog: "https://huggingface.co/blog"
    tags: [open-source, ecosystem]

feeds:
  - key: hf_daily
    name: "Hugging Face Daily Papers"
    url: "https://huggingface.co/papers"
    tags: [papers]

  - key: arxiv_cs_cl
    name: "arXiv cs.CL"
    rss: "http://export.arxiv.org/rss/cs.CL"
    tags: [papers, nlp]

  - key: arxiv_cs_lg
    name: "arXiv cs.LG"
    rss: "http://export.arxiv.org/rss/cs.LG"
    tags: [papers, ml]

  - key: import_ai
    name: "Import AI (Jack Clark)"
    url: "https://importai.substack.com/"
    tags: [newsletter, policy, frontier]

  - key: the_batch
    name: "The Batch (DeepLearning.AI)"
    url: "https://www.deeplearning.ai/the-batch/"
    tags: [newsletter, weekly]

  - key: latent_space
    name: "Latent Space (swyx)"
    url: "https://www.latent.space/"
    tags: [newsletter, engineering, agents]
"""


def _seed_records() -> list[dict]:
    now = datetime.now(timezone.utc)
    iso = lambda d: d.isoformat()  # noqa: E731
    return [
        {
            "source_key": "karpathy",
            "source_kind": "person",
            "url": "https://example.test/karpathy/seed-llm-zoo",
            "title": "Karpathy: краткий обзор LLM zoo 2026",
            "summary_ru": "Карпатый прошёлся по текущим архитектурам — что выжило, что отвалилось, куда смотрит лагерь академии vs индустрии.",
            "summary_en": "Karpathy's quick map of the 2026 LLM zoo — what survived, what didn't, where academia diverges from industry.",
            "published_at": iso(now - timedelta(days=1)),
            "tags_json": '["education", "agents", "llm-internals"]',
            "novelty_score": 0.7,
            "relevance_hint": "",
        },
        {
            "source_key": "anthropic",
            "source_kind": "org",
            "url": "https://example.test/anthropic/seed-mech-interp",
            "title": "Anthropic: интерпретируемость головок Claude — март 2026",
            "summary_ru": "Новый paper по mechanistic interpretability: разбор где в Claude хранится «личность» агента и как это меняется через тонкие настройки.",
            "summary_en": "New mech-interp paper: dissecting where Claude stores an agent persona and how light fine-tunes shift it.",
            "published_at": iso(now - timedelta(days=3)),
            "tags_json": '["interpretability", "claude", "safety"]',
            "novelty_score": 0.85,
            "relevance_hint": "",
        },
        {
            "source_key": "openai",
            "source_kind": "org",
            "url": "https://example.test/openai/seed-realtime-agents",
            "title": "OpenAI: realtime API для агентов c голосом",
            "summary_ru": "OpenAI обновили realtime API — добавили поддержку tool-use внутри голосовых сессий с задержкой <250 мс.",
            "summary_en": "OpenAI ships realtime API tool-use inside voice sessions, sub-250ms latency.",
            "published_at": iso(now - timedelta(days=5)),
            "tags_json": '["gpt", "agents", "voice"]',
            "novelty_score": 0.6,
            "relevance_hint": "",
        },
        {
            "source_key": "hf_daily",
            "source_kind": "feed",
            "url": "https://example.test/hf/seed-paper-rlhf-cheaper",
            "title": "Paper: RLHF дешевле на порядок через self-play preference data",
            "summary_ru": "Авторы предлагают генерить preference-пары полностью моделью и матчатся с человеческими разметками на 96%.",
            "summary_en": "Authors generate preference pairs from the model itself and match human labels at 96% — 10× cheaper than human RLHF.",
            "published_at": iso(now - timedelta(days=2)),
            "tags_json": '["papers", "rlhf"]',
            "novelty_score": 0.55,
            "relevance_hint": "",
        },
        {
            "source_key": "deepmind",
            "source_kind": "org",
            "url": "https://example.test/deepmind/seed-gemini-coder",
            "title": "DeepMind: Gemini Coder 2 — SOTA на SWE-bench Verified",
            "summary_ru": "Новый кодер от DeepMind рвёт SWE-bench Verified на 8 п.п. за счёт улучшенного длинного контекста и patch-первой архитектуры.",
            "summary_en": "DeepMind's new coder takes SWE-bench Verified by 8 points via better long-context and patch-first architecture.",
            "published_at": iso(now - timedelta(hours=14)),
            "tags_json": '["coding", "gemini", "benchmarks"]',
            "novelty_score": 0.75,
            "relevance_hint": "",
        },
    ]


async def main() -> int:
    sources_path = ai_radar.DEFAULT_SOURCES_PATH
    sources_path.parent.mkdir(parents=True, exist_ok=True)
    if not sources_path.exists():
        sources_path.write_text(SOURCES_YAML, encoding="utf-8")
        print(f"wrote watchlist: {sources_path}")
    else:
        print(f"watchlist already exists: {sources_path} (left untouched)")

    db_path = "data/dreaming.db"
    db = SqliteDB(db_path)
    await db.connect()
    try:
        inserted = await db.insert_radar_findings(_seed_records())
        rows = await db.list_radar_findings(limit=20)
        print(f"inserted: {inserted} / 5 seed records")
        print(f"radar table now holds: {len(rows)} rows")
    finally:
        await db.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
