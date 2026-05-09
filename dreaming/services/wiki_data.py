"""Project-aware wiki status: presence check + domain count.

Wave 2 lean — full deep-audit / health metrics arrive in Wave 4.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


@dataclass
class WikiStatus:
    wiki_dir: str
    exists: bool
    domains_count: int
    domains: list[str]  # short list of first 20 domain names


def get_wiki_status(wiki_dir: str) -> WikiStatus:
    p = Path(wiki_dir)
    if not p.exists() or not p.is_dir():
        return WikiStatus(wiki_dir=wiki_dir, exists=False, domains_count=0, domains=[])
    # Domain markdown files: convention varies — try {wiki_dir}/domains/*.md, then fall back to *.md at root
    domains_dir = p / "domains"
    if domains_dir.exists() and domains_dir.is_dir():
        files = sorted(domains_dir.glob("*.md"))
    else:
        files = sorted(p.glob("*.md"))
    return WikiStatus(
        wiki_dir=wiki_dir,
        exists=True,
        domains_count=len(files),
        domains=[f.stem for f in files[:20]],
    )
