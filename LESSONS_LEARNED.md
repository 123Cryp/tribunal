# Tribunal — Lessons Learned (live-verified on GenLayer Studio, Sep 16 2026)

This document records only behaviors that were **live-tested and confirmed
on Studio**, not anything read only in documentation. The goal is that the
next project doesn't have to rediscover these from scratch.

## 1. New, previously undocumented constraint: header comment length

**Finding:** a long comment block (20+ lines) between
`# { "Depends": ... }` and `from genlayer import *` causes schema-loading
to fail completely — `VM_ERROR: invalid_contract`, with **completely
empty** `stdout`/`stderr` (not even a traceback). This was isolated from
the contract's actual logic through careful bisection (many test files
with different combinations) — the exact same logic, with a short header,
always deployed successfully.

**Practical rule:** limit the contract `.py` file to **at most 2 lines** of
header comment:
```
# v0.1.0
# { "Depends": "py-genlayer:<hash>" }
```
Do not put any other comment immediately after that (not even one line).
Put detailed explanations in `DESIGN_DECISIONS.md`/`README.md`, not in the
code file itself.

**Important note:** the first line (`# v0.1.0`) is itself required —
without it, the parser emits a warning `runner comment does not start with
version, using default`, and this sometimes also leads to the same
`invalid_contract` failure.

## 2. Studio behavior: cross-tab/cross-session error leakage

Several times we saw an error message displayed in one tab that actually
belonged to a completely different file/tab (e.g. a traceback for a
`get_last_sentiment` contract that didn't even exist in the project). This
is a real bug on Studio's frontend side, not something fixable from the
code. **Fix:** when an error doesn't match the code you're looking at,
close all other tabs and fully refresh the page before trying again.

## 3. After a page refresh, the connection to a deployed instance is lost

If the Studio page refreshes, the file tab reverts to "Not deployed yet.",
even though the contract still exists on-chain. Quick fix: deploy a **new
instance** (you get a new address, but the old state is untouched since
the old contract isn't deleted, only the UI's link to it is lost). The
Explorer (`explorer-studio.genlayer.com`) is **read-only** (Read Contract);
for Write you must use Studio itself (the Explorer explicitly says "Write
methods require a connected wallet... use GenLayer Studio").

## 4. `gl.eq_principle.prompt_comparative` — the real signature

Documentation (several sources, including a dev.to article) shows `task=`
as a keyword, but the real SDK signature (confirmed both from a live error
and from `sdk.genlayer.com/main/api/genlayer.html`) is:
```python
gl.eq_principle.prompt_comparative(fn, principle: str)  # second arg is positional, named "principle"
```
Calling it with `task=` raises `TypeError: prompt_comparative() got an
unexpected keyword argument 'task'` — this error only appears when that
code path is actually **executed** (not at deploy/schema-check time), so
it stays hidden until that branch actually runs.

By contrast, `gl.eq_principle.prompt_non_comparative(fn, *, task, criteria)`
genuinely does take `task`/`criteria` as keyword-only arguments — this one
was documented correctly and caused no issue.

## 5. Cross-contract calls: confirmed live rules (from initial diagnostics)

- Both `.view()` and `.emit()` must be called **outside** any
  `run_nondet`/`eq_principle` block. Calling them from inside a
  `leader_fn`/`validator_fn` raises `SystemError: 6: forbidden` — a
  VM-level trap, not a Python exception, so it cannot be caught with
  `try/except`.
- `.view()` called outside nondet returns the value directly and usable
  (no `unpack_result` needed).
- `.emit()` (whether with arguments or via `emit_transfer`) is
  **asynchronous**: immediately after `.emit()`, a `.view()` on the same
  contract within the **same transaction** still shows the old value. The
  write does actually happen, but in a separate transaction/round, with a
  delay.

## 6. `gl.message.sender_address` inside a cross-contract call

When contract A calls contract B via `.emit()`, inside B,
`gl.message.sender_address` shows the address of **A**, not the original
human user whose transaction triggered A. If B needs the original sender's
address (e.g. to refund funds), A must explicitly pass that address as
part of the data it sends — B must not assume `sender_address` is the
final human address.

## 7. GEN units

`gl.message.value` returns a value with 18 decimal places (like wei in
Ethereum) — i.e. "10 GEN" is stored/read as `10000000000000000000`, not
`10`.

## 8. Prior constraints (from AccreditationCheck/Covenant) reconfirmed today

- Always `raise gl.vm.UserError(...)`, never a bare `UserError`.
- `gl.vm.run_nondet(leader_fn, validator_fn)` positional-only.
- The validator must call `gl.vm.unpack_result()` before using the
  leader's result.
- Constructor address inputs must be normalized (may arrive as `int`/`str`).
- LLM JSON output must be stripped of markdown fencing before `json.loads`.
- Raw `int` is not supported for persistent fields — must use `u256`/
  `i32`/`bigint`.

## 9. Final deployed addresses for Tribunal (Studio, Sep 21 2026 — v1.1, with access control)

- `PrecedentRegistry`: `0x35fc91c3D7e80Dd1d4D113eB4D5A03902cBaaa39`
- `FirstInstanceCourt`: `0x464534F7BC295126e3C64e8052CF4cBAaF9e5764`
- `AppealsCourt`: `0xB34cE011A103D471422f05C3aed8b77C406F5d5E`

Live end-to-end test confirmed: `file_case` (low tier, strict_eq) →
async `.emit()` to `PrecedentRegistry` → `request_appeal` (only callable
by the case's own claimant) → `AppealsCourt` (only callable by the
configured `FirstInstanceCourt`; three framings via `prompt_comparative`)
→ verdict overturned → bond correctly refunded to the real claimant →
final verdict recorded again in `PrecedentRegistry` (only callable by the
configured court contracts) — `get_entry_count` confirmed 2 entries.

## 10. Access-control gap found by portal review (fixed)

A steward reviewing the first submission flagged a real gap: none of the
cross-contract write entry points checked *who* was calling them.
Concretely:

- `PrecedentRegistry.record_verdict` accepted a verdict from **any**
  caller, not just the two configured court contracts.
- `AppealsCourt.file_appeal` accepted an appeal from **any** caller, not
  just the configured `FirstInstanceCourt` — meaning anyone could forge a
  fake `case_json` and trigger an appeal review directly.
- `FirstInstanceCourt.request_appeal` let **any** address request an
  appeal for **any** case_id, not just the case's own claimant.

**Fix:** each contract now stores the address(es) it should trust
(`first_instance_court`, `appeals_court` on `PrecedentRegistry`;
`first_instance_court` on `AppealsCourt`), settable exactly once by the
deployer via a dedicated `set_*` method, and the sensitive write methods
now `raise gl.vm.UserError(...)` if `gl.message.sender_address` doesn't
match. `request_appeal` additionally checks the caller against the
case's own recorded `claimant` field. This added a new circular
bootstrapping step to deployment (see the updated 7-step order in
`README.md`) since `PrecedentRegistry` is deployed before the two courts
that need to be registered on it.
