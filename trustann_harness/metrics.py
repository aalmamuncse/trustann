import csv, json, math, os, statistics

def percentile(values, q):
    xs = sorted(float(x) for x in values if x is not None)
    if not xs:
        return float("nan")
    if len(xs) == 1:
        return xs[0]
    k = (len(xs)-1) * q
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return xs[int(k)]
    return xs[f] + (xs[c]-xs[f])*(k-f)

def summarize_latencies(xs):
    return {
        "p50_ms": percentile(xs, .50),
        "p95_ms": percentile(xs, .95),
        "p99_ms": percentile(xs, .99),
        "mean_ms": statistics.mean(xs) if xs else float("nan"),
    }

def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, sort_keys=True)

def append_jsonl(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(obj, sort_keys=True) + "\n")

def write_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not rows:
        return
    keys = sorted({k for r in rows for k in r})
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
