import os

def latex_table(rows, cols, caption, label, formats=None):
    formats = formats or {}
    lines=[
        r"\begin{table}[t]",
        r"\centering",
        r"\footnotesize",
        rf"\caption{{{caption}}}",
        rf"\label{{{label}}}",
        r"\begin{tabular}{" + "l" * len(cols) + r"}",
        r"\toprule",
        " & ".join(cols) + r" \\",
        r"\midrule"
    ]
    for r in rows:
        vals=[]
        for c in cols:
            v=r.get(c,"--")
            if c in formats and isinstance(v,(int,float)):
                v=formats[c].format(v)
            vals.append(str(v))
        lines.append(" & ".join(vals) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)

def write_tables(data, outdir):
    os.makedirs(outdir, exist_ok=True)
    specs=[
      ("clean_overhead", ["system","trusted_rate","qps","p50_ms","p95_ms","p95_overhead_pct"], "Clean distributed ANN baseline versus TrustANN overhead.", "tab:harness-clean-overhead"),
      ("retrieval_attacks", ["attack","condition","trusted_rate","r_asr","p50_ms","p95_ms"], "TrustANN retrieval manipulation attacks.", "tab:harness-retrieval-attacks"),
      ("correlated_failures", ["pattern","trusted","failed_workers","min_diversity","client_ms"], "Correlated versus independent replica failures.", "tab:harness-correlated-failures"),
      ("kmax_recovery", ["kmax","trusted","recovery_rounds","client_ms"], "AvailGuard bounded recovery sensitivity to Kmax.", "tab:harness-kmax"),
      ("consistency_independence_ablation", ["policy","trusted","r_asr","consistency","diversity","selected"], "TrustBind consistency and independence ablation.", "tab:harness-consistency-independence"),
      ("ablation", ["theta","pattern","scenario","r_asr","trusted","available","selected","consistency","diversity"], "TrustBind decision-boundary and evidence-condition ablation.", "tab:harness-ablation"),
      ("integrity", ["system","r_asr","trusted","selected_attack"], "Retrieval integrity with clean positive and Byzantine-minority controls.", "tab:harness-integrity"),
      ("fanout", ["fanout","client_ms","evidence"], "Fan-out sensitivity measured by the AWS harness.", "tab:harness-fanout"),
      ("failures", ["crashed_pct","trusted","fallback","client_ms","theta","gamma","dmin","min_evidence","min_consistency","min_diversity"], "Replica-failure sweep with explicit trust-condition instrumentation.", "tab:harness-failure"),
      ("cross_shard", ["kmax","trusted","naive_global_trusted","shard0_available","shard1_available","recovery_rounds","client_ms"], "Per-shard evidence isolation and bounded recovery.", "tab:harness-cross-shard"),
      ("offpath", ["load_qps","query_p95_ms","commits","commit_p95_ms","waits"], "CoordShift off-path behavior measured by the AWS harness.", "tab:harness-offpath"),
      ("recovery", ["event","reconfig_ms","queries","errors","p95_ms"], "Recovery and reconfiguration measurements.", "tab:harness-recovery"),
      ("coordshift_resilience", ["k","p","sampling","clustered","adv_influenced","domain_coverage"], "CoordShift resilience measurements.", "tab:harness-coordshift")
    ]
    for exp, cols, cap, label in specs:
        rows=data.get(exp, [])
        if not rows:
            continue

        # Aggregate query-level experiments into one row per configuration.
        if exp in ("fanout", "failures", "integrity", "cross_shard"):
            key_cols = {
                "fanout": ["fanout"],
                "failures": ["crashed_pct"],
                "integrity": ["system"],
                "cross_shard": ["kmax"],
            }[exp]
            groups={}
            for r in rows:
                groups.setdefault(tuple(r.get(c) for c in key_cols), []).append(r)
            out=[]
            for key, rr in groups.items():
                base={c:v for c,v in zip(key_cols,key)}
                # Average every numeric measurement except identifiers.
                for c in cols:
                    if c in key_cols:
                        continue
                    vals=[]
                    for x in rr:
                        v=x.get(c)
                        if isinstance(v,(int,float)) and not isinstance(v,bool):
                            vals.append(float(v))
                    if vals:
                        base[c]=sum(vals)/len(vals)
                    elif rr and c in rr[0]:
                        base[c]=rr[0][c]
                out.append(base)
            rows=out

        text=latex_table(rows, cols, cap, label)
        with open(os.path.join(outdir,f"{exp}.tex"),"w") as f:
            f.write(text)
