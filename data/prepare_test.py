# SPDX-FileCopyrightText: 2026 CoreWeave, Inc.
# SPDX-License-Identifier: Apache-2.0
# SPDX-PackageName: senpai

"""One-time offline script: generate test input and ground truth files.

Reads the split manifest (with test indices and test_meta) and produces:
  test_inputs.pt         — shared storage, visible to kagglers (no y values)
  test_ground_truth.pt   — organizer-only (hidden y values + domain tags)

Samples are shuffled with a fixed seed so ordering doesn't reveal source.

Run: python data/prepare_test.py [--quick]
"""

import json
import torch
import numpy as np
from pathlib import Path

from data.prepare import load_pickle
from data.prepare_multi import preprocess_sample_multi

SEED = 123  # different from split seed to avoid correlation
MANIFEST_PATH = Path("data/split_manifest.json")
TEST_INPUTS_DIR = Path("/mnt/new-pvc/datasets/tandemfoil")
TEST_GT_DIR = Path("/mnt/new-pvc/datasets/tandemfoil/.test_gt")


def main():
    import sys
    quick = "--quick" in sys.argv

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    test_indices = manifest["splits"]["test"]
    test_meta = manifest["test_meta"]
    pickle_paths = [Path(p) for p in manifest["pickle_paths"]]

    # Build global_idx → (file_idx, local_idx) mapping
    file_sizes = []
    for p in pickle_paths:
        raw = load_pickle(p)
        file_sizes.append(len(raw))
        del raw

    offsets = []
    acc = 0
    for n in file_sizes:
        offsets.append(acc)
        acc += n

    def global_to_file_local(global_idx):
        for fi in range(len(offsets)):
            end = offsets[fi] + file_sizes[fi]
            if global_idx < end:
                return fi, global_idx - offsets[fi]
        raise ValueError(f"global_idx {global_idx} out of range")

    # Build domain lookup from test_meta
    domain_by_idx = {m["global_idx"]: m["domain"] for m in test_meta}

    # Collect test samples
    print(f"Collecting {len(test_indices)} test samples...")
    entries = []
    for global_idx in test_indices:
        fi, li = global_to_file_local(global_idx)
        entries.append({
            "global_idx": global_idx,
            "file_idx": fi,
            "local_idx": li,
            "domain": domain_by_idx[global_idx],
        })

    # Shuffle with fixed seed
    rng = np.random.default_rng(SEED)
    order = list(range(len(entries)))
    rng.shuffle(order)
    entries = [entries[i] for i in order]

    if quick:
        entries = entries[:4]
        print(f"  [QUICK] Using only {len(entries)} samples")

    # Process samples file-by-file for efficiency
    entries_by_file: dict[int, list] = {}
    for sample_id, entry in enumerate(entries):
        entry["sample_id"] = sample_id
        entries_by_file.setdefault(entry["file_idx"], []).append(entry)

    test_inputs = [None] * len(entries)
    test_gt = [None] * len(entries)

    for fi in sorted(entries_by_file):
        print(f"  Loading file {fi} ({pickle_paths[fi].name})...")
        raw = load_pickle(pickle_paths[fi])
        for entry in entries_by_file[fi]:
            sample = raw[entry["local_idx"]]
            x, y, is_surface = preprocess_sample_multi(sample)
            sid = entry["sample_id"]
            test_inputs[sid] = {"sample_id": sid, "x": x, "is_surface": is_surface}
            test_gt[sid] = {"sample_id": sid, "y": y, "is_surface": is_surface, "domain": entry["domain"]}
        del raw

    # Save
    inputs_path = TEST_INPUTS_DIR / "test_inputs.pt"
    gt_path = TEST_GT_DIR / "test_ground_truth.pt"

    TEST_INPUTS_DIR.mkdir(parents=True, exist_ok=True)
    TEST_GT_DIR.mkdir(parents=True, exist_ok=True)

    torch.save(test_inputs, inputs_path)
    print(f"Wrote {inputs_path} ({len(test_inputs)} samples)")

    torch.save(test_gt, gt_path)
    print(f"Wrote {gt_path} ({len(test_gt)} samples)")

    # Summary
    domains = {}
    for gt in test_gt:
        d = gt["domain"]
        domains[d] = domains.get(d, 0) + 1
    print("\nDomain breakdown:")
    for d, count in sorted(domains.items()):
        print(f"  {d}: {count}")


if __name__ == "__main__":
    main()
