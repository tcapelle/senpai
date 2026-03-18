# SPDX-FileCopyrightText: 2026 CoreWeave, Inc.
# SPDX-License-Identifier: Apache-2.0
# SPDX-PackageName: senpai

"""Generate predictions on the hidden test set.

Loads a trained model checkpoint and runs inference on test_inputs.pt,
saving denormalized predictions in physical units.

Run:
  python predict.py --checkpoint models/model-<id>/checkpoint.pt
"""

import json
from dataclasses import dataclass
from pathlib import Path

import simple_parsing as sp
import torch
import yaml
from tqdm import tqdm

from data.prepare_multi import X_DIM


PREDICTIONS_DIR = Path("/mnt/new-pvc/predictions")


@dataclass
class PredictConfig:
    """Generate test set predictions from a trained checkpoint."""
    checkpoint: str                # path to best model checkpoint
    test_inputs: str = "/mnt/new-pvc/datasets/tandemfoil/test_inputs.pt"
    stats_file: str = "data/split_stats.json"
    agent: str | None = None       # kaggler name — used for output path
    batch_size: int = 4


cfg = sp.parse(PredictConfig)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Device: {device}")

# Derive output path: /mnt/new-pvc/predictions/<agent>/<run_id>/predictions.pt
checkpoint_dir = Path(cfg.checkpoint).parent
run_id = checkpoint_dir.name  # e.g. "model-abc123"
agent_name = cfg.agent or "unknown"
output_dir = PREDICTIONS_DIR / agent_name / run_id
output_dir.mkdir(parents=True, exist_ok=True)
output_path = output_dir / "predictions.pt"
config_path = checkpoint_dir / "config.yaml"
with open(config_path) as f:
    model_config = yaml.safe_load(f)

# Import model class from train.py
from train import Transolver
model = Transolver(**model_config).to(device)
model.load_state_dict(torch.load(cfg.checkpoint, map_location=device, weights_only=True))
model.eval()
print(f"Loaded model from {cfg.checkpoint}")

# Load normalization stats
with open(cfg.stats_file) as f:
    stats_data = json.load(f)
x_mean = torch.tensor(stats_data["x_mean"], dtype=torch.float32, device=device)
x_std = torch.tensor(stats_data["x_std"], dtype=torch.float32, device=device)
y_mean = torch.tensor(stats_data["y_mean"], dtype=torch.float32, device=device)
y_std = torch.tensor(stats_data["y_std"], dtype=torch.float32, device=device)

# Load test inputs
test_inputs = torch.load(cfg.test_inputs, map_location="cpu", weights_only=True)
print(f"Loaded {len(test_inputs)} test samples from {cfg.test_inputs}")

# Run inference
predictions = []
with torch.no_grad():
    for i in tqdm(range(0, len(test_inputs), cfg.batch_size), desc="Predicting"):
        batch = test_inputs[i:i + cfg.batch_size]
        xs = [sample["x"] for sample in batch]

        # Pad to same length within batch
        max_n = max(x.shape[0] for x in xs)
        B = len(xs)
        x_pad = torch.zeros(B, max_n, X_DIM, device=device)
        mask = torch.zeros(B, max_n, dtype=torch.bool, device=device)
        for j, x in enumerate(xs):
            n = x.shape[0]
            x_pad[j, :n] = x.to(device)
            mask[j, :n] = True

        # Normalize inputs
        x_norm = (x_pad - x_mean) / x_std

        # Forward
        pred_norm = model({"x": x_norm})["preds"]

        # Denormalize to physical units
        pred = pred_norm * y_std + y_mean

        # Extract per-sample predictions (unpadded)
        for j, x in enumerate(xs):
            n = x.shape[0]
            predictions.append(pred[j, :n].cpu())

torch.save(predictions, output_path)
print(f"Saved {len(predictions)} predictions to {output_path}")
