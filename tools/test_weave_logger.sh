#!/bin/bash
# SPDX-FileCopyrightText: 2026 CoreWeave, Inc.
# SPDX-License-Identifier: Apache-2.0
# SPDX-PackageName: senpai
#
# Smoke test for the weave_logger daemon launched by entrypoint-advisor.sh.
# Run inside a devpod / pod that has uv and python available.
#
# Usage: bash tools/test_weave_logger.sh
# Expected: all checks print PASS, exit 0

set -euo pipefail

WORKDIR="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

ok()   { echo "  PASS  $*"; PASS=$((PASS+1)); }
fail() { echo "  FAIL  $*"; FAIL=$((FAIL+1)); }

echo "=== weave_logger smoke test ==="
echo "WORKDIR: $WORKDIR"
echo ""

# ── 1. weave in pyproject.toml ────────────────────────────────────────────────
echo "[ 1 ] weave listed in pyproject.toml"
if grep -q '"weave"' "$WORKDIR/pyproject.toml"; then
    ok "weave found in pyproject.toml"
else
    fail "weave NOT found in pyproject.toml"
fi

# ── 2. uv install picks up weave ─────────────────────────────────────────────
echo "[ 2 ] uv pip install -e . installs weave"
cd "$WORKDIR"
uv pip install --system -e . -q 2>&1 | tail -3
if python3 -c "import weave" 2>/dev/null; then
    ok "import weave succeeded"
else
    fail "import weave FAILED after uv install"
fi

# ── 3. script is importable / arg-parseable ───────────────────────────────────
echo "[ 3 ] weave_logger.py --help exits cleanly"
if python3 tools/weave_logger.py --help > /dev/null 2>&1; then
    ok "--help exit 0"
else
    fail "--help exited non-zero"
fi

# ── 4. daemon starts and logs turns from a real session file ─────────────────
echo "[ 4 ] daemon starts, connects to Weave, logs at least one turn"

# Requires WANDB_API_KEY in environment (set as k8s secret on real pods).
if [ -z "${WANDB_API_KEY:-}" ]; then
    echo "       WANDB_API_KEY not set — skipping live Weave test"
    ok "skipped (no credentials)"
else
    LOGFILE=$(mktemp /tmp/weave_logger_test_XXXX.log)
    # Point at the project's own session files if they exist, else make a
    # synthetic one-line JSONL that contains a completed turn.
    PROJECT_DIR="$HOME/.claude/projects/$(echo "$WORKDIR" | sed 's|/|-|g')"

    if [ ! -d "$PROJECT_DIR" ]; then
        echo "       No session dir at $PROJECT_DIR — creating synthetic fixture"
        PROJECT_DIR=$(mktemp -d /tmp/weave_test_sessions_XXXX)
        SESSION_ID="test-session-$(date +%s)"
        FIXTURE="$PROJECT_DIR/${SESSION_ID}.jsonl"
        cat > "$FIXTURE" <<JSONL
{"type":"user","uuid":"aaaa-0001","parentUuid":null,"promptId":"p1","message":{"role":"user","content":"hello from test"},"sessionId":"${SESSION_ID}","timestamp":"2026-01-01T00:00:00Z","gitBranch":"weave-thread-logger"}
{"type":"assistant","uuid":"aaaa-0002","parentUuid":"aaaa-0001","message":{"model":"claude-sonnet-4-6","role":"assistant","content":[{"type":"text","text":"hi, I am the test assistant"}],"stop_reason":"end_turn","usage":{"input_tokens":10,"output_tokens":5}},"sessionId":"${SESSION_ID}","timestamp":"2026-01-01T00:00:01Z","gitBranch":"weave-thread-logger"}
JSONL
    fi

    python3 "$WORKDIR/tools/weave_logger.py" \
        --role advisor \
        --agent-name advisor-test \
        --project-dir "$PROJECT_DIR" \
        > "$LOGFILE" 2>&1 &
    DAEMON_PID=$!

    # Give it up to 15s to connect and log at least one turn
    for i in $(seq 1 15); do
        sleep 1
        if grep -q "turn logged" "$LOGFILE" 2>/dev/null; then
            break
        fi
    done

    kill "$DAEMON_PID" 2>/dev/null; wait "$DAEMON_PID" 2>/dev/null || true

    if grep -q "Logged in as Weights & Biases user" "$LOGFILE"; then
        ok "connected to Weave"
    else
        fail "did not connect to Weave (check WANDB_API_KEY / network)"
        echo "--- daemon log ---"
        cat "$LOGFILE"
        echo "------------------"
    fi

    if grep -q "turn logged" "$LOGFILE"; then
        TURNS=$(grep -c "turn logged" "$LOGFILE" || true)
        ok "logged ${TURNS} turn(s)"
    else
        fail "no turns logged"
        echo "--- daemon log ---"
        cat "$LOGFILE"
        echo "------------------"
    fi

    rm -f "$LOGFILE"
fi

# ── 5. entrypoint launches daemon before the loop ────────────────────────────
echo "[ 5 ] entrypoint-advisor.sh contains daemon launch line"
if grep -q "weave_logger.py.*--role advisor" "$WORKDIR/k8s/entrypoint-advisor.sh"; then
    ok "daemon launch found in entrypoint-advisor.sh"
else
    fail "daemon launch NOT found in entrypoint-advisor.sh"
fi

echo "[ 5b ] entrypoint-student.sh contains daemon launch line"
if grep -q "weave_logger.py.*--role student" "$WORKDIR/k8s/entrypoint-student.sh"; then
    ok "daemon launch found in entrypoint-student.sh"
else
    fail "daemon launch NOT found in entrypoint-student.sh"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed ==="
[ "$FAIL" -eq 0 ]
