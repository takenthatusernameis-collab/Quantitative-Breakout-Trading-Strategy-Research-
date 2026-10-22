#!/usr/bin/env python3
"""The v6 universe rules: pure, offline and provider-free.

This module holds every rule the preregistered v6 specification
(``configs/research_v6.json``) freezes, in one place, so that the retrieval
script, the manifest producer and the read-only verifier all apply **exactly**
the same rule. It never contacts a provider, never writes to the repository
and never reads a candle.

The rules are:

* the **floor rule** -- the v6 batch contains only assets whose market
  capitalization is *strictly* below the floor recomputed from
  ``research/universe_manifest_v5.json`` (the source the specification names);
* the **identity rule** -- an asset is excluded when its base Binance symbol
  **or** its CoinGecko id occurs in the eligible assets of the v1, the v2, the
  v3, the v4 or the v5 universe manifest; a renamed asset keeps its CoinGecko id
  and is therefore the same asset;
* the **exclusion rules** -- the v1 ``exclusion_rules`` fixed lists (copied
  unchanged, as ``configs/research_v6.json`` ->
  ``universe.eligibility_validation.exclusion_rules`` requires) are evaluated
  first, and the published exclusion classifier of the effective v4 exclusion
  amendment is evaluated next. That classifier's five groups implement exactly
  the six categories the v5 specification names
  (``universe.exclusions``: stablecoins, wrapped_tokens, bridged_tokens,
  leveraged_tokens, synthetic_tokens, derivative_tokens) and it is reused
  read-only: the amendment is hash-bound and is never edited by the v5 chain;
* the **ordering rule** -- the batch is the ``top_n`` qualifying assets in
  strictly descending market-capitalization order, and a shortfall is recorded
  rather than padded.

The v6 specification is the rule book; this module is its application. Every
number the manifests record is re-derived here from the artifacts that own it.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v3_exclusion_classifier import (  # noqa: E402
    classify_entry,
    entry_symbol,
    fixed_list_groups,
    prior_universe_match,
)

#: The v6 specification.
SPEC_RELATIVE = "configs/research_v6.json"

#: The universe manifests, in the order the identity rule covers them.
PRIOR_UNIVERSE_RELATIVES = (
    "research/universe_manifest.json",
    "research/universe_manifest_v2.json",
    "research/universe_manifest_v3.json",
    "research/universe_manifest_v4.json",
    "research/universe_manifest_v5.json",
)

#: The manifest the floor is recomputed from.
FLOOR_SOURCE_RELATIVE = "research/universe_manifest_v5.json"

#: The glob of the published v4 exclusion amendments.
V4_EXCLUSION_AMENDMENT_GLOB = "configs/research_v4_exclusion_amendment_*.json"

#: The v1 manifest that owns the inherited fixed exclusion lists.
V1_UNIVERSE_RELATIVE = "research/universe_manifest.json"

#: The exclusion reasons the v1 fixed lists map to, as the v3 classifier does.
FIXED_LIST_GROUP_REASONS = {
    "exchange_tokens": "exchange_token_excluded",
    "leveraged_synthetic": "leveraged_or_synthetic_excluded",
    "low_liquidity_or_new": "low_liquidity_or_new_excluded",
    "stablecoins": "stablecoin_excluded",
    "wrapped_bridged": "wrapped_or_bridged_excluded",
}

MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)
DATA_MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash", "snapshot_identity.data_manifest_hash")

HOUR_MS = 60 * 60 * 1000

#: The frozen v6 execution protocol, the amendment that supersedes the one
#: block of it whose recorded world state went stale, and the selection
#: authorization whose publication made it stale.
V6_EXECUTION_RELATIVE = "configs/research_v6_execution.json"
V6_EXECUTION_AMENDMENT_1_RELATIVE = "configs/research_v6_execution_amendment_1.json"
V6_SELECTION_AUTHORIZATION_RELATIVE = "configs/research_v6_selection_authorization_1.json"

#: The blocks a v6 execution amendment may restate.
V6_EXECUTION_AMENDMENT_BLOCKS: Tuple[str, ...] = ("execution_authorization",)

#: The authority flags the effective execution-authorization block keeps
#: false: the protocol authorizes no run of any kind.
V6_EXECUTION_AUTHORITY_FLAGS: Tuple[str, ...] = (
    "execution_authorized",
    "grid_run_authorized",
    "candle_fetch_authorized",
    "confirmatory_evaluation_authorized",
    "second_run_authorized",
)


class V6RuleError(RuntimeError):
    """A v6 rule could not be resolved, so the consumer must fail closed."""


# ---------------------------------------------------------------------------
# hashing and time helpers
# ---------------------------------------------------------------------------


def canonical(obj: Any) -> str:
    """The canonical JSON form every hash in the v5 chain is taken over."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_manifest_hash(document: Dict[str, Any],
                          excluded_keys: Tuple[str, ...] = MANIFEST_HASH_EXCLUDED_KEYS) -> str:
    """The sha256 of the document body with the excluded keys removed.

    A dotted key removes a nested key, so that the data manifest can carry the
    data-manifest hash inside its own snapshot identity without hashing itself
    into a cycle.
    """
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body).encode("utf-8"))


