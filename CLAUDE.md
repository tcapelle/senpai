<!--
SPDX-FileCopyrightText: 2026 CoreWeave, Inc.
SPDX-License-Identifier: Apache-2.0
SPDX-PackageName: senpai
-->

# senpai — Development Context

Autonomous ML research on CFD surrogates, coordinated through GitHub PRs with an advisor/student model.

## Key docs

- `program.md` — research context, goals, metrics, file constraints
- `advisor.md` — advisor role workflow
- `student.md` — student role workflow

## Architecture

- **Advisor pod** — no GPU, runs Claude Code in a loop. Queries W&B, reviews student PRs, generates new hypotheses, and creates draft PRs to assign work.
- **Student pods** — GPU workers, each running Claude Code. Poll for assigned PRs, implement the hypothesis, run training, report results.

## k8s layout

- `k8s/advisor-deployment.yaml` / `k8s/student-deployment.yaml` — pod specs
- `k8s/entrypoint-advisor.sh` / `k8s/entrypoint-student.sh` — startup scripts
- `k8s/launch.py` — helper to template and apply deployments

## instructions/

Role-specific CLAUDE.md files. The Student and Advisor both use Claude Code. At pod launch, the appropriate role-specific file is copied over this CLAUDE.md:
- `instructions/ADVISOR-CLAUDE.md` → advisor pods
- `instructions/STUDENT-CLAUDE.md` → student pods
