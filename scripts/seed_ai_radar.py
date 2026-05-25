"""Seed AI Radar: write the default watchlist, then populate it with REAL
findings via the live RSS/Atom scanner (dreaming.services.ai_radar_scan).

Idempotent: UNIQUE(source_key, url) dedups across runs.

    python scripts/seed_ai_radar.py
"""
from __future__ import annotations
import asyncio
import sys
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


async def main() -> int:
    sources_path = ai_radar.DEFAULT_SOURCES_PATH
    sources_path.parent.mkdir(parents=True, exist_ok=True)
    if not sources_path.exists():
        sources_path.write_text(SOURCES_YAML, encoding="utf-8")
        print(f"wrote watchlist: {sources_path}")
    else:
        print(f"watchlist already exists: {sources_path} (left untouched)")

    # Populate with REAL findings via the live RSS/Atom scanner (no fake data).
    from dreaming.services.ai_radar_scan import scan_now
    db = SqliteDB("data/dreaming.db")
    await db.connect()
    try:
        res = await scan_now(db)
        print(f"scan: {res['sources_with_feed']}/{res['sources']} sources had a feed, "
              f"{res['items']} items, {res['inserted']} new inserted")
        rows = await db.list_radar_findings(limit=500)
        print(f"radar table now holds: {len(rows)} rows")
    finally:
        await db.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