def parse_iso_utc(value: str) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def published_manifest_hash(repo_root: Path, relative: str) -> Optional[str]:
    """The manifest hash of a published artifact, recomputed from its bytes.

    ``None`` means the artifact is not published yet; a caller records that
    state explicitly instead of inventing a digest. The excluded-key set is
    read from the artifact itself, so the returned value is never a constant
    copied out of another document.
    """
    path = Path(repo_root) / relative
    if not path.exists():
        return None
    document = read_json(path)
    excluded = tuple(
        (document.get("hashing") or {}).get("manifest_hash_excluded_keys")
        or MANIFEST_HASH_EXCLUDED_KEYS
    )
    return compute_manifest_hash(document, excluded)


def canonical_source_digest(repo_root: Path = REPO_ROOT) -> str:
    """The portable identity of the hashed source tree.

    Every ``*.py`` file under the hashed set contributes its POSIX relative path
    and the sha256 hex digest of its bytes, in ascending path order. Unlike the
    ordered digest of ``compute_code_hash()`` this does not depend on the
    directory enumeration order of the checkout, so it is reproducible on any
    machine.
    """
    base = Path(repo_root) / "src" / "breakout_research"
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def authorized_code_hash(repo_root: Path = REPO_ROOT) -> Optional[str]:
    """The authorized value of record for the hashed set."""
    path = Path(repo_root) / "research_state" / "campaign_authorization.json"
    if not path.exists():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = document.get("code_hash")
    return str(value) if value else None


# ---------------------------------------------------------------------------
# the effective v6 execution protocol
# ---------------------------------------------------------------------------


