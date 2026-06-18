#!/usr/bin/env bash
# Smoke test — runs only if xahc + xahc-prover are installed (else SKIP, exit 0).
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
XAHC="${XAHC:-$HOME/Desktop/xahc/target/release/xahc}"
PROVER="${XAHC_PROVER_DIR:-$HOME/Desktop/xahc-prover}"
HOOK="$PROVER/hooks/agent_guardrail.wasm"
if [ ! -x "$XAHC" ] || [ ! -d "$PROVER" ] || [ ! -f "$HOOK" ]; then
  echo "SKIP: toolchain not present (set XAHC / XAHC_PROVER_DIR to run the smoke test)"; exit 0
fi
echo "== --list =="; python3 "$ROOT/report.py" --list | head -3
echo "== single invariant (preview-faithfulness on agent_guardrail -> PROVEN, exit 0) =="
python3 "$ROOT/report.py" "$HOOK" --invariant preview-faithfulness >/dev/null; rc=$?
[ "$rc" = "0" ] && echo "ok (exit 0)" || { echo "FAIL exit $rc"; exit 1; }
echo "== json shape =="; python3 "$ROOT/report.py" "$HOOK" --json | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['summary']['total']>=1; print('ok', d['summary'])"
echo "SMOKE PASS"
