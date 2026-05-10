"""Project-aware sidecar findings parser.

Sidecar reviewers (vera/svetlana/silent-failure-hunter etc.) emit JSON files
with arrays of findings. This module discovers and aggregates them.

JSON layout typically:
  [
    {"id": "...", "title": "...", "severity": "...", "module": "...", "file": "...", "rule": "..."},
    ...
  ]
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import json


@dataclass
class SidecarFinding:
    source_file: str
    reviewer: str
    id: str
    title: str
    severity: str
    module: str
    file: str
    rule: str
    raw: dict = field(default_factory=dict)


def list_sidecar_findings(sidecar_dir: str) -> list[SidecarFinding]:
    p = Path(sidecar_dir)
    if not p.exists() or not p.is_dir():
        return []
    out: list[SidecarFinding] = []
    for jf in sorted(p.rglob("*.json")):
        if jf.name.startswith("_"):
            continue
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        # Heuristic: reviewer name = parent dir or filename stem
        reviewer = jf.parent.name if jf.parent != p else jf.stem
        items = data if isinstance(data, list) else (data.get("findings") or data.get("items") or [])
        for entry in items:
            if not isinstance(entry, dict):
                continue
            out.append(SidecarFinding(
                source_file=str(jf),
                reviewer=reviewer,
                id=str(entry.get("id") or entry.get("uid") or ""),
                title=str(entry.get("title") or entry.get("summary") or ""),
                severity=str(entry.get("severity") or entry.get("priority") or ""),
                module=str(entry.get("module") or ""),
                file=str(entry.get("file") or entry.get("path") or ""),
                rule=str(entry.get("rule") or entry.get("rule_id") or ""),
                raw=entry,
            ))
    return out
