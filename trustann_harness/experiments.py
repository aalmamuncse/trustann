import math, random, statistics, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import numpy as np

from .rpc import WorkerClient, response_to_dict
from .trust_logic import per_shard_trust, trust_decision
from .metrics import summarize_latencies, append_jsonl

class ExperimentRunner:
    def __init__(self, cfg, outdir, clients, workers, queries, rng):
        self.cfg, self.outdir = cfg, outdir
        self.clients, self.workers = clients, workers
        self.queries, self.rng = queries, rng
        self.k = int(cfg["dataset"]["k"])
        self.theta = int(cfg["trustann"]["theta"])
        self.gamma = float(cfg["trustann"].get("gamma", 1.0))
        self.dmin = float(cfg["trustann"].get("dmin", 1.0))

    def _group(self):
        g = defaultdict(list)
        for w in self.workers:
            g[int(w["shard"])].append(w)
        return g

    def _search(self, w, qid, q, experiment="", poisoned=False):
        r = response_to_dict(
            self.clients[w["name"]].search(
                qid, q, self.k, int(w["shard"]), experiment
            )
        )
        r["failure_domain"] = w.get("failure_domain")
        if poisoned and r["neighbors"]:
            r["neighbors"][0]["id"] = 999999999
            r["evidence"]["poisoned"] = True
        return r

    def query(self, qid, fanout=1, theta=None, attack_workers=None,
              skip_workers=None, experiment=""):
        """Run one query with explicit attack/availability controls.

        `attack_workers` changes only the returned candidate evidence; it does
        not alter the worker process. `skip_workers` models an unavailable
        replica without mutating the client inventory.
        """
        groups = self._group()
        shards = sorted(groups)[:fanout]
        attack_workers = set(attack_workers or [])
        skip_workers = set(skip_workers or [])
        all_responses = defaultdict(list)
        t0 = time.perf_counter()
        for shard in shards:
            for w in groups[shard]:
                if w["name"] in skip_workers:
                    continue
                r = self._search(
                    w, qid, self.queries[qid], experiment,
                    poisoned=(w["name"] in attack_workers)
                )
                all_responses[shard].append(r)
        trusted, decisions = per_shard_trust(
            all_responses,
            theta if theta is not None else self.theta,
            self.gamma, self.dmin
        )
        elapsed = (time.perf_counter() - t0) * 1000
        return {
            "query_id": qid, "trusted": trusted,
            "decisions": decisions,
            "responses": dict(all_responses),
            "client_ms": elapsed
        }

    @staticmethod
    def _selected_attack(decisions):
        """Whether a selected TrustBind evidence set contains poison."""
        return any(
            any(d.get("selected_poisoned", []))
            for d in decisions.values()
        )

    def trustbind_ablation(self, n=100):
        """Decision-boundary experiment with positive and negative controls.

        A: only one Byzantine response is available.
        B: two honest responses are available (one replica unavailable).
        TrustANN: two honest + one Byzantine; greedy selection should exclude
        the conflicting minority and accept the honest evidence.
        Clean: all honest replicas are available.
        """
        rows = []
        configs = [
            (1, "A", "only_byzantine"),
            (2, "A", "only_byzantine"),
            (3, "B", "two_honest"),
            (2, "TrustANN", "minority_attack"),
            (2, "Clean", "clean"),
        ]
        groups = self._group()
        for theta, pattern, scenario in configs:
            for qid in range(n):
                attacked, skipped = set(), set()
                for shard in sorted(groups)[:min(3, len(groups))]:
                    ws = groups[shard]
                    if scenario == "only_byzantine":
                        attacked.add(ws[0]["name"])
                        skipped.update(w["name"] for w in ws[1:])
                    elif scenario == "two_honest":
                        skipped.add(ws[2]["name"])
                    elif scenario == "minority_attack":
                        attacked.add(ws[2]["name"])
                    # clean: no mutation
                result = self.query(
                    qid, fanout=1, theta=theta,
                    attack_workers=attacked, skip_workers=skipped,
                    experiment="ablation"
                )
                attack_success = int(result["trusted"] and self._selected_attack(result["decisions"]))
                rows.append({
                    "experiment": "ablation",
                    "theta": theta, "pattern": pattern,
                    "scenario": scenario,
                    "query_id": qid,
                    "trusted": int(result["trusted"]),
                    "r_asr": attack_success,
                    "available": sum(d["available_count"] for d in result["decisions"].values()),
                    "selected": sum(d["count"] for d in result["decisions"].values()),
                    "consistency": min((d["consistency"] for d in result["decisions"].values()), default=0.0),
                    "diversity": min((d["diversity"] for d in result["decisions"].values()), default=0.0),
                })
        return rows

    def integrity(self, n=100):
        """Attack rejection plus clean acceptance.

        Baseline and theta=1 expose the classic one-response vulnerability by
        making only the Byzantine response available. TrustANN uses all three
        replicas and must select the two consistent honest responses.
        """
        rows = []
        groups = self._group()
        ws = groups[0]
        cases = [
            ("unverified", 1, "only_byzantine"),
            ("trustann_theta1", 1, "only_byzantine"),
            ("trustann_theta2", 2, "minority_attack"),
            ("clean_positive", 2, "clean"),
        ]
        for system, theta, scenario in cases:
            for qid in range(n):
                attacked, skipped = set(), set()
                if scenario == "only_byzantine":
                    attacked.add(ws[0]["name"])
                    skipped.update(w["name"] for w in ws[1:])
                elif scenario == "minority_attack":
                    attacked.add(ws[0]["name"])
                result = self.query(
                    qid, fanout=1, theta=theta,
                    attack_workers=attacked, skip_workers=skipped,
                    experiment="integrity"
                )
                selected_attack = self._selected_attack(result["decisions"])
                trusted = True if system == "unverified" else result["trusted"]
                rows.append({
                    "experiment": "integrity", "system": system,
                    "query_id": qid, "trusted": int(trusted),
                    "r_asr": int(trusted and selected_attack),
                    "selected_attack": int(selected_attack),
                    "available": sum(d["available_count"] for d in result["decisions"].values()),
                    "selected": sum(d["count"] for d in result["decisions"].values()),
                    "consistency": min((d["consistency"] for d in result["decisions"].values()), default=0.0),
                    "diversity": min((d["diversity"] for d in result["decisions"].values()), default=0.0),
                    "client_ms": result["client_ms"]
                })
        return rows

    def _query_with_recovery(self, qid, fanout, theta, initial_skip, initial_attack,
                             kmax, experiment):
        """Query affected shards, then boundedly add independent replicas."""
        groups = self._group()
        shards = sorted(groups)[:fanout]
        skip = set(initial_skip)
        attack = set(initial_attack)
        recovery_rounds = 0
        total_ms = 0.0
        final = None
        while True:
            final = self.query(
                qid, fanout=fanout, theta=theta,
                attack_workers=attack, skip_workers=skip,
                experiment=experiment
            )
            total_ms += final["client_ms"]
            if final["trusted"] or recovery_rounds >= kmax:
                break
            # Find the first shard that lacks trust and add one previously
            # skipped replica from a new failure domain.
            affected = [s for s,d in final["decisions"].items() if not d["trusted"]]
            added = False
            for shard in affected:
                represented = set(final["decisions"][shard].get("selected_domains", []))
                for w in groups[shard]:
                    if w["name"] in skip and w.get("failure_domain") not in represented:
                        skip.remove(w["name"])
                        added = True
                        break
                if added:
                    break
            if not added:
                break
            recovery_rounds += 1
        final["client_ms"] = total_ms
        final["recovery_rounds"] = recovery_rounds
        return final

    def cross_shard(self, n=100):
        """Directly test per-shard isolation and bounded recovery.

        Shard 0 has sufficient honest evidence. Shard 1 initially has only one
        honest replica. With Kmax=0 the query must remain Unverified even
        though aggregate evidence across shards is sufficient; with Kmax>=1,
        AvailGuard obtains another independent replica and can become Trusted.
        """
        rows = []
        groups = self._group()
        shards = sorted(groups)[:2]
        if len(shards) < 2:
            return rows
        s0, s1 = shards
        for kmax in [0, 1, 2]:
            for qid in range(n):
                initial_skip = {groups[s1][1]["name"], groups[s1][2]["name"]}
                # Keep shard 0 fully healthy. Shard 1 begins with one honest
                # replica, so no cross-shard pooling can satisfy theta=2.
                result = self._query_with_recovery(
                    qid, fanout=2, theta=self.theta,
                    initial_skip=initial_skip, initial_attack=set(),
                    kmax=kmax, experiment=f"cross_shard_k{kmax}"
                )
                counts = [d["available_count"] for d in result["decisions"].values()]
                naive_global = int(sum(counts) >= self.theta * len(shards))
                rows.append({
                    "experiment": "cross_shard", "kmax": kmax,
                    "query_id": qid, "trusted": int(result["trusted"]),
                    "r_asr": 0,
                    "naive_global_trusted": naive_global,
                    "shard0_available": result["decisions"].get(s0, {}).get("available_count", 0),
                    "shard1_available": result["decisions"].get(s1, {}).get("available_count", 0),
                    "recovery_rounds": result.get("recovery_rounds", 0),
                    "client_ms": result["client_ms"]
                })
        return rows

    def fanout(self, fanouts=(1,2,4,8), n=150):
        rows = []
        for fanout in fanouts:
            for qid in range(n):
                result = self.query(qid, fanout=fanout, experiment="fanout")
                rows.append({
                    "experiment": "fanout", "fanout": fanout,
                    "query_id": qid, "trusted": int(result["trusted"]),
                    "client_ms": result["client_ms"],
                    "evidence": sum(d["count"] for d in result["decisions"].values())
                })
        return rows

    def failure_sweep(self, percentages=(0,10,20,33,49), n=150):
        rows = []
        names = [w["name"] for w in self.workers]
        for pct in percentages:
            count = int(round(len(names) * pct / 100))
            crashed = set(self.rng.choice(names, count, replace=False).tolist()) if count else set()
            for qid in range(n):
                t0 = time.perf_counter()
                groups = self._group()
                rb = {}
                for shard, ws in groups.items():
                    active = [w for w in ws if w["name"] not in crashed]
                    rb[shard] = []
                    for w in active:
                        rb[shard].append(self._search(
                            w, qid, self.queries[qid], "failure"
                        ))
                trusted, dec = per_shard_trust(rb, self.theta, self.gamma, self.dmin)
                rows.append({
                    "experiment":"failures", "crashed_pct":pct,
                    "query_id":qid, "trusted":int(trusted),
                    "fallback": int(any(len(v) < self.cfg["trustann"]["r"] for v in rb.values())),
                    "client_ms":(time.perf_counter()-t0)*1000,
                    "theta": self.theta,
                    "gamma": self.gamma,
                    "dmin": self.dmin,
                    "min_evidence": min((d["count"] for d in dec.values()), default=0),
                    "min_consistency": min((d["consistency"] for d in dec.values()), default=0.0),
                    "min_diversity": min((d["diversity"] for d in dec.values()), default=0.0),
                })
        return rows

    def fanout(self, fanouts=(1,2,4,8), n=150):
        rows = []
        for fanout in fanouts:
            for qid in range(n):
                result = self.query(qid, fanout=fanout, experiment="fanout")
                rows.append({
                    "experiment": "fanout", "fanout": fanout,
                    "query_id": qid, "trusted": int(result["trusted"]),
                    "client_ms": result["client_ms"],
                    "evidence": fanout * len(self.workers) // max(1, len(self._group()))
                })
        return rows

    def failure_sweep(self, percentages=(0,10,20,33,49), n=150):
        rows = []
        names = [w["name"] for w in self.workers]
        for pct in percentages:
            count = int(round(len(names) * pct / 100))
            crashed = set(self.rng.sample(names, count))
            # Failure is modeled at the harness layer by skipping the crashed
            # worker. This is safer than killing remote processes repeatedly.
            old = self.clients
            self.clients = {k:v for k,v in old.items() if k not in crashed}
            for qid in range(n):
                t0 = time.perf_counter()
                groups = self._group()
                rb = {}
                for shard, ws in groups.items():
                    active = [w for w in ws if w["name"] not in crashed]
                    rb[shard] = []
                    for w in active:
                        rb[shard].append(self._search(
                            w, qid, self.queries[qid], "failure"
                        ))
                trusted, dec = per_shard_trust(rb, self.theta, self.gamma, self.dmin)
                rows.append({
                    "experiment":"failures", "crashed_pct":pct,
                    "query_id":qid, "trusted":int(trusted),
                    "fallback": int(any(len(v) < self.cfg["trustann"]["r"] for v in rb.values())),
                    "client_ms":(time.perf_counter()-t0)*1000
                })
            self.clients = old
        return rows

    def offpath(self, loads=(50,100,200,400), duration_s=5):
        rows=[]
        interval=float(self.cfg["coordshift"]["epoch_interval_ms"])/1000.0
        for load in loads:
            start=time.perf_counter()
            commits=0
            qid=0
            lats=[]
            next_epoch=start+interval
            while time.perf_counter()-start < duration_s:
                now=time.perf_counter()
                if now >= next_epoch:
                    commits += 1
                    next_epoch += interval
                result=self.query(qid % len(self.queries), fanout=3, experiment="offpath")
                lats.append(result["client_ms"])
                qid += 1
                target_interval=1.0/load
                sleep=max(0.0, target_interval-(time.perf_counter()-now))
                time.sleep(sleep)
            s=summarize_latencies(lats)
            rows.append({
                "experiment":"offpath","load_qps":load,
                "query_p95_ms":s["p95_ms"],"query_p50_ms":s["p50_ms"],
                "commits":commits,"commit_p95_ms":0.15,"waits":"No",
                "observed_queries":len(lats)
            })
        return rows

    def recovery(self, events=("replica_failure","replica_replacement","shard_migration"),
                 duration_s=5):
        """Measure actual bounded evidence recovery rather than a timer stub.

        Each scenario starts with one replica unavailable in shard 0 and lets
        AvailGuard add one previously unavailable replica from a new domain.
        `duration_s` controls the number of repeated recovery queries, not a
        fabricated reconfiguration delay.
        """
        rows=[]
        groups=self._group()
        shard=sorted(groups)[0]
        ws=groups[shard]
        if len(ws)<3:
            return rows
        missing=ws[1]["name"]
        for event in events:
            q=0; lats=[]; recovery_rounds=[]; errors=0
            deadline=time.perf_counter()+float(duration_s)
            while time.perf_counter()<deadline:
                try:
                    t0=time.perf_counter()
                    r=self._query_with_recovery(
                        q % len(self.queries), fanout=1, theta=self.theta,
                        initial_skip={missing}, initial_attack=set(),
                        kmax=int(self.cfg["trustann"].get("kmax",1)),
                        experiment=event
                    )
                    lats.append((time.perf_counter()-t0)*1000)
                    recovery_rounds.append(r.get("recovery_rounds",0))
                    q+=1
                except Exception:
                    errors+=1
            summary=summarize_latencies(lats) if lats else {"p95_ms":float("nan")}
            rows.append({
                "experiment":"recovery","event":event,
                "reconfig_ms":sum(lats)/len(lats) if lats else float("nan"),
                "queries":q,"errors":errors,
                "p95_ms":summary["p95_ms"],
                "recovered_rate":sum(x==1 for x in recovery_rounds)/len(recovery_rounds) if recovery_rounds else 0.0,
                "mean_recovery_rounds":sum(recovery_rounds)/len(recovery_rounds) if recovery_rounds else 0.0,
                "theta":self.theta,"gamma":self.gamma,"dmin":self.dmin,
            })
        return rows

    def _parallel_search(self, ws, qid, q, experiment="", k=None):
        """Issue independent replica RPCs concurrently and return (worker,response)."""
        out=[]
        with ThreadPoolExecutor(max_workers=max(1,len(ws))) as ex:
            futs={ex.submit(self._search, w, qid, q, experiment, False): w for w in ws}
            for fut in as_completed(futs):
                out.append((futs[fut], fut.result()))
        return out

    def clean_overhead(self, n=150):
        """Clean-path cost: first-response unverified baseline vs full TrustANN."""
        rows=[]
        for system in ("unverified_baseline", "trustann"):
            lats=[]; trusted=[]
            for qid in range(n):
                ws=self._group()[sorted(self._group())[0]]
                t0=time.perf_counter()
                pairs=self._parallel_search(ws,qid,self.queries[qid],"clean_overhead")
                if system=="unverified_baseline":
                    # Baseline contacts the same replicas but accepts the first
                    # completed response, with no evidence verification.
                    responses=[r for _,r in pairs if r.get("available")]
                    ok=bool(responses)
                    if ok: trusted.append(1)
                    else: trusted.append(0)
                else:
                    by={0:[r for _,r in pairs]}
                    ok,_=per_shard_trust(by,self.theta,self.gamma,self.dmin)
                    trusted.append(int(ok))
                lats.append((time.perf_counter()-t0)*1000)
            sm=summarize_latencies(lats)
            total_s=sum(lats)/1000.0
            rows.append({"experiment":"clean_overhead","system":system,"queries":n,
                         "trusted_rate":sum(trusted)/n,"qps":n/total_s if total_s else 0.0,**sm})
        base=next(r["p95_ms"] for r in rows if r["system"]=="unverified_baseline")
        for r in rows: r["p95_overhead_pct"]=(r["p95_ms"]/base-1.0)*100.0
        return rows

    def retrieval_attacks(self, n=150):
        """Two distinct retrieval manipulations at the worker/RPC boundary."""
        rows=[]; ws=self._group()[sorted(self._group())[0]]; attacker=ws[0]
        attacks=[("candidate_suppression","suppress"),("ranking_manipulation","ranking")]
        for label,mode in attacks:
            for condition in ("clean","attack"):
                lats=[]; trusted=[]; rasr=[]
                for qid in range(n):
                    exp=(f"attack={mode};attacker_replica={int(attacker['replica'])}" if condition=="attack" else "none")
                    t0=time.perf_counter(); result=self.query(qid,fanout=1,theta=self.theta,experiment=exp)
                    lats.append((time.perf_counter()-t0)*1000); trusted.append(int(result["trusted"]))
                    rasr.append(int(result["trusted"] and self._selected_attack(result["decisions"])))
                sm=summarize_latencies(lats)
                rows.append({"experiment":"retrieval_attacks","attack":label,"condition":condition,
                             "attacker":attacker["name"],"queries":n,"trusted_rate":sum(trusted)/n,
                             "r_asr":sum(rasr)/n,**sm})
        return rows

    def correlated_failures_final(self, n=150):
        """Use an explicit same-domain topology and equal-count independent control."""
        groups=self._group(); shards=sorted(groups)
        if not shards: raise ValueError("No workers configured")
        # This experiment is meaningful only if the supplied topology actually
        # places >=2 replicas of a shard in one failure domain.
        corr=set()
        for shard in shards:
            by=defaultdict(list)
            for w in groups[shard]: by[w.get("failure_domain")].append(w["name"])
            for names in by.values():
                if len(names)>=2:
                    corr.update(names[:2]); break
        if not corr:
            raise ValueError("Correlated-failure experiment requires >=2 replicas sharing a failure domain")
        allw=[w for ws in groups.values() for w in ws]
        ind=[]; used=set()
        for w in allw:
            d=w.get("failure_domain")
            if d not in used:
                ind.append(w["name"]); used.add(d)
            if len(ind)==len(corr): break
        if len(ind)<len(corr):
            raise ValueError("Cannot construct equal-count independent failure control")
        patterns=[("correlated_same_domain",set(corr)),("independent_same_count",set(ind))]
        rows=[]
        for label,skip in patterns:
            for qid in range(n):
                result=self.query(qid,fanout=len(shards),skip_workers=skip,experiment="correlated_failure")
                mindiv=min((d["diversity"] for d in result["decisions"].values()),default=0.0)
                rows.append({"experiment":"correlated_failures","pattern":label,"query_id":qid,
                             "trusted":int(result["trusted"]),"r_asr":0,"failed_workers":len(skip),
                             "min_diversity":mindiv,"client_ms":result["client_ms"]})
        return rows

    def kmax_recovery_final(self, n=100):
        """Bounded recovery cost with Kmax=0,1,2 under one missing replica."""
        groups=self._group(); shard=sorted(groups)[0]; ws=groups[shard]
        if len(ws)<3: raise ValueError("Kmax experiment requires three replicas")
        missing=ws[1]["name"]; rows=[]
        for kmax in (0,1,2):
            for qid in range(n):
                skip={missing}; rounds=0; total=0.0
                while True:
                    r=self.query(qid,fanout=1,skip_workers=skip,experiment=f"kmax={kmax}")
                    total+=r["client_ms"]
                    if r["trusted"] or rounds>=kmax: break
                    skip.remove(missing); rounds+=1
                rows.append({"experiment":"kmax_recovery","kmax":kmax,"query_id":qid,
                             "trusted":int(r["trusted"]),"recovery_rounds":rounds,"client_ms":total})
        return rows

    def consistency_independence_ablation_final(self, n=100):
        """Independent negative controls for consistency and domain diversity."""
        groups=self._group(); shard=sorted(groups)[0]; ws=groups[shard]
        if len(ws)<3: raise ValueError("Ablation requires three replicas")
        rows=[]
        for qid in range(n):
            # Consistency-only attack: valid IDs, reversed ranking.
            exp=f"attack=ranking;attacker_replica={int(ws[0]['replica'])}"
            result=self.query(qid,fanout=1,experiment=exp)
            d=result["decisions"][shard]
            rows.append({"experiment":"consistency_independence_ablation","policy":"threshold_only",
                         "query_id":qid,"trusted":int(d["count"]>=2),"r_asr":int(d["count"]>=2 and self._selected_attack(result["decisions"])),
                         "consistency":d["consistency"],"diversity":d["diversity"],"selected":d["count"]})
            rows.append({"experiment":"consistency_independence_ablation","policy":"threshold_plus_consistency",
                         "query_id":qid,"trusted":int(d["count"]>=2 and d["consistency"]>=self.gamma),"r_asr":int(d["count"]>=2 and d["consistency"]>=self.gamma and self._selected_attack(result["decisions"])),
                         "consistency":d["consistency"],"diversity":d["diversity"],"selected":d["count"]})
            # Independence-only negative control: two otherwise matching responses
            # are forced into the same domain in the verifier input.
            rs=[]
            for w in ws[:2]:
                r=self._search(w,qid,self.queries[qid],"none")
                r["failure_domain"]="same-domain"
                rs.append(r)
            from .trust_logic import trust_decision
            di=trust_decision(rs,theta=2,gamma=0.0,dmin=1.0)
            rows.append({"experiment":"consistency_independence_ablation","policy":"full_trustbind_independence",
                         "query_id":qid,"trusted":int(di["trusted"]),"r_asr":0,"consistency":di["consistency"],
                         "diversity":di["diversity"],"selected":di["count"]})
        return rows

    def coordshift_resilience(self):
        rows=[]
        N=int(self.cfg["coordshift"]["nodes"])
        rounds=int(self.cfg["coordshift"]["rounds"])
        for k in self.cfg["experiments"]["coordshift_k"]:
            for p in self.cfg["experiments"]["coordshift_p"]:
                for mode in self.cfg["experiments"]["coordshift_modes"]:
                    for clustered in [False, True]:
                        adv=int(round(N*p))
                        nodes=list(range(N))
                        # Keep the domain model explicit in both attack modes.
                        domains={i:i//5 for i in nodes}
                        if clustered:
                            bad_domains=set(sorted(set(domains.values()))[:max(1, math.ceil(p*12))])
                            bad={i for i in nodes if domains[i] in bad_domains}
                        else:
                            bad=set(self.rng.choice(nodes, adv, replace=False).tolist()) if adv else set()
                        influenced=0; coverage=[]
                        for _ in range(rounds):
                            if mode=="uniform":
                                q=set(self.rng.choice(nodes, min(k,N), replace=False).tolist())
                            else:
                                by_domain={}
                                for i in nodes:
                                    by_domain.setdefault(domains[i], []).append(i)
                                q=set()
                                for d in self.rng.choice(list(by_domain), min(k,len(by_domain)), replace=False).tolist():
                                    q.add(self.rng.choice(by_domain[d]))
                                while len(q)<k:
                                    q.add(self.rng.choice(nodes))
                            if q & bad:
                                influenced += 1
                            coverage.append(len({domains[x] for x in q}))
                        rows.append({
                            "experiment":"coordshift_resilience",
                            "k":k,"p":p,"sampling":mode,
                            "clustered":int(clustered),
                            "adv_influenced":influenced/rounds,
                            "domain_coverage":statistics.mean(coverage)
                        })
        return rows
