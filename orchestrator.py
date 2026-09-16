#!/usr/bin/env python3
import argparse, json, os, shlex, subprocess, sys, time, traceback, uuid, shutil
from pathlib import Path
import numpy as np
from trustann_harness.remote import SSH
from trustann_harness.rpc import WorkerClient
from trustann_harness.experiments import ExperimentRunner
from trustann_harness.metrics import write_csv, write_json, append_jsonl
from trustann_harness.plotting import make_plots
from trustann_harness.tables import write_tables

def load_cfg(path):
    with open(path) as f: return json.load(f)

def now_id():
    return time.strftime("%Y%m%d_%H%M%S")+"_"+uuid.uuid4().hex[:6]

def load_queries(path,n,dim,seed):
    # Supports fvecs and npy/npz. The coordinator owns the dataset.
    if path.endswith(".fvecs"):
        rows=[]
        with open(path,"rb") as f:
            import struct
            while True:
                b=f.read(4)
                if not b: break
                d=struct.unpack("<i",b)[0]
                rows.append(np.frombuffer(f.read(4*d),dtype="<f4"))
                if len(rows)>=max(n*3,n): break
        x=np.asarray(rows,dtype=np.float32)
    else:
        x=np.load(path,mmap_mode="r")
        if isinstance(x,np.lib.npyio.NpzFile): x=x["queries"] if "queries" in x.files else x[x.files[0]]
    if x.ndim!=2 or x.shape[1]!=dim: raise ValueError(f"Expected [N,{dim}], got {x.shape}")
    rng=np.random.default_rng(seed); idx=rng.choice(len(x),size=min(n,len(x)),replace=False)
    return np.asarray(x[idx],dtype=np.float32)

def cfg_from_topology(path):
    raw=load_cfg(path)
    # Mac sends a topology JSON whose fields are already experiment config.
    c={
      "ssh":{"user":"ec2-user","key":"/home/ec2-user/.ssh/trustann-key.pem","connect_timeout_s":15},
      "coordinator":{"host":"127.0.0.1"},
      "workers":raw["workers"],
      "paths":{"rpc_package":os.path.expanduser("~/TrustANN_AWS_Experiment_Harness"),
               "python":sys.executable,
               "server_module":"trustann.rpc.worker_server",
               "query_file":raw["dataset"]["query_file"]},
      "dataset":raw["dataset"], "ann":raw.get("ann",{}),
      "trustann":raw["trustann"], "coordshift":raw["coordshift"],
      "experiments":raw["experiments"]
    }
    return c

def package_and_install(cfg):
    root=Path(os.path.expanduser(cfg["paths"]["rpc_package"]))
    # Coordinator is source of truth; generated protobuf files are created here.
    proto=root/"trustann/rpc/worker.proto"
    subprocess.run([sys.executable,"-m","grpc_tools.protoc","-I",str(proto.parent),
                    "--python_out",str(proto.parent),"--grpc_python_out",str(proto.parent),
                    str(proto)],check=True)
    return root

def stage_hnswlib_from_coordinator(cfg):
    """Stage the already-working coordinator hnswlib binary for same-AMI workers.

    This avoids rebuilding hnswlib nine times on Amazon Linux. The coordinator
    and workers use the same Python/OS architecture in this deployment.
    """
    import tempfile
    p = subprocess.run(
        [sys.executable, "-c",
         "import hnswlib; print(hnswlib.__file__)"],
        text=True, capture_output=True, check=True
    )
    so = Path(p.stdout.strip())
    if not so.exists():
        raise RuntimeError(f"Coordinator hnswlib binary not found: {so}")
    if so.suffix != ".so":
        # hnswlib normally resolves directly to its extension module.
        candidates = list(so.parent.glob("hnswlib*.so"))
        if not candidates:
            raise RuntimeError(f"Could not locate hnswlib .so near {so}")
        so = candidates[0]
    stage = Path("/tmp/trustann_hnswlib_stage")
    stage.mkdir(parents=True, exist_ok=True)
    local_so = stage / so.name
    shutil.copy2(so, local_so)
    return local_so

