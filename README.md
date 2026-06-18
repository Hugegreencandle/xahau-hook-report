# xahau-hook-report

A one-command **safety report card** for a Xahau Hook. Runs the [xahc-prover] invariant battery over
a compiled Hook (`.wasm`) and prints an honest, per-invariant scorecard — proven / counterexample /
inconclusive / n-a — plus JSON for the Proof Registry or CI.

```sh
python report.py <hook.wasm>                    # full report card
python report.py <hook.wasm> --json             # machine-readable (registry / CI)
python report.py <hook.wasm> --invariant authz  # run a single invariant
python report.py --list                         # list the battery
```

Each row is one invariant that xahc-prover settles **for all inputs** (symbolic execution + Z3):
`✓ PROVEN` · `✗ COUNTEREXAMPLE` · `? INCONCLUSIVE` · `— N/A`.

### Example
```
  XAHAU HOOK SAFETY REPORT CARD — agent_guardrail.wasm
   ✓  conservation           PROVEN         emits <= received (no value creation)
   ✓  reentrancy             PROVEN         cbak re-entry is reserve-before-emit safe (SC05)
   ✓  preview-faithfulness   PROVEN         a wallet's pre-sign preview matches execution (decision+state)
   ✗  authz                  COUNTEREXAMPLE only the owner can trigger it (SC01)
   ...
  6 proven · 1 counterexample · 1 inconclusive · 7 n/a
```

## Honesty (the whole point)
- **PROVEN** = proven for *that* invariant under *its* scope — **not** a blanket "safe".
- A **COUNTEREXAMPLE** means the property does **not** hold. Whether that's a *bug* depends on whether
  the property was **intended** for this hook — e.g. `authz` failing on a public payment guardrail is
  by design. The card reports verdicts; you map them to intent.
- **N/A** (not exercised) and **INCONCLUSIVE** (prover failed closed) are **not passes**.
- Every row is **independently re-verifiable**: re-run `xahc prove <hook> --invariant <name>` and get
  the same result. This card is a convenience over the prover, not a trust authority.

## Exit codes
`0` no counterexamples · `2` at least one counterexample · `3` setup/usage error.

## Requires
[`xahc`] + [`xahc-prover`] installed. Override locations with `XAHC` (the binary) and
`XAHC_PROVER_DIR` (the prover this CLI shells to); the tool preflights both and explains if missing.

`tests/smoke.sh` runs against `agent_guardrail.wasm` if the toolchain is present (else SKIPs).

This is the PoC of the "verify any hook" funnel in the Xahau **Proof Registry** design; a future
version fetches a deployed hook's wasm from the ledger by account / HookHash.

[xahc-prover]: https://github.com/Hugegreencandle/xahc
[`xahc`]: https://github.com/Hugegreencandle/xahc
[`xahc-prover`]: https://github.com/Hugegreencandle/xahc
