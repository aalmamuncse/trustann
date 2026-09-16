# TrustANN

**Anonymous artifact for double-blind review**

<p align="center">
  <strong>Trustworthy Distributed Vector Retrieval under Byzantine Retrieval and Replica Failures</strong>
</p>

<p align="center">
  <em>This repository contains the experimental artifact for TrustANN.</em>
</p>

---

## Artifact Overview

TrustANN is a middleware layer for trustworthy distributed vector retrieval. It operates above existing distributed ANN indexes and provides three complementary mechanisms:

<ul>
<li><strong>TrustBind:</strong> verifies retrieval evidence using replica agreement, consistency, diversity, and provenance.</li>
<li><strong>CoordShift:</strong> performs asynchronous failure-domain-aware coordination without blocking the query critical path.</li>
<li><strong>AvailGuard:</strong> performs bounded recovery when replicas are unavailable, stale, or provide conflicting evidence.</li>
</ul>

The artifact contains the implementation, experiment harness, configuration files, test cases, and scripts used to evaluate these mechanisms.

The artifact is intended to allow reviewers to:

<ol>
<li>verify that the TrustANN retrieval and verification pipeline executes correctly;</li>
<li>reproduce the TrustBind attack-detection and threshold experiments;</li>
<li>evaluate the overhead of verification and distributed retrieval;</li>
<li>exercise failure and recovery scenarios;</li>
<li>evaluate CoordShift's asynchronous operation and failure-domain-aware coordination; and</li>
<li>inspect the implementation and experiment configuration used to obtain the reported results.</li>
</ol>

---

# 1. Getting Started Instructions

This section provides a short path for verifying that the artifact is functional.

## 1.1 Requirements

The artifact requires:

<ul>
<li>Linux or macOS</li>
<li>Python 3.x</li>
<li>Git</li>
<li>Python packages listed in <code>requirements.txt</code></li>
</ul>

The local tests and synthetic experiments do not require an AWS deployment.

For the distributed experiments, the artifact additionally uses:

<ul>
<li>AWS EC2 instances</li>
<li>gRPC communication between coordinator and workers</li>
<li>HNSW-based local ANN indexes</li>
</ul>

> <strong>Note:</strong> The AWS experiments require access to an AWS account and appropriate EC2 permissions. The repository does not contain AWS credentials, private keys, or other secrets.

---

## 1.2 Clone and Install

```bash
git clone <ANONYMOUS-REPOSITORY-URL>
cd TrustANN

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

If the repository provides a different environment specification, use the provided environment/configuration files.

---

## 1.3 Run the Unit Tests

Run the TrustANN logic tests:

```bash
pytest tests/test_trust_logic.py
```

Run the experiment tests:

```bash
pytest tests/test_experiments_synthetic.py
```

Run the complete artifact test suite:

```bash
pytest tests/
```

A successful execution verifies the core TrustBind logic, experiment harness, and synthetic evaluation pipeline.

---

## 1.4 Run a Minimal Synthetic Experiment

The artifact includes synthetic experiment support that does not require an AWS cluster.

Use the provided experiment configuration:

```bash
python orchestrator.py --config config/final_mandatory.json
```

If the repository version uses a different command-line interface, the corresponding options are documented in the configuration and experiment scripts.

The generated output includes experiment measurements that can be used to verify:

<ul>
<li>retrieval verification;</li>
<li>TrustBind acceptance/rejection;</li>
<li>failure handling;</li>
<li>latency measurements; and</li>
<li>experiment summary tables.</li>
</ul>

---

# 2. Detailed Instructions

## 2.1 Artifact Organization

The repository is organized as follows:

```text
TrustANN/
├── trustann/
│   ├── models.py
│   ├── fault.py
│   └── rpc/
│       ├── worker.proto
│       ├── worker_server.py
│       └── worker_client.py
│
├── trustann_harness/
│   ├── experiments.py
│   ├── metrics.py
│   ├── plotting.py
│   ├── remote.py
│   ├── rpc.py
│   ├── tables.py
│   └── trust_logic.py
│
├── tests/
│   ├── test_trust_logic.py
│   ├── test_experiments_synthetic.py
│   └── test_final_mandatory.py
│
├── scripts/
├── orchestrator.py
├── config/
├── requirements.txt
└── README.md
```

The experimental package contains approximately 1.5K lines of Python code, excluding tests, configuration files, and auxiliary scripts.

---

## 2.2 System Configuration

The default TrustANN configuration uses:

<table>
<thead>
<tr>
<th>Parameter</th>
<th>Default</th>
</tr>
</thead>
<tbody>
<tr>
<td>Dataset</td>
<td>Deep10M subset</td>
</tr>
<tr>
<td>Vectors</td>
<td>100K</td>
</tr>
<tr>
<td>Dimension</td>
<td>96</td>
</tr>
<tr>
<td>Distance</td>
<td>L2</td>
</tr>
<tr>
<td>Shards</td>
<td>3</td>
</tr>
<tr>
<td>Replicas per shard</td>
<td>3</td>
</tr>
<tr>
<td>Total workers</td>
<td>9</td>
</tr>
<tr>
<td>HNSW M</td>
<td>16</td>
</tr>
<tr>
<td>HNSW efConstruction</td>
<td>200</td>
</tr>
<tr>
<td>HNSW efSearch</td>
<td>64</td>
</tr>
<tr>
<td>TrustBind threshold (<code>&theta;</code>)</td>
<td>2</td>
</tr>
<tr>
<td>AvailGuard recovery budget (<code>K<sub>max</sub></code>)</td>
<td>1</td>
</tr>
<tr>
<td>CoordShift quorum</td>
<td>9</td>
</tr>
</tbody>
</table>

---

# 3. Reproducing the Main Experiments

The experiments are organized around five evaluation questions.

## Q1. TrustBind Verification

The TrustBind experiments evaluate whether retrieval evidence is accepted only when sufficient independent and consistent evidence is available.

The experiments include:

<ul>
<li>threshold-boundary experiments;</li>
<li>replica-counting ablations;</li>
<li>consistency-based verification;</li>
<li>candidate-suppression attacks;</li>
<li>ranking-manipulation attacks; and</li>
<li>integrity/attack positive-control experiments.</li>
</ul>

The relevant experiment can be invoked through the experiment harness using the provided configuration.

The primary result to inspect is whether the attack succeeds in producing a trusted retrieval result. The corresponding metric is reported as <code>R-ASR</code>.

A successful verification run should show:

```text
TrustBind threshold >= required evidence
        |
        v
