#!/usr/bin/env python3
"""Build the preregistered v2 code-hash amendment 2 (the RL1 location correction).

``configs/research_v2_code_hash_amendment_1.json`` records residual limitation
``RL1`` and names its location as

    src/breakout_research/campaign.py (_verify_pilot_gate) and
    src/breakout_research/pilot_gate_validator.py

That location is **not exact**: ``pilot_gate_validator.py`` compares the pilot
evidence with itself and is therefore environment independent, while
``backtest/shards.py`` compares the live ordered code hash with a recorded one
and was not named at all. The limitation, its consequence and the behaviour of
the gate are unaffected; only the recorded *location* is wrong.

The frozen artifact must not be edited in place -- its ``manifest_hash``
``4409b6af...`` is recorded in the v2 identity chain -- so the correction is
carried by a versioned amendment, exactly as the established pattern requires
(execution amendment 1 -> code-hash amendment 1 -> execution amendment 2 ->
prerequisite reconciliation amendment 1 -> code-hash amendment 2).

What makes the amendment worth an artifact rather than a prose note is that the
corrected location is **mechanically recomputable**. A *code-hash comparison
site* is a comparison in the hashed source set whose source segment mentions
``code_hash``; the producer scans the tree for them with the Python AST, so a
site that is added, removed or renamed cannot be silently omitted from -- or
added to -- the amendment. Each site is classified as ``LIVE_VS_RECORDED``
(the live ordered digest compared with a recorded digest: checkout dependent)
or ``RECORDED_VS_RECORDED`` (both sides recorded: environment independent), and
every classification carries the *evidence* for it: the chain of source steps
that carries the live digest to the comparison, and the chain that carries the
recorded value to it. The verifier re-resolves every recorded step against the
current source, so a source edit invalidates the amendment.

The script is deterministic: the creation instant is pinned and every other
field is derived from the repository, so re-running it reproduces the same
bytes. It never writes to the hashed set, never edits a frozen artifact, never
fetches anything, never runs a grid and never reads a candle.

Usage::

    python3 scripts/build_v2_code_hash_amendment_2.py            # write the artifact
    python3 scripts/build_v2_code_hash_amendment_2.py --force    # rewrite it
    python3 scripts/build_v2_code_hash_amendment_2.py --print     # print, write nothing
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v2_code_hash_amendment_2.json"

#: The artifact whose ``residual_limitations[RL1].location`` field is corrected.
CORRECTED_ARTIFACT_RELATIVE = "configs/research_v2_code_hash_amendment_1.json"

#: The instant at which this amendment is created. It is pinned here so that
#: the artifact is byte-reproducible; it must not be moved once the artifact
#: has been committed.
CREATED_UTC = "2026-10-20T09:05:00Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

#: The source tree that ``compute_code_hash()`` hashes, recursively.
HASHED_SET_ROOT = "src/breakout_research"

#: Calls that read a persisted artifact. The first step of a recorded-value
#: chain must contain one of them; the list is part of the recorded scan rule
#: and is duplicated verbatim in the verifier.
PERSISTED_READ_MARKERS = (
    "_read_json_file(",
    "load_authorization(",
    "_read_json(",
    "_read_manifest(",
)

#: The call that produces the live, checkout-dependent ordered digest.
LIVE_DIGEST_MARKER = "compute_code_hash("

#: The v1 campaign authorization that holds the authorized value of record.
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"

#: The pre-flight that implements the BRAIN-010 decision, outside the hashed set.
PREFLIGHT_RELATIVE = "scripts/verify_v1_gate_compatibility.py"

#: The classification of every code-hash comparison site in the hashed set.
#:
#: The scan is mechanical (see :func:`scan_code_hash_comparison_sites`); this
#: table only says how each site is classified and which source steps are the
#: evidence for that classification. A scanned site that is missing from the
#: table -- or a table entry that no longer matches the source -- aborts the
#: build, so the amendment can never silently drift from the tree.
SITE_TABLE: Tuple[Dict[str, Any], ...] = (
    {
        "path": "src/breakout_research/campaign.py",
        "comparison": "stored_code != code_hash",
        "classification": "LIVE_VS_RECORDED",
        "live_digest_chain": (
            ("src/breakout_research/campaign.py", "code_hash = compute_code_hash()", 1),
            (
                "src/breakout_research/campaign.py",
                "self._verify_stale_checkpoint(protocol_hash, code_hash)",
                1,
            ),
        ),
        "recorded_value_chains": (
            (
                ("src/breakout_research/campaign.py", "stored = _read_json_file(CHECKPOINT_PATH)", 1),
                ("src/breakout_research/campaign.py", 'stored_code = stored.get("code_hash")', 1),
            ),
        ),
        "recorded_artifact_resolution": {"kind": "constant", "name": "CHECKPOINT_PATH"},
        "effect": (
            "A resumed v1 campaign refuses to start on a checkout whose directory "
            "enumeration order does not reproduce the authorized ordered digest, with "
            "the message 'code changed since checkpoint, refusing to resume'."
        ),
    },
    {
        "path": "src/breakout_research/campaign.py",
        "comparison": "auth.get('code_hash') != code_hash",
        "classification": "LIVE_VS_RECORDED",
        "live_digest_chain": (
            ("src/breakout_research/campaign.py", "code_hash = compute_code_hash()", 1),
            (
                "src/breakout_research/campaign.py",
                "self._verify_pilot_gate(protocol_hash, code_hash)",
                1,
            ),
        ),
        "recorded_value_chains": (
            (
                (
                    "src/breakout_research/campaign.py",
                    "auth = load_authorization(VALIDATOR_ARTIFACT_PATH)",
                    1,
                ),
            ),
        ),
        "recorded_artifact_resolution": {"kind": "constant", "name": "VALIDATOR_ARTIFACT_PATH"},
        "effect": (
            "The v1 campaign pilot gate refuses to start on a checkout whose directory "
            "enumeration order does not reproduce the authorized ordered digest, with "
            "the message 'Code has changed since authorization.'"
        ),
    },
    {
        "path": "src/breakout_research/backtest/shards.py",
        "comparison": 'manifest.get("code_hash") != self.code_hash',
        "classification": "LIVE_VS_RECORDED",
        "live_digest_chain": (
            ("src/breakout_research/campaign.py", "code_hash = compute_code_hash()", 1),
            ("src/breakout_research/campaign.py", "store = ResultStore(", 5),
            ("src/breakout_research/backtest/shards.py", "self.code_hash = code_hash", 1),
        ),
        "recorded_value_chains": (
            (
                ("src/breakout_research/backtest/shards.py", "manifest = self._read_manifest()", 1),
            ),
        ),
        "recorded_artifact_resolution": {"kind": "default_argument", "name": "manifest_path"},
        "effect": (
            "The result-store reconciliation refuses to resume on a checkout whose "
            "directory enumeration order does not reproduce the ordered digest the "
            "results manifest was written with, with the message 'Result manifest bound "
            "to different spec/code/data versions'."
        ),
    },
    {
        "path": "src/breakout_research/pilot_gate_validator.py",
        "comparison": 'evidence.get("code_hash") != code_hash',
        "classification": "RECORDED_VS_RECORDED",
        "live_digest_chain": (),
        "recorded_value_chains": (
            (
                (
                    "src/breakout_research/pilot_gate_validator.py",
                    "pilot = _read_json(pilot_evidence_path)",
                    1,
                ),
                (
                    "src/breakout_research/pilot_gate_validator.py",
                    'code_hash = pilot.get("code_hash")',
                    1,
                ),
            ),
        ),
        "recorded_artifact_resolution": {
            "kind": "default_argument",
            "name": "pilot_evidence_path",
        },
        "effect": (
            "The comparison is between the pilot evidence's own code hash and the code "
            "hash of the same pilot evidence; it is independent of the checkout's "
            "directory enumeration order and is not a residual limitation."
        ),
    },
    {
        "path": "src/breakout_research/pilot_gate_validator.py",
        "comparison": 'checkpoint_state.get("code_hash") != code_hash',
        "classification": "RECORDED_VS_RECORDED",
        "live_digest_chain": (),
        "recorded_value_chains": (
            (
                (
                    "src/breakout_research/pilot_gate_validator.py",
                    "pilot = _read_json(pilot_evidence_path)",
                    1,
                ),
                (
                    "src/breakout_research/pilot_gate_validator.py",
                    'code_hash = pilot.get("code_hash")',
                    1,
                ),
            ),
            (
                (
                    "src/breakout_research/pilot_gate_validator.py",
                    "pilot = _read_json(pilot_evidence_path)",
                    1,
                ),
                (
                    "src/breakout_research/pilot_gate_validator.py",
                    'checkpoint_state = evidence.get("checkpoint_state", {})',
                    1,
                ),
            ),
        ),
        "recorded_artifact_resolution": {
            "kind": "default_argument",
            "name": "pilot_evidence_path",
        },
        "effect": (
            "Both sides are read from the persisted pilot evidence -- the checkpoint "
            "state snapshot and the evidence's code hash -- so the comparison is "
            "independent of the checkout's directory enumeration order and is not a "
            "residual limitation."
        ),
    },
)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body).encode("utf-8"))


def canonical_source_digest(
    repo_root: Path = REPO_ROOT, hashed_set_root: str = HASHED_SET_ROOT
) -> str:
    """The portable identity of the hashed source tree."""
    base = repo_root / hashed_set_root
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def live_ordered_code_hash(repo_root: Path = REPO_ROOT) -> Optional[str]:
    """Reproduce ``compute_code_hash()`` exactly, for the informational report."""
    src_dir = repo_root / HASHED_SET_ROOT
    if not src_dir.exists():
        return None
    digest = hashlib.sha256()
    for root, _dirs, files in os.walk(src_dir):
        for name in sorted(files):
            if name.endswith(".py"):
                digest.update((Path(root) / name).read_bytes())
    return digest.hexdigest()


def scan_code_hash_comparison_sites(repo_root: Path = REPO_ROOT) -> List[Dict[str, Any]]:
    """Find every code-hash comparison site in the hashed set.

    A *code-hash comparison site* is a comparison expression whose source
    segment mentions ``code_hash``. The scan is mechanical, so it cannot omit a
    site and cannot invent one.
    """
    base = repo_root / HASHED_SET_ROOT
    sites: List[Dict[str, Any]] = []
    for path in sorted(base.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            segment = ast.get_source_segment(source, node) or ""
            if "code_hash" not in segment:
                continue
            sites.append(
                {
                    "path": path.relative_to(repo_root).as_posix(),
                    "line": node.lineno,
                    "comparison": segment,
                    "symbol": _enclosing_symbol(tree, node),
                }
            )
    sites.sort(key=lambda site: (site["path"], site["line"]))
    return sites


def _enclosing_symbol(tree: ast.AST, target: ast.AST) -> str:
    """The dotted name of the function or class that encloses ``target``."""
    found: List[str] = []

    def visit(node: ast.AST, scope: List[str]) -> None:
        if node is target:
            found.append(".".join(scope) if scope else "<module>")
            return
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                visit(child, scope + [child.name])
            else:
                visit(child, scope)

    visit(tree, [])
    return found[0] if found else "<module>"


def corrected_location_string(sites: Sequence[Dict[str, Any]]) -> str:
    """Render the corrected location from the live-vs-recorded sites."""
    by_file: Dict[str, List[int]] = {}
    for site in sites:
        if site["classification"] != "LIVE_VS_RECORDED":
            continue
        by_file.setdefault(site["path"], []).append(int(site["line"]))
    parts: List[str] = []
    for path in sorted(by_file):
        lines = sorted(by_file[path])
        if len(lines) == 1:
            parts.append(f"{path} (line {lines[0]})")
        else:
            rendered = ", ".join(str(line) for line in lines[:-1])
            parts.append(f"{path} (lines {rendered} and {lines[-1]})")
    return " and ".join(parts)


def _resolve_anchor(
    repo_root: Path, relative: str, anchor: str, span: int
) -> Dict[str, Any]:
    """Locate ``anchor`` in ``relative`` and return the recorded step."""
    path = repo_root / relative
    lines = path.read_text(encoding="utf-8").splitlines()
    hits = [index + 1 for index, line in enumerate(lines) if line.strip() == anchor]
    if len(hits) != 1:
        raise SystemExit(
            f"the anchor {anchor!r} occurs {len(hits)} times in {relative}; it must be unique"
        )
    start = hits[0]
    text = "\n".join(lines[start - 1 : start - 1 + span])
    return {"path": relative, "anchor": anchor, "span": span, "line": start, "text": text}


def _resolve_chain(
    repo_root: Path, chain: Sequence[Tuple[str, str, int]]
) -> List[Dict[str, Any]]:
    return [_resolve_anchor(repo_root, relative, anchor, span) for relative, anchor, span in chain]


def _resolve_recorded_artifact(
    repo_root: Path, site: Dict[str, Any], resolution: Dict[str, Any]
) -> Dict[str, Any]:
    """Resolve the persisted artifact a recorded-value chain reads.

    ``kind = constant`` resolves a module-level constant in the file of the
    first recorded-value step; ``kind = default_argument`` resolves a default
    argument of the function that performs the read.
    """
    kind = resolution.get("kind")
    name = str(resolution.get("name") or "")
    chain = site["recorded_value_chains"][0]
    relative = chain[0][0]
    path = repo_root / relative
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)

    if kind == "constant":
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name for target in node.targets
            ):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return {
                        "kind": "constant",
                        "name": name,
                        "resolved_via": "constant",
                        "path": relative,
                        "line": node.lineno,
                        "text": lines[node.lineno - 1],
                        "value": node.value.value,
                    }
        raise SystemExit(f"{relative} does not define the constant {name}")

    if kind == "default_argument":
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = node.args.args
            defaults = node.args.defaults
            offset = len(args) - len(defaults)
            for index, arg in enumerate(args):
                if arg.arg != name:
                    continue
                default = defaults[index - offset]
                value: Optional[str] = None
                source_line: Optional[str] = None
                if isinstance(default, ast.Constant) and isinstance(default.value, str):
                    value = default.value
                    source_line = default.lineno
                elif isinstance(default, ast.Name):
                    for assignment in tree.body:
                        if isinstance(assignment, ast.Assign) and any(
                            isinstance(target, ast.Name) and target.id == default.id
                            for target in assignment.targets
                        ):
                            if isinstance(assignment.value, ast.Constant) and isinstance(
                                assignment.value.value, str
                            ):
                                value = assignment.value.value
                                source_line = assignment.lineno
                                break
                if value is None or source_line is None:
                    continue
                return {
                    "kind": "default_argument",
                    "name": name,
                    "resolved_via": "constant" if isinstance(default, ast.Name) else "direct_value",
                    "path": relative,
                    "line": source_line,
                    "text": lines[source_line - 1],
                    "value": value,
                }
        raise SystemExit(f"{relative} does not define the default argument {name}")

    raise SystemExit(f"unknown recorded-artifact resolution kind: {kind!r}")


def _build_sites(repo_root: Path) -> List[Dict[str, Any]]:
    scanned = scan_code_hash_comparison_sites(repo_root)
    table = {
        (entry["path"], entry["comparison"]): entry for entry in SITE_TABLE
    }
    scanned_keys = {(site["path"], site["comparison"]) for site in scanned}
    table_keys = set(table)
    missing = sorted(scanned_keys - table_keys)
    if missing:
        raise SystemExit(
            "the source contains code-hash comparison sites that the classification "
            f"table does not cover: {missing}; the amendment must be superseded"
        )
    stale = sorted(table_keys - scanned_keys)
    if stale:
        raise SystemExit(
            f"the classification table names sites that no longer exist in the source: {stale}"
        )

    built: List[Dict[str, Any]] = []
    for site in scanned:
        entry = table[(site["path"], site["comparison"])]
        live_chain = _resolve_chain(repo_root, entry["live_digest_chain"])
        recorded_chains = [
            _resolve_chain(repo_root, chain) for chain in entry["recorded_value_chains"]
        ]
        artifact = _resolve_recorded_artifact(repo_root, entry, entry["recorded_artifact_resolution"])
        built.append(
            {
                "path": site["path"],
                "line": site["line"],
                "symbol": site["symbol"],
                "comparison": site["comparison"],
                "classification": entry["classification"],
                "live_digest_chain": live_chain,
                "recorded_value_chains": recorded_chains,
                "recorded_artifact": artifact,
                "effect": entry["effect"],
            }
        )
    return built


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assemble the code-hash amendment 2 from the repository."""
    authorization = json.loads(
        (repo_root / AUTHORIZATION_RELATIVE).read_text(encoding="utf-8")
    )
    authorized_code_hash = authorization["code_hash"]
    canonical_digest = canonical_source_digest(repo_root)

    corrected_path = repo_root / CORRECTED_ARTIFACT_RELATIVE
    corrected = json.loads(corrected_path.read_text(encoding="utf-8"))
    rl1 = None
    for limitation in corrected.get("residual_limitations") or []:
        if limitation.get("id") == "RL1":
            rl1 = limitation
            break
    if rl1 is None:
        raise SystemExit(f"{CORRECTED_ARTIFACT_RELATIVE} records no residual limitation RL1")

    sites = _build_sites(repo_root)
    live_files = sorted({site["path"] for site in sites if site["classification"] == "LIVE_VS_RECORDED"})
    recorded_files = sorted(
        {site["path"] for site in sites if site["classification"] == "RECORDED_VS_RECORDED"}
    )
    corrected_location = corrected_location_string(sites)

    document: Dict[str, Any] = {
        "artifact": "v2_code_hash_amendment",
        "artifact_version": "v2-code-hash-amendment-2",
        "protocol_version": "v2",
        "universe_version": "v2",
        "created_utc": CREATED_UTC,
        "amendment_status": "PREREGISTERED_CODE_HASH_AMENDMENT_2_DESIGN_ONLY",
        "specification_purpose": (
            "Correct the recorded location of residual limitation RL1 in "
            "configs/research_v2_code_hash_amendment_1.json. The frozen artifact is not "
            "edited: the corrected location is recorded here by reference. The "
            "limitation, its consequence, the behaviour of the v1 campaign runtime gate "
            "and every recorded identity stay exactly as they are. This artifact "
            "authorizes nothing, runs nothing and reads no candle."
        ),
        "design_basis": {
            "brainstorming_item": "BRAIN-010",
            "decision_record": "research_state/brainstorming_queue.md -> BRAIN-010",
            "chosen_design": "A",
            "chosen_design_summary": (
                "The v1 campaign runtime gate is not modified; the gate's comparison is "
                "reinterpreted as a statement about checkout compatibility, never about "
                "source drift, and a pre-flight outside the hashed set decides whether a "
                "v1 resume may be started. This amendment carries the location "
                "correction that the decision record required."
            ),
            "correction_mechanism": "VERSIONED_AMENDMENT",
            "alternatives_considered": [
                {
                    "option": "VERSIONED_AMENDMENT",
                    "verdict": "CHOSEN",
                    "reason": (
                        "The corrected location is a machine-readable field of a frozen "
                        "artifact. An amendment records it where every consumer of the "
                        "artifact can find it, and the verifier can enforce it: the site "
                        "set is recomputed from the source tree, so the amendment cannot "
                        "omit a site -- the very defect of the original record -- nor "
                        "invent one."
                    ),
                },
                {
                    "option": "NON_EDITING_NOTE_IN_THE_BRAINSTORMING_QUEUE",
                    "verdict": "REJECTED",
                    "reason": (
                        "A note cannot correct the field itself: every consumer of the "
                        "frozen artifact would keep reading the defective location, and "
                        "nothing would be recomputable. The correction would remain an "
                        "assertion."
                    ),
                },
                {
                    "option": "EDIT_THE_FROZEN_ARTIFACT_IN_PLACE",
                    "verdict": "FORBIDDEN",
                    "reason": (
                        "Immutable artifacts are corrected by versioned amendment, never "
                        "by editing. Editing would change the manifest_hash 4409b6af... "
                        "that the v2 identity chain records, and would therefore "
                        "invalidate the identity of the executed v2 run."
                    ),
                },
            ],
        },
        "correction": {
            "target_artifact": CORRECTED_ARTIFACT_RELATIVE,
            "target_manifest_hash": corrected.get("manifest_hash"),
            "target_file_sha256": sha256_file(corrected_path),
            "target_field": "residual_limitations[RL1].location",
            "recorded_location": rl1.get("location"),
            "corrected_location": corrected_location,
            "recorded_location_defect": (
                "The recorded location names one file too wide -- "
                "src/breakout_research/pilot_gate_validator.py compares the pilot evidence "
                "with itself and is environment independent -- and one file too narrow: "
                "src/breakout_research/backtest/shards.py compares the live ordered code "
                "hash with the code hash recorded in the results manifest and was not "
                "named at all."
            ),
            "behaviour_change": False,
            "limitation_text_changed": False,
            "consequence_text_changed": False,
            "target_artifact_edited": False,
            "correction_scope": (
                "The location only. RL1 itself, its consequence, the gate's behaviour, the "
                "authorized value of record, the canonical digest and every v1 and v2 "
                "artifact stay exactly as they are."
            ),
            "decision_record_correction": {
                "source": "BRAIN-010, evidence 4 and section 3 rule 8",
                "recorded_correction": (
                    "The RL1 location is corrected to src/breakout_research/campaign.py "
                    "(lines 171 and 189); pilot_gate_validator.py is environment "
                    "independent."
                ),
                "is_complete": False,
                "omission": (
                    "src/breakout_research/backtest/shards.py (line 480) compares the live "
                    "ordered code hash with the code hash recorded in the results manifest "
                    "and was not named. It is a live-vs-recorded site, so it belongs to "
                    "RL1: on a checkout whose directory enumeration order differs, the "
                    "result-store reconciliation refuses to resume with 'Result manifest "
                    "bound to different spec/code/data versions'."
                ),
                "second_omission": (
                    "pilot_gate_validator.py:139 (checkpoint_state.get(\"code_hash\") != "
                    "code_hash) was not enumerated either. It is recorded-vs-recorded, so "
                    "excluding it from RL1's location is correct; the enumeration was "
                    "simply incomplete."
                ),
                "evidence": (
                    "The mechanical scan of the hashed set finds five code-hash comparison "
                    "sites: three live-vs-recorded and two recorded-vs-recorded. This "
                    "amendment records all five, with the evidence for each."
                ),
            },
        },
        "code_hash_comparison_sites": {
            "hashed_set_root": HASHED_SET_ROOT,
            "scan_rule": {
                "site_definition": (
                    "A comparison expression in a *.py file under src/breakout_research "
                    "whose source segment mentions the token code_hash."
                ),
                "scan_method": "python ast: every ast.Compare node of the parsed module",
                "classification_rule": (
                    "LIVE_VS_RECORDED when one operand's value chain reaches a "
                    "compute_code_hash() call inside the hashed set without crossing a "
                    "persisted-artifact read, and the other operand's value chain reaches "
                    "a persisted-artifact read; RECORDED_VS_RECORDED otherwise."
                ),
                "persisted_read_markers": list(PERSISTED_READ_MARKERS),
                "live_digest_marker": LIVE_DIGEST_MARKER,
                "evidence_rule": (
                    "Each site records the source steps that carry the live digest and "
                    "the recorded value to the comparison. Every step is re-resolved "
                    "against the current source, so a source edit invalidates the "
                    "amendment."
                ),
            },
            "total_sites": len(sites),
            "live_vs_recorded_site_count": sum(
                1 for site in sites if site["classification"] == "LIVE_VS_RECORDED"
            ),
            "recorded_vs_recorded_site_count": sum(
                1 for site in sites if site["classification"] == "RECORDED_VS_RECORDED"
            ),
            "corrected_location_files": live_files,
            "excluded_location_files": recorded_files,
            "sites": sites,
        },
        "code_hash_constraint": {
            "hashed_set_root": HASHED_SET_ROOT,
            "authorized_code_hash": authorized_code_hash,
            "authorized_code_hash_source": (
                "research_state/campaign_authorization.json (protocol_version v1, authorized true)"
            ),
            "authorized_code_hash_status": "RETAINED_AS_VALUE_OF_RECORD",
            "canonical_source_digest": canonical_digest,
            "canonical_source_digest_algorithm": {
                "name": "canonical_source_digest_v1",
                "description": (
                    "sha256 over the concatenation, for every *.py file under "
                    "src/breakout_research in ascending POSIX relative-path order, of the "
                    "relative path, a newline, the sha256 hex digest of the file bytes, and "
                    "a newline."
                ),
                "portable": True,
            },
            "hashed_set_unchanged": (
                "No file under src/breakout_research is added, edited or removed by this "
                "amendment. The canonical digest above is the identity of the tree and is "
                "unchanged; the live ordered digest is an environment fact about the "
                "checkout's directory enumeration order and is never a drift signal."
            ),
            "gate_behaviour_unchanged": (
                "The v1 campaign runtime gate is not modified. BRAIN-010 keeps it "
                "byte-exact and reinterprets its comparison as checkout compatibility; a "
                "red comparison is reported as an environment fact, never repaired by "
                "editing the hashed set."
            ),
        },
        "preflight": {
            "path": PREFLIGHT_RELATIVE,
            "required_capability": (
                "The pre-flight must compute the canonical source digest of the hashed set, "
                "report the live ordered digest and the checkout's enumeration order, and "
                "refuse a v1 resume on an incompatible checkout with an environment-fact "
                "message rather than a drift message."
            ),
            "decision": (
                "BRAIN-010 requires a v1 resume to be started only through a pre-flight "
                "outside the hashed set that proves the tree has not drifted (the "
                "canonical digest), reports the live ordered digest and the enumeration "
                "order, and refuses to start on an incompatible checkout with an "
                "environment-fact message."
            ),
            "covers_the_corrected_location": (
                "The pre-flight compares the live ordered digest with the authorized value "
                "of record, so it covers every site the correction names -- the pilot "
                "gate, the stale-checkpoint check and the result-store reconciliation."
            ),
            "implementation_status": "IMPLEMENTED",
            "note": (
                "The pre-flight's bytes are not pinned here: it is an operational script, "
                "not a frozen artifact, and a later edit to it does not invalidate this "
                "correction. The verifier checks that it exists and implements the "
                "capability recorded above."
            ),
        },
        "execution_authorization": {
            "grid_run_authorized": False,
            "candidate_selection_authorized": False,
            "confirmatory_evaluation_authorized": False,
            "candle_fetch_authorized": False,
            "source_tree_change_authorized": False,
            "v1_reauthorization_authorized": False,
            "v1_resume_authorized": False,
            "statement": (
                "This artifact authorizes nothing. It corrects one recorded location, "
                "adds no behaviour and changes no identity. It does not change the "
                "hashed set, does not re-authorize the v1 campaign and does not permit "
                "any v1 or v2 run."
            ),
        },
        "related_artifacts": {
            "v1_campaign_authorization": {
                "path": AUTHORIZATION_RELATIVE,
                "code_hash": authorized_code_hash,
                "note": (
                    "The functional field of the authorization is recorded, not the digest "
                    "of its bytes: the controller refreshes the authorized_at_utc "
                    "timestamp, so the file digest changes without the authorization "
                    "changing."
                ),
            },
            "v2_code_hash_amendment_1": {
                "path": CORRECTED_ARTIFACT_RELATIVE,
                "manifest_hash": corrected.get("manifest_hash"),
                "note": (
                    "This amendment corrects one field of that artifact and leaves the "
                    "file byte-identical; its manifest_hash stays the recorded value."
                ),
            },
        },
        "producer": {
            "path": "scripts/build_v2_code_hash_amendment_2.py",
            "verify_command": "python3 scripts/verify_research_v2_code_hash_amendment_2.py",
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the document body with manifest_hash "
                "removed, following the pattern of the other v2 artifacts."
            ),
        },
    }

    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    return document


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--force", action="store_true", help="overwrite an existing artifact")
    parser.add_argument("--print", dest="print_only", action="store_true", help="print, write nothing")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    document = build(repo_root)
    rendered = json.dumps(document, indent=2, ensure_ascii=False) + "\n"

    if args.print_only:
        sys.stdout.write(rendered)
        return 0

    target = repo_root / "configs" / "research_v2_code_hash_amendment_2.json"
    if target.exists() and not args.force:
        print(f"refusing to overwrite {target} without --force", file=sys.stderr)
        return 1
    target.write_text(rendered, encoding="utf-8")
    print(f"wrote {target.relative_to(repo_root)} manifest_hash={document['manifest_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
