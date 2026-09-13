#!/usr/bin/env bash
# End-to-end GrammarGuard demo: model server on :8000, admission proxy on :8080, client run.
#
#   ./run_demo.sh                 # full run
#   ./run_demo.sh --only a,b,g    # extra args go to client.py
#
# Environment: SERVER_PORT, PROXY_PORT, VENV (defaults to ../../../.venv relative to this
# file), PYTHON (defaults to "python" from the activated venv), DEVICE (auto|mps|cpu).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
VENV="${VENV:-$REPO/../.venv}"
SERVER_PORT="${SERVER_PORT:-8000}"
PROXY_PORT="${PROXY_PORT:-8080}"
DEVICE="${DEVICE:-auto}"
LOGS="$HERE/logs"
mkdir -p "$LOGS"

if [ -f "$VENV/bin/activate" ]; then
  # shellcheck disable=SC1090
  source "$VENV/bin/activate"
fi
PYTHON="${PYTHON:-python}"

SERVER_PID=""
PROXY_PID=""
cleanup() {
  local status=$?
  trap - EXIT INT TERM
  echo
  echo "[run_demo] shutting down"
  for pid in "$PROXY_PID" "$SERVER_PID"; do
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  for pid in "$PROXY_PID" "$SERVER_PID"; do
    [ -n "$pid" ] && wait "$pid" 2>/dev/null || true
  done
  echo "[run_demo] logs: $LOGS/server.log $LOGS/proxy.log $LOGS/client.log"
  exit "$status"
}
trap cleanup EXIT INT TERM

port_in_use() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

wait_for() {  # wait_for URL SECONDS NAME PID
  local url="$1" deadline=$(( $(date +%s) + $2 )) name="$3" pid="$4"
  until curl -sf "$url" >/dev/null 2>&1; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "[run_demo] $name exited before becoming ready; see $LOGS/$name.log" >&2
      return 1
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      echo "[run_demo] timed out waiting for $name at $url" >&2
      return 1
    fi
    sleep 0.5
  done
  echo "[run_demo] $name ready at $url"
}

for port in "$SERVER_PORT" "$PROXY_PORT"; do
  if port_in_use "$port"; then
    echo "[run_demo] port $port is already in use; set SERVER_PORT/PROXY_PORT" >&2
    exit 1
  fi
done

echo "[run_demo] starting model server on :$SERVER_PORT (device=$DEVICE) -> $LOGS/server.log"
"$PYTHON" "$HERE/server.py" --host 127.0.0.1 --port "$SERVER_PORT" --device "$DEVICE" >"$LOGS/server.log" 2>&1 &
SERVER_PID=$!
wait_for "http://127.0.0.1:$SERVER_PORT/health" 300 server "$SERVER_PID"

echo "[run_demo] starting grammar-guard proxy on :$PROXY_PORT -> $LOGS/proxy.log"
"$PYTHON" -m formatron.proxy --upstream "http://127.0.0.1:$SERVER_PORT" --host 127.0.0.1 --port "$PROXY_PORT" \
  >"$LOGS/proxy.log" 2>&1 &
PROXY_PID=$!
wait_for "http://127.0.0.1:$PROXY_PORT/grammar-guard/health" 60 proxy "$PROXY_PID"

echo "[run_demo] running client -> $LOGS/client.log"
echo
"$PYTHON" "$HERE/client.py" --base-url "http://127.0.0.1:$PROXY_PORT" "$@" | tee "$LOGS/client.log"
