# Final TrustANN experiments

Mandatory AWS runs:

1. Existing correlated-failure CSV: use `scripts/extract_correlated_failures.py`; this is an extraction step, not an AWS rerun.
2. Clean overhead: `clean_overhead` compares an unverified first-response baseline with full TrustANN evidence verification using the same parallel replica fan-out.
3. Retrieval attacks: `candidate_suppression` and `ranking_manipulation` are injected at the worker/RPC boundary via the `experiment` field.

Optional:
4. `kmax_recovery`
5. `consistency_independence_ablation`

Run unit tests:
`python3 -m pytest -q tests`

Compile-check:
`python3 -m compileall -q .`

AWS group:
`./macctl/trustannctl run --groups mandatory --no-cleanup`

Then, if desired, run optional experiments separately:
`./macctl/trustannctl run --groups optional --no-cleanup`

Important: the correlated-failure runner intentionally refuses to run when the configured topology has no shard with at least two replicas in the same failure domain. That prevents a nominally different “correlated” condition from being scientifically identical to independent replica loss.
