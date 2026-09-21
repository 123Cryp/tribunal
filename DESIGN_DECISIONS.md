# Tribunal — Design Decisions

## 0. Context and goal

Third project after AccreditationCheck (accepted, 100 points) and Covenant
(three independent escrow contracts, each with its own equivalence
principle, all deployed and live-tested). The lesson learned from the
competing project Penumbra (20 contracts, very comprehensive, but only 500
points): **quantity alone does not earn points.** What earns points is a
clear narrative + a genuinely new mechanism + real execution (live
deployment, not just code on paper). Tribunal deliberately has fewer
contracts than Penumbra (3) but they are actually wired together, not three
escrows placed side by side.

## 1. The new mechanism (before writing a single line of code)

Covenant showed that consensus strictness should match the *type of
evidence*. Tribunal goes one step further: **an adjudication pipeline whose
consensus strictness rescales with the value/importance of the dispute
itself, and whose verdicts have memory** — a new case is not decided in a
vacuum; the system actually consults real precedent. This is exactly what
no single escrow contract (even with the best equivalence principle) can
produce, because a single escrow has neither an appeal path nor precedent.

Three primitives that together create something genuinely new, not three
separate contracts:

- **FirstInstanceCourt** on its own is just "a dispute-resolution contract
  with variable strictness" — something similar already existed in Covenant
  (Measured/Fulfillment/Divergent each had a strictness tier).
- **AppealsCourt** on its own does nothing — without a first-instance court
  that actually writes to it, AppealsCourt is an orphaned contract.
- **PrecedentRegistry** on its own is just an append-only database — unless
  FirstInstanceCourt actually reads from it, it's just a useless log.

What distinguishes these three from "three escrows sharing a name" is that
**each one's behavior depends on the existence of the others**:
FirstInstanceCourt renders its verdict by looking at PrecedentRegistry (not
in isolation from precedent); if a party appeals, FirstInstanceCourt itself
cannot change the verdict — it must genuinely write to an independent
contract (AppealsCourt) that re-judges under stricter criteria; and
AppealsCourt's own verdict becomes future precedent. This cycle of "verdict
→ precedent → next verdict that consults the precedent" is the new
primitive: **an on-chain adjudication system with real memory, not three
independent instances of one pattern.**

A test that would fail if this cycle were fake/no-op: a test that
pre-populates PrecedentRegistry with a "precedent-setting" case whose
verdict deliberately contradicts the initial intuition for a similar new
case, then asserts that FirstInstanceCourt's verdict actually reflects that
precedent (not that it gives the same answer with an empty precedent
prompt) — i.e. mocking/stubbing the `.view()` call to supply two
contradictory precedents and observing the verdict flip both times.

## 2. The three contracts and the justification for each equivalence principle

### FirstInstanceCourt — strictness proportional to claimed amount (three paths, three EPs)
**What it does:** a dispute is filed with a claimed amount; depending on
the amount:
- **Low amount (below a threshold):** `strict_eq` on a binary/canonical
  fact (e.g. "did condition X occur or not" — something with no meaningful
  ambiguity).
