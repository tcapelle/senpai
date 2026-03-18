#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 CoreWeave, Inc.
# SPDX-License-Identifier: Apache-2.0
# SPDX-PackageName: senpai

"""Launch senpai organizer and kaggler agents as K8s resources."""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import simple_parsing as sp

KAGGLER_TEMPLATE = Path(__file__).parent / "kaggler-deployment.yaml"
ORGANIZER_TEMPLATE = Path(__file__).parent / "organizer-deployment.yaml"

KAGGLER_NAMES = [
    "frieren", "fern", "tanjiro", "nezuko", "alphonse", "edward",
    "thorfinn", "askeladd", "violet", "gilbert", "senku", "kohaku",
    "emma", "norman", "chihiro", "haku", "shoya", "shouko",
    "mitsuha", "taki", "shinji", "rei", "kaneda", "tetsuo",
]


@dataclass
class Args:
    """Launch senpai organizer and/or kaggler agents on Kubernetes."""
    tag: str  # research tag (e.g. mar13)
    names: str = ""  # comma-separated kaggler names (e.g. "frieren,fern")
    n_kagglers: int = 4  # number of kagglers to launch (ignored if --names is provided)
    repo_url: str = "https://github.com/wandb/senpai.git"  # git repo URL
    repo_branch: str = "main"  # git branch to clone
    image: str = "ghcr.io/tcapelle/dev_box:latest"  # container image for kagglers
    wandb_entity: str = "wandb-applied-ai-team"  # W&B entity (team or username)
    wandb_project: str = "senpai-v1"  # W&B project name
    organizer_branch: str = "jurgen"  # branch the organizer works on (PRs target this, not main)
    organizer: bool = False  # also deploy the organizer pod (default: kagglers only)
    dry_run: bool = False  # print manifests without applying


def render_template(template: str, replacements: dict[str, str]) -> str:
    """Replace {{PLACEHOLDER}} tokens in a K8s manifest template."""
    out = template
    for key, value in replacements.items():
        out = out.replace(f"{{{{{key}}}}}", value)
    return out


def render_configmap(name: str, labels: dict[str, str], data: dict[str, str]) -> str:
    """Generate a ConfigMap YAML document."""
    lines = ["apiVersion: v1", "kind: ConfigMap", "metadata:", f"  name: {name}", "  labels:"]
    for k, v in labels.items():
        lines.append(f"    {k}: {v}")
    lines.append("data:")
    for k, v in data.items():
        lines.append(f"  {k}: \"{v}\"")
    return "\n".join(lines)


def render_kaggler(template: str, kaggler_name: str, tag: str, args: Args) -> str:
    configmap = render_configmap(
        name=f"senpai-config-kaggler-{kaggler_name}",
        labels={"app": "senpai", "role": "kaggler", "research-tag": tag},
        data={
            "REPO_URL": args.repo_url,
            "REPO_BRANCH": args.repo_branch,
            "KAGGLER_NAME": kaggler_name,
            "RESEARCH_TAG": tag,
            "WANDB_ENTITY": args.wandb_entity,
            "WANDB_PROJECT": args.wandb_project,
            "ORGANIZER_BRANCH": args.organizer_branch,
            "WANDB_MODE": "online",
        },
    )
    deployment = render_template(template, {
        "KAGGLER_NAME": kaggler_name,
        "RESEARCH_TAG": tag,
        "IMAGE": args.image,
        "ORGANIZER_BRANCH": args.organizer_branch,
    })
    return configmap + "\n---\n" + deployment


def render_organizer(template: str, tag: str, kaggler_list: list[str], args: Args) -> str:
    configmap = render_configmap(
        name="senpai-config-organizer",
        labels={"app": "senpai", "role": "organizer", "research-tag": tag},
        data={
            "REPO_URL": args.repo_url,
            "REPO_BRANCH": args.repo_branch,
            "RESEARCH_TAG": tag,
            "KAGGLER_NAMES": ",".join(kaggler_list),
            "WANDB_ENTITY": args.wandb_entity,
            "WANDB_PROJECT": args.wandb_project,
            "ORGANIZER_BRANCH": args.organizer_branch,
        },
    )
    deployment = render_template(template, {"RESEARCH_TAG": tag})
    return configmap + "\n---\n" + deployment


def kubectl_apply(manifest: str, name: str):
    """Apply a manifest via kubectl."""
    print(f"Launching: {name}")
    result = subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=manifest,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr.strip()}", file=sys.stderr)
    else:
        print(f"  {result.stdout.strip()}")


def main():
    args = sp.parse(Args)

    # Resolve kaggler list
    if args.names:
        kaggler_list = [n.strip() for n in args.names.split(",")]
    else:
        if args.n_kagglers > len(KAGGLER_NAMES):
            print(f"ERROR: max {len(KAGGLER_NAMES)} kagglers (got {args.n_kagglers})", file=sys.stderr)
            sys.exit(1)
        kaggler_list = KAGGLER_NAMES[:args.n_kagglers]

    kaggler_template = KAGGLER_TEMPLATE.read_text()
    organizer_template = ORGANIZER_TEMPLATE.read_text()

    # --- Deploy kagglers ---
    for name in kaggler_list:
        manifest = render_kaggler(kaggler_template, name, args.tag, args)
        if args.dry_run:
            print(f"--- Kaggler: {name} ---")
            print(manifest)
            print()
        else:
            kubectl_apply(manifest, f"kaggler {name}")

    # --- Deploy organizer ---
    if args.organizer:
        manifest = render_organizer(organizer_template, args.tag, kaggler_list, args)
        if args.dry_run:
            print("--- Organizer ---")
            print(manifest)
            print()
        else:
            kubectl_apply(manifest, "organizer")

    if not args.dry_run:
        print(f"\nLaunched {len(kaggler_list)} kagglers: {', '.join(kaggler_list)}")
        if args.organizer:
            print("Launched organizer pod")
        print(f"\nMonitor:")
        print(f"  kubectl get deployments -l research-tag={args.tag}")
        print(f"  kubectl get deployment senpai-organizer")
        print(f"  kubectl logs -f deployment/senpai-{kaggler_list[0]}")
        print(f"\nStop:")
        print(f"  kubectl delete deployments,configmaps -l research-tag={args.tag}")


if __name__ == "__main__":
    main()
