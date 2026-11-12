"""Preprocessing guarantees: gap-aware windows, blocked split, provenance."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai-engine"))

from data.preprocess import (  # noqa: E402
    assign_segments,
    build_chunk_windows,
    compute_entity_baselines,
    drop_incomplete_rows,
    split_entities_blocked,
)

FEATURES = ["qps", "server_latency_p95", "client_latency_p95", "error_rate_5xx",
            "max_pod_cpu_pct", "max_pod_ram_pct", "ram_floor_2m_pct", "gc_pause_rate"]
FLOORS = {f: 1.0 for f in FEATURES}


def frame(n, start=0, run="run01", entity=("aws", "teastore-webui"), gap_at=None, missing_at=None):
    ts = start + 10 * np.arange(n)
    if gap_at is not None:
        ts[gap_at:] += 300
    rows = pd.DataFrame({"timestamp": ts, "cloud_provider": entity[0], "service_name": entity[1],
                         "source_run": run, "anomaly_label": 0, "missing_metrics": ""})
    for i, f in enumerate(FEATURES):
        rows[f] = np.arange(n, dtype=float) + i
    if missing_at is not None:
        rows.loc[missing_at, "missing_metrics"] = "max_pod_cpu_pct"
    return rows


class BlockedSplitTest(unittest.TestCase):
    def prepare(self, df, block=20, every=4, embargo=3, window=5):
        df, dropped = drop_incomplete_rows(df)
        df = assign_segments(df, max_gap_seconds=25)
        df, audit = split_entities_blocked(df, block, every, embargo, window)
        baselines = compute_entity_baselines(df[df["split"] == "train"], FEATURES, FLOORS)
        return df, audit, baselines, dropped

    def test_windows_never_span_a_time_gap(self):
        df, _, baselines, _ = self.prepare(frame(200, gap_at=50), block=1000, every=1000)
        windows, _, _ = build_chunk_windows(df, baselines, FEATURES, 5, 1, "train")
        # 50 + 150 contiguous rows -> (50-4) + (150-4) windows; a window across the gap would add 4.
        self.assertEqual(len(windows), 46 + 146)

    def test_single_incomplete_row_is_dropped_like_a_skipped_detector_cycle(self):
        # The detector skips one UNKNOWN cycle and keeps its buffer, so a 20s hole
        # (< max_gap) stays inside one segment, exactly as served.
        df, _, baselines, dropped = self.prepare(frame(100, missing_at=40), block=1000, every=1000)
        self.assertEqual(dropped, 1)
        windows, _, _ = build_chunk_windows(df, baselines, FEATURES, 5, 1, "train")
        self.assertEqual(len(windows), 99 - 4)

    def test_long_incomplete_stretch_breaks_windows(self):
        df, _, baselines, dropped = self.prepare(frame(100, missing_at=list(range(40, 45))), block=1000, every=1000)
        self.assertEqual(dropped, 5)
        windows, _, _ = build_chunk_windows(df, baselines, FEATURES, 5, 1, "train")
        self.assertEqual(len(windows), (40 - 4) + (55 - 4))

    def test_split_is_interleaved_disjoint_and_embargoed(self):
        df, audit, baselines, _ = self.prepare(frame(400))
        train, _, train_ts = build_chunk_windows(df, baselines, FEATURES, 5, 1, "train")
        val, _, val_ts = build_chunk_windows(df, baselines, FEATURES, 5, 1, "val")
        self.assertFalse(train_ts & val_ts)
        ordered = df.sort_values("timestamp")["split"].tolist()
        # Validation appears in several separate blocks across the run, not only at the end.
        val_blocks = sum(1 for a, b in zip(["train"] + ordered, ordered) if b == "val" and a != "val")
        self.assertEqual(val_blocks, 5)
        for i, label in enumerate(ordered):
            if label == "val":
                neighbours = ordered[max(0, i - 3):i] + ordered[i + 1:i + 4]
                self.assertNotIn("train", [n for n in neighbours if n != "val"])
        self.assertEqual(sum(v["embargo_rows"] for v in audit.values()), 5 * 3 + 4 * 3)
        self.assertTrue(len(train) and len(val))

    def test_training_fill_never_reads_validation_values(self):
        """End to end: changing only validation values must not change train baselines."""
        p99s = []
        for val_value in (100.0, 200.0):
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                target = tmp / "raw" / "20990101_teastore_normal-a_run01" / "metrics" / "entity_features.csv"
                target.parent.mkdir(parents=True)
                df = frame(400).drop(columns=["source_run"])
                df["qps"] = 1.0
                df.loc[120:159, "qps"] = val_value          # 4th 40-row block -> validation
                df.loc[160:179, "qps"] = np.nan             # missing right after it (12 embargo + 8 train rows)
                df.to_csv(target, index=False)
                cfg = yaml.safe_load((ROOT / "ai-engine/configs/model_config.yaml").read_text())
                cfg["data"].update(raw_csv_paths=[str(target)], processed_dir=str(tmp / "processed"),
                                   entity_baselines_path=str(tmp / "baselines.json"), split_strategy="blocked",
                                   split_block_rows=40, val_every_n_blocks=4, embargo_rows=12)
                (tmp / "config.yaml").write_text(yaml.safe_dump(cfg))
                subprocess.run([sys.executable, str(ROOT / "ai-engine/data/preprocess.py"), "--config", str(tmp / "config.yaml")],
                               check=True, capture_output=True, cwd=ROOT)
                baselines = json.loads((tmp / "baselines.json").read_text())
                p99s.append(baselines["aws:teastore-webui"]["features"]["qps"]["p99"])
        self.assertEqual(p99s[0], p99s[1])
        self.assertEqual(p99s[0], 1.0)

    def test_baselines_use_training_rows_only(self):
        df = frame(400)
        df, _, baselines, _ = self.prepare(df)
        train_median = float(np.median(df[df["split"] == "train"]["qps"]))
        self.assertAlmostEqual(baselines["aws:teastore-webui"]["features"]["qps"]["median"], train_median, places=4)

    def test_cli_records_source_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            paths = []
            for run, start in (("20990101_teastore_normal-a_run01", 0), ("20990101_teastore_normal-b_run01", 10_000)):
                target = tmp / "raw" / run / "metrics" / "entity_features.csv"
                target.parent.mkdir(parents=True)
                parts = [frame(260, start=start, run=run, entity=e) for e in (("aws", "teastore-webui"), ("gcp", "teastore-recommender"))]
                pd.concat(parts).drop(columns=["source_run"]).to_csv(target, index=False)
                paths.append(str(target))
            cfg = yaml.safe_load((ROOT / "ai-engine/configs/model_config.yaml").read_text())
            cfg["data"].update(raw_csv_paths=paths, processed_dir=str(tmp / "processed"),
                               entity_baselines_path=str(tmp / "baselines.json"), split_strategy="blocked",
                               split_block_rows=40, val_every_n_blocks=4, embargo_rows=12)
            config = tmp / "config.yaml"
            config.write_text(yaml.safe_dump(cfg))
            subprocess.run([sys.executable, str(ROOT / "ai-engine/data/preprocess.py"), "--config", str(config)],
                           check=True, capture_output=True, cwd=ROOT)
            summary = json.loads((tmp / "processed/preprocess_summary.json").read_text())
            self.assertEqual(summary["source_runs"], ["20990101_teastore_normal-a_run01", "20990101_teastore_normal-b_run01"])
            self.assertEqual(summary["split_strategy"], "blocked_interleaved_with_embargo")
            self.assertEqual(summary["window_overlap_between_train_and_val"], 0)
            self.assertGreater(summary["val_windows"], 0)
            self.assertEqual(np.load(tmp / "processed/val_windows.npy").shape[1:], (12, 8))


if __name__ == "__main__":
    unittest.main()
