# TrustANN AWS Experiment Harness — Revised Decision-Boundary Evaluation

This revision is designed to fix the main evaluation problems identified in the
previous AWS run. It keeps the existing Mac-controlled deployment model and
3-shard × 3-replica topology.

## What changed

### 1. TrustBind now performs explicit greedy evidence selection
The previous harness computed consistency over *all* available responses. A
single poisoned minority response could therefore make the entire evidence set
inconsistent and force `Trusted=0`, even when two honest replicas were
sufficient. The revised `trust_logic.py` selects a consistent subset before
checking the TrustBind conditions:

`|S| >= theta`, `C(S) >= gamma`, and `D(S) >= dmin`.

The selected replica IDs, domains, and poison flags are recorded so an attack
cannot be counted as successful merely because some unselected response was
malicious.

### 2. TrustBind experiments now contain positive controls
The revised ablation contains:

- `A / only_byzantine / theta=1`: intentionally unsafe weak-threshold control;
- `A / only_byzantine / theta=2`: insufficient evidence, must be Unverified;
- `B / two_honest / theta=3`: insufficient evidence, must be Unverified;
- `TrustANN / minority_attack / theta=2`: two honest + one Byzantine; must be Trusted and must not select the poisoned response;
- `Clean / clean / theta=2`: clean positive control; must be Trusted.

This prevents a paper claim from being supported by an experiment that rejects
everything.

### 3. Integrity R-ASR is now selection-aware
`r_asr=1` only when a query is trusted **and the selected evidence actually
contains the poisoned response**. This fixes the previous shortcut where
`r_asr` was simply set equal to the trusted flag.

### 4. Cross-shard experiment directly tests the per-shard boundary
Shard 0 starts with sufficient evidence while shard 1 starts with one available
replica. With `Kmax=0`, the global result must remain Unverified. With
`Kmax>=1`, AvailGuard adds an independent replica and can become Trusted. The
CSV also records a `naive_global_trusted` diagnostic and per-shard evidence
counts.

### 5. Failure results expose the trust-condition invariants
Failure rows now record `theta`, `gamma`, `dmin`, selected evidence count,
selected consistency, and selected diversity. The threshold is never modified
by the failure sweep.

### 6. Recovery is no longer a timer stub
The recovery experiment now exercises bounded evidence recovery using the same
selection/recovery logic. `reconfig_ms` is the measured recovery-query cost;
it is **not** a fabricated five-second reconfiguration time.

### 7. CoordShift simulation is made deterministic and domain-explicit
The existing coordination-resilience simulation now uses NumPy-compatible
sampling and explicitly defines domains for both uniform and diversity-aware
modes. Its main claim should remain fault-domain coverage/correlation control,
not guaranteed reduction of Byzantine influence.

## Scientific guardrails

The current deployment uses the provisioned Deep100K smoke-test data at
`/data/trustann/deep100k`. It is a 100K subset of Deep10M. Do not describe the
result as a full 10M-vector experiment unless the full Deep10M data is actually
installed and evaluated.

The harness still uses a lightweight evidence adapter rather than a complete
cryptographic TrustBind implementation with production signatures/Merkle proofs.
Therefore the generated numbers should be treated as prototype-system evidence
until the exact cryptographic implementation used in the paper is wired into
the harness.

Also, the current `offpath` experiment is a harness-level isolation test; it
must not be described as a measurement of a real asynchronous CoordShift gRPC
service unless such a service is actually running during the experiment.

## One-time Mac setup

```bash
cd TrustANN_AWS_Experiment_Harness_Revised
python3 -m pip install -r requirements.txt
chmod +x macctl/trustannctl
./macctl/trustannctl bootstrap
```

## Deploy / verify workers

```bash
./macctl/trustannctl up --workers 9
./macctl/trustannctl status
```

If the 9 workers already exist and are running, use:

```bash
./macctl/trustannctl deploy
```

## Run the revised evaluation

For the critical security experiments first:

```bash
./macctl/trustannctl run --groups trustbind
```

Then run integrity and per-shard recovery:

```bash
./macctl/trustannctl run --groups integrity,cross_shard
```

Then failures and recovery:

```bash
./macctl/trustannctl run --groups failures,recovery
```

Then performance / coordination experiments:

```bash
./macctl/trustannctl run --groups fanout,offpath,coordshift
```

Or run the complete configured suite:

```bash
./macctl/trustannctl run --no-cleanup
```

The run prints a result directory such as:

`RESULTS=results/20260916_XXXXXX_xxxxx`

The result directory contains CSVs, LaTeX tables, plots, raw grouped JSON,
and a manifest.

## Unit tests

The revised trust logic has 12 local tests covering clean acceptance,
Byzantine-minority exclusion, weak-threshold failure, diversity constraints,
per-shard isolation, ablation behavior, integrity behavior, and bounded
cross-shard recovery.

Run locally on the Mac before syncing:

```bash
python3 -m pytest -q tests
```

Expected result:

`12 passed`

## Recommended execution order

1. Run `python3 -m pytest -q tests`.
2. Sync/bootstrap the revised harness.
3. Run `trustbind` alone and inspect that Clean and TrustANN minority-attack
   cases are Trusted while the weak-threshold attack is rejected only when the
   stronger threshold is used.
4. Run `integrity,cross_shard` and inspect `selected_attack`,
   `naive_global_trusted`, and per-shard evidence counts.
5. Run `failures,recovery` and verify the logged `theta/gamma/dmin` values are
   invariant.
6. Only after those checks run the full suite.

## Important AWS safety note

`up` / `scale` manage only instances tagged `Project=TrustANN` and
`Role=Worker`. The two stopped accidental coordinator instances from the prior
setup are not worker instances and are not touched by this harness.
