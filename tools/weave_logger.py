#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 CoreWeave, Inc.
# SPDX-License-Identifier: Apache-2.0
# SPDX-PackageName: senpai
"""
Weave thread logger daemon for senpai Claude Code agents.

Polls ~/.claude/projects/<hash>/ every 30s for new session JSONL lines,
reconstructs completed conversation turns, and logs them as Weave Threads.

One Weave Thread per Claude Code sessionId.
One Turn per completed prompt→response cycle (assistant stop_reason=end_turn).

Usage:
    python tools/weave_logger.py --role advisor --agent-name advisor
    python tools/weave_logger.py --role student --agent-name frieren
"""

import argparse
import json
import os
import time
from pathlib import Path

import weave

POLL_INTERVAL = 30  # seconds
STATE_FILE = Path.home() / ".claude" / "weave_logger_state.json"


@weave.op()
def log_agent_turn(messages: list[dict], model: str, usage: dict) -> dict:
    """Single agent turn — inputs/output captured by Weave as a Thread Turn."""
    return {"role": "assistant", "content": messages[-1]["content"]}


# ---------------------------------------------------------------------------
# JSONL parsing helpers
# ---------------------------------------------------------------------------

def extract_text(content) -> str:
    """Extract plain text from a message content field (str or block list)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(p for p in parts if p)
    return ""


def find_human_text(start_uuid: str, all_messages: dict) -> str:
    """
    Walk parentUuid chain upward from start_uuid to find the nearest
    human-authored user message (not a tool_result).
    """
    visited: set[str] = set()
    current = start_uuid
    while current and current not in visited:
        visited.add(current)
        msg = all_messages.get(current)
        if msg is None:
            break
        if msg.get("type") == "user":
            content = msg.get("message", {}).get("content", "")
            # Plain string = actual human prompt
            if isinstance(content, str) and content.strip():
                return content
            # List of blocks — look for text blocks (not tool_result)
            if isinstance(content, list):
                texts = [
                    b.get("text", "")
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                joined = "\n".join(t for t in texts if t)
                if joined:
                    return joined
        current = msg.get("parentUuid")
    return ""


# ---------------------------------------------------------------------------
# Per-session processing
# ---------------------------------------------------------------------------

def process_session_file(
    session_file: Path,
    state: dict,
    agent_name: str,
    role: str,
) -> None:
    """
    Read new lines from a session JSONL, find completed turns, log to Weave.
    State is mutated in-place (caller saves it to disk).
    """
    session_id = session_file.stem
    file_state = state.setdefault(session_id, {"offset": 0, "logged": []})
    logged_set = set(file_state["logged"])

    # How much have we already read?
    prev_offset = file_state["offset"]
    file_size = session_file.stat().st_size
    if file_size <= prev_offset:
        return  # nothing new

    # Read the whole file to build the parentUuid chain (needed for lookups),
    # but only inspect new lines for completed turns.
    all_messages: dict[str, dict] = {}
    new_lines: list[str] = []

    with open(session_file, encoding="utf-8", errors="replace") as f:
        for i, raw in enumerate(f):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if obj.get("type") in ("user", "assistant") and "uuid" in obj:
                all_messages[obj["uuid"]] = obj

        # Re-read just the new bytes for the "what's new" check
        f.seek(prev_offset)
        new_lines = f.readlines()

    file_state["offset"] = file_size

    # Walk new lines looking for completed turns
    for raw in new_lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if obj.get("type") != "assistant":
            continue
        msg = obj.get("message", {})
        if msg.get("stop_reason") != "end_turn":
            continue

        uuid = obj.get("uuid")
        if not uuid or uuid in logged_set:
            continue

        # Extract assistant text
        assistant_text = extract_text(msg.get("content", []))
        if not assistant_text:
            # Pure tool-call turn, no text to log
            logged_set.add(uuid)
            continue

        # Find the human prompt that started this turn
        user_text = find_human_text(obj.get("parentUuid"), all_messages)

        messages = []
        if user_text:
            messages.append({"role": "user", "content": user_text})
        messages.append({"role": "assistant", "content": assistant_text})

        usage_raw = msg.get("usage", {})
        usage = {
            "input_tokens": usage_raw.get("input_tokens", 0)
            + usage_raw.get("cache_read_input_tokens", 0),
            "output_tokens": usage_raw.get("output_tokens", 0),
        }

        attrs = {
            "agent_name": agent_name,
            "role": role,
            "git_branch": obj.get("gitBranch", "unknown"),
            "session_id": session_id,
        }

        with weave.thread(thread_id=session_id):
            with weave.attributes(attrs):
                log_agent_turn(
                    messages=messages,
                    model=msg.get("model", "unknown"),
                    usage=usage,
                )

        logged_set.add(uuid)
        print(
            f"[weave_logger] turn logged  session={session_id[:8]}  uuid={uuid[:8]}"
            f"  tokens={usage['input_tokens']}+{usage['output_tokens']}"
        )

    file_state["logged"] = list(logged_set)


# ---------------------------------------------------------------------------
# Project dir resolution
# ---------------------------------------------------------------------------

def compute_project_dir(workdir: str) -> Path:
    """
    Derive ~/.claude/projects/<hash>/ from the working directory.
    Claude Code computes the hash as the absolute path with / replaced by -.
    e.g. /workspace/senpai -> ~/.claude/projects/-workspace-senpai/
    """
    path_hash = workdir.replace("/", "-")
    return Path.home() / ".claude" / "projects" / path_hash


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> None:
    project_dir = (
        Path(args.project_dir)
        if args.project_dir
        else compute_project_dir(args.workdir)
    )

    entity = args.wandb_entity or os.environ.get("WANDB_ENTITY", "")
    project = args.wandb_project or os.environ.get("WANDB_PROJECT", "")
    if not entity or not project:
        raise SystemExit("[weave_logger] WANDB_ENTITY and WANDB_PROJECT must be set")

    weave.init(f"{entity}/{project}")
    print(
        f"[weave_logger] started\n"
        f"  watching : {project_dir}\n"
        f"  role     : {args.role}\n"
        f"  agent    : {args.agent_name}\n"
        f"  poll     : {POLL_INTERVAL}s\n"
    )

    while True:
        state: dict = {}
        if STATE_FILE.exists():
            try:
                state = json.loads(STATE_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        if project_dir.exists():
            for session_file in sorted(project_dir.glob("*.jsonl")):
                try:
                    process_session_file(session_file, state, args.agent_name, args.role)
                except Exception as exc:
                    print(f"[weave_logger] error on {session_file.name}: {exc}")

        try:
            STATE_FILE.write_text(json.dumps(state, indent=2))
        except OSError as exc:
            print(f"[weave_logger] failed to save state: {exc}")

        time.sleep(POLL_INTERVAL)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Weave thread logger daemon for senpai Claude Code agents"
    )
    p.add_argument("--role", required=True, choices=["advisor", "student"])
    p.add_argument("--agent-name", required=True, help="advisor or student name (e.g. frieren)")
    p.add_argument("--workdir", default="/workspace/senpai", help="Claude Code working directory")
    p.add_argument("--project-dir", default=None, help="Override ~/.claude/projects/<hash>/ path")
    p.add_argument("--wandb-entity", default="", help="W&B entity (falls back to $WANDB_ENTITY)")
    p.add_argument("--wandb-project", default="", help="W&B project (falls back to $WANDB_PROJECT)")
    run(p.parse_args())


if __name__ == "__main__":
    main()
