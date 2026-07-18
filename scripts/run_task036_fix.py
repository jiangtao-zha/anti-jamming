"""Reproduce the Task 036-fix formal stages without touching legacy Task 036 results."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = PROJECT_ROOT / 'results' / 'phase1' / 'task036_fix'
STAGE_SCRIPTS = {
    'fixture': 'scripts/task036_fix_stageB.py',
    'gating': 'scripts/task036_fix_stageC.py',
    'calibration': 'scripts/task036_fix_stageD.py',
    'heldout': 'scripts/task036_fix_stageE.py',
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage_result_dir(stage: str) -> Path:
    return RESULT_ROOT / {'fixture': 'stageB', 'gating': 'stageC', 'calibration': 'stageD', 'heldout': 'stageE'}[stage]


def assert_calibration_allowed() -> None:
    heldout_dir = stage_result_dir('heldout')
    if (heldout_dir / 'final_decision.json').exists() or (heldout_dir / 'heldout_lock.json').exists():
        raise RuntimeError('calibration is locked after held-out results exist')


def freeze_candidate() -> tuple[Path, str]:
    candidate_path = stage_result_dir('calibration') / 'selected_candidate.json'
    if not candidate_path.exists():
        raise RuntimeError(f'missing frozen calibration candidate file: {candidate_path}')
    payload = json.loads(candidate_path.read_text())
    if payload.get('selected_candidate') is not None:
        raise RuntimeError('held-out requires the Stage D candidate freeze to remain rejection-confirmation-only')
    if not payload.get('rejection_confirmation_candidate'):
        raise RuntimeError('Stage D did not provide a rejection-confirmation representative')
    return candidate_path, sha256(candidate_path)


def run_stage(stage: str) -> None:
    if stage == 'calibration':
        assert_calibration_allowed()
    candidate_path = None
    candidate_hash = None
    if stage == 'heldout':
        candidate_path, candidate_hash = freeze_candidate()
    output_dir = stage_result_dir(stage)
    output_dir.mkdir(parents=True, exist_ok=True)
    python = PROJECT_ROOT / '.venv' / 'bin' / 'python'
    executable = str(python if python.exists() else Path(sys.executable))
    command = [executable, STAGE_SCRIPTS[stage], '--output-dir', str(output_dir)]
    result = subprocess.run(command, cwd=PROJECT_ROOT, text=True, capture_output=True)
    (output_dir / 'stdout.txt').write_text(result.stdout)
    (output_dir / 'stderr.txt').write_text(result.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    if stage == 'heldout':
        assert candidate_path is not None and candidate_hash is not None
        if sha256(candidate_path) != candidate_hash:
            raise RuntimeError('candidate freeze changed during held-out execution')
        (output_dir / 'heldout_lock.json').write_text(json.dumps({
            'candidate_file': str(candidate_path.relative_to(PROJECT_ROOT)),
            'candidate_file_sha256': candidate_hash,
            'calibration_locked_after_heldout': True,
        }, indent=2, ensure_ascii=False))
    print(f'{stage}: completed; outputs={output_dir.relative_to(PROJECT_ROOT)}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('fixture', 'gating', 'calibration', 'heldout', 'all'), required=True)
    args = parser.parse_args()
    stages = list(STAGE_SCRIPTS) if args.stage == 'all' else [args.stage]
    for stage in stages:
        run_stage(stage)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