def resolve_effective_v6_execution_protocol(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """The effective v6 execution protocol: the amendment first, the protocol second.

    ``configs/research_v6_execution.json`` is hash-bound and is not edited in
    place. Its ``execution_authorization`` block records
    ``selection_authorization_present = false``, which was true at the
    protocol's publication instant -- the v6 selection authorization did not
    exist yet -- and is stale now: the v6 selection authorization has been
    published. ``configs/research_v6_execution_amendment_1.json`` records the
    effective block and wins over the protocol for the blocks it restates.

    This is the **one** resolution: the repository verifier and the future
    ``src/v6_campaign`` run gate both call it, so the gate cannot resolve the
    effective rule by a different rule than the verifier does. It fails closed:
    when the amendment is absent, unreadable, does not recompute its own hash,
    does not name the current protocol or does not restate the block it claims
    to supersede, it raises :class:`V6RuleError` instead of falling back to the
    stale block.
    """
    root = Path(repo_root)
    protocol_path = root / V6_EXECUTION_RELATIVE
    if not protocol_path.exists():
        raise V6RuleError(
            f"the v6 execution protocol {V6_EXECUTION_RELATIVE} does not exist"
        )
    protocol = read_json(protocol_path)
    protocol_excluded = tuple(
        (protocol.get("hashing") or {}).get("manifest_hash_excluded_keys")
        or MANIFEST_HASH_EXCLUDED_KEYS
    )
    protocol_hash = compute_manifest_hash(protocol, protocol_excluded)
    if protocol.get("manifest_hash") != protocol_hash:
        raise V6RuleError(
            "the v6 execution protocol does not recompute its own manifest_hash: recorded "
            f"{protocol.get('manifest_hash')}, recomputed {protocol_hash}"
        )

    amendment_path = root / V6_EXECUTION_AMENDMENT_1_RELATIVE
    if not amendment_path.exists():
        raise V6RuleError(
            "the v6 execution amendment 1 does not exist, so the effective "
            "execution-authorization block cannot be resolved and the chain fails closed"
        )
    try:
        amendment = read_json(amendment_path)
    except (OSError, ValueError) as error:
        raise V6RuleError(
            f"the v6 execution amendment 1 cannot be read: {error}"
        ) from error
    amendment_excluded = tuple(
        (amendment.get("hashing") or {}).get("manifest_hash_excluded_keys")
        or MANIFEST_HASH_EXCLUDED_KEYS
    )
    amendment_hash = compute_manifest_hash(amendment, amendment_excluded)
    if amendment.get("manifest_hash") != amendment_hash:
        raise V6RuleError(
            "the v6 execution amendment 1 does not recompute its own manifest_hash: recorded "
            f"{amendment.get('manifest_hash')}, recomputed {amendment_hash}"
        )
    amends = amendment.get("amends") or {}
    if amends.get("file") != V6_EXECUTION_RELATIVE:
        raise V6RuleError(
            "the v6 execution amendment 1 does not name the v6 execution protocol"
        )
    if amends.get("manifest_hash") != protocol_hash:
        raise V6RuleError(
            "the v6 execution amendment 1 is not bound to the current v6 execution protocol"
        )
    if amends.get("sha256") != sha256_file(protocol_path):
        raise V6RuleError(
            "the v6 execution amendment 1 records a stale digest of the v6 execution protocol"
        )
    superseded = tuple((amendment.get("precedence") or {}).get("superseded") or ())
    if not superseded:
        raise V6RuleError(
            "the v6 execution amendment 1 names no superseded block of the v6 execution protocol"
        )
    for block in superseded:
        if block not in amendment:
            raise V6RuleError(
                f"the v6 execution amendment 1 does not restate the block {block!r} it claims "
                "to supersede"
            )
    effective = json.loads(json.dumps(protocol))
    for block in superseded:
        effective[block] = amendment[block]
    for block in V6_EXECUTION_AMENDMENT_BLOCKS:
        if block in amendment:
            effective[block] = amendment[block]
    effective["_effective_blocks_from_amendment"] = list(superseded)
    effective["_amendment_manifest_hash"] = amendment_hash
    effective["_amendment_path"] = V6_EXECUTION_AMENDMENT_1_RELATIVE
    return effective


def verify_v6_historical_execution_authorization(
    repo_root: Path = REPO_ROOT,
) -> Dict[str, Any]:
    """The frozen protocol's historical statement must stay on disk unchanged.

    The protocol's ``selection_authorization_present = false`` records the state
    of the chain at its publication instant. It stays on disk, visible and
    unchanged: the effective state is the amendment's. The expected historical
    value is not a constant: it is the value the amendment itself records.
    """
    root = Path(repo_root)
    try:
        amendment = read_json(root / V6_EXECUTION_AMENDMENT_1_RELATIVE)
        protocol = read_json(root / V6_EXECUTION_RELATIVE)
    except (OSError, ValueError) as error:
        raise V6RuleError(
            f"the v6 execution artifacts cannot be read: {error}"
        ) from error
    historical = (amendment.get("problem") or {}).get(
        "historical_selection_authorization_present"
    )
    if historical is not False:
        raise V6RuleError(
            "the v6 execution amendment 1 does not record the historical state it preserves"
        )
    block = protocol.get("execution_authorization") or {}
    if block.get("selection_authorization_present") is not historical:
        raise V6RuleError(
            "the frozen v6 execution protocol no longer records the historical state of the chain"
        )
    return {"historical_selection_authorization_present": historical}


def verify_effective_v6_selection_authorization(
    repo_root: Path = REPO_ROOT,
    effective: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Check the effective execution-authorization block against the repository.

    The block's one statement about the world -- ``selection_authorization_present``
    -- is recomputed here: the named selection authorization must exist, must
    recompute its own manifest hash, and must be the artifact whose identity the
    block names. The five authority flags stay false, because the protocol
    authorizes no run of any kind: the single bounded v6 selection run is
    authorized by the selection authorization and by nothing else.

    Raises :class:`V6RuleError` when the block and the repository disagree.
    """
    root = Path(repo_root)
    if effective is None:
        effective = resolve_effective_v6_execution_protocol(root)
    block = effective.get("execution_authorization") or {}
    for flag in V6_EXECUTION_AUTHORITY_FLAGS:
        if block.get(flag) is not False:
            raise V6RuleError(
                f"the effective execution authorization does not record {flag} as false"
            )
    if block.get("selection_authorization_present") is not True:
        raise V6RuleError(
            "the effective execution authorization does not record the published v6 selection "
            "authorization; the single bounded run is gated on that artifact"
        )
    recorded_path = str(block.get("selection_authorization_path") or "")
    if recorded_path != V6_SELECTION_AUTHORIZATION_RELATIVE:
        raise V6RuleError(
            "the effective execution authorization names another selection authorization"
        )
    path = root / recorded_path
    if not path.exists():
        raise V6RuleError(
            "the v6 selection authorization named by the effective execution authorization does "
            "not exist"
        )
    published = read_json(path)
    published_excluded = tuple(
        (published.get("hashing") or {}).get("manifest_hash_excluded_keys")
        or MANIFEST_HASH_EXCLUDED_KEYS
    )
    published_hash = compute_manifest_hash(published, published_excluded)
    if published.get("manifest_hash") != published_hash:
        raise V6RuleError(
            "the v6 selection authorization does not recompute its own manifest_hash"
        )
    if block.get("selection_authorization_manifest_hash") != published_hash:
        raise V6RuleError(
            "the effective execution authorization names another manifest hash for the v6 "
            "selection authorization"
        )
    published_digest = sha256_file(path)
    if block.get("selection_authorization_sha256") != published_digest:
        raise V6RuleError(
            "the effective execution authorization names another file digest for the v6 "
            "selection authorization"
        )
    run = published.get("authorized_run") or {}
    if run.get("authorized") is not True:
        raise V6RuleError("the v6 selection authorization does not authorize a run")
    if block.get("selection_authorization_run_id") != run.get("run_id"):
        raise V6RuleError(
            "the effective execution authorization names another run for the v6 selection "
            "authorization"
        )
    if block.get("selection_authorization_campaign_id") != run.get("campaign_id"):
        raise V6RuleError(
            "the effective execution authorization names another campaign for the v6 selection "
            "authorization"
        )
    return {
        "selection_authorization_path": recorded_path,
        "selection_authorization_manifest_hash": published_hash,
        "selection_authorization_sha256": published_digest,
        "selection_authorization_run_id": run.get("run_id"),
        "selection_authorization_campaign_id": run.get("campaign_id"),
    }


# ---------------------------------------------------------------------------
# the rules
# ---------------------------------------------------------------------------


def recompute_floor(source_universe: Dict[str, Any]) -> Tuple[str, int]:
    """Recompute the floor from the universe manifest the specification names.

    The floor is the minimum ``market_cap_usd`` over the *eligible assets* of
    the source manifest -- the whole batch, not only its validated subset. The
    recorded value is never trusted: the verifier recomputes it.
    """
    assets = source_universe.get("eligible_assets") or []
    if not assets:
        raise SystemExit("the source universe manifest has no eligible assets")
    lowest = min(assets, key=lambda entry: int(entry.get("market_cap_usd") or 0))
    return str(lowest.get("symbol")), int(lowest.get("market_cap_usd") or 0)


def prior_universe_assets(*universes: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Collect the prior-universe identities: base Binance symbol and CoinGecko id.

    The Binance marker is the *base* symbol: the ``USDT`` suffix of a
    ``binance_pair`` is stripped before the comparison, so ``BTCUSDT`` and
    ``BTC`` are one marker and not two.
    """
    symbols: Dict[str, str] = {}
    identifiers: Dict[str, str] = {}
    for universe in universes:
        version = str(
            universe.get("universe_version") or universe.get("protocol_version") or "prior"
        )
        for entry in universe.get("eligible_assets") or []:
            symbol = str(entry.get("symbol") or "")
            if symbol.endswith("USDT"):
                symbol = symbol[:-4]
            if symbol:
                symbols.setdefault(symbol.upper(), version)
            identifier = entry.get("coingecko_id")
            if identifier:
                identifiers.setdefault(str(identifier), version)
    return symbols, identifiers


def resolve_effective_v4_amendment(repo_root: Path = REPO_ROOT) -> Tuple[Path, Dict[str, Any]]:
    """The effective v4 exclusion amendment: the highest-numbered one on disk.

    The v6 chain reuses that amendment's **classifier** read-only, exactly as
    the v5 chain did: it is the published classifier that implements the six
    exclusion categories the v6 specification names, and the v6 specification
    names no other classifier. The amendment's v4-specific derived
    classification and derived candidate batch are never used by the v6 chain.
    """
    candidates = sorted(Path(repo_root).glob(V4_EXCLUSION_AMENDMENT_GLOB))
    if not candidates:
        raise SystemExit(f"no v4 exclusion amendment found in {V4_EXCLUSION_AMENDMENT_GLOB}")

    def suffix(path: Path) -> int:
        stem = path.stem.rsplit("_", 1)[-1]
        return int(stem) if stem.isdigit() else -1

    path = max(candidates, key=suffix)
    return path, read_json(path)


def load_exclusion_rules(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """The two published exclusion sources the v6 chain applies.

    * the **inherited fixed lists** -- the ``exclusion_rules`` block of
      ``research/universe_manifest.json`` (the v1 manifest, copied unchanged
      into the v2 manifest and required unchanged by the v5 specification);
    * the **published classifier** -- the ``classifier`` block of the effective
      v4 exclusion amendment, whose five groups implement the six categories
      the v5 specification names.
    """
    repo_root = Path(repo_root)
    v1_universe = read_json(repo_root / V1_UNIVERSE_RELATIVE)
    fixed_lists = {
        str(group): list(symbols or [])
        for group, symbols in (v1_universe.get("exclusion_rules") or {}).items()
    }
    amendment_path, amendment = resolve_effective_v4_amendment(repo_root)
    classifier = amendment.get("classifier") or {}
    return {
        "fixed_lists": fixed_lists,
        "fixed_lists_source": {
            "path": V1_UNIVERSE_RELATIVE,
            "sha256": sha256_file(repo_root / V1_UNIVERSE_RELATIVE),
            "rule": (
                "the v1 exclusion_rules fixed lists, applied verbatim as "
                "configs/research_v6.json -> universe.eligibility_validation."
                "exclusion_rules requires"
            ),
        },
        "classifier": classifier,
        "classifier_source": {
            "path": amendment_path.relative_to(repo_root).as_posix(),
            "sha256": sha256_file(amendment_path),
            "amendment_hash": amendment.get("amendment_hash"),
            "classifier_version": classifier.get("classifier_version"),
            "group_order": list(classifier.get("group_order") or []),
            "spec_categories": sorted(
                {
                    str(category)
                    for definition in (classifier.get("groups") or {}).values()
                    for category in str(definition.get("spec_category") or "").split(",")
                    if category
                }
            ),
            "reuse_rule": (
                "the classifier is reused read-only: the amendment is hash-bound, it is "
                "never edited by the v6 chain, and only its classifier block is used -- "
                "its v4 derived classification and derived candidate batch are not"
            ),
            "semantics_source": "scripts/v3_exclusion_classifier.py",
        },
    }


def derive_batch(spec: Dict[str, Any], markets: List[Dict[str, Any]],
                 prior_universes: List[Dict[str, Any]],
                 exclusion_rules: Dict[str, Any],
                 check_published_batch: bool = True) -> Tuple[List[Dict[str, Any]],
                                                                List[Dict[str, Any]],
                                                                List[Dict[str, Any]]]:
    """Re-derive the v6 candidate batch from the snapshot and the published rules.

    The batch is the ``top_n`` qualifying assets in strictly descending
    market-capitalization order, where qualifying means: not excluded by the
    inherited fixed lists, not excluded by the published classifier, not an
    asset of the v1, the v2, the v3, the v4 or the v5 universe and strictly below
    the recomputed **v5** floor.

    The member list is always re-derived from the snapshot rows; it is never
    copied from a recorded list.
    """
    universe_spec = spec["universe"]
    top_n = int(universe_spec["top_n"])
    floor_symbol, floor_market_cap = recompute_floor(prior_universes[-1])

    fixed_groups = fixed_list_groups(exclusion_rules["fixed_lists"])
    classifier = exclusion_rules["classifier"]
    prior_symbols, prior_ids = prior_universe_assets(*prior_universes)

    eligible: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    records: List[Dict[str, Any]] = []
    for position, market in enumerate(markets, start=1):
        symbol = entry_symbol(market)
        identifier = str(market.get("id") or "")
        market_cap = market.get("market_cap")
        market_cap_usd = int(market_cap) if isinstance(market_cap, (int, float)) else None
        record: Dict[str, Any] = {
            "coingecko_id": identifier,
            "market_cap_rank": market.get("market_cap_rank"),
            "market_cap_usd": market_cap_usd,
            "name": market.get("name"),
            "snapshot_position": position,
            "symbol": symbol,
        }
        outcome = classify_entry(market, classifier, fixed_groups)
        if outcome is not None:
            group = str(outcome["exclusion_group"])
            record.update({
                "excluded": True,
                "exclusion_group": group,
                "exclusion_reason": outcome["exclusion_reason"],
                "matched_markers": outcome["matched_markers"],
                "rule_source": (
                    "inherited_fixed_list"
                    if outcome["rule_source"] == "inherited_fixed_list"
                    else "v4_exclusion_amendment_classifier"
                ),
            })
            excluded.append(record)
            records.append(record)
            continue
        identity = prior_universe_match(market, prior_symbols, prior_ids)
        if identity is not None:
            record.update({
                "excluded": True,
                "exclusion_group": "prior_universe",
                "exclusion_reason": "already_in_prior_universe",
                "matched_markers": identity.get("matched_on"),
                "prior_universe_versions": identity.get("prior_universe_versions"),
                "rule_source": "specification_expansion_scope",
            })
            excluded.append(record)
            records.append(record)
            continue
        if market_cap_usd is None or market_cap_usd >= floor_market_cap:
            record.update({
                "excluded": True,
                "exclusion_group": "market_cap_floor",
                "exclusion_reason": "not_below_prior_universe_floor",
                "matched_markers": [],
                "rule_source": "specification_expansion_scope",
            })
            excluded.append(record)
            records.append(record)
            continue
        record["excluded"] = False
        record["exclusion_group"] = None
        record["exclusion_reason"] = None
        record["matched_markers"] = []
        record["rule_source"] = None
        eligible.append(record)
        records.append(record)

    eligible.sort(key=lambda record: (-int(record["market_cap_usd"] or 0), record["snapshot_position"]))
    batch = eligible[:top_n]
    for rank, record in enumerate(batch, start=1):
        record["rank"] = rank
        record["binance_pair"] = f"{record['symbol']}USDT"

    if check_published_batch:
        published = (
            spec.get("universe", {})
            .get("expansion_scope", {})
            .get("published_candidate_batch", {})
            .get("members")
        )
        if published is not None:
            derived_pairs = [record["binance_pair"] for record in batch]
            published_pairs = [str(member.get("binance_pair")) for member in published]
            if derived_pairs != published_pairs:
                raise SystemExit(
                    "the re-derived candidate batch does not match the published batch: "
                    f"{derived_pairs} != {published_pairs}"
                )
    return batch, excluded, records


def qualifying_count(spec: Dict[str, Any], markets: List[Dict[str, Any]],
                      prior_universes: List[Dict[str, Any]],
                      exclusion_rules: Dict[str, Any]) -> int:
    """How many assets qualify for the batch in the given snapshot rows.

    The v6 specification's depth policy reads the second page only when the
    first page yields fewer than ``top_n`` qualifying names, so the count is
    needed before the (conditional) second page is read.
    """
    batch, _excluded, _records = derive_batch(
        spec, markets, prior_universes, exclusion_rules, check_published_batch=False
    )
    return len(batch)


def development_window(spec: Dict[str, Any]) -> Dict[str, Any]:
    """The v6 development window: the closed hourly span that ends at the cutoff.

    The last development candle is the one that **closes exactly at** the
    development cutoff (the inclusive convention), and the first candle opens
    ``candle_count - 1`` hours before it. Both bounds are recomputed from the
    cutoff and the candle count, never copied from a recorded value.
    """
    cutoff = spec["holdout"]["development_cutoff_utc"]
    candle_count = int(spec["holdout"]["development_window"]["candle_count"])
    cutoff_ms = int(parse_iso_utc(cutoff).timestamp() * 1000)
    last_open_ms = (cutoff_ms // HOUR_MS - 1) * HOUR_MS
    first_open_ms = last_open_ms - (candle_count - 1) * HOUR_MS
    return {
        "candle_count": candle_count,
        "cutoff_ms": cutoff_ms,
        "cutoff_utc": cutoff,
        "first_open_ms": first_open_ms,
        "last_open_ms": last_open_ms,
        "boundary": "inclusive: the last development candle closes exactly at the cutoff",
    }
