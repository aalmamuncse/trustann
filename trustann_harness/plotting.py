import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def _save(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()

def make_plots(csv_rows, outdir):
    by_exp={}
    for r in csv_rows:
        by_exp.setdefault(r.get("experiment"), []).append(r)


    rows=by_exp.get("ablation", [])
    if rows:
        groups={}
        for r in rows:
            key=f"{r['pattern']}:{r['scenario']}"
            groups.setdefault(key, []).append(int(r["trusted"]))
        labels=list(groups)
        vals=[sum(groups[x])/len(groups[x]) for x in labels]
        plt.figure(figsize=(max(6, len(labels)*1.3), 4))
        plt.bar(range(len(labels)), vals)
        plt.xticks(range(len(labels)), labels, rotation=30, ha="right")
        plt.ylabel("Trusted-query rate")
        plt.ylim(0,1.05)
        plt.title("TrustBind decision-boundary ablation")
        _save(os.path.join(outdir,"trustbind_ablation.pdf"))

    rows=by_exp.get("cross_shard", [])
    if rows:
        groups={}
        for r in rows:
            groups.setdefault(int(r["kmax"]), []).append(int(r["trusted"]))
        xs=sorted(groups)
        ys=[sum(groups[x])/len(groups[x]) for x in xs]
        plt.figure()
        plt.plot(xs, ys, marker="o")
        plt.xlabel("AvailGuard Kmax")
        plt.ylabel("Trusted-query rate")
        plt.ylim(-0.02,1.02)
        plt.title("Per-shard isolation and bounded recovery")
        _save(os.path.join(outdir,"cross_shard_recovery.pdf"))

    rows=by_exp.get("fanout", [])
    if rows:
        groups={}
        for r in rows:
            groups.setdefault(int(r["fanout"]), []).append(float(r["client_ms"]))
        xs=sorted(groups)
        ys=[sum(groups[x])/len(groups[x]) for x in xs]
        plt.figure()
        plt.plot(xs, ys, marker="o")
        plt.xlabel("Fan-out")
        plt.ylabel("Mean client latency (ms)")
        plt.title("TrustANN fan-out latency")
        _save(os.path.join(outdir,"fanout_latency.pdf"))

    rows=by_exp.get("failures", [])
    if rows:
        groups={}
        for r in rows:
            groups.setdefault(int(r["crashed_pct"]), []).append(int(r["trusted"]))
        xs=sorted(groups)
        ys=[sum(groups[x])/len(groups[x]) for x in xs]
        plt.figure()
        plt.plot(xs, ys, marker="o")
        plt.xlabel("Crashed replicas (%)")
        plt.ylabel("Trusted-query rate")
        plt.ylim(-0.02,1.02)
        plt.title("AvailGuard failure resilience")
        _save(os.path.join(outdir,"failure_trusted_rate.pdf"))

    rows=by_exp.get("offpath", [])
    if rows:
        xs=[int(r["load_qps"]) for r in rows]
        ys=[float(r["query_p95_ms"]) for r in rows]
        plt.figure()
        plt.plot(xs, ys, marker="o")
        plt.xlabel("Offered load (QPS)")
        plt.ylabel("Query p95 (ms)")
        plt.title("CoordShift off-path behavior")
        _save(os.path.join(outdir,"coordshift_offpath.pdf"))

    rows=by_exp.get("coordshift_resilience", [])
    if rows:
        plt.figure()
        for sampling in sorted(set(r["sampling"] for r in rows)):
            rr=[r for r in rows if r["sampling"]==sampling and not int(r["clustered"])]
            rr=sorted(rr,key=lambda x:(int(x["k"]),float(x["p"])))
            if rr:
                plt.plot(range(len(rr)), [float(x["adv_influenced"]) for x in rr],
                         marker="o", label=sampling)
        plt.xlabel("Configuration index")
        plt.ylabel("Adversary-influenced fraction")
        plt.title("CoordShift adversarial exposure (descriptive)")
        plt.legend()
        _save(os.path.join(outdir,"coordshift_resilience.pdf"))

        plt.figure()
        for sampling in sorted(set(r["sampling"] for r in rows)):
            rr=[r for r in rows if r["sampling"]==sampling and not int(r["clustered"])]
            rr=sorted(rr,key=lambda x:(int(x["k"]),float(x["p"])))
            if rr:
                plt.plot(range(len(rr)), [float(x["domain_coverage"]) for x in rr],
                         marker="o", label=sampling)
        plt.xlabel("Configuration index")
        plt.ylabel("Mean fault-domain coverage")
        plt.title("CoordShift fault-domain diversity")
        plt.legend()
        _save(os.path.join(outdir,"coordshift_domain_coverage.pdf"))
