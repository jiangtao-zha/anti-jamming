#!/usr/bin/env python3
"""Reproducible stage dispatcher for Task 037.

Each stage owns a separate result directory.  The dispatcher refuses to
overwrite an existing non-empty stage directory unless --overwrite is given.
Later stages are intentionally wired to their stage scripts as they are
implemented; an absent script is a dispatch error rather than a fabricated
result.
"""

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = ROOT / 'results' / 'phase1' / 'task037'
STAGES = {
    'audit': ('stage1', 'task037_stage1.py'),
    'separability': ('stage2', 'task037_stage2.py'),
    'oracle': ('stage3', 'task037_stage3.py'),
    'prototype': ('stage4', 'task037_stage4.py'),
    'calibration': ('stage5', 'task037_stage5.py'),
    'heldout': ('stage6', 'task037_stage6.py'),
}


def run_one(stage_name, overwrite=False):
    stage, script_name = STAGES[stage_name]
    output = RESULT_ROOT / stage
    script = ROOT / 'scripts' / script_name
    if not script.exists():
        print(f'DISPATCH_ERROR: {stage_name} -> missing {script}', file=sys.stderr)
        return 2
    if output.exists() and any(output.iterdir()) and not overwrite:
        print(f'RESULT_EXISTS: refusing to overwrite {output}', file=sys.stderr)
        return 2
    if stage_name == 'heldout':
        candidate_summary = RESULT_ROOT / 'stage5' / 'summary.json'
        if not candidate_summary.exists():
            print(f'DISPATCH_ERROR: heldout requires frozen Stage 5 summary {candidate_summary}', file=sys.stderr)
            return 2
    if stage_name == 'calibration' and (RESULT_ROOT / 'stage6' / 'summary.json').exists():
        print('DISPATCH_ERROR: calibration is forbidden after heldout', file=sys.stderr)
        return 2
    output.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(script), '--output-dir', str(output)]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    (output / 'stdout.txt').write_text(completed.stdout)
    (output / 'stderr.txt').write_text(completed.stderr)
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    print(f'TASK037_DISPATCH stage={stage_name} exit={completed.returncode}', file=sys.stderr)
    return completed.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=['audit', 'separability', 'oracle', 'prototype', 'calibration', 'heldout', 'all'], required=True)
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args()
    if args.stage == 'all':
        for stage_name in STAGES:
            status = run_one(stage_name, overwrite=args.overwrite)
            if status:
                raise SystemExit(status)
        return
    raise SystemExit(run_one(args.stage, overwrite=args.overwrite))


if __name__ == '__main__':
    main()