insufficient / inconsistent evidence
        |
        v
Unverified
```

rather than accepting the corrupted retrieval.

---

## Q2. CoordShift Off-Path Operation

CoordShift is evaluated independently from the query critical path.

The experiment varies background load:

```text
50 QPS
100 QPS
200 QPS
400 QPS
```

and measures:

<ul>
<li>observed query throughput;</li>
<li>query latency;</li>
<li>coordination commits; and</li>
<li>whether queries wait for coordination.</li>
</ul>

The expected behavior is that coordination continues asynchronously without introducing a query-side coordination barrier.

---

## Q3. Failure and Recovery

TrustANN is evaluated under uniformly distributed replica failures from:

```text
0%
10%
20%
33%
49%
```

The experiment measures:

<ul>
<li>trusted retrieval rate;</li>
<li>fallback/recovery activity;</li>
<li>p50 latency;</li>
<li>p95 latency; and</li>
<li>the point at which sufficient evidence can no longer be established.</li>
</ul>

The default configuration does not reduce the TrustBind evidence threshold when replicas fail. When sufficient evidence cannot be established, TrustANN returns:

```text
Unverified
```

rather than lowering the verification requirements.

---

## Q4. Distributed Retrieval and Verification Cost

The artifact evaluates the cost of increasing retrieval fan-out.

The fan-out experiment uses:

```text
1 shard
2 shards
3 shards
```

and records:

<ul>
<li>number of retrieval/evidence responses;</li>
<li>p50 latency; and</li>
<li>p95 latency.</li>
</ul>

This experiment isolates the cost associated with obtaining and verifying additional distributed evidence.

---

## Q5. CoordShift Failure-Domain Diversity

CoordShift is evaluated separately using a 60-worker coordination deployment.

The experiment varies:

```text
quorum size k = {5, 9, 15, 21}
adversarial fraction p = {0.10, 0.30}
```

Each configuration executes 1,500 coordination rounds.

Two coordination policies are compared:

<ul>
<li>uniform selection; and</li>
<li>failure-domain-aware diversity selection.</li>
</ul>

The primary metric is failure-domain coverage. The experiment is designed to determine whether diversity-aware selection increases the number of distinct failure domains represented in the selected quorum.

The experiment does <strong>not</strong> assume that diversity-aware selection universally reduces adversarial influence. The artifact reports both coverage and adversarial-influence measurements.

---

# 4. AWS Deployment

The distributed evaluation uses:

```text
1 coordinator
9 worker instances
3 shards
3 replicas per shard
gRPC communication
```

Each worker hosts a local HNSW index.

The deployment scripts configure:

<ul>
<li>worker instances;</li>
<li>shard/replica placement;</li>
<li>network communication;</li>
<li>fault injection;</li>
<li>experiment execution; and</li>
<li>result collection.</li>
</ul>

Before launching AWS experiments, configure the deployment parameters in the provided example configuration.

<strong>Do not place AWS credentials, SSH private keys, or account-specific secrets in the repository.</strong>

---

# 5. Fault Injection

The artifact supports experiments involving:

<ul>
<li>crashed replicas;</li>
<li>unreachable replicas;</li>
<li>stale epochs;</li>
<li>corrupted retrieval evidence;</li>
<li>corrupted coordination summaries;</li>
<li>replica replacement; and</li>
<li>shard migration.</li>
</ul>

The fault-injection experiments are intended to evaluate the behavior of TrustBind and AvailGuard under the failure model described in the paper.

---

# 6. Output and Results

Experiment outputs are written to the configured results directory.

The repository provides utilities for:

<ul>
<li>aggregating experiment measurements;</li>
<li>computing latency and throughput statistics;</li>
<li>generating result tables; and</li>
<li>generating plots from collected measurements.</li>
</ul>

The experiment outputs can therefore be regenerated without manually editing the raw measurements.

---

# 7. Mapping Artifact Experiments to Paper Claims

<table>
<thead>
<tr>
<th>Paper Evaluation</th>
<th>Artifact Component</th>
<th>What to Inspect</th>
</tr>
</thead>
<tbody>
<tr>
<td>TrustBind attack detection</td>
<td><code>trust_logic.py</code> + experiment harness</td>
<td>Trusted rate and R-ASR</td>
</tr>
<tr>
<td>Threshold boundary</td>
<td>TrustBind experiment</td>
<td>Acceptance/rejection at different thresholds</td>
</tr>
<tr>
<td>Retrieval integrity</td>
<td>Attack/integrity experiments</td>
<td>R-ASR and latency</td>
</tr>
<tr>
<td>CoordShift off-path operation</td>
<td>CoordShift experiments</td>
<td>Latency, throughput, coordination waits</td>
</tr>
<tr>
<td>Failure resilience</td>
<td>Failure experiments + AvailGuard</td>
<td>Trusted rate and fallback behavior</td>
</tr>
<tr>
<td>Distributed retrieval cost</td>
<td>Fan-out experiments</td>
<td>Evidence volume and p95 latency</td>
</tr>
<tr>
<td>CoordShift diversity</td>
<td>60-worker resilience experiment</td>
<td>Failure-domain coverage</td>
</tr>
<tr>
<td>Recovery</td>
<td>Recovery experiments</td>
<td>Query errors and reconfiguration time</td>
</tr>
</tbody>
</table>

---

# 8. Reproducibility Notes

The artifact uses deterministic query seeds and fixed experiment configurations where applicable. Corresponding experimental configurations use identical query sets and seeds to make comparisons consistent.

The AWS experiments use a 100K-vector subset of Deep10M rather than the complete 10M-vector dataset. The subset preserves the original 96-dimensional representation and uses L2 distance.

Some experiments are intentionally separated from the default nine-worker retrieval deployment. In particular, the CoordShift resilience experiment uses a dedicated 60-worker deployment to study coordination behavior at larger quorum sizes.

Results may exhibit small variations due to:

<ul>
<li>AWS instance scheduling;</li>
<li>network conditions;</li>
<li>background system load; and</li>
<li>timing variability in distributed execution.</li>
</ul>

The goal of reproduction is therefore to validate the reported trends and claims rather than require bit-for-bit identical measurements.

---

# 9. Safety and Resource Considerations

The artifact performs distributed-system experiments and may create AWS resources when the AWS deployment scripts are used.

Reviewers should:

<ul>
<li>verify AWS credentials and permissions before deployment;</li>
<li>review the configured instance count and instance type;</li>
<li>terminate EC2 instances after completing experiments;</li>
<li>remove unused storage resources; and</li>
<li>avoid running deployment scripts against production infrastructure.</li>
</ul>

The repository does not intentionally perform destructive operations against external systems.

---

# 10. Troubleshooting

### Python dependency errors

Recreate the virtual environment and reinstall dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Test failures

Run the failing test independently:

```bash
pytest -v tests/test_trust_logic.py
```

or:

```bash
pytest -v tests/test_experiments_synthetic.py
```

### AWS deployment failures

Check:

<ul>
<li>AWS credentials and permissions;</li>
<li>security-group rules;</li>
<li>instance availability in the selected region;</li>
<li>SSH connectivity;</li>
<li>worker configuration; and</li>
<li>coordinator/worker network connectivity.</li>
</ul>

Do not commit credentials or private SSH keys while debugging deployment problems.

---

# 11. Artifact Scope

This artifact is intended to reproduce and inspect the experimental claims made in the accompanying paper.

In particular, the artifact provides the implementation and evaluation infrastructure necessary to examine:

<ul>
<li>TrustBind's evidence-based retrieval verification;</li>
<li>CoordShift's asynchronous coordination;</li>
<li>AvailGuard's bounded failure recovery;</li>
<li>the latency and communication overhead of verification; and</li>
<li>failure-domain-aware coordination behavior.</li>
</ul>

The artifact does not claim to provide a formal guarantee of ANN recall preservation. TrustANN operates above an existing ANN index and evaluates the trustworthiness and sufficiency of distributed retrieval evidence under the fault model described in the paper.

---

# 12. License

This artifact is provided for research and evaluation purposes.

See `LICENSE` for the applicable license terms.

--
