# Tribunal

A complete on-chain adjudication pipeline, built from three GenLayer
Intelligent Contracts that genuinely talk to each other via
`gl.get_contract_at()`:

- **FirstInstanceCourt** — selects consensus strictness based on the
  claimed amount (`strict_eq` / `prompt_comparative` /
  `prompt_non_comparative`), and reads similar precedent from
  `PrecedentRegistry` before rendering a verdict.
- **AppealsCourt** — re-reviews with stricter criteria (three independent
  framings); can confirm or overturn the first verdict.
- **PrecedentRegistry** — an append-only archive of resolved cases that
  both `FirstInstanceCourt` and `AppealsCourt` read from / write to.

Full architecture details and the justification for each equivalence
principle are in [`DESIGN_DECISIONS.md`](./DESIGN_DECISIONS.md).
Live-verified GenVM findings (including a previously undocumented
constraint) are recorded in [`LESSONS_LEARNED.md`](./LESSONS_LEARNED.md).

## Deployed addresses (GenLayer Studio)

| Contract | Address |
|---|---|
| PrecedentRegistry | `0x35fc91c3D7e80Dd1d4D113eB4D5A03902cBaaa39` |
| FirstInstanceCourt | `0x464534F7BC295126e3C64e8052CF4cBAaF9e5764` |
| AppealsCourt | `0xB34cE011A103D471422f05C3aed8b77C406F5d5E` |

## Access control

Each contract enforces the caller relationships implied by the design:

- `PrecedentRegistry.record_verdict` only accepts calls from the
  configured `FirstInstanceCourt` or `AppealsCourt` addresses.
- `AppealsCourt.file_appeal` only accepts calls from the configured
  `FirstInstanceCourt` address.
- `FirstInstanceCourt.request_appeal` only accepts calls from the case's
  recorded claimant, and only once per case.

## Repository structure

```
contracts/
  precedent_registry.py
  first_instance_court.py
  appeals_court.py
tests/
  test_offline.py
DESIGN_DECISIONS.md
LESSONS_LEARNED.md
README.md
```

## Testing

```bash
pip install genlayer-test
pytest tests/ -v
```

## Deployment

Use GenLayer Studio (`studio.genlayer.com`). Deployment order matters
because the contracts need each other's addresses, and each court must be
explicitly authorized on the contracts it calls into:

1. `precedent_registry.py` (no arguments)
2. `first_instance_court.py` with `precedent_registry_address`,
   `low_threshold`, `high_threshold`
3. `appeals_court.py` with `precedent_registry_address`
4. On `FirstInstanceCourt`, call `set_appeals_court` with the
   `AppealsCourt` address
5. On `AppealsCourt`, call `set_first_instance_court` with the
   `FirstInstanceCourt` address
6. On `PrecedentRegistry`, call `set_first_instance_court` with the
   `FirstInstanceCourt` address
7. On `PrecedentRegistry`, call `set_appeals_court` with the
   `AppealsCourt` address

Only after all 7 steps are complete will `record_verdict` and
`file_appeal` accept calls (they reject any caller that isn't the
configured court contract).

**Important:** keep each `.py` file's header to at most 2 lines of comment
(`# v0.1.0` + `Depends`) — longer comment blocks cause schema-loading to
fail. Details in `LESSONS_LEARNED.md`.
