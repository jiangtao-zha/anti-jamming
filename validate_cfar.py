#!/usr/bin/env python3
"""Monte Carlo validation of the power-domain CA-CFAR implementation."""

import argparse
import csv
from pathlib import Path

import numpy as np

from utils.evaluation import _ca_cfar


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--trials', type=int, default=10000)
    parser.add_argument('--length', type=int, default=256)
    parser.add_argument('--pfa', type=float, default=1e-4)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--output', default='results/phase1/evaluation_v2/cfar_pfa.csv')
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    detections = 0
    valid_cells = 0
    min_refs = args.length
    max_refs = 0
    for _ in range(args.trials):
        noise = (
            rng.standard_normal(args.length)
            + 1j * rng.standard_normal(args.length)
        ) / np.sqrt(2.0)
        detected, _, reference_count = _ca_cfar(
            np.abs(noise), guard_cells=4, reference_cells=20, pfa=args.pfa
        )
        detections += int(np.count_nonzero(detected))
        valid_cells += int(np.count_nonzero(reference_count > 0))
        min_refs = min(min_refs, int(reference_count.min()))
        max_refs = max(max_refs, int(reference_count.max()))

    measured = detections / valid_cells
    error = measured - args.pfa
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            'requested_pfa', 'measured_pfa', 'error', 'trials',
            'length', 'valid_cells', 'min_reference_cells',
            'max_reference_cells',
        ])
        writer.writeheader()
        writer.writerow({
            'requested_pfa': args.pfa,
            'measured_pfa': measured,
            'error': error,
            'trials': args.trials,
            'length': args.length,
            'valid_cells': valid_cells,
            'min_reference_cells': min_refs,
            'max_reference_cells': max_refs,
        })
    print(f'requested_pfa={args.pfa}')
    print(f'measured_pfa={measured:.8f}')
    print(f'error={error:.8f}')
    print(f'reference_cells={min_refs}..{max_refs}')


if __name__ == '__main__':
    main()