- **Medium amount:** `prompt_comparative` — two evaluators with different
  framings (similar to DivergentAssessorArbitration but with only 2 here,
  since a medium-value dispute doesn't justify ≥3 evaluators).
- **High amount:** multiple independent `prompt_non_comparative` reviews
  (the leader produces a full analysis, validators audit it).
**Why these three together and not a fixed EP:** this is exactly the same
lesson from Covenant, but this time the axis of separation is "amount at
stake" rather than "type of evidence" — a completely different dimension
of the EP-selection decision, which shows that the principle "consensus
strictness must match the nature of what is being judged" is a more
general principle, not a trick specific to escrows.

### AppealsCourt — ≥3 evaluators with different framings, `prompt_comparative`
**What it does:** when FirstInstanceCourt renders a verdict and the losing
party requests an appeal within a time window with a bond, AppealsCourt
re-reviews with stricter criteria than FirstInstanceCourt — it either
confirms or overturns the first verdict.
**Why stricter than FirstInstanceCourt (≥3 evaluators instead of 2, each
with a different framing):** an appeals court must deliberately be
stricter than a first-instance court, otherwise an appeal is just a
re-vote with the same error probability, not a real filter. Different
framings (not the same prompt run three times) are exactly the necessary
condition for "agreement among three evaluators" to have real meaning,
rather than being three copies of one judgment.
**Why `prompt_comparative` and not `prompt_non_comparative`:** here we
genuinely need three (or more) *independent* judgments that get compared
against each other, because the whole point of an appeal is whether
independent judgments converge on one outcome — using an asymmetric
leader/validator structure (non-comparative) would just repeat
FirstInstanceCourt's single-authority structure and make the appeal
meaningless.

### PrecedentRegistry — no EP of its own, but the system's real connective tissue
**What it does:** an append-only archive of (case summary, final verdict,
amount/tier). Two real cross-contract interactions:
1. Before rendering a verdict, FirstInstanceCourt reads similar prior
   cases from PrecedentRegistry with a real `.view()` and feeds them into
   the `prompt_comparative`/`prompt_non_comparative` prompt as context —
   not a placeholder, but data that actually changes the verdict.
2. After the final verdict, AppealsCourt records it in PrecedentRegistry
   with a real `.emit()`.
**Why this contract has no EP of its own:** this is not a judging
contract — writing to it is pure append (no LLM judgment) and reading from
it is a purely deterministic view; imposing an unnecessary EP on it would
be exactly the kind of "hello-world with a fake EP" the portal rejects.
Its value is not in an EP of its own but in the fact that its existence
makes the system's "memory" real — something that did not exist at all in
Covenant.

## 3. What is deliberately NOT built

Per the portal's exclusion list: no thin LLM wrapper ("ask AI about X"), no
purely-formatting validator, no storage hello-world. Even though
PrecedentRegistry is simple, it is not merely a key-value store — its role
is explicitly justified (section 2), not added just because "we need a
third place to store something." No contract was added merely to reach an
arbitrary count — exactly the lesson learned from Penumbra's low score.

## 4. Confirmed GenVM constraints inherited from AccreditationCheck and Covenant (not rediscovered)

- The runner header must pin a real hash, never `:latest`/`:test`.
  **Confirmed hash (verified via web search across several independent
  pages on docs.genlayer.com, including `introduction`, `storage`,
  `upgradability`, as of June 2026):**
  `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`
- Always `raise gl.vm.UserError(...)` — `UserError` is not re-exported by
  `from genlayer import *` (Covenant §4i).
- `gl.vm.run_nondet(leader_fn, validator_fn)` positional-only, no keywords
  (Covenant §4f).
- Every validator must call `gl.vm.unpack_result(leader_result)` as its
  first line before any comparison/operation on the leader's result — even
  `==` silently fails, only `>`/`<`/arithmetic give a clear error (§4h).
- Constructor address inputs must be normalized: they may arrive as a raw
  `int` or `str`, not only `Address` (§4d).
- An LLM's JSON output may arrive wrapped in a ` ```json ... ``` ` fence;
  it must be stripped before `json.loads`, with a fallback that slices the
  outermost `{...}` (§4e).
- `worldtimeapi.org` is permanently sunset (HTTP 410) — the time source
  must be `https://www.cloudflare.com/cdn-cgi/trace` (the `ts=<unix>`
  line) (§4g).
- GEN transfer from within a contract: `gl.get_contract_at(addr).emit_transfer(value=amount)`
  — there is no top-level `gl.transfer`/`gl.send` (§4b).

## 5. What still needed live verification in Studio before relying on it

This project was the first to genuinely need **two other kinds** of
cross-contract interaction not used in Covenant: a real `.view()` (not
just `.emit_transfer`) and an `.emit().method()` with arguments (not just
argument-less `emit_transfer`). Official documentation
(`sdk.genlayer.com/main/api/genlayer.html` and the changelog) confirms this
shape:

```python
contract = gl.get_contract_at(addr)
result = contract.view().some_view_method(arg1, arg2)
contract.emit(value=u256(100)).some_write_method(arg1)
```

but per the same lesson from Covenant (§4b–4i: documentation is not
necessarily consistent with the runner's live behavior), before finally
relying on this signature in the three main contracts, a small diagnostic
contract pair was deployed live on Studio and the following was confirmed:

1. Is `.view()` callable from inside a `@gl.public.write`, or only from a
   `@gl.public.view`?
2. Is the return value of `.view()` directly usable, or does it need
   `unpack_result`/unwrapping like `run_nondet`?
3. What does `.emit().method(args)` do from inside a `run_nondet`
   leader/validator?
4. Is a cross-contract write finalized within the same transaction, or
   does it create a separate async transaction that must be polled for?

**Live results (see `LESSONS_LEARNED.md` for full detail):**
1. `.view()` works fine when called from a plain (non-nondet) write or
   view method.
2. The return value is directly usable, no unwrapping needed.
3. **Forbidden.** Both `.view()` and `.emit()` raise `SystemError: 6:
   forbidden` when called from inside a `leader_fn`/`validator_fn` — a
   VM-level trap, not catchable with `try/except`.
4. **Asynchronous.** An immediate same-transaction `.view()` of the
   written-to contract still shows the pre-write value; the write lands in
   a separate, later transaction.

## 6. Final architecture consequences of the live findings

- All `gl.get_contract_at(...)` calls (`.view()` and `.emit()`) happen
  strictly **outside** any `run_nondet`/`eq_principle` block, directly in
  the body of a `@gl.public.write`/`@gl.public.view` method.
- Because cross-contract writes are asynchronous, no contract logic
  assumes an immediate, same-transaction result from a write it just
  issued to another contract.
- `gl.message.sender_address` inside a contract reached via `.emit()` is
  the address of the calling contract, not the original human sender — any
  contract that needs the original sender's address must receive it
  explicitly as part of the passed data.

## 7. Status

Design finalized, three contracts written, deployed live, and verified
end-to-end (first-instance verdict → precedent record → appeal → verdict
overturned → bond correctly refunded to the original claimant → final
verdict recorded again in PrecedentRegistry). A portal steward review
flagged that the cross-contract write entry points lacked caller
authorization; each contract now restricts its sensitive write methods to
the specific configured court contract(s), and `request_appeal` is
restricted to the case's own recorded claimant. See `LESSONS_LEARNED.md`
for the complete list of live-verified GenVM behaviors, including a
previously-undocumented constraint on file header comment length and the
access-control fix.
