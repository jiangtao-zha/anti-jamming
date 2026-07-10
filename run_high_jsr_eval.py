#!/usr/bin/env python3
"""Run the P0 high-JSR full-matrix algorithm evaluation.

The experiment intentionally uses the same RadarEnvironment and evaluator as
the existing validation scripts.  It records one aggregate row for every
JSR x jammer x anti-jamming algorithm combination and keeps per-trial errors
in the JSON output so a failed adapter cannot be mistaken for a valid result.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
from scipy import signal

from unified_framework import (
    AntiJammingProcessor,
    JammerLoader,
    RadarEnvironment,
    UnifiedEvaluator,
)


JAMMERS = [
    "ISDJ",
    "SMSP",
    "RGPO",
    "FMZuse",
    "FMNoiseAimedJam",
    "AMNoiseGaiJam",
    "FMNoiseSaopin",
    "NoiseProductJamming",
    "NoiseConvolutionJamming",
]

ANTIJAM_ALGORITHMS = [
    "WLN",
    "FrequencyDomainCanceller",
    "adapt_filter",
    "frft_filter",
    "qpzh",
    "FastSlowTimeProcessor",
    "wave_agile",
    "Frequency_agile",
]

# These are the adapter defaults used by the current unified interface.  They
# are kept here as experiment metadata instead of relying on hidden defaults.
ANTIJAM_KWARGS = {
    "WLN": {"par1": 0.3, "par2": 6},
    "FrequencyDomainCanceller": {"cancellation_strength": 0.8},
    "adapt_filter": {"par1": 0.01},
    "frft_filter": {"mask_threshold": 0.1},
    "qpzh": {"m": 8, "n": 2},
    "FastSlowTimeProcessor": {"limit_factor": 3.0},
    "wave_agile": {},
    "Frequency_agile": {},
}

BASELINE = {
    "f0": 15e6,
    "Bw": 5e6,
    "Pw": 20e-6,
    "Fs": 50e6,
    "M": 1,
    "N": 5000,
    "target_dist": 6000,
    "target_amp": 1.0,
    "jammer_amp": 8.0,
    "noise_var": 0.1,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--jsr", nargs="+", type=float, default=[20.0, 30.0],
        help="JSR values in dB (default: 20 30)",
    )
    parser.add_argument(
        "--trials", type=int, default=10,
        help="Independent trials per combination (default: 10)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Base seed; trial i uses seed + i * 1000 (default: 42)",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("experiment_results/high_jsr_eval_20260707"),
        help="Directory for CSV, JSON and Markdown outputs",
    )
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be at least 1")
    if not args.jsr:
        parser.error("--jsr must contain at least one value")
    return args


def _matched_filter_profile(radar_par: dict, processed_signal, processed_template):
    signal_matrix = np.asarray(processed_signal)
    if signal_matrix.ndim == 2:
        signal_row = signal_matrix[0]
    else:
        signal_row = signal_matrix

    template = np.asarray(processed_template).reshape(-1)
    if template.size == 0:
        template = np.asarray(radar_par["St_base"]).reshape(-1)
    profile = signal.fftconvolve(signal_row, np.conj(template[::-1]), mode="same")
    return np.abs(profile)


def run_trial(jammer_type: str, antijam_type: str, jsr: float, seed: int):
    np.random.seed(seed)
    radar_params = dict(BASELINE)
    radar_params["JSR_dB"] = jsr

    env = RadarEnvironment(radar_params)
    evaluator = UnifiedEvaluator(guard_cells=4, ref_cells=20, Pfa=1e-4)
    result = {
        "seed": seed,
        "sinr_before": None,
        "sinr_after": None,
        "improvement": None,
        "detected_before": None,
        "detected_after": None,
        "error": None,
    }

    try:
        jammer = JammerLoader.load(
            jammer_type,
            f0=BASELINE["f0"],
            B=BASELINE["Bw"],
            T=BASELINE["Pw"],
            Tr=100e-6,
            Fs=BASELINE["Fs"],
        )
        radar_par = env.generate_with_jammer(jammer)
        original_profile = _matched_filter_profile(
            radar_par, radar_par["Srt_matrix"], radar_par["St_base"]
        )
        before = evaluator.evaluate(original_profile, radar_par["target_idx"])
        result["sinr_before"] = float(before["sinr_db"])
        result["detected_before"] = bool(before["is_detected"])

        processor = AntiJammingProcessor(antijam_type)
        processed_signal, processed_template = processor.process(
            radar_par, **ANTIJAM_KWARGS[antijam_type]
        )
        filtered_profile = _matched_filter_profile(
            radar_par, processed_signal, processed_template
        )
        after = evaluator.evaluate(filtered_profile, radar_par["target_idx"])
        result["sinr_after"] = float(after["sinr_db"])
        result["improvement"] = float(after["sinr_db"] - before["sinr_db"])
        result["detected_after"] = bool(after["is_detected"])
    except Exception as exc:  # Keep the matrix complete when one pair fails.
        result["error"] = f"{type(exc).__name__}: {exc}"

    return result


def _stats(trials: list[dict]) -> dict:
    valid = [trial for trial in trials if trial["error"] is None]
    errors = [trial for trial in trials if trial["error"] is not None]

    def values(name):
        return np.asarray([trial[name] for trial in valid], dtype=float)

    summary = {
        "trials": len(trials),
        "valid_trials": len(valid),
        "error_count": len(errors),
    }
    for name, prefix in (
        ("sinr_before", "SINR_before"),
        ("sinr_after", "SINR_after"),
        ("improvement", "SINR_improvement"),
    ):
        data = values(name)
        summary[f"{prefix}_mean"] = float(np.mean(data)) if len(data) else None
        summary[f"{prefix}_std"] = float(np.std(data)) if len(data) else None
        summary[f"{prefix}_min"] = float(np.min(data)) if len(data) else None
        summary[f"{prefix}_max"] = float(np.max(data)) if len(data) else None

    for name, output in (
        ("detected_before", "det_rate_before"),
        ("detected_after", "det_rate_after"),
    ):
        data = [trial[name] for trial in valid]
        summary[output] = float(np.mean(data)) if data else None

    summary["errors"] = [trial["error"] for trial in errors]
    return summary


def _write_csv(path: Path, rows: list[dict]):
    fields = [
        "jsr_db", "jammer", "algorithm", "trials", "valid_trials", "error_count",
        "SINR_before_mean", "SINR_before_std", "SINR_before_min", "SINR_before_max",
        "SINR_after_mean", "SINR_after_std", "SINR_after_min", "SINR_after_max",
        "SINR_improvement_mean", "SINR_improvement_std",
        "SINR_improvement_min", "SINR_improvement_max",
        "det_rate_before", "det_rate_after",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def _format(value):
    return "-" if value is None else f"{value:.3f}"


def _write_markdown(path: Path, metadata: dict, rows: list[dict]):
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# High JSR Evaluation Summary\n\n")
        handle.write(f"- JSR: {', '.join(f'{v:g} dB' for v in metadata['jsr_db'])}\n")
        handle.write(f"- Trials per combination: {metadata['trials']}\n")
        handle.write(f"- Base seed: {metadata['seed']}\n")
        handle.write("- Baseline: Pw=20us, Fs=50MHz, target_idx=1500, M=1\n\n")
        handle.write(
            "| JSR | Jammer | Algorithm | SINR before | SINR after | Improvement | "
            "Detect before | Detect after | Errors |\n"
        )
        handle.write("|---:|---|---|---:|---:|---:|---:|---:|---:|\n")
        for row in rows:
            handle.write(
                f"| {row['jsr_db']:g} | {row['jammer']} | {row['algorithm']} | "
                f"{_format(row['SINR_before_mean'])} | {_format(row['SINR_after_mean'])} | "
                f"{_format(row['SINR_improvement_mean'])} | "
                f"{_format(row['det_rate_before'])} | {_format(row['det_rate_after'])} | "
                f"{row['error_count']} |\n"
            )


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "jsr_db": [float(value) for value in args.jsr],
        "trials": args.trials,
        "seed": args.seed,
        "baseline": BASELINE,
        "jammers": JAMMERS,
        "algorithms": ANTIJAM_ALGORITHMS,
        "algorithm_kwargs": ANTIJAM_KWARGS,
        "evaluator": {"guard_cells": 4, "ref_cells": 20, "Pfa": 1e-4},
    }
    rows = []
    details = []
    total = len(args.jsr) * len(JAMMERS) * len(ANTIJAM_ALGORITHMS)
    completed = 0

    for jsr in args.jsr:
        for jammer in JAMMERS:
            for algorithm in ANTIJAM_ALGORITHMS:
                trial_results = [
                    run_trial(jammer, algorithm, jsr, args.seed + trial * 1000)
                    for trial in range(args.trials)
                ]
                summary = _stats(trial_results)
                row = {"jsr_db": jsr, "jammer": jammer, "algorithm": algorithm, **summary}
                rows.append(row)
                details.append({**row, "trial_results": trial_results})
                completed += 1
                print(
                    f"[{completed}/{total}] JSR={jsr:g} {jammer} vs {algorithm}: "
                    f"improvement={_format(summary['SINR_improvement_mean'])} dB, "
                    f"errors={summary['error_count']}",
                    flush=True,
                )

    _write_csv(args.output_dir / "summary.csv", rows)
    with (args.output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump({"metadata": metadata, "results": details}, handle, indent=2, ensure_ascii=False)
    _write_markdown(args.output_dir / "summary.md", metadata, rows)
    print(f"Wrote evaluation outputs to {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