def configure_worker(cfg,w):
    ssh=SSH(cfg["ssh"]["user"],cfg["ssh"]["key"],cfg["ssh"]["connect_timeout_s"])
    root="/home/ec2-user/trustann-worker"
    # Prepare the worker entirely through the coordinator's private-IP SSH connection.
    remote = f"""set -e
rm -rf {root}
mkdir -p {root}/trustann/rpc {root}/data
if [ ! -x {root}/venv/bin/python ]; then
  python3 -m venv {root}/venv
fi
command -v g++ >/dev/null
g++ --version | head -n 1
{root}/venv/bin/python -m pip install -q --disable-pip-version-check --upgrade pip setuptools wheel
{root}/venv/bin/python -m pip install -q --disable-pip-version-check grpcio grpcio-tools numpy
"""
    # Preserve newlines: shell control structures such as "if ...; then" must not
    # be collapsed into whitespace.
    ssh.run(w["host"],remote)

    # Reuse the coordinator's known-good hnswlib extension instead of compiling
    # hnswlib on every worker. All workers are the same AMI/architecture.
    hnsw_so = stage_hnswlib_from_coordinator(cfg)
    subprocess.run([
        "scp","-q","-o","StrictHostKeyChecking=accept-new",
        "-i",cfg["ssh"]["key"],
        str(hnsw_so),
        f'{cfg["ssh"]["user"]}@{w["host"]}:{root}/venv/lib/python3.9/site-packages/{hnsw_so.name}'
    ],check=True)
    verify_code = (
        "import hnswlib, numpy; "
        "print('hnswlib OK', hnswlib.__file__); "
        "print('numpy', numpy.__version__)"
    )
    verify_cmd = (
        f"cd {root} && {root}/venv/bin/python -c "
        + shlex.quote(verify_code)
    )
    ssh.run(w["host"], verify_cmd)

    rpc_root=Path(cfg["paths"]["rpc_package"])/"trustann/rpc"
    # Copy the RPC runtime directly from the coordinator to the worker.
    subprocess.run([
        "scp","-q","-o","StrictHostKeyChecking=accept-new",
        "-i",cfg["ssh"]["key"],
        str(rpc_root/"worker.proto"),
        str(rpc_root/"worker_server.py"),
        str(rpc_root/"worker_client.py"),
        str(rpc_root/"__init__.py"),
        str(Path(cfg["paths"]["rpc_package"]) / "trustann/models.py"),
        str(Path(cfg["paths"]["rpc_package"]) / "trustann/fault.py"),
        f'{cfg["ssh"]["user"]}@{w["host"]}:{root}/trustann/rpc/'
    ],check=True)

    ssh.run(
        w["host"],
        f"cd {root} && {root}/venv/bin/python -m grpc_tools.protoc "
        f"-I trustann/rpc --python_out=trustann/rpc "
        f"--grpc_python_out=trustann/rpc trustann/rpc/worker.proto"
    )

    sid=int(w["shard"]); rid=int(w["replica"])
    src=f"/data/trustann/deep100k/shards/shard{sid}"
    dst=f"{root}/data/shard{sid}/replica{rid}"
    ssh.run(w["host"],f"mkdir -p {dst}")

    # Copy the shard from the coordinator to the worker over the private VPC path.
    subprocess.run([
        "scp","-q","-o","StrictHostKeyChecking=accept-new",
        "-i",cfg["ssh"]["key"],"-r",
        f"{src}/.",
        f'{cfg["ssh"]["user"]}@{w["host"]}:{dst}/'
    ],check=True)

    log=f"{root}/worker_{sid}_{rid}.log"
    ssh.run(w["host"],f"""set -e
if [ -f {root}/worker.pid ]; then
  kill $(cat {root}/worker.pid) 2>/dev/null || true
  rm -f {root}/worker.pid
fi
cd {root}
nohup env PYTHONPATH={root} {root}/venv/bin/python -m trustann.rpc.worker_server \
  --host 0.0.0.0 --port {w['port']} --shard-id {sid} --replica-id {rid} \
  --index {dst}/index.bin --ids {dst}/global_ids.npy \
  > {log} 2>&1 < /dev/null &
echo $! > {root}/worker.pid
""")
    return True

def deploy_workers(cfg):
    package_and_install(cfg)
    for w in cfg["workers"]:
        print(f"DEPLOY {w['name']} {w['host']} shard={w['shard']} replica={w['replica']}")
        configure_worker(cfg,w)
    # wait and health check
    time.sleep(3)
    for w in cfg["workers"]:
        c=WorkerClient(w["host"],int(w["port"]))
        h=c.health()
        if not h.ok: raise RuntimeError(f"Health failed: {w['name']}")
        print(f"READY {w['name']} shard={h.shard_id} replica={h.replica_id} vectors={h.indexed_vectors}")

def worker_debug(cfg, host):
    """Run diagnostics on one worker through the coordinator's VPC SSH."""
    ssh=SSH(cfg["ssh"]["user"],cfg["ssh"]["key"],cfg["ssh"]["connect_timeout_s"])
    root="/home/ec2-user/trustann-worker"
    cmd = f"""set +e
echo '=== OS ==='
uname -a
cat /etc/os-release | head -n 8
echo '=== Python/compiler ==='
python3 --version
command -v gcc; gcc --version | head -n 1
command -v g++; g++ --version | head -n 1
echo '=== C++11 compile test ==='
tmp=$(mktemp /tmp/cxx11.XXXXXX.cpp)
printf '%s\\n' '#include <iostream>' 'int main(){{std::cout << 1;}}' > "$tmp"
g++ -std=c++11 "$tmp" -o "${{tmp%.cpp}}.out"
echo "cxx11_rc=$?"
rm -f "$tmp" "${{tmp%.cpp}}.out"
echo '=== Worker venv ==='
{root}/venv/bin/python --version
{root}/venv/bin/python -m pip --version
{root}/venv/bin/python -c 'import sys; print(sys.executable)'
echo '=== hnswlib ==='
{root}/venv/bin/python -c 'import hnswlib; print(hnswlib.__file__)'
echo '=== NumPy ==='
{root}/venv/bin/python -c 'import numpy; print(numpy.__version__)'
echo '=== port ==='
ss -lntp 2>/dev/null | grep -E ':(50051|50052)\\b' || true
"""
    return ssh.run(host, cmd, check=False)

