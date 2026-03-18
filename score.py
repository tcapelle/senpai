# SPDX-FileCopyrightText: 2026 CoreWeave, Inc.
# SPDX-License-Identifier: Apache-2.0
# SPDX-PackageName: senpai

"""Score kaggler predictions against hidden ground truth.

Organizer-only script. Computes per-domain and overall MAE for surface
and volume nodes across all test samples.

Run:
  python score.py --predictions predictions.pt
"""

from dataclasses import dataclass

import simple_parsing as sp
import torch


@dataclass
class ScoreConfig:
    """Score predictions against hidden test ground truth."""
    predictions: str                 # path to kaggler's predictions.pt
    ground_truth: str = "/mnt/new-pvc/datasets/tandemfoil/.test_gt/test_ground_truth.pt"
    output_format: str = "markdown"  # "markdown" or "json"


cfg = sp.parse(ScoreConfig)

# Load data
preds = torch.load(cfg.predictions, map_location="cpu", weights_only=True)
gt = torch.load(cfg.ground_truth, map_location="cpu", weights_only=False)

assert len(preds) == len(gt), f"Prediction count {len(preds)} != ground truth count {len(gt)}"

# Accumulate per-domain metrics
CHANNELS = ["Ux", "Uy", "p"]
domains: dict[str, dict] = {}

for i in range(len(preds)):
    pred_y = preds[i]
    gt_entry = gt[i]
    true_y = gt_entry["y"]
    is_surface = gt_entry["is_surface"]
    domain = gt_entry["domain"]

    assert pred_y.shape == true_y.shape, (
        f"Sample {i}: shape mismatch {pred_y.shape} vs {true_y.shape}"
    )

    err = (pred_y - true_y).abs()
    surf_mask = is_surface
    vol_mask = ~is_surface

    if domain not in domains:
        domains[domain] = {
            "mae_surf": torch.zeros(3), "n_surf": 0,
            "mae_vol": torch.zeros(3), "n_vol": 0,
        }
    d = domains[domain]
    d["mae_surf"] += (err * surf_mask.unsqueeze(-1)).sum(dim=0)
    d["n_surf"] += surf_mask.sum().item()
    d["mae_vol"] += (err * vol_mask.unsqueeze(-1)).sum(dim=0)
    d["n_vol"] += vol_mask.sum().item()

# Compute final MAEs
results = {}
for domain, d in domains.items():
    results[domain] = {
        "mae_surf": (d["mae_surf"] / max(d["n_surf"], 1)).tolist(),
        "mae_vol": (d["mae_vol"] / max(d["n_vol"], 1)).tolist(),
    }

# Compute overall
total_surf = torch.zeros(3)
total_vol = torch.zeros(3)
total_n_surf = 0
total_n_vol = 0
for d in domains.values():
    total_surf += d["mae_surf"]
    total_n_surf += d["n_surf"]
    total_vol += d["mae_vol"]
    total_n_vol += d["n_vol"]
results["OVERALL"] = {
    "mae_surf": (total_surf / max(total_n_surf, 1)).tolist(),
    "mae_vol": (total_vol / max(total_n_vol, 1)).tolist(),
}

# Output
if cfg.output_format == "json":
    import json
    print(json.dumps(results, indent=2))
else:
    # Markdown table
    domain_order = ["single", "tandem_known", "tandem_transfer", "cruise_known", "cruise_ood_re", "OVERALL"]
    ordered = [d for d in domain_order if d in results]

    header = "| Domain | mae_surf_p | mae_surf_Ux | mae_surf_Uy | mae_vol_p | mae_vol_Ux | mae_vol_Uy |"
    sep = "|--------|-----------|-------------|-------------|----------|-----------|-----------|"
    print(header)
    print(sep)
    for domain in ordered:
        r = results[domain]
        s = r["mae_surf"]
        v = r["mae_vol"]
        name = f"**{domain}**" if domain == "OVERALL" else domain
        print(f"| {name} | {s[2]:.2f} | {s[0]:.2f} | {s[1]:.2f} | {v[2]:.2f} | {v[0]:.2f} | {v[1]:.2f} |")
