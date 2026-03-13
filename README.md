<!--
SPDX-FileCopyrightText: 2026 CoreWeave, Inc.
SPDX-License-Identifier: Apache-2.0
SPDX-PackageName: senpai
-->

# senpai

Autonomous ML research on CFD surrogates, powered by Claude Code agents coordinated through GitHub PRs.

![val/loss over time](scatter_plot.png)

## How it works

An **advisor** agent (no GPU) creates hypothesis PRs with detailed instructions and assigns them to **student** agents (GPU nodes). Students implement, run experiments, and report results on the PR. The advisor reviews: merge winners, iterate on promising ideas, close dead ends. Coordination uses GitHub labels (`senpai`, `student:<name>`, `status:wip`, `status:review`). W&B tracks metrics.

See `advisor.md`, `student.md`, and `program.md` for the full protocols.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Kubernetes Cluster                         │
│                                                                   │
│  ┌───────────────────┐                                            │
│  │     Advisor Pod    │  No GPU, lightweight                      │
│  │   (Claude Code)    │  Creates hypothesis PRs                   │
│  │                    │  Reviews results, merges/closes            │
│  └────────┬───────────┘                                           │
│           │ GitHub PRs (draft → review → merge/close)             │
│           │                                                       │
│  ┌────────▼───────────────────────────────────────────────────┐   │
│  │           Student Deployments (one per GPU node)            │   │
│  │                                                             │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐                 │   │
│  │  │ frieren  │  │   fern   │  │ tanjiro  │  ...             │   │
│  │  │ 8x GPU   │  │ 8x GPU   │  │ 8x GPU   │                │   │
│  │  └──────────┘  └──────────┘  └──────────┘                 │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
         │                              │
┌────────▼─────────┐          ┌─────────▼─────────┐
│     GitHub        │          │   Weights &        │
│  PRs = hypotheses │          │   Biases            │
│  Labels = routing │          │  Metrics, runs     │
└───────────────────┘          └────────────────────┘
```

### PR lifecycle

```
Advisor creates draft PR ──→ student:frieren + status:wip
        │
        ▼
Student picks up PR, implements, runs experiments
        │
        ▼
Student pushes results ──→ status:review
        │
        ▼
Advisor reviews:
  ├── Merge (squash) ──→ improvement lands on main
  ├── Request changes ──→ status:wip (student iterates)
  └── Close ──→ dead end, branch deleted
```

## Key files

| File | Purpose |
|------|---------|
| `program.md` | Shared context: problem, constraints, metrics |
| `advisor.md` | Advisor protocol: hypotheses, review, merge/close |
| `student.md` | Student protocol: poll, implement, experiment, report |
| `train.py` / `transolver.py` | Training script and model (modifiable by students) |
| `.claude/skills/wandb-primary/` | W&B query skill (advisor + students) |
| `.claude/skills/list-experiments/` | Experiment log skill (advisor only, stripped from students) |

## References

`TandemFoilSet: Datasets for Flow Field Prediction of Tandem-Airfoil Through the Reuse of Single Airfoils` is distributed by CC-BY-4.0.
```bibtex
@inproceedings{
lim2026tandemfoilset,
title={**TandemFoilSet**: Datasets for Flow Field Prediction of Tandem-Airfoil Through the Reuse of Single Airfoils},
author={Wei Xian Lim and Loh Sher En Jessica and Zenong Li and Thant Zin Oo and Wai Lee Chan and Adams Wai-Kin Kong},
booktitle={The Fourteenth International Conference on Learning Representations},
year={2026},
url={https://openreview.net/forum?id=4Z0P4Nbosn}
}
```
