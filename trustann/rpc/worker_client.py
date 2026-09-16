import grpc
from trustann.rpc import worker_pb2, worker_pb2_grpc
class WorkerClient:
    def __init__(self,address,timeout_s=2.0): self.address=address; self.timeout_s=timeout_s
    def health(self):
        with grpc.insecure_channel(self.address) as ch: return worker_pb2_grpc.WorkerStub(ch).Health(worker_pb2.HealthRequest(),timeout=self.timeout_s)
    def search(self,query_id,vector,k,shard_id,experiment='aws'):
        with grpc.insecure_channel(self.address) as ch:
            req=worker_pb2.QueryRequest(query_id=query_id,vector=list(map(float,vector)),k=k,shard_id=shard_id,experiment=experiment)
            return worker_pb2_grpc.WorkerStub(ch).Search(req,timeout=self.timeout_s)
