import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trustann_harness.trust_logic import (
    consistency, independence, select_evidence, trust_decision, per_shard_trust
)


def resp(replica, ids, domain, poisoned=False):
    return {
        "available": True,
        "replica_id": replica,
        "failure_domain": domain,
        "neighbors": [{"id": i} for i in ids],
        "evidence": {"poisoned": poisoned},
    }


HONEST=[1,2,3,4,5,6,7,8,9]
BAD=[999999999,2,3,4,5,6,7,8,9]


def test_clean_three_replica_trust():
    rs=[resp(0,HONEST,"a"),resp(1,HONEST,"b"),resp(2,HONEST,"c")]
    d=trust_decision(rs,theta=2,gamma=1.0,dmin=1.0)
    assert d["trusted"]
    assert d["count"]==2
    assert d["consistency"]==1.0
    assert d["diversity"]==1.0
    assert not any(d["selected_poisoned"])


def test_byzantine_minority_is_excluded():
    rs=[resp(0,BAD,"a",True),resp(1,HONEST,"b"),resp(2,HONEST,"c")]
    d=trust_decision(rs,theta=2,gamma=1.0,dmin=1.0)
    assert d["trusted"]
    assert d["count"]==2
    assert not any(d["selected_poisoned"])


def test_single_byzantine_passes_weak_theta_one():
    rs=[resp(0,BAD,"a",True)]
    d=trust_decision(rs,theta=1,gamma=1.0,dmin=1.0)
    assert d["trusted"]
    assert any(d["selected_poisoned"])


def test_single_byzantine_fails_theta_two():
    rs=[resp(0,BAD,"a",True)]
    d=trust_decision(rs,theta=2,gamma=1.0,dmin=1.0)
    assert not d["trusted"]
    assert d["count"]<2


def test_two_honest_available_pass_theta_two():
    rs=[resp(0,HONEST,"a"),resp(1,HONEST,"b")]
    d=trust_decision(rs,theta=2,gamma=1.0,dmin=1.0)
    assert d["trusted"]


def test_two_honest_available_fail_theta_three():
    rs=[resp(0,HONEST,"a"),resp(1,HONEST,"b")]
    d=trust_decision(rs,theta=3,gamma=1.0,dmin=1.0)
    assert not d["trusted"]


def test_diversity_blocks_same_domain():
    rs=[resp(0,HONEST,"a"),resp(1,HONEST,"a"),resp(2,HONEST,"b")]
    d=trust_decision(rs,theta=2,gamma=1.0,dmin=1.0)
    assert d["trusted"]
    assert set(d["selected_domains"])=={"a","b"}


def test_conflict_blocks_two_response_set():
    rs=[resp(0,HONEST,"a"),resp(1,BAD,"b",True)]
    d=trust_decision(rs,theta=2,gamma=1.0,dmin=1.0)
    assert not d["trusted"]


def test_per_shard_isolation():
    by={
        0:[resp(0,HONEST,"a"),resp(1,HONEST,"b")],
        1:[resp(0,HONEST,"a")],
    }
    trusted, decisions=per_shard_trust(by,theta=2,gamma=1.0,dmin=1.0)
    assert not trusted
    assert decisions[0]["trusted"]
    assert not decisions[1]["trusted"]


if __name__=="__main__":
    import pytest
    raise SystemExit(pytest.main([__file__,"-q"]))
