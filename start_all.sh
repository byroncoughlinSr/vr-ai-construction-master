#!/bin/bash
# Start pm-mcp (:8765, the construction plan), backend (uvicorn :8000) and
# dashboard (Vite :3001) together. Ctrl+C stops what this script started.

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT/backend-core/backend"
DASHBOARD_DIR="$ROOT/backend-core/dashboard"
BACKEND_LOG="$BACKEND_DIR/backend.log"
# pm-mcp holds phases, tasks, permits, inspections, budget lines and change
# orders. The default board is the one Claude Code and OpenWork use too.
PM_MCP_BIN="${PM_MCP_BIN:-/development/pm-mcp/.venv/bin/pm-mcp}"
PM_MCP_DB="${PM_MCP_DB:-$HOME/.local/share/pm-mcp/pm.db}"
PM_MCP_PORT="${PM_MCP_PORT:-8765}"
PM_MCP_LOG="$BACKEND_DIR/pm-mcp.log"

cleanup() {
    trap - EXIT INT TERM
    echo ""
    echo "🛑 Stopping..."
    [ -n "$DASH_PID" ] && kill "$DASH_PID" 2>/dev/null
    [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
    [ -n "$PM_PID" ] && kill "$PM_PID" 2>/dev/null
    wait "$DASH_PID" "$BACKEND_PID" $PM_PID 2>/dev/null
    echo "   ✓ Stopped backend and dashboard${PM_PID:+ and pm-mcp}"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

if [ ! -x "$BACKEND_DIR/venv/bin/python" ]; then
    echo "❌ No venv at $BACKEND_DIR/venv (create it with python3.12 -m venv venv)"
    exit 1
fi
if [ ! -d "$DASHBOARD_DIR/node_modules" ]; then
    echo "📦 Installing dashboard dependencies..."
    (cd "$DASHBOARD_DIR" && npm install) || exit 1
fi

echo "1. Clearing ports 8000 and 3001..."
pkill -f "uvicorn app.main" 2>/dev/null
for port in 8000 3001; do
    pids=$(lsof -ti:"$port" 2>/dev/null)
    [ -n "$pids" ] && kill $pids 2>/dev/null
done
sleep 1

# Anything still listening (e.g. the vr_backend_dev Docker container from
# docker compose) can't be killed from here; uvicorn would fail to bind.
for port in 8000 3001; do
    if ss -ltn "sport = :$port" | grep -q LISTEN; then
        echo "❌ Port $port is still in use:"
        docker ps --filter "publish=$port" --format '   docker container: {{.Names}}' 2>/dev/null
        echo "   Free it (e.g. docker stop vr_backend_dev) and re-run."
        exit 1
    fi
done

echo "2. Starting pm-mcp on :$PM_MCP_PORT..."
if ss -ltn "sport = :$PM_MCP_PORT" | grep -q LISTEN; then
    echo "   ✓ Already running; using it"
elif [ -x "$PM_MCP_BIN" ]; then
    "$PM_MCP_BIN" --transport streamable-http --port "$PM_MCP_PORT" --db "$PM_MCP_DB" >"$PM_MCP_LOG" 2>&1 &
    PM_PID=$!
    for _ in $(seq 1 30); do
        ss -ltn "sport = :$PM_MCP_PORT" | grep -q LISTEN && break
        sleep 0.5
    done
    if ss -ltn "sport = :$PM_MCP_PORT" | grep -q LISTEN; then
        echo "   ✓ pm-mcp up on http://127.0.0.1:$PM_MCP_PORT/mcp (board: $PM_MCP_DB, log: $PM_MCP_LOG)"
    else
        echo "⚠️  pm-mcp did not start (see $PM_MCP_LOG); the schedule, budget and permits pages need it"
    fi
else
    echo "⚠️  pm-mcp not found at $PM_MCP_BIN; the schedule, budget and permits pages need it"
fi

echo "3. Starting backend (log: $BACKEND_LOG)..."
cd "$BACKEND_DIR" || exit 1
venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

# Model loading can take a while; wait up to 120s for the port to open.
for _ in $(seq 1 120); do
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "❌ Backend exited during startup. Last log lines:"
        tail -20 "$BACKEND_LOG"
        exit 1
    fi
    curl -s -o /dev/null http://localhost:8000/docs && break
    sleep 1
done
echo "   ✓ Backend up on http://0.0.0.0:8000 (docs: /docs)"

echo "4. Starting dashboard..."
cd "$DASHBOARD_DIR" || exit 1
npm run dev &
DASH_PID=$!

echo ""
echo "✅ Running — backend log: tail -f $BACKEND_LOG"
echo "   Press Ctrl+C to stop both"

# Exit (and clean up) as soon as either process dies.
wait -n "$BACKEND_PID" "$DASH_PID"
