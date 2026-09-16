import json
import os
import sys
import time
import numpy as np

# Allow execution from a copied harness directory containing the RPC package.
def load_rpc():
    try:
        import grpc
        from trustann.rpc import worker_pb2, worker_pb2_grpc
        return grpc, worker_pb2, worker_pb2_grpc
    except ImportError as e:
        raise RuntimeError(
            "RPC dependencies/package unavailable. Install grpcio and ensure "
            "the TrustANN RPC package is on PYTHONPATH."
        ) from e

class WorkerClient:
    def __init__(self, host, port, timeout_s=3.0):
        grpc, pb2, pb2_grpc = load_rpc()
        self.grpc = grpc
        self.pb2 = pb2
        self.stub = pb2_grpc.WorkerStub(
            grpc.insecure_channel(f"{host}:{port}")
        )
        self.host, self.port, self.timeout_s = host, port, timeout_s

    def health(self):
        req = self.pb2.HealthRequest()
        return self.stub.Health(req, timeout=self.timeout_s)

    def search(self, query_id, vector, k, shard_id, experiment=""):
        v = np.asarray(vector, dtype=np.float32).reshape(-1)
        req = self.pb2.QueryRequest(
            query_id=str(query_id),
            vector=v.tolist(),
            k=int(k),
            shard_id=int(shard_id),
            experiment=str(experiment),
        )
        return self.stub.Search(req, timeout=self.timeout_s)

def response_to_dict(r):
    return {
        "query_id": int(r.query_id),
        "shard_id": int(r.shard_id),
        "replica_id": int(r.replica_id),
        "available": bool(r.available),
        "neighbors": [
            {"id": int(n.id), "distance": float(n.distance)}
            for n in r.neighbors
        ],
        "evidence": {
            "commitment": r.evidence.commitment.hex()
            if isinstance(r.evidence.commitment, (bytes, bytearray))
            else str(r.evidence.commitment),
            "candidate_count": int(r.evidence.candidate_count),
            "consistency": float(r.evidence.consistency),
            "diversity": float(r.evidence.diversity),
            "poisoned": bool(r.evidence.poisoned),
        },
        "server_ms": float(r.server_ms),
        "error": str(r.error),
    }
