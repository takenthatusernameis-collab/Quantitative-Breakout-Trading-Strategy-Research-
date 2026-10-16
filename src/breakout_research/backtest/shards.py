"""Bounded, immutable, hash-verified result shards for campaign resume.

New verified results are written under research/results_shards/<campaign_id>/
as deterministic JSONL shards, each at most MAX_SHARD_BYTES serialized bytes.
A compact research/results_manifest.json binds shard hashes, counts, and ID
sets to the spec/code/data versions. Resume reconstructs the completed
experiment-ID set from verified shards and derives the next missing unit from
it. Legacy research/results.jsonl is never appended to by this module.
"""
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Tuple

SCHEMA_VERSION = "result-shard-v1"
MAX_SHARD_BYTES = 4 * 1024 * 1024
SHARD_NAME_PREFIX = "shard_"
SHARD_NAME_SUFFIX = ".jsonl"
TMP_SUFFIX = ".tmp"


class ResultStoreError(RuntimeError):
    """Raised when result storage cannot guarantee integrity."""


def compute_experiment_id(
    spec_hash: str,
    code_hash: str,
    data_hash: str,
    asset: str,
    config_id: str,
    fold_index: int,
    start_time: int,
    end_time: int,
    is_holdout: bool,
    cost_multiplier: float,
    schema_version: str = SCHEMA_VERSION,
) -> str:
    """Stable experiment ID bound to protocol, code, data, and unit bounds.

    Wall-clock metadata is intentionally excluded from identity.
    """
    payload = {
        "schema_version": schema_version,
        "spec_hash": spec_hash,
        "code_hash": code_hash,
        "data_hash": data_hash,
        "asset": asset,
        "config_id": config_id,
        "fold_index": int(fold_index),
        "start_time": int(start_time),
        "end_time": int(end_time),
        "is_holdout": bool(is_holdout),
        "cost_multiplier": float(cost_multiplier),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def serialize_record(record: Dict[str, Any]) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = f".{path.name}.{os.getpid()}.tmp"
    temporary_path = path.parent / temporary_name
    try:
        with temporary_path.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        directory_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _atomic_write_text(path: Path, content: str) -> None:
    _atomic_write_bytes(path, content.encode("utf-8"))


def _shard_path(shard_root: Path, campaign_id: str, index: int) -> Path:
    return shard_root / campaign_id / f"{SHARD_NAME_PREFIX}{index:06d}{SHARD_NAME_SUFFIX}"


def _list_shard_files(shard_root: Path, campaign_id: str) -> List[Path]:
    campaign_dir = shard_root / campaign_id
    if not campaign_dir.is_dir():
        return []
    return sorted(
        path
        for path in campaign_dir.iterdir()
        if path.is_file()
        and path.name.startswith(SHARD_NAME_PREFIX)
        and path.name.endswith(SHARD_NAME_SUFFIX)
    )


def next_missing_unit(
    units: Iterable[Tuple[Dict[str, Any], str]],
    completed_ids: Set[str],
) -> Optional[Dict[str, Any]]:
    """First deterministic unit whose experiment ID is not completed.

    Units must be supplied in the campaign's fixed processing order.
    """
    for unit, experiment_id in units:
        if experiment_id not in completed_ids:
            return unit
    return None


class ShardWriter:
    """Append rows to the current shard, rolling to a new shard before the byte ceiling."""

    def __init__(
        self,
        campaign_id: str,
        shard_root: str = "research/results_shards",
        max_shard_bytes: int = MAX_SHARD_BYTES,
    ) -> None:
        self.campaign_id = campaign_id
        self.shard_root = Path(shard_root)
        self.max_shard_bytes = int(max_shard_bytes)
        self.campaign_dir = self.shard_root / campaign_id
        self.campaign_dir.mkdir(parents=True, exist_ok=True)
        existing = _list_shard_files(self.shard_root, campaign_id)
        self.next_index = len(existing)
        if existing:
            last_path = existing[-1]
            self.current_bytes = last_path.stat().st_size
            self._handle = last_path.open("a", encoding="utf-8")
        else:
            self.current_bytes = 0
            self._handle = None
        self.current_path: Optional[Path] = None
        if self._handle is not None:
            self.current_path = last_path

    def _open_new_shard(self) -> None:
        if self._handle is not None:
            self._handle.flush()
            os.fsync(self._handle.fileno())
            self._handle.close()
            self._handle = None
        self.current_path = _shard_path(self.shard_root, self.campaign_id, self.next_index)
        self.next_index += 1
        self.current_bytes = 0
        temporary_path = Path(str(self.current_path) + TMP_SUFFIX)
        self._handle = temporary_path.open("w", encoding="utf-8")

    def _promote_current_shard(self) -> None:
        if self._handle is None:
            return
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()
        temporary_path = Path(str(self.current_path) + TMP_SUFFIX)
        os.replace(temporary_path, self.current_path)
        directory_fd = os.open(str(self.current_path.parent), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        self._handle = None

    def append(self, record: Dict[str, Any]) -> None:
        line = serialize_record(record)
        line_bytes = len(line.encode("utf-8"))
        if line_bytes > self.max_shard_bytes:
            raise ResultStoreError(
                f"Single result row of {line_bytes} bytes exceeds shard ceiling {self.max_shard_bytes}"
            )
        if self._handle is None:
            self._open_new_shard()
        if self.current_bytes + line_bytes > self.max_shard_bytes and self.current_bytes > 0:
            self._promote_current_shard()
            self._open_new_shard()
        self._handle.write(line)
        self.current_bytes += line_bytes

    def flush(self) -> List[Dict[str, Any]]:
        """Promote the current shard and return its verified metadata."""
        if self._handle is None:
            return []
        self._promote_current_shard()
        assert self.current_path is not None
        shard_info = self._shard_metadata(self.current_path)
        self.current_path = None
        self.current_bytes = 0
        self._handle = None
        return [shard_info]

    def _shard_metadata(self, path: Path) -> Dict[str, Any]:
        ids: List[str] = []
        record_count = 0
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                ids.append(record["experiment_id"])
                record_count += 1
        return {
            "path": str(path),
            "shard_index": int(path.stem.split("_")[1]),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
            "records": record_count,
            "experiment_ids": ids,
        }

    def close(self) -> None:
        if self._handle is not None:
            self.flush()


class ResultStore:
    """Verified result store: shards plus a hash-bound manifest."""

    def __init__(
        self,
        campaign_id: str,
        spec_hash: str,
        code_hash: str,
        data_manifest_hash: str,
        shard_root: str = "research/results_shards",
        manifest_path: str = "research/results_manifest.json",
        max_shard_bytes: int = MAX_SHARD_BYTES,
    ) -> None:
        self.campaign_id = campaign_id
        self.spec_hash = spec_hash
        self.code_hash = code_hash
        self.data_manifest_hash = data_manifest_hash
        self.shard_root = Path(shard_root)
        self.manifest_path = Path(manifest_path)
        self.max_shard_bytes = max_shard_bytes
        self.writer = ShardWriter(campaign_id, shard_root, max_shard_bytes)
        self.manifest: Dict[str, Any] = {}
        self._loaded = False

    def _manifest_template(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": self.campaign_id,
            "specification_hash": self.spec_hash,
            "code_hash": self.code_hash,
            "data_manifest_hash": self.data_manifest_hash,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "updated_utc": datetime.now(timezone.utc).isoformat(),
            "shards": [],
            "total_records": 0,
            "total_bytes": 0,
        }

    def _read_manifest(self) -> Dict[str, Any]:
        if not self.manifest_path.exists():
            return self._manifest_template()
        try:
            with self.manifest_path.open("r", encoding="utf-8") as handle:
                manifest = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise ResultStoreError(f"Cannot read result manifest {self.manifest_path}: {exc}") from exc
        for key in ("schema_version", "campaign_id", "shards", "total_records", "total_bytes"):
            if key not in manifest:
                raise ResultStoreError(f"Result manifest missing required key {key}")
        manifest.setdefault("specification_hash", self.spec_hash)
        manifest.setdefault("code_hash", self.code_hash)
        manifest.setdefault("data_manifest_hash", self.data_manifest_hash)
        manifest.setdefault("shards", [])
        manifest.setdefault("total_records", 0)
        manifest.setdefault("total_bytes", 0)
        return manifest

    def _write_manifest(self, manifest: Dict[str, Any]) -> None:
        manifest["updated_utc"] = datetime.now(timezone.utc).isoformat()
        content = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        _atomic_write_text(self.manifest_path, content)

    def _verify_shard(self, path: Path, expected_hash: Optional[str] = None) -> Dict[str, Any]:
        actual_hash = sha256_file(path)
        if expected_hash is not None and actual_hash != expected_hash:
            raise ResultStoreError(f"Shard hash mismatch for {path}")
        ids: List[str] = []
        records: List[Dict[str, Any]] = []
        record_count = 0
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ResultStoreError(
                            f"Shard {path} has unparseable JSON on line {line_number}: {exc}"
                        ) from exc
                    if not isinstance(record, dict) or "experiment_id" not in record:
                        raise ResultStoreError(
                            f"Shard {path} line {line_number} is not a valid result record"
                        )
                    record_id = record["experiment_id"]
                    recomputed = compute_experiment_id(
                        spec_hash=self.spec_hash,
                        code_hash=self.code_hash,
                        data_hash=record.get("data_hash", ""),
                        asset=record.get("asset", ""),
                        config_id=record.get("config_id", ""),
                        fold_index=record.get("fold_index", 0),
                        start_time=record.get("start_time", 0),
                        end_time=record.get("end_time", 0),
                        is_holdout=record.get("is_holdout", False),
                        cost_multiplier=record.get("cost_multiplier", 0.0),
                    )
                    if recomputed != record_id:
                        raise ResultStoreError(
                            f"Shard {path} line {line_number}: experiment_id does not match record content"
                        )
                    ids.append(record_id)
                    records.append(record)
                    record_count += 1
        except ResultStoreError:
            raise
        except OSError as exc:
            raise ResultStoreError(f"Cannot read shard {path}: {exc}") from exc
        return {
            "path": str(path),
            "sha256": actual_hash,
            "bytes": path.stat().st_size,
            "records": record_count,
            "experiment_ids": ids,
            "records_payload": records,
        }

    def reconcile(self) -> Tuple[Dict[str, Dict[str, Any]], int]:
        """Verify every shard in the campaign directory and rebuild completed IDs.

        Shard files present on disk but missing from the manifest are adopted
        after verification, so a crash between shard promotion and manifest
        update cannot lose verified records. Conflicting content for one ID
        fails closed.
        """
        completed: Dict[str, Dict[str, Any]] = {}
        shard_infos: List[Dict[str, Any]] = []
        total_bytes = 0
        for path in _list_shard_files(self.shard_root, self.campaign_id):
            info = self._verify_shard(path)
            for record_id in info["experiment_ids"]:
                if record_id in completed:
                    existing = completed[record_id]
                    if existing.get("record") != info["records_payload"][
                        info["experiment_ids"].index(record_id)
                    ] if record_id in info["experiment_ids"] else existing:
                        raise ResultStoreError(f"Conflicting records for experiment ID {record_id}")
                completed[record_id] = {
                    "record": info["records_payload"][info["experiment_ids"].index(record_id)],
                    "shard": str(path),
                }
            shard_infos.append(info)
            total_bytes += info["bytes"]
        manifest = self._read_manifest()
        if (
            manifest.get("specification_hash") != self.spec_hash
            or manifest.get("code_hash") != self.code_hash
            or manifest.get("data_manifest_hash") != self.data_manifest_hash
        ):
            raise ResultStoreError("Result manifest bound to different spec/code/data versions")
        # Adopt verified shards missing from the manifest; drop manifest entries
        # whose files no longer verify.
        known_paths = {info["path"] for info in shard_infos}
        adopted: List[Dict[str, Any]] = []
        for info in shard_infos:
            adopted.append(
                {
                    "path": info["path"],
                    "shard_index": info["shard_index"],
                    "sha256": info["sha256"],
                    "bytes": info["bytes"],
                    "records": info["records"],
                    "experiment_ids": info["experiment_ids"],
                }
            )
        adopted.sort(key=lambda item: item["shard_index"])
        manifest["shards"] = adopted
        manifest["total_records"] = sum(item["records"] for item in adopted)
        manifest["total_bytes"] = total_bytes
        self._write_manifest(manifest)
        self.manifest = manifest
        self._loaded = True
        return completed, total_bytes

    def _manifest_shard_paths(self) -> Set[str]:
        return {str(entry.get("path")) for entry in self.manifest.get("shards", [])}

    def _is_new_shard(self, path: Path) -> bool:
        return str(path) not in self._manifest_shard_paths()

    def append(self, experiment_id: str, record: Dict[str, Any]) -> None:
        if "experiment_id" in record and record["experiment_id"] != experiment_id:
            raise ResultStoreError("Record experiment_id does not match supplied ID")
        record["experiment_id"] = experiment_id
        record["schema_version"] = SCHEMA_VERSION
        record["data_hash"] = record.get("data_hash", "")
        record.setdefault("stored_utc", datetime.now(timezone.utc).isoformat())
        self.writer.append(record)

    def flush(self) -> None:
        shard_infos = self.writer.flush()
        if not shard_infos:
            return
        manifest = self._read_manifest() if self.manifest else self.manifest
        if not manifest:
            manifest = self._manifest_template()
        known_paths = self._manifest_shard_paths()
        for info in shard_infos:
            if info["path"] in known_paths:
                continue
            manifest.setdefault("shards", []).append(
                {
                    "path": info["path"],
                    "shard_index": info["shard_index"],
                    "sha256": info["sha256"],
                    "bytes": info["bytes"],
                    "records": info["records"],
                    "experiment_ids": info["experiment_ids"],
                }
            )
            known_paths.add(info["path"])
        manifest["shards"].sort(key=lambda item: item["shard_index"])
        manifest["total_records"] = sum(entry.get("records", 0) for entry in manifest["shards"])
        manifest["total_bytes"] = sum(entry.get("bytes", 0) for entry in manifest["shards"])
        self._write_manifest(manifest)
        self.manifest = manifest
        self._loaded = True

    def close(self) -> None:
        self.writer.close()

    @property
    def pending_bytes(self) -> int:
        return self.writer.current_bytes