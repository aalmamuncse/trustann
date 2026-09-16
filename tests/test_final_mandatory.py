import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trustann_harness.trust_logic import pair_consistency, trust_decision
from trustann_harness.experiments import ExperimentRunner
from trustann.fault import apply_fault

class FakeResponse:
    def __init__(self, qid, shard, replica, ids):
        self.query_id=str(qid); self.shard_id=shard; self.replica_id=replica; self.available=True; self.error=""; self.server_ms=0.1
        self.neighbors=[type("N",(),{"id":i,"distance":float(j+1)})() for j,i in enumerate(ids)]
        self.evidence=type("E",(),{"commitment":"x","candidate_count":len(ids),"consistency":1.0,"diversity":1.0,"poisoned":False})()

class FakeClient:
    def __init__(self, replica): self.replica=replica
    def search(self,qid,q,k,shard,experiment):
        ids=list(range(1,k+1))
        if "attack=ranking" in experiment and self.replica==0: ids=list(reversed(ids))
        if "attack=suppress" in experiment and self.replica==0: ids=list(range(2,k+2))
        return FakeResponse(qid,shard,self.replica,ids)

class RNG:
    def choice(self,a,size=None,replace=False):
        vals=list(a)
        if size is None: return vals[0]
        return __import__('numpy').array(vals[:size])


def runner():
    workers=[]; clients={}
    for r in range(3):
        name=f"s0r{r}"; workers.append({"name":name,"shard":0,"replica":r,"failure_domain":f"d{r}","port":50051}); clients[name]=FakeClient(r)
    cfg={"dataset":{"k":9},"trustann":{"r":3,"theta":2,"gamma":1.0,"dmin":1.0},"coordshift":{"nodes":60,"rounds":10},"experiments":{}}
    qs={i:[0.0]*9 for i in range(5)}
    return ExperimentRunner(cfg,"/tmp",clients,workers,qs,RNG())


def test_rank_change_lowers_consistency():
    a={"available":True,"neighbors":[{"id":1},{"id":2},{"id":3}]}; b={"available":True,"neighbors":[{"id":3},{"id":2},{"id":1}]}
    assert pair_consistency(a,b) < 1.0


def test_rank_attack_is_rejected_at_gamma_one():
    clean=[{"available":True,"replica_id":1,"failure_domain":"a","neighbors":[{"id":1},{"id":2},{"id":3}]},
           {"available":True,"replica_id":2,"failure_domain":"b","neighbors":[{"id":1},{"id":2},{"id":3}]},
           {"available":True,"replica_id":0,"failure_domain":"c","neighbors":[{"id":3},{"id":2},{"id":1}]}]
    d=trust_decision(clean,2,1.0,1.0)
    assert d["trusted"]
    assert not any(d["selected_poisoned"])


def test_fault_modes_have_expected_semantics():
    from trustann.models import Candidate
    real=tuple(Candidate(str(i),float(i)) for i in range(1,11))
    assert len(apply_fault("suppress",real,1,9))==9 and apply_fault("suppress",real,1,9)[0].item_id=="2"
    assert apply_fault("ranking",real,1,9)[0].item_id=="9"
    assert apply_fault("byzantine_fabricate",real,1,3)[0].item_id.startswith("attacker-fake-")


def test_clean_overhead_produces_both_systems():
    r=runner(); rows=r.clean_overhead(3)
    assert {x["system"] for x in rows}=={"unverified_baseline","trustann"}
    assert all(x["queries"]==3 for x in rows)


def test_attack_runner_produces_two_attack_families():
    r=runner(); rows=r.retrieval_attacks(2)
    assert {x["attack"] for x in rows}=={"candidate_suppression","ranking_manipulation"}
    assert all(x["condition"] in {"clean","attack"} for x in rows)


def test_correlated_failure_fails_fast_without_shared_domain():
    r=runner()
    try: r.correlated_failures_final(1)
    except ValueError as e: assert "sharing a failure domain" in str(e)
    else: raise AssertionError("expected topology validation failure")
