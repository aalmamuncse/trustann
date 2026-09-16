"""Deterministic retrieval fault operators used by the AWS evaluation.

The worker receives an experiment string of the form
``attack=<mode>;attacker_replica=<id>``. Only the selected replica applies the
fault, so the attack is exercised at the actual worker/RPC boundary rather than
mutated in the coordinator after receipt.
"""
from __future__ import annotations
from typing import Sequence, Tuple
from trustann.models import Candidate

FABRICATED_ID_PREFIX = "attacker-fake-"

def apply_fault(mode: str, real_candidates: Sequence[Candidate], rng_seed: int, k: int,
                poison_distance: float = 1e-4) -> Tuple[Candidate, ...]:
    real = tuple(real_candidates)
    if mode in (None, "", "none"):
        return real[:k]
    if mode == "byzantine_fabricate":
        return tuple(Candidate(f"{FABRICATED_ID_PREFIX}{i}", float(i)) for i in range(k))
    if mode in ("ranking", "byzantine_plausible"):
        # Valid IDs, adversarial ordering. Distances are retained with the IDs
        # so the only changed semantic signal is ranking/order.
        return tuple(reversed(real[:k]))
    if mode in ("suppress", "candidate_suppression"):
        if not real:
            return tuple()
        # Suppress the best candidate and fill from the next genuine candidate
        # when available. The caller should request k+1 candidates for this mode.
        return tuple(real[1:k+1])
    raise ValueError(f"unknown fault mode: {mode!r}")
