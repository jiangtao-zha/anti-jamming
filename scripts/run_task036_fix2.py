"""Reproduce Task 036-fix2 deduplication and corrected held-out evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task036_fix_dispatch import dispatch_info  # noqa: E402


RESULT_ROOT = PROJECT_ROOT / 'results' / 'phase1' / 'task036_fix2'
STAGE_SCRIPTS = {
    'dedup': ('scripts/task036_fix_stageD.py', 'stageB'),
    'heldout': ('scripts/task036_fix_stageE.py', 'stageC'),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_path() -> Path:
    return RESULT_ROOT / 'stageB' / 'selected_candidate.json'


def freeze_candidate() -> tuple[dict, str]:
    path = candidate_path()
    if not path.exists():
        raise RuntimeError(f'missing Stage B frozen candidate: {path}')
    payload = json.loads(path.read_text())
    candidate = payload.get('selected_candidate') or payload.get('rejection_confirmation_candidate')
    if candidate is None:
        raise RuntimeError('Stage B did not freeze a candidate representative')
    dispatch_info(candidate)
    return candidate, sha256(path)


def run_stage(stage: str) -> None:
    script, result_subdir = STAGE_SCRIPTS[stage]
    if stage == 'dedup' and (RESULT_ROOT / 'stageC' / 'final_decision.json').exists():
        raise RuntimeError('deduplication is locked after held-out results exist')
    frozen_path = None
    frozen_hash = None
    if stage == 'heldout':
        frozen_path = candidate_path()
        _, frozen_hash = freeze_candidate()
    output_dir = RESULT_ROOT / result_subdir
    output_dir.mkdir(parents=True, exist_ok=True)
    python = PROJECT_ROOT / '.venv' / 'bin' / 'python'
    executable = str(python if python.exists() else Path(sys.executable))
    result = subprocess.run(
        [executable, script, '--output-dir', str(output_dir)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
    )
    (output_dir / 'stdout.txt').write_text(result.stdout)
    (output_dir / 'stderr.txt').write_text(result.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    if stage == 'heldout':
        assert frozen_path is not None and frozen_hash is not None
        if sha256(frozen_path) != frozen_hash:
            raise RuntimeError('frozen candidate changed during held-out execution')
        (output_dir / 'heldout_lock.json').write_text(json.dumps({
            'candidate_file': str(frozen_path.relative_to(PROJECT_ROOT)),
            'candidate_file_sha256': frozen_hash,
            'dedup_locked_after_heldout': True,
        }, indent=2, ensure_ascii=False))
    print(f'{stage}: completed; outputs={output_dir.relative_to(PROJECT_ROOT)}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('dedup', 'heldout', 'all'), required=True)
    args = parser.parse_args()
    stages = ('dedup', 'heldout') if args.stage == 'all' else (args.stage,)
    for stage in stages:
        run_stage(stage)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
