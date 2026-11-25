"""Black-box regression check for future-data leakage during missing-value fill."""
import copy
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]


class MissingDataLeakageTests(unittest.TestCase):
    def test_missing_train_feature_does_not_read_future_validation_values(self):
        config = yaml.safe_load((ROOT / "ai-engine/configs/model_config.yaml").read_text())
        medians = []
        with tempfile.TemporaryDirectory(prefix="ai-missing-data-test-") as directory:
            for future_value in (100.0, 200.0):
                folder = Path(directory) / str(int(future_value))
                folder.mkdir()
                features = config["data"]["features"]
                with (folder / "raw.csv").open("w", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=["timestamp", "cloud_provider", "service_name", *features])
                    writer.writeheader()
                    for index in range(40):
                        row = {name: 0.0 for name in features}
                        row.update(timestamp=1000 + index * 6, cloud_provider="aws",
                                   service_name="teastore-test", qps="" if index < 30 else future_value)
                        writer.writerow(row)
                cfg = copy.deepcopy(config)
                cfg["data"].update(raw_csv_path=str(folder / "raw.csv"),
                                   processed_dir=str(folder / "processed"),
                                   entity_baselines_path=str(folder / "baselines.json"),
                                   window_size=6, val_split=0.25)
                (folder / "config.yaml").write_text(yaml.safe_dump(cfg))
                subprocess.run([sys.executable, str(ROOT / "ai-engine/data/preprocess.py"),
                                "--config", str(folder / "config.yaml")], cwd=ROOT,
                               check=True, capture_output=True, text=True, timeout=30)
                baseline = json.loads((folder / "baselines.json").read_text())
                medians.append(baseline["aws:teastore-test"]["features"]["qps"]["median"])
        self.assertEqual(medians[0], medians[1],
                         "Identical training rows produced different baselines when only future validation "
                         f"values changed: {medians}. Fill missing values after splitting the data.")


if __name__ == "__main__":
    unittest.main()
