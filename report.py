#!/usr/bin/env python3
"""xahau-hook-report — a one-command SAFETY REPORT CARD for a Xahau Hook.

Runs the xahc-prover invariant battery over a compiled Hook (.wasm) via the public `xahc prove`
CLI and prints an honest, per-invariant scorecard (+ JSON for the Proof Registry / CI).

Each row is one invariant that xahc-prover settles FOR ALL INPUTS (symbolic execution + Z3):
  ✓ PROVEN        — holds for every input, under that invariant's stated scope
  ✗ COUNTEREXAMPLE— a concrete input violates it (re-run the prover to see it)
  ? INCONCLUSIVE  — the prover fails closed and could not decide (NOT a pass)
  — N/A           — the hook does not exercise this property (NOT a pass)

THE HONESTY RULES (this tool lives or dies by them):
  - PROVEN means proven FOR THAT INVARIANT under its scope — NOT "safe" in general.
  - A COUNTEREXAMPLE means the property does NOT hold. Whether that's a BUG depends on whether the
    property was INTENDED for this hook (e.g. `authz` failing on a public payment guardrail is by
    design). The card reports verdicts; YOU map them to intent.
  - N/A and INCONCLUSIVE are NOT passes.
  - Every row is independently re-verifiable: re-run `xahc prove <hook> --invariant <name>`.

Usage:
  report.py <hook.wasm>            full report card
  report.py <hook.wasm> --json     machine-readable (Proof Registry / CI input)
  report.py <hook.wasm> --invariant <name>   run a single invariant
  report.py --list                 list the battery

Exit: 0 = no counterexamples · 2 = at least one counterexample · 3 = setup/usage error.

Env: XAHC (xahc binary, default ~/Desktop/xahc/target/release/xahc)
     XAHC_PROVER_DIR (default ~/Desktop/xahc-prover)
"""
import json
import os
import subprocess
import sys

XAHC = os.environ.get("XAHC", os.path.expanduser("~/Desktop/xahc/target/release/xahc"))
PROVER_DIR = os.environ.get("XAHC_PROVER_DIR", os.path.expanduser("~/Desktop/xahc-prover"))

# The argless battery — invariants that give a meaningful all-inputs verdict without a hook-specific
# CLI argument. (Param-targeted runs like `validate <KEY>` or `monotonic --field SLOT:OFF:LEN` are
# deeper follow-ups, not part of the generic card.)
BATTERY = [
    ("limit", "per-tx native spend <= LIM"),
    ("guardrail", "agent-guardrail: per-tx spend cap + destination allowlist"),
    ("limit-iou", "per-tx IOU/issued spend <= LIM"),
    ("period-budget", "stateful spend budget over a period stays <= PLM"),
    ("authz", "only the owner can trigger it (SC01)"),
    ("termination", "no guard-violation (tecHOOK_REJECTED) for any input"),
    ("monotonic", "persisted state never moves backwards (replay/rollback)"),
    ("nospend", "bounded emits (no double-spend)"),
    ("conservation", "emits <= received (no value creation)"),
    ("reserve", "stays above account reserve after emits + fees"),
    ("overflow", "no uint64 wrap bypasses a limit check (SC07/09)"),
    ("foreign-authz", "every foreign-state write is grant-authorized"),
    ("time-nonce", "no accept decision hinges on the grindable ledger nonce (SC03)"),
    ("unchecked-return", "every failable state_set/emit return is checked (SC06)"),
    ("emission", "emit count <= etxn_reserve (static)"),
    ("reentrancy", "cbak re-entry is reserve-before-emit safe (SC05)"),
    ("resource-conservation", "an in-world resource slot is not inflated"),
    ("commitment", "a committed root == hash(state) (commitment integrity)"),
    ("preview-faithfulness", "a wallet's pre-sign preview matches execution (decision+state; v1)"),
    ("cron", "re-arms <= 1 CronSet per invocation (no cron stacking)"),
    ("partial-payment", "accept => not a tfPartialPayment (no dust delivered_amount trick)"),
    ("constant-product", "AMM no-drain: accept => newRX*newRY >= oldRX*oldRY (native-product regime)"),
    ("native-amount", "accept => incoming sfAmount is native XAH (byte0 0x80 clear; no IOU-misread-as-drops)"),
    ("emit-budget", "accept => cumulative EMITTED spend <= CAP (autonomous outgoing-spend bound; Cron primitives)"),
    ("emit-dst-lock", "accept => every emitted Payment goes only to the locked payee PAY (autonomous payee lock)"),
    ("trigger-lock", "accept-with-emit => otxn_type==ttCRON (autonomous Hook fires only on its own cron, not any tx)"),
    ("time-release", "accept-with-emit => ledger_last_time >= CLF (vesting/scheduled release: nothing before the cliff)"),
]
VERDICT = {0: ("PROVEN", "✓"), 1: ("N/A", "—"), 2: ("COUNTEREXAMPLE", "✗"), 3: ("INCONCLUSIVE", "?")}


