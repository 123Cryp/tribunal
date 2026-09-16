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
| PrecedentRegistry | `0x4A84CEA53f5f635c571edfE7e9ad637e24eB244A` |
| FirstInstanceCourt | `0x636c1Bf978BCdF1a6fc0b8ACeeC9AbB3E297e3D2` |
| AppealsCourt | `0x329340e855C37Dc91A734DA5bda070984F563A9C` |

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
because the contracts need each other's addresses:

1. `precedent_registry.py` (no arguments)
2. `first_instance_court.py` with `precedent_registry_address`,
   `low_threshold`, `high_threshold`
3. `appeals_court.py` with `precedent_registry_address`
4. On `FirstInstanceCourt`, call `set_appeals_court` with the
   `AppealsCourt` address

**Important:** keep each `.py` file's header to at most 2 lines of comment
(`# v0.1.0` + `Depends`) — longer comment blocks cause schema-loading to
fail. Details in `LESSONS_LEARNED.md`.
