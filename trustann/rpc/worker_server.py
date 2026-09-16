#!/usr/bin/env python3
import argparse, hashlib, time
from concurrent import futures
import grpc, numpy as np, hnswlib
from trustann.rpc import worker_pb2, worker_pb2_grpc
from trustann.models import Candidate
from trustann.fault import apply_fault


def parse_experiment(experiment):
    vals={}
    for part in str(experiment or "").split(";"):
        if "=" in part:
            k,v=part.split("=",1); vals[k]=v
    return vals

class HNSWStore:
    def __init__(self,index_path,ids_path,dim=96):
        self.ids=np.load(ids_path,mmap_mode="r")
        self.index=hnswlib.Index(space="l2",dim=int(dim))
        self.index.load_index(index_path, max_elements=len(self.ids))
        self.index.set_num_threads(1)
        self.index.set_ef(64)
        self.dim=self.index.dim
    def search(self,q,k):
        k=min(int(k),len(self.ids))
        labels,dists=self.index.knn_query(np.asarray(q,dtype=np.float32).reshape(1,-1),k=k)
        return [(int(i),float(d)) for i,d in zip(np.asarray(labels).reshape(-1),np.asarray(dists).reshape(-1))]

class Worker(worker_pb2_grpc.WorkerServicer):
    def __init__(self,shard,replica,index,ids,poison=False,dim=96):
        self.shard=shard; self.replica=replica; self.store=HNSWStore(index,ids,dim); self.poison=poison

    def Search(self,request,context):
        t=time.perf_counter()
        try:
            q=np.asarray(request.vector,dtype=np.float32)
            if q.size!=self.store.dim: raise ValueError(f"query dimension {q.size} != index dimension {self.store.dim}")
            spec=parse_experiment(request.experiment)
            mode=spec.get("attack","none")
            attacker=int(spec.get("attacker_replica",-1))
            requested_k=int(request.k)
            search_k=requested_k+1 if mode in ("suppress","candidate_suppression") and attacker==self.replica else requested_k
            ns=self.store.search(q,search_k)
            candidates=tuple(Candidate(str(i),d) for i,d in ns)
            poisoned=False
            if attacker==self.replica and mode!="none":
                candidates=apply_fault(mode,candidates,int(request.query_id),requested_k)
                poisoned=True
            elif self.poison and candidates:
                candidates=apply_fault("byzantine_fabricate",candidates,int(request.query_id),requested_k)
                poisoned=True
            commitment=hashlib.sha256(",".join(f"{c.item_id}:{c.distance:.7g}" for c in candidates).encode()).hexdigest()
            ev=worker_pb2.Evidence(commitment=commitment,candidate_count=len(candidates),consistency=1.0,diversity=1.0,poisoned=poisoned)
            return worker_pb2.QueryResponse(query_id=request.query_id,shard_id=self.shard,replica_id=self.replica,available=True,
                neighbors=[worker_pb2.Neighbor(id=int(c.item_id) if c.item_id.lstrip('-').isdigit() else 999999999,distance=c.distance) for c in candidates],
                evidence=ev,server_ms=(time.perf_counter()-t)*1000)
        except Exception as e:
            return worker_pb2.QueryResponse(query_id=request.query_id,shard_id=self.shard,replica_id=self.replica,available=False,error=str(e),server_ms=(time.perf_counter()-t)*1000)

    def Health(self,request,context):
        return worker_pb2.HealthResponse(ok=True,shard_id=self.shard,replica_id=self.replica,indexed_vectors=len(self.store.ids))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--host",default="0.0.0.0"); p.add_argument("--port",type=int,default=50051)
    p.add_argument("--shard-id",type=int,required=True); p.add_argument("--replica-id",type=int,required=True)
    p.add_argument("--index",required=True); p.add_argument("--ids",required=True); p.add_argument("--poison",action="store_true")
    a=p.parse_args(); s=grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    worker_pb2_grpc.add_WorkerServicer_to_server(Worker(a.shard_id,a.replica_id,a.index,a.ids,a.poison),s)
    s.add_insecure_port(f"{a.host}:{a.port}"); s.start(); print(f"WORKER_READY shard={a.shard_id} replica={a.replica_id} port={a.port}",flush=True)
    try:
        while True: time.sleep(3600)
    except KeyboardInterrupt: s.stop(0)
if __name__=="__main__": main()
