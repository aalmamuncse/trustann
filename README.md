<h1>TrustANN</h1>

<p>
  TrustANN is a middleware trust layer for distributed approximate
  nearest-neighbor (ANN) retrieval. It operates above an existing ANN
  backend and is independent of the underlying ANN indexing method.
  The current artifact uses FAISS with HNSW indexes for evaluation.
</p>

<p>TrustANN provides three complementary protocols:</p>

<ul>
  <li>
    <strong>TrustBind:</strong> query-level retrieval verification using
    authenticated, consistent, and failure-domain-independent replica
    evidence.
  </li>
  <li>
    <strong>CoordShift:</strong> asynchronous, diversity-aware coordination
    that builds reusable coordination epochs without placing coordination
    on the query critical path.
  </li>
  <li>
    <strong>AvailGuard:</strong> bounded, independence-aware evidence
    recovery that preserves the trust criterion under replica failures.
  </li>
</ul>

<h2>1. Requirements</h2>

<ul>
  <li>Linux or macOS</li>
  <li>Python 3.x</li>
  <li>Git</li>
  <li>Packages listed in <code>requirements.txt</code></li>
</ul>

<p>
  Local tests and synthetic experiments do not require AWS.
</p>

<p>Distributed experiments additionally require:</p>

<ul>
  <li>AWS EC2</li>
  <li>gRPC</li>
  <li>FAISS with HNSW</li>
</ul>

<blockquote>
  <strong>Note:</strong> Do not place AWS credentials, SSH private keys,
  or other secrets in the repository.
</blockquote>

<h2>2. Installation</h2>

<pre><code>git clone &lt;ANONYMOUS-REPOSITORY-URL&gt;
cd TrustANN

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt</code></pre>

<h2>3. Tests</h2>

<p>Run the TrustANN logic tests:</p>

<pre><code>pytest tests/test_trust_logic.py</code></pre>

<p>Run the synthetic experiment tests:</p>

<pre><code>pytest tests/test_experiments_synthetic.py</code></pre>

<p>Run the complete test suite:</p>

<pre><code>pytest tests/</code></pre>

<h2>4. Minimal Experiment</h2>

<p>
  The artifact provides synthetic experiments that do not require an AWS
  cluster.
</p>

<pre><code>python orchestrator.py --config config/final_mandatory.json</code></pre>

<p>
  The experiments evaluate retrieval verification, TrustBind
  acceptance/rejection, failure handling, latency, and experiment outputs.
</p>

<h2>5. Default Configuration</h2>

<table>
  <thead>
    <tr>
      <th>Parameter</th>
      <th>Default</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>Dataset</td><td>Deep10M subset</td></tr>
    <tr><td>Vectors</td><td>100K</td></tr>
    <tr><td>Dimension</td><td>96</td></tr>
    <tr><td>Distance</td><td>L2</td></tr>
    <tr><td>Shards</td><td>3</td></tr>
    <tr><td>Replicas/shard</td><td>3</td></tr>
    <tr><td>Workers</td><td>9</td></tr>
    <tr><td>FAISS index</td><td>HNSW</td></tr>
    <tr><td>HNSW M</td><td>16</td></tr>
    <tr><td>HNSW efConstruction</td><td>200</td></tr>
    <tr><td>HNSW efSearch</td><td>64</td></tr>
    <tr><td>TrustBind threshold (&theta;)</td><td>2</td></tr>
    <tr><td>AvailGuard K<sub>max</sub></td><td>1</td></tr>
    <tr><td>CoordShift quorum</td><td>9</td></tr>
  </tbody>
</table>

<h2>6. Reproducing the Main Experiments</h2>

<p>
  The artifact reproduces five evaluation dimensions.
</p>

<h3>Q1. TrustBind Verification</h3>

<p>
  Tests threshold boundaries, evidence-condition ablations, candidate
  suppression, ranking manipulation, and retrieval integrity using
  <code>R-ASR</code>.
</p>

<h3>Q2. CoordShift Off-Path Operation</h3>

