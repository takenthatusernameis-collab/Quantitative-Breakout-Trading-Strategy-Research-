#!/usr/bin/env python3
"""Application semantics of the published v3 exclusion classifier.

The classifier itself is *data*, not code: it is frozen in
``configs/research_v3_exclusion_amendment_1.json`` so that it is hash-bound,
human-readable and auditable. This module implements only the published
application semantics, so that the builder, the constituent validation and the
verifiers all apply exactly the same rule:

* a **text marker** is a case-insensitive substring of the lower-cased
  concatenation of the snapshot entry's ``name`` and ``id`` fields;
* a **symbol_exact** entry matches a snapshot entry whose upper-cased
  ``symbol`` field equals it exactly;
* the **inherited fixed lists** (the v1 ``exclusion_rules`` block, applied
  verbatim as the v3 specification's ``eligibility_validation.exclusion_rules``
  requires) are evaluated first, then the **classifier groups** in the
  published ``group_order``; the first group that matches an entry is the
  recorded exclusion group and the matched markers are recorded with it.

The module never contacts a provider and never writes to the repository.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

#: The published rename marker. A provider that renames an asset keeps the old
#: ticker visible in the name ("POL (ex-MATIC)"), so the old ticker can be
#: recovered from the name without any hand-written mapping.
RENAME_NAME_PATTERN = re.compile(r"\(ex-([A-Za-z0-9]+)\)", re.IGNORECASE)

#: The exclusion reason recorded for each published group. The first five are
#: the reasons the v2 constituent validation already used for the v1 fixed
#: lists; the last two are the reasons for the two categories that the v1
#: fixed list could not express.
GROUP_REASONS: Dict[str, str] = {
    "exchange_tokens": "exchange_token_excluded",
    "leveraged_synthetic": "leveraged_or_synthetic_excluded",
    "low_liquidity_or_new": "low_liquidity_or_new_excluded",
    "stablecoins": "stablecoin_excluded",
    "wrapped_bridged": "wrapped_or_bridged_excluded",
    "synthetic_tokens": "synthetic_token_excluded",
    "derivative_tokens": "derivative_token_excluded",
}


def reason_for_group(group: str) -> str:
    """The exclusion reason recorded for ``group``."""
    return GROUP_REASONS.get(group, f"{group}_excluded")


def entry_text(entry: Dict[str, Any]) -> str:
    """The lower-cased ``name`` + ``id`` text that a text marker is matched against."""
    name = str(entry.get("name") or "")
    identifier = str(entry.get("id") or "")
    return f"{name} {identifier}".lower()


def entry_symbol(entry: Dict[str, Any]) -> str:
    """The upper-cased ticker of a snapshot entry."""
    return str(entry.get("symbol") or "").upper()


def fixed_list_groups(fixed_lists: Dict[str, List[str]]) -> Dict[str, str]:
    """Map every symbol of the inherited fixed lists to its exclusion group.

    The first group that lists a symbol wins, so the mapping is deterministic
    even when two groups name the same ticker.
    """
    mapping: Dict[str, str] = {}
    for group, symbols in (fixed_lists or {}).items():
        for symbol in symbols or []:
            mapping.setdefault(str(symbol).upper(), str(group))
    return mapping


def classify_entry(entry: Dict[str, Any], classifier: Dict[str, Any],
                   fixed_groups: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Classify one snapshot entry.

    Returns ``None`` when the entry is not excluded by any published rule, and
    otherwise a record with the exclusion group, the exclusion reason, the
    rule source and the markers that matched.
    """
    symbol = entry_symbol(entry)
    if symbol in fixed_groups:
        group = fixed_groups[symbol]
        return {
            "exclusion_group": group,
            "exclusion_reason": reason_for_group(group),
            "matched_markers": [],
            "rule_source": "inherited_fixed_list",
        }

    text = entry_text(entry)
    for group in classifier.get("group_order") or []:
        definition = (classifier.get("groups") or {}).get(group) or {}
        matched: List[str] = []
        for marker in definition.get("text_markers") or []:
            marker_text = str(marker).lower()
            if marker_text and marker_text in text:
                matched.append(str(marker))
        for exact in definition.get("symbol_exact") or []:
            if str(exact).upper() == symbol:
                matched.append(f"symbol:{str(exact).upper()}")
        if matched:
            reason = definition.get("exclusion_reason") or reason_for_group(group)
            return {
                "exclusion_group": group,
                "exclusion_reason": reason,
                "matched_markers": sorted(matched),
                "rule_source": "v3_exclusion_classifier",
            }
    return None


def classify_snapshot(markets: List[Dict[str, Any]], classifier: Dict[str, Any],
                      fixed_lists: Dict[str, List[str]]) -> Dict[str, Dict[str, Any]]:
    """Classify every snapshot entry, keyed by its upper-cased ticker."""
    fixed_groups = fixed_list_groups(fixed_lists)
    classification: Dict[str, Dict[str, Any]] = {}
    for entry in markets:
        symbol = entry_symbol(entry)
        if not symbol or symbol in classification:
            continue
        outcome = classify_entry(entry, classifier, fixed_groups)
        if outcome is not None:
            classification[symbol] = outcome
    return classification


def rename_marker_ticker(entry: Dict[str, Any]) -> Optional[str]:
    """The old ticker of a renamed asset, recovered from its name.

    A provider that renames an asset keeps the old ticker visible in the name
    ("POL (ex-MATIC)"), so the rename can be detected without a hand-written
    mapping from old ticker to new ticker.
    """
    match = RENAME_NAME_PATTERN.search(str(entry.get("name") or ""))
    if not match:
        return None
    return match.group(1).upper()


def prior_universe_match(entry: Dict[str, Any], prior_symbols: Dict[str, str],
                          prior_ids: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Whether a snapshot entry is already an asset of a prior universe.

    Three published rules are applied:

    * the Binance symbol (without the USDT quote) occurs in a prior universe;
    * the CoinGecko id occurs in a prior universe;
    * the name carries a rename marker whose old ticker occurs in a prior
      universe -- a rename can come with a *new* provider id, so the id rule
      alone does not catch it.

    Returns ``None`` when the entry is new, and otherwise the matched rules and
    the prior universe versions that matched.
    """
    symbol = entry_symbol(entry)
    identifier = str(entry.get("id") or "")
    matched_on: List[str] = []
    versions: List[str] = []
    if symbol in prior_symbols:
        matched_on.append("binance_symbol")
        versions.append(prior_symbols[symbol])
    if identifier and identifier in prior_ids:
        matched_on.append("coingecko_id")
        versions.append(prior_ids[identifier])
    old_ticker = rename_marker_ticker(entry)
    if old_ticker and old_ticker in prior_symbols:
        matched_on.append(f"coingecko_name_rename:ex-{old_ticker}")
        versions.append(prior_symbols[old_ticker])
    if not matched_on:
        return None
    return {
        "matched_on": sorted(set(matched_on)),
        "prior_universe_versions": sorted(set(versions)),
    }