def preflight():
    """Return None if the toolchain is usable, else an error string."""
    if not (os.path.isfile(XAHC) and os.access(XAHC, os.X_OK)):
        return (f"xahc binary not found/executable at {XAHC}.\n"
                "  Set XAHC=/path/to/xahc, or build it: cd <xahc repo> && cargo build --release.")
    if not os.path.isdir(PROVER_DIR):
        return (f"xahc-prover not found at {PROVER_DIR}.\n"
                "  Set XAHC_PROVER_DIR=/path/to/xahc-prover (the prover this CLI shells to).")
    try:
        subprocess.run([XAHC, "--version"], capture_output=True, timeout=30)
    except Exception as e:  # noqa: BLE001
        return f"could not run `{XAHC} --version`: {e}"
    return None


def run_one(wasm, inv):
    env = dict(os.environ, XAHC_PROVER_DIR=PROVER_DIR)
    try:
        p = subprocess.run([XAHC, "prove", wasm, "--invariant", inv],
                           capture_output=True, text=True, env=env, timeout=600)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        return {"invariant": inv, "exit": -1, "verdict": "TIMEOUT", "mark": "!"}
    except Exception as e:  # noqa: BLE001 — surface as a row, never a silent pass
        return {"invariant": inv, "exit": -1, "verdict": "ERROR", "mark": "!", "detail": str(e)[:120]}
    name, mark = VERDICT.get(rc, (f"EXIT_{rc}", "!"))
    return {"invariant": inv, "exit": rc, "verdict": name, "mark": mark}


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    if argv[0] == "--list":
        for inv, d in BATTERY:
            print(f"  {inv:<22} {d}")
        return 0

    wasm = argv[0]
    as_json = "--json" in argv[1:]
    only = None
    if "--invariant" in argv:
        only = argv[argv.index("--invariant") + 1]

    err = preflight()
    if err:
        print(f"SETUP ERROR: {err}", file=sys.stderr); return 3
    if not os.path.isfile(wasm):
        print(f"ERROR: no such hook wasm: {wasm}", file=sys.stderr); return 3

    battery = [(only, dict(BATTERY).get(only, ""))] if only else BATTERY
    desc = dict(BATTERY)
    rows = [run_one(wasm, inv) for inv, _ in battery]
    cex = [r for r in rows if r["exit"] == 2]
    proven = [r for r in rows if r["exit"] == 0]
    inconcl = [r for r in rows if r["exit"] == 3]

    if as_json:
        print(json.dumps({"hook": os.path.basename(wasm), "results": rows,
                          "summary": {"proven": len(proven), "counterexamples": len(cex),
                                       "inconclusive": len(inconcl), "total": len(rows)}}, indent=2))
        return 2 if cex else 0

    print(f"\n  XAHAU HOOK SAFETY REPORT CARD — {os.path.basename(wasm)}")
    print("  ✓ PROVEN for-all-inputs · ✗ COUNTEREXAMPLE · ? INCONCLUSIVE (not a pass) · — N/A (not exercised)\n")
    for r in rows:
        print(f"   {r['mark']}  {r['invariant']:<22} {r['verdict']:<14} {desc.get(r['invariant'],'')}")
    na = len(rows) - len(proven) - len(cex) - len(inconcl)
    print(f"\n  {len(proven)} proven · {len(cex)} counterexample · {len(inconcl)} inconclusive · {na} n/a")
    if cex:
        print(f"  ⚠  {len(cex)} property(ies) do NOT hold — re-run e.g. "
              f"`xahc prove {os.path.basename(wasm)} --invariant {cex[0]['invariant']}` to see the "
              "failing input. (A failing property may be BY DESIGN — judge against the hook's intent.)")
    print("\n  A PROVEN row means proven for THAT property under its scope — not a blanket 'safe'. "
          "Verify any row yourself by re-running the prover.\n")
    return 2 if cex else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
