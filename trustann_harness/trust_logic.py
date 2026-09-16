"""TrustBind evidence selection and per-shard trust decision logic.

The implementation follows the paper's safety boundary:
  support (theta) + consistency (gamma) + failure-domain diversity (dmin).

Consistency is rank-aware: it combines candidate-set Jaccard overlap with
rank agreement. This is required to distinguish a Byzantine response that
reuses valid candidate IDs but changes their ranking from an honest response.
"""
from itertools import combinations


def neighbor_ids(resp):
    return tuple(int(x["id"]) for x in resp.get("neighbors", []))


def rank_agreement(a, b):
    """Normalized rank agreement over the common candidate IDs.

    Score is 1 for identical order and approaches 0 as common candidates are
    placed farther apart. Missing candidates receive no rank-agreement credit.
    """
    aa, bb = neighbor_ids(a), neighbor_ids(b)
    pa = {x: i for i, x in enumerate(aa)}
    pb = {x: i for i, x in enumerate(bb)}
    common = set(pa) & set(pb)
    if not common:
        return 0.0
    denom = max(1, max(len(aa), len(bb)) - 1)
    vals = [1.0 - abs(pa[x] - pb[x]) / denom for x in common]
    return max(0.0, min(1.0, sum(vals) / len(vals)))


def pair_consistency(a, b):
    """Candidate overlap + rank agreement used by TrustBind."""
    sa, sb = set(neighbor_ids(a)), set(neighbor_ids(b))
    union = sa | sb
    jaccard = len(sa & sb) / len(union) if union else 1.0
    rank = rank_agreement(a, b)
    return 0.5 * jaccard + 0.5 * rank


def consistency(responses):
    responses = [r for r in responses if r.get("available")]
    if len(responses) < 2:
        return 1.0 if len(responses) == 1 else 0.0
    vals = [pair_consistency(a, b) for a, b in combinations(responses, 2)]
    return sum(vals) / len(vals)


def independence(responses):
    available = [r for r in responses if r.get("available")]
    if not available:
        return 0.0
    replicas = {int(r["replica_id"]) for r in available}
    domains = {r.get("failure_domain") for r in available if r.get("failure_domain") is not None}
    if domains:
        return min(1.0, len(domains) / max(1, len(replicas)))
    return 1.0 if len(replicas) == len(available) else 0.0


def _domain_ok(selected, candidate):
    d = candidate.get("failure_domain")
    return True if d is None else all(x.get("failure_domain") != d for x in selected)


def select_evidence(responses, theta, gamma=1.0, dmin=1.0):
    available = [r for r in responses if r.get("available")]
    if not available:
        return []
    if theta <= 1:
        return [available[0]]

    def avg_to_set(candidate, selected):
        if not selected:
            return 1.0
        return sum(pair_consistency(candidate, x) for x in selected) / len(selected)

    scored = []
    for i, r in enumerate(available):
        others = [x for j, x in enumerate(available) if j != i]
        scored.append((avg_to_set(r, others) if others else 1.0, i, r))
    scored.sort(key=lambda x: (-x[0], x[1]))
    selected = [scored[0][2]]
    remaining = [r for r in available if r is not selected[0]]

    while len(selected) < theta and remaining:
        candidates = []
        for idx, cand in enumerate(remaining):
            if not _domain_ok(selected, cand):
                continue
            trial = selected + [cand]
            c = consistency(trial)
            if c >= gamma:
                candidates.append((avg_to_set(cand, selected), idx, cand))
        if not candidates:
            break
        candidates.sort(key=lambda x: (-x[0], x[1]))
        selected.append(candidates[0][2])
        remaining = [r for r in remaining if r is not candidates[0][2]]
    return selected


def trust_decision(responses, theta, gamma=1.0, dmin=1.0):
    available = [r for r in responses if r.get("available")]
    selected = select_evidence(available, int(theta), float(gamma), float(dmin))
    c = consistency(selected)
    d = independence(selected)
    ok = len(selected) >= int(theta) and c >= float(gamma) and d >= float(dmin)
    return {
        "trusted": bool(ok),
        "available_count": len(available),
        "count": len(selected),
        "consistency": c,
        "diversity": d,
        "selected_replicas": [int(r["replica_id"]) for r in selected],
        "selected_domains": [r.get("failure_domain") for r in selected],
        "selected_poisoned": [bool(r.get("evidence", {}).get("poisoned", False)) for r in selected],
    }


def per_shard_trust(responses_by_shard, theta, gamma=1.0, dmin=1.0):
    decisions = {int(shard): trust_decision(responses, theta, gamma, dmin)
                 for shard, responses in responses_by_shard.items()}
    trusted = all(x["trusted"] for x in decisions.values()) if decisions else False
    return trusted, decisions
