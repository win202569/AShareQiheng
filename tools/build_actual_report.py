"""Build the bounded progress artifact from the current persisted pipeline state."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ashare_pipeline.reporting import build_progress_artifact


def _read_mapping(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, part_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".part", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(part_name, path)
    except BaseException:
        Path(part_name).unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()

    data_root = Path(arguments.data_root).resolve()
    pipeline_status = _read_mapping(data_root / "status" / "pipeline_status.json")
    quality_document = _read_mapping(data_root / "status" / "quality.json")
    quality = quality_document.get("metrics", quality_document)
    pilot_path = data_root / "pilot_status.json"
    pilot_status = _read_mapping(pilot_path) if pilot_path.exists() else None
    generated_at = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()

    artifact = build_progress_artifact(
        pipeline_status=pipeline_status,
        quality=quality if isinstance(quality, dict) else None,
        pilot_status=pilot_status,
        generated_at=generated_at,
        plan_path="work/a_share_pipeline/PLAN.md",
        scoring_spec_path="work/a_share_pipeline/SCORING_SPEC_V2.md",
    )
    output = Path(arguments.output).resolve()
    _atomic_write(output, artifact)
    headline = artifact["snapshot"]["datasets"]["headline_metrics"][0]
    print(json.dumps({
        "output": str(output),
        "status": artifact["snapshot"]["status"],
        "universe_count": headline.get("universe_count"),
        "disclosure_coverage": headline.get("disclosure_coverage"),
        "prefilter_candidate_count": headline.get("prefilter_candidate_count"),
        "formal_pool_count": headline.get("formal_pool_count"),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