def stop_workers(cfg):
    ssh=SSH(cfg["ssh"]["user"],cfg["ssh"]["key"],cfg["ssh"]["connect_timeout_s"])
    root="/home/ec2-user/trustann-worker"
    for w in cfg["workers"]:
        ssh.run(
            w["host"],
            f"if [ -f {root}/worker.pid ]; then "
            f"kill $(cat {root}/worker.pid) 2>/dev/null || true; "
            f"rm -f {root}/worker.pid; fi",
            check=False
        )

def run_experiments(cfg, groups):
    out=Path("results")/now_id()
    for d in ["raw","csv","figures","tables","logs"]: (out/d).mkdir(parents=True,exist_ok=True)
    manifest={"config":cfg,"groups":groups,"weak_scaling":False,"status":"started","started_at":time.time()}
    write_json(out/"manifest.json",manifest)
    queries=load_queries(cfg["paths"]["query_file"],cfg["dataset"]["query_count"],cfg["dataset"]["dimension"],cfg["dataset"]["query_seed"])
    clients={w["name"]:WorkerClient(w["host"],int(w["port"])) for w in cfg["workers"]}
    rng=np.random.default_rng(cfg["dataset"]["query_seed"])
    runner=ExperimentRunner(cfg,str(out),clients,cfg["workers"],queries,rng)
    grouped={}
    if "trustbind" in groups:
        grouped["trustbind"]=runner.trustbind_ablation(cfg["experiments"]["ablation_queries"])
        grouped["integrity"]=runner.integrity(cfg["experiments"]["integrity_queries"])
    if "mandatory" in groups:
        grouped["clean_overhead"]=runner.clean_overhead(cfg["experiments"].get("clean_overhead_queries",150))
        grouped["retrieval_attacks"]=runner.retrieval_attacks(cfg["experiments"].get("retrieval_attack_queries",150))
    if "optional" in groups:
        grouped["kmax_recovery"]=runner.kmax_recovery_final(cfg["experiments"].get("kmax_queries",100))
        grouped["consistency_independence_ablation"]=runner.consistency_independence_ablation_final(cfg["experiments"].get("consistency_ablation_queries",100))
    if "cross_shard" in groups: grouped["cross_shard"]=runner.cross_shard(cfg["experiments"]["cross_shard_queries"])
    if "offpath" in groups: grouped["offpath"]=runner.offpath(cfg["experiments"]["offpath_loads_qps"])
    if "failures" in groups: grouped["failures"]=runner.failure_sweep(cfg["experiments"]["failure_percentages"],cfg["experiments"]["failure_queries"])
    if "fanout" in groups: grouped["fanout"]=runner.fanout(cfg["experiments"]["fanouts"])
    if "recovery" in groups: grouped["recovery"]=runner.recovery(cfg["experiments"]["recovery_events"])
    if "coordshift" in groups: grouped["coordshift_resilience"]=runner.coordshift_resilience()
    for k,v in grouped.items():
        if v: write_csv(out/"csv"/f"{k}.csv",v)
    write_json(out/"raw"/"grouped.json",grouped)
    make_plots([x for v in grouped.values() for x in v],str(out/"figures"))
    write_tables(grouped,str(out/"tables"))
    write_json(out/"manifest.json",{**manifest,"status":"completed","finished_at":time.time(),
                                     "experiment_counts":{k:len(v) for k,v in grouped.items()}})
    print(f"RESULTS={out}")
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--config",required=True)
    p.add_argument("--deploy",action="store_true")
    p.add_argument("--run",action="store_true")
    p.add_argument("--groups",default="")
    p.add_argument("--no-cleanup",action="store_true")
    p.add_argument("--stop-workers",action="store_true")
    p.add_argument("--aws-status",action="store_true")
    p.add_argument("--worker-debug",default="")
    a=p.parse_args()
    cfg=cfg_from_topology(a.config)
    if a.aws_status:
        print("Coordinator control plane OK; worker inventory is owned by Mac AWS CLI.")
        return
    if a.worker_debug:
        worker_debug(cfg, a.worker_debug); return
    if a.deploy:
        deploy_workers(cfg); return
    if a.stop_workers:
        stop_workers(cfg); return
    if a.run:
        names=["trustbind","cross_shard","offpath","failures","fanout","recovery","coordshift","mandatory"]
        groups=names if not a.groups else [x.strip() for x in a.groups.split(",") if x.strip()]
        try:
            run_experiments(cfg,groups)
        finally:
            if not a.no_cleanup: stop_workers(cfg)
        return
    p.error("choose --deploy, --run, --stop-workers, or --aws-status")

if __name__=="__main__": main()
