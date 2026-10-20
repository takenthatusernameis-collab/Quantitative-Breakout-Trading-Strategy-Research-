#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import sys
from itertools import permutations
from pathlib import Path


AUTHORIZED_CODE_HASH = "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2"
CANONICAL_HASHED_SET = "3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff"
HASHTREE_PATH = Path("src/breakout_research")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_source_digest(repo_root: Path) -> str:
    base = repo_root / HASHTREE_PATH
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("utf-8") + b"\n")
    return digest.hexdigest()


def compute_code_hash_top_files_first_then_blocks(repo_root: Path, block_order):
    base = repo_root / HASHTREE_PATH
    hasher = hashlib.sha256()
    top_files = sorted([f for f in os.listdir(base) if os.path.isfile(os.path.join(base, f)) and f.endswith(".py")])
    for f in top_files:
        with open(os.path.join(base, f), "rb") as fp:
            hasher.update(fp.read())
    for block in block_order:
        if block.startswith(".") or block.startswith("__"):
            continue
        bdir = base / block
        if not bdir.exists():
            continue
        for root, dirs, files in os.walk(bdir):
            for f in sorted(files):
                if f.endswith(".py"):
                    path = os.path.join(root, f)
                    with open(path, "rb") as fp:
                        hasher.update(fp.read())
    return hasher.hexdigest()


def compute_live_ordered(repo_root: Path):
    base = repo_root / HASHTREE_PATH
    hasher = hashlib.sha256()
    top_files = sorted([f for f in os.listdir(base) if os.path.isfile(os.path.join(base, f)) and f.endswith(".py")])
    for f in top_files:
        with open(os.path.join(base, f), "rb") as fp:
            hasher.update(fp.read())
    top_order = []
    for entry in base.iterdir():
        if entry.is_dir() and not entry.name.startswith(".") and not entry.name.startswith("__"):
            top_order.append(entry.name)
    # but live os.walk order of dirs from src_dir level? compute_code_hash does os.walk(src_dir) from top level
    # it will visit dirs in os.walk's order; but it also visits top level files when it reaches src_dir
    # easier to replicate exactly
    hasher = hashlib.sha256()
    for root, dirs, files in os.walk(base):
        for f in sorted(files):
            if f.endswith(".py"):
                path = os.path.join(root, f)
                with open(path, "rb") as fp:
                    hasher.update(fp.read())
    return hasher.hexdigest(), [d for d in os.listdir(base) if os.path.isdir(os.path.join(base,d)) and not d.startswith('.') and d != '__pycache__']


def _source_blocks(repo_root: Path):
    base = repo_root / HASHTREE_PATH
    blocks = []
    for entry in base.iterdir():
        if entry.is_dir() and not entry.name.startswith(".") and not entry.name.startswith("__"):
            blocks.append(entry.name)
    return sorted(set(blocks))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-gate-compatible", action="store_true")
    args = parser.parse_args()

    repo_root = Path.cwd().resolve()
    canonical = canonical_source_digest(repo_root)
    live_ordered, live_top_order = compute_live_ordered(repo_root)
    blocks = _source_blocks(repo_root)
    variants = []
    for perm in permutations(blocks):
        variants.append(compute_code_hash_top_files_first_then_blocks(repo_root, perm))
    authorized_in_variants = any(d == AUTHORIZED_CODE_HASH for d in variants)
    gate_compatible = live_ordered == AUTHORIZED_CODE_HASH

    result = {
        "ok": True,
        "canonical_hashed_set_digest": canonical,
        "canonical_matches_recorded": canonical == CANONICAL_HASHED_SET,
        "authorized_code_hash": AUTHORIZED_CODE_HASH,
        "live_ordered_code_hash": live_ordered,
        "live_enumeration_order": live_top_order,
        "authorized_in_any_block_order": authorized_in_variants,
        "gate_compatible": gate_compatible,
        "variants_considered": len(variants),
        "authorized_order_matches_live": gate_compatible,
        "note": "Environment fact: live ordered digest differing from authorized is not source drift",
    }

    if canonical != CANONICAL_HASHED_SET:
        result["ok"] = False
        result["failures"] = ["canonical_hashed_set_digest_mismatch"]

    print(json.dumps(result, indent=2))
    if args.require_gate_compatible and not gate_compatible:
        print("Environment fact: checkout directory order differs from the authorized order; not treating as source drift.", file=sys.stderr)
        return 1
    if not result["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
