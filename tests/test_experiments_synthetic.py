import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trustann_harness.experiments import ExperimentRunner

class R:
    def __init__(self, qid, shard, replica, ids):
        self.query_id=str(qid); self.shard_id=shard; self.replica_id=replica
        self.available=True; self.error=""; self.server_ms=0.1
        self.neighbors=[type("N",(),{"id":i,"distance":0.1})() for i in ids]
        self.evidence=type("E",(),{"commitment":"x","candidate_count":len(ids),"consistency":1.0,"diversity":1.0,"poisoned":False})()

class FakeClient:
    def __init__(self, shard, replica): self.shard=shard; self.replica=replica
    def search(self,qid,q,k,shard_id,experiment):
        ids=list(range(1,k+1))
        if "integrity" in experiment and self.replica==0:
            ids[0]=999999999
        if "ablation" in experiment and self.replica==2:
            ids[0]=999999999
        return R(qid, self.shard, self.replica, ids)

class RNG:
    def choice(self, a, size=None, replace=False):
        import numpy as np
        a=list(a)
        if size is None: return np.array(a[0])
        return np.array(a[:size])


def make_runner():
    workers=[]; clients={}
    for s in range(3):
        for r in range(3):
            name=f"s{s}r{r}"
            workers.append({"name":name,"shard":s,"replica":r,"failure_domain":f"d{r}","port":50051})
            clients[name]=FakeClient(s,r)
    cfg={"dataset":{"k":9},"trustann":{"theta":2,"gamma":1.0,"dmin":1.0,"r":3},"coordshift":{"nodes":60,"rounds":10},"experiments":{"coordshift_k":[5],"coordshift_p":[.1],"coordshift_modes":["uniform","diversity_aware"]}}
    return ExperimentRunner(cfg,"/tmp",clients,workers,{i:[0.0]*9 for i in range(3)},RNG())


def test_ablation_has_positive_control_and_weak_threshold_vulnerability():
    r=make_runner(); rows=r.trustbind_ablation(2)
    by={(x["pattern"],x["theta"]):x for x in rows if x["query_id"]==0}
    assert by[("Clean",2)]["trusted"]==1
    assert by[("A",1)]["trusted"]==1 and by[("A",1)]["r_asr"]==1
    assert by[("A",2)]["trusted"]==0
    assert by[("B",3)]["trusted"]==0
    assert by[("TrustANN",2)]["trusted"]==1 and by[("TrustANN",2)]["r_asr"]==0


def test_integrity_attack_rejected_but_clean_accepted():
    r=make_runner(); rows=r.integrity(2)
    by={x["system"]:x for x in rows if x["query_id"]==0}
    assert by["unverified"]["r_asr"]==1
    assert by["trustann_theta1"]["r_asr"]==1
    assert by["trustann_theta2"]["trusted"]==1 and by["trustann_theta2"]["r_asr"]==0
    assert by["clean_positive"]["trusted"]==1


def test_cross_shard_isolation_then_recovery():
    r=make_runner(); rows=r.cross_shard(1)
    by={x["kmax"]:x for x in rows}
    assert by[0]["trusted"]==0
    assert by[0]["naive_global_trusted"]==0 or by[0]["shard1_available"] < 2
    assert by[1]["trusted"]==1
    assert by[1]["recovery_rounds"]==1
