"""Task 036-fix Stage B: validate physical component-recomposition fixtures."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from task036_fix_fixture import (  # noqa: E402
    JAMMERS,
    JSRS,
    SAFE_TARGET_CENTERS,
    POSITION_POLICIES,
    POLICY_EVIDENCE,
    compose,
    generate_bank,
    power_change_db,
    target_support,
    translate_component,
)


SEEDS = tuple(range(6100, 6105))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def validate_row(bank, case: dict) -> dict:
    target = case['target']
    jammer = case['jammer_component']
    noise = case['noise']
    received = case['received']
    target_start, target_end, target_samples = target_support(target)
    expected_start = int(case['target_position'] - bank.template.size // 2)
    target_error = power_change_db(target, bank.target_base)
    noise_error = power_change_db(noise, bank.noise_base)
    jammer_error = power_change_db(jammer, bank.jammer_base)
    received_error = power_change_db(received, bank.received_base)
    measured = float(case['measured_jsr_db'])
    jsr_error = 0.0 if bank.jammer == 'NoJammer' else measured - float(bank.jsr_db)
    target_ok = target_start == expected_start and target_end == expected_start + bank.template.size - 1 and target_samples == bank.template.size
    jsr_ok = bank.jammer == 'NoJammer' or abs(jsr_error) < 1e-9
    finite_ok = all(np.all(np.isfinite(x)) for x in (target, jammer, noise, received))
    shape_ok = all(x.shape == (bank.config['N'],) for x in (target, jammer, noise, received))
    status = 'NO_JAMMER_NOT_APPLICABLE' if bank.jammer == 'NoJammer' else 'PASS'
    if bank.jammer != 'NoJammer' and not (target_ok and jsr_ok and finite_ok and shape_ok):
        status = 'FAIL'
    if bank.jammer == 'NoJammer' and not (target_ok and finite_ok and shape_ok):
        status = 'FAIL'
    return {
        'jammer': bank.jammer,
        'jsr_db': bank.jsr_db,
        'seed': bank.seed,
        'target_position': case['target_position'],
        'fixture_label': case['fixture_label'],
        'position_policy': bank.policy,
        'target_energy_error_db': target_error,
        'noise_energy_error_db': noise_error,
        'jammer_energy_error_db': jammer_error,
        'received_energy_error_db': received_error,
        'measured_jsr_db': measured,
        'jsr_error_db': jsr_error,
        'jsr_status': case['jsr_status'],
        'target_start_idx': target_start,
        'target_end_idx': target_end,
        'expected_target_start_idx': expected_start,
        'target_nonzero_samples': target_samples,
        'target_energy_consistent': abs(target_error) < 1e-12,
        'noise_energy_consistent': abs(noise_error) < 1e-12,
        'jammer_energy_consistent': abs(jammer_error) < 1e-12,
        'target_support_valid': target_ok,
        'finite': finite_ok,
        'shape_valid': shape_ok,
        'fixture_status': status,
    }


def comparison_row(bank, center: int) -> dict:
    physical = compose(bank, center)
    shift = int(center - bank.config['target_idx'])
    stress_received = translate_component(bank.received_base, shift)
    stress_target = translate_component(bank.target_base, shift)
    stress_jammer = translate_component(bank.jammer_base, shift)
    stress_noise = translate_component(bank.noise_base, shift)
    return {
        'jammer': bank.jammer,
        'jsr_db': bank.jsr_db,
        'seed': bank.seed,
        'target_position': center,
        'position_policy': bank.policy,
        'fixture_label_physical': 'PHYSICAL_COMPONENT_RECOMPOSITION',
        'fixture_label_stress': 'WHOLE_RECORD_TRANSLATION_STRESS',
        'physical_received_energy_error_db': power_change_db(physical['received'], bank.received_base),
        'stress_received_energy_error_db': power_change_db(stress_received, bank.received_base),
        'physical_target_energy_error_db': power_change_db(physical['target'], bank.target_base),
        'stress_target_energy_error_db': power_change_db(stress_target, bank.target_base),
        'physical_noise_energy_error_db': power_change_db(physical['noise'], bank.noise_base),
        'stress_noise_energy_error_db': power_change_db(stress_noise, bank.noise_base),
        'physical_jammer_energy_error_db': power_change_db(physical['jammer_component'], bank.jammer_base),
        'stress_jammer_energy_error_db': power_change_db(stress_jammer, bank.jammer_base),
        'physical_measured_jsr_db': physical['measured_jsr_db'],
        'stress_received_finite': bool(np.all(np.isfinite(stress_received))),
    }


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    policy_rows = [
        {'jammer': jammer, 'position_policy': POSITION_POLICIES[jammer], 'policy_evidence': POLICY_EVIDENCE[jammer]}
        for jammer in JAMMERS
    ]
    validation_rows = []
    comparison_rows = []
    for jammer in JAMMERS:
        for jsr_db in JSRS:
            for seed in SEEDS:
                bank = generate_bank(jammer, jsr_db, seed)
                for center in SAFE_TARGET_CENTERS:
                    validation_rows.append(validate_row(bank, compose(bank, center)))
                    comparison_rows.append(comparison_row(bank, center))
    write_csv(output_dir / 'jammer_position_policy.csv', policy_rows)
    write_csv(output_dir / 'fixture_validation.csv', validation_rows)
    write_csv(output_dir / 'fixture_comparison.csv', comparison_rows)
    metadata = {
        'task': '036-fix',
        'stage': 'stageB',
        'fixture_labels': ['PHYSICAL_COMPONENT_RECOMPOSITION', 'WHOLE_RECORD_TRANSLATION_STRESS'],
        'formal_label': 'PHYSICAL_COMPONENT_RECOMPOSITION',
        'stress_label': 'WHOLE_RECORD_TRANSLATION_STRESS',
        'jammers': list(JAMMERS),
        'jsrs_db': list(JSRS),
        'seeds': [SEEDS[0], SEEDS[-1]],
        'target_centers': list(SAFE_TARGET_CENTERS),
        'noise_rule': 'same jammer x JSR x seed noise realization reused at every target position',
        'target_rule': 'template embedded at target center with no truncation',
        'policies': policy_rows,
    }
    (output_dir / 'fixture_metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    status_counts = {}
    for row in validation_rows:
        status_counts[row['fixture_status']] = status_counts.get(row['fixture_status'], 0) + 1
    failed = sum(1 for row in validation_rows if row['fixture_status'] == 'FAIL')
    summary = {
        'task': '036-fix',
        'stage': 'stageB',
        'status': 'COMPLETED' if failed == 0 else 'BLOCKED',
        'validation_rows': len(validation_rows),
        'comparison_rows': len(comparison_rows),
        'fixture_status_counts': status_counts,
        'physical_fixture_failures': failed,
        'formal_fixture_label': 'PHYSICAL_COMPONENT_RECOMPOSITION',
        'whole_record_translation_status': 'STRESS_ONLY_NOT_FORMAL_EVIDENCE',
        'next_stage': 'stageC' if failed == 0 else 'stageC',
    }
    (output_dir / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default='results/phase1/task036_fix/stageB')
    args = parser.parse_args()
    summary = run(Path(args.output_dir))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary['status'] == 'COMPLETED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
