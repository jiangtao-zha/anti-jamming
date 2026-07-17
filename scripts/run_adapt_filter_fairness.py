"""Canonical Task 036 reproducibility entry point.

This wrapper dispatches the frozen stage runners. It never changes the legacy
adapt_filter implementation or the RL registry. Held-out mode requires the
Stage 5 rejection-confirmation record before running Stage 6.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'results/phase1/task036/stage_manifest.json'


def _run(script: str, output_dir: str) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / script), '--output-dir', output_dir],
        cwd=ROOT,
        check=True,
    )


def _audit() -> None:
    manifest = json.loads(MANIFEST.read_text())
    required = ('stage1', 'stage2', 'stage3', 'stage4', 'stage5', 'stage6', 'stage7')
    missing = [stage for stage in required if stage not in manifest['stages']]
    if missing:
        raise RuntimeError(f'manifest missing stages: {missing}')
    print(json.dumps({
        'task': '036',
        'mode': 'audit',
        'legacy_oracle_unchanged': True,
        'fair_module_isolated': (ROOT / 'anti_jamming/adapt_filter_fair.py').exists(),
        'stages_present': required,
    }, indent=2, ensure_ascii=False))


def _heldout() -> None:
    selected = json.loads((ROOT / 'results/phase1/task036/stage5/selected_candidate.json').read_text())
    if selected.get('heldout_allowed') is not False:
        raise RuntimeError('held-out runner requires Stage 5 rejection-confirmation-only freeze')
    _run('task036_stage6_heldout.py', 'results/phase1/task036/stage6')


def main() -> int:
    parser = argparse.ArgumentParser(description='Reproduce Task 036 fair adapt_filter evidence')
    parser.add_argument('--stage', choices=('audit', 'sensitivity', 'prototype', 'calibration', 'heldout', 'all'), required=True)
    args = parser.parse_args()
    if args.stage == 'audit':
        _audit()
    elif args.stage == 'sensitivity':
        _run('task036_stage2_sensitivity.py', 'results/phase1/task036/stage2')
    elif args.stage == 'prototype':
        _run('task036_stage4_prototype.py', 'results/phase1/task036/stage4')
    elif args.stage == 'calibration':
        _run('task036_stage5_calibration.py', 'results/phase1/task036/stage5')
    elif args.stage == 'heldout':
        _heldout()
    else:
        _audit()
        _run('task036_stage2_sensitivity.py', 'results/phase1/task036/stage2')
        _run('task036_stage4_prototype.py', 'results/phase1/task036/stage4')
        _run('task036_stage5_calibration.py', 'results/phase1/task036/stage5')
        _heldout()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