<p>
  Tests 50, 100, 200, and 400 QPS and measures query latency,
  throughput, coordination commits, and query waits.
</p>

<h3>Q3. Failure and Recovery</h3>

<p>
  Tests uniformly distributed replica crashes from 0% to 49% while
  preserving the TrustBind evidence threshold. When sufficient evidence
  cannot be established, TrustANN returns <code>Unverified</code>.
</p>

<h3>Q4. Distributed Retrieval Cost</h3>

<p>
  Varies query fan-out from one to three shards and measures evidence
  volume and p50/p95 latency.
</p>

<h3>Q5. CoordShift Failure-Domain Diversity</h3>

<p>
  Uses a separate 60-worker coordination deployment with
  <code>k &isin; {5, 9, 15, 21}</code> and adversarial fractions
  <code>p &isin; {0.10, 0.30}</code>. It measures failure-domain coverage
  and adversary-influenced rounds.
</p>

<h2>7. AWS Deployment</h2>

<p>The default distributed deployment uses:</p>

<pre><code>1 coordinator
9 worker instances
3 shards
3 replicas per shard
gRPC communication
FAISS HNSW indexes</code></pre>

<p>
  Separate scale-out experiments use up to <strong>144 workers</strong>,
  while the CoordShift resilience experiment uses a dedicated
  <strong>60-worker</strong> deployment.
</p>

<h2>8. Fault Injection</h2>

<p>The artifact supports:</p>

<ul>
  <li>crashed or unreachable replicas;</li>
  <li>stale epochs;</li>
  <li>corrupted retrieval evidence;</li>
  <li>corrupted coordination summaries;</li>
  <li>replica replacement; and</li>
  <li>shard migration.</li>
</ul>

<p>
  These experiments evaluate TrustBind, CoordShift, and AvailGuard under
  the fault model described in the paper.
</p>

<h2>9. Outputs</h2>

<p>Experiment outputs include:</p>

<ul>
  <li>trusted-query rate;</li>
  <li>R-ASR;</li>
  <li>p50/p95 latency;</li>
  <li>throughput;</li>
  <li>fallback activity;</li>
  <li>coordination behavior;</li>
  <li>failure-domain coverage; and</li>
  <li>generated tables and plots.</li>
</ul>

<p>
  The repository provides utilities for aggregating measurements and
  generating experiment results.
</p>

<h2>10. Reproducibility Notes</h2>

<p>
  Experiments use fixed configurations and deterministic query seeds where
  applicable. The AWS evaluation uses a 100K-vector subset of Deep10M with
  96 dimensions and L2 distance.
</p>

<p>
  The 60-worker CoordShift experiment and the 18&ndash;144-worker scale-out
  experiment use separate deployments from the default 9-worker topology.
</p>

<p>
  Results may vary slightly due to AWS scheduling, network conditions,
  and distributed timing. Reproduction is intended to validate the
  reported trends and claims rather than require bit-for-bit identical
  measurements.
</p>

<h2>11. Artifact Scope</h2>

<p>
  The artifact provides the implementation and evaluation infrastructure
  for:
</p>

<ul>
  <li>TrustBind's evidence-based retrieval verification;</li>
  <li>CoordShift's asynchronous coordination;</li>
  <li>AvailGuard's bounded evidence recovery;</li>
  <li>verification and distributed-retrieval overhead; and</li>
  <li>failure-domain-aware coordination.</li>
</ul>

<p>
  TrustANN operates above an existing ANN index and does not formally
  guarantee ANN recall preservation. The current evaluation uses FAISS
  with HNSW as the underlying ANN backend.
</p>

<h2>12. Safety</h2>

<p>When running AWS experiments:</p>

<ul>
  <li>verify AWS credentials and permissions;</li>
  <li>review the configured instance count and type;</li>
  <li>terminate EC2 instances after experiments;</li>
  <li>remove unused storage resources; and</li>
  <li>never run deployment scripts against production infrastructure.</li>
</ul>

<p>
  See <code>LICENSE</code> for license terms.
</p>
