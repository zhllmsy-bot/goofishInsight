from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_ALIAS_CONFIG_PATH = Path(__file__).resolve().parents[4] / "configs" / "rule_aliases.json"


@dataclass(frozen=True, slots=True)
class RuleAliasEntry:
    category_code: str
    field: str
    value: str
    aliases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuleAliasMatch:
    category_code: str
    field: str
    value: str
    alias: str
    match_type: str
    confidence: float


def normalize_alias_text(value: str) -> str:
    return re.sub(r"[\s\-_/·.]+", "", str(value or "").strip().lower())


@lru_cache(maxsize=16)
def load_rule_alias_entries(config_path: str | None = None) -> tuple[RuleAliasEntry, ...]:
    path = Path(config_path) if config_path else DEFAULT_ALIAS_CONFIG_PATH
    raw_entries = json.loads(path.read_text(encoding="utf-8"))
    entries: list[RuleAliasEntry] = []
    for raw in raw_entries:
        aliases = tuple(str(alias).strip() for alias in raw.get("aliases", []) if str(alias).strip())
        if not aliases:
            continue
        entries.append(
            RuleAliasEntry(
                category_code=str(raw.get("category_code") or "").strip(),
                field=str(raw.get("field") or "").strip(),
                value=str(raw.get("value") or "").strip(),
                aliases=aliases,
            )
        )
    return tuple(entries)


def match_rule_alias(
    *,
    title: str,
    category_code: str,
    field: str,
    config_path: str | None = None,
) -> RuleAliasMatch | None:
    normalized_title = normalize_alias_text(title)
    if not normalized_title:
        return None

    exact_candidates: list[RuleAliasMatch] = []
    contains_candidates: list[RuleAliasMatch] = []
    for entry in load_rule_alias_entries(config_path):
        if entry.category_code != category_code or entry.field != field:
            continue
        for alias in entry.aliases:
            normalized_alias = normalize_alias_text(alias)
            if not normalized_alias:
                continue
            if normalized_title == normalized_alias:
                exact_candidates.append(_build_match(entry, alias=alias, match_type="exact", confidence=0.95))
            elif normalized_alias in normalized_title:
                confidence = 0.75 if len(normalized_alias) >= 4 else 0.62
                contains_candidates.append(
                    _build_match(entry, alias=alias, match_type="contains", confidence=confidence)
                )

    # Rule application order is explicit:
    # exact alias -> contains alias -> template token fallback (outside this matcher).
    if exact_candidates:
        return _pick_best_match(exact_candidates)
    if contains_candidates:
        return _pick_best_match(contains_candidates)
    return None


def match_rule_aliases(
    *,
    title: str,
    category_code: str,
    config_path: str | None = None,
) -> dict[str, RuleAliasMatch]:
    fields = {entry.field for entry in load_rule_alias_entries(config_path) if entry.category_code == category_code}
    matches: dict[str, RuleAliasMatch] = {}
    for field in fields:
        match = match_rule_alias(title=title, category_code=category_code, field=field, config_path=config_path)
        if match is not None:
            matches[field] = match
    return matches


def _build_match(
    entry: RuleAliasEntry,
    *,
    alias: str,
    match_type: str,
    confidence: float,
) -> RuleAliasMatch:
    return RuleAliasMatch(
        category_code=entry.category_code,
        field=entry.field,
        value=entry.value,
        alias=alias,
        match_type=match_type,
        confidence=confidence,
    )


def _pick_best_match(candidates: list[RuleAliasMatch]) -> RuleAliasMatch:
    return sorted(
        candidates,
        key=lambda match: (match.confidence, len(normalize_alias_text(match.alias))),
        reverse=True,
    )[0]


def serialize_rule_alias_match(match: RuleAliasMatch | None) -> dict[str, Any] | None:
    if match is None:
        return None
    return {
        "categoryCode": match.category_code,
        "field": match.field,
        "value": match.value,
        "alias": match.alias,
        "matchType": match.match_type,
        "confidence": match.confidence,
    }
