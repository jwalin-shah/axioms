# Data Quality / ML Pipeline Oracle

Source: "ML Test Score" (Breck et al., 2016, Google), "TFX: A Production ML Pipeline" (Baylor et al., 2017),
"Model Cards for Model Reporting" (Mitchell et al., 2019), "Datasheets for Datasets" (Gebru et al., 2018),
"Scalable and Accurate Deep Learning with eXascale" (TensorFlow Extended), evidently.ai documentation,
NannyML documentation, "The Algorithmic Foundations of Differential Privacy" (Dwork & Roth, 2014),
"k-Anonymity: A Model for Protecting Privacy" (Sweeney, 2002), "Fairness and Machine Learning" (Barocas, Hardt, Narayanan, 2019).

This is how you ensure data quality and ML pipeline correctness. Every invariant is expressed as a
formal property, an enforcement pattern across ML frameworks, and an orbit-specific application.

---

## 1. Schema Validation

**Principle:** Every dataset has a schema — column names, types, nullability, and value ranges.
The schema is the contract between data producers and data consumers. Any row that violates the
schema is a bug before it enters the pipeline.

**Formal invariants:**
```
∀row ∈ dataset: row satisfies schema S
∀column c ∈ S: type(c) = expected_type(c)
∀column c ∈ S: if nullable(c) = false then row[c] ≠ null
∀column c ∈ S: if domain(c) exists then row[c] ∈ domain(c)
∀column c ∈ S: if regex(c) exists then pattern_match(regex(c), row[c])
```

**Ingress enforcement (TFX / TensorFlow Data Validation):**
- TFDV generates a schema from training data (`tfdv.generate_statistics_from_csv` → `tfdv.infer_schema`)
- Schema drift detection: `tfdv.validate_statistics` compares incoming data against the schema
- Anomaly proto: `anomaly_info.short_description` describes the exact violation per column
- `tfdv.get_feature` returns the expected type, domain, and presence constraints
- `tfdv.set_domain` declares enum or int ranges

**Cross-framework enforcement patterns:**
```
# TFX/TFDV
schema = tfdv.infer_schema(stats)
tfdv.set_domain(schema, 'age', int_domain=IntDomain(min=0, max=150))
anomalies = tfdv.validate_instance(schema, row)

# PyTorch (torchdata / custom)
class SchemaValidator(Dataset):
    def __init__(self, schema, source):
        self.schema = schema
        self.source = source
    def __getitem__(self, idx):
        row = self.source[idx]
        assert isinstance(row['age'], int) or row['age'] is None
        assert row['age'] is None or (0 <= row['age'] <= 150)
        return row

# JAX (tf.data + custom filter)
def validate_schema(schema):
    def fn(row):
        for col, spec in schema.items():
            if spec.required and row[col] is None:
                return False
            if spec.range and not (spec.range[0] <= row[col] <= spec.range[1]):
                return False
        return True
    return dataset.filter(fn)

# scikit-learn (Pipeline + custom transformer)
class SchemaValidator(BaseEstimator, TransformerMixin):
    def transform(self, X):
        for col, (min_val, max_val) in self.range_constraints.items():
            col_data = X[:, col]
            assert np.all(col_data >= min_val) and np.all(col_data <= max_val)
        return X
```

**Python detection (no framework):**
```python
def validate_row(schema, row):
    errors = []
    for col, spec in schema.items():
        val = row.get(col)
        if spec.required and val is None:
            errors.append(f"Missing required column: {col}")
        if val is not None and spec.type and not isinstance(val, spec.type):
            errors.append(f"Column {col}: expected {spec.type}, got {type(val)}")
        if val is not None and spec.range and not (spec.range[0] <= val <= spec.range[1]):
            errors.append(f"Column {col}: value {val} outside range {spec.range}")
    return errors
```

**Orbit-specific applications:**
- `pkg/dspy` — Signature fields (`Sig.In`, `Sig.Out`) must match input/output maps at runtime. Missing fields = schema violation. Invariant: `∀row ∈ dataset: ∀field ∈ sig.In: field ∈ row`.
- `pkg/featurestore` — Every feature has a `Values` (float64 slice), `Version` (uint64), and `Expires` (time.Time). Schema invariant: `∀f ∈ FeatureStore: f.Values != nil ∧ f.Version > 0`.
- `pkg/evalmetrics` — BLEU, ROUGE, METEOR operate on tokenized text. Schema invariant: `∀(ref, hyp): len(refs) == len(hyp)` — mismatched lengths are a schema violation that must error, not panic.
- `pkg/lorafinetuner` — LoRA rank, alpha, and target modules must match the base model's parameter schema. Invariant: `∀r ∈ LoRAConfig: r.target_module ∈ model.parameter_names`.
- `pkg/neuralnet` — Tensor shapes must match between layers. Schema invariant: `∀layer L, tensor T: T.Shape[1] == L.weights.Shape[0]`.

---

## 2. Distribution Drift (Training-Serving Skew, Covariate Shift, Concept Drift)

**Principle:** The distribution of features in production must match the distribution the model was
trained on. If it doesn't, the model's predictions are unreliable. Three types of drift:

1. **Training-serving skew (ingress drift)**: Data preprocessing differs between train and serve.
2. **Covariate shift (feature drift)**: P(X) changes while P(Y|X) stays the same.
3. **Concept drift (label drift)**: P(Y|X) changes while P(X) stays the same.

**Formal invariants:**
```
∀feature f: D_KL(P_train(f) || P_serve(f)) ≤ ε_drift       (Kullback-Leibler divergence)
∀feature f: KS_statistic(P_train(f), P_serve(f)) ≤ ε_ks     (Kolmogorov-Smirnov test)
∀feature f: |μ_train(f) - μ_serve(f)| ≤ ε_mean              (mean shift)
∀feature f: |σ_train(f) - σ_serve(f)| ≤ ε_std               (std deviation shift)
∀feature f: χ²(P_train(f), P_serve(f)) ≤ ε_chisq            (chi-squared for categorical)
```

**Drift detection methods:**

| Method | Type | When to use | Threshold |
|--------|------|-------------|-----------|
| KS test | Distribution | Continuous features | p < 0.05 (or stricter with Bonferroni) |
| PSI (Population Stability Index) | Distribution | Binned continuous | PSI > 0.1 = moderate, > 0.25 = severe |
| Chi-squared | Categorical | Categorical features | p < 0.05 |
| Jenson-Shannon divergence | Distribution | General purpose | JS > 0.1 |
| Wasserstein distance | Distribution | When support matters | Depends on feature scale |
| Z-score on mean | Feature-level | Quick alert | |z| > 3 |
| L-infinity drift | Feature-level | Binary features | Percentage change |

**Multi-framework enforcement:**
```
# TFX / TFDV
serving_stats = tfdv.generate_statistics_from_tfrecord(serving_data)
skew_anomalies = tfdv.validate_statistics(serving_stats, training_stats, schema)
# tfdv.get_anomalies() returns per-feature drift violations

# evidently.ai
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset
report = Report(metrics=[DataDriftPreset()])
report.run(reference_data=train, current_data=serve)
report.json()  # per-feature drift metrics

# NannyML
from nannyml import UnivariateDriftCalculator
calc = UnivariateDriftCalculator(column_names=features, treat_as_categorical=cats)
calc.fit(train)
drift_result = calc.calculate(serve)

# Custom (PyTorch / JAX / scikit-learn)
def detect_ks_drift(reference, current, alpha=0.05):
    from scipy import stats
    drift_features = {}
    for col in reference.columns:
        stat, p = stats.ks_2samp(reference[col], current[col])
        drift_features[col] = {'statistic': stat, 'p_value': p, 'drifted': p < alpha}
    return drift_features
```

**Orbit-specific applications:**
- `pkg/sampler` — Sampling strategies (temperature, top-k, top-p) change the output distribution of the LLM. Invariant: `∀sampler S: distribution(S.output) ≈ distribution(training_data) within ε, unless temperature > 1`.
- `pkg/dspy` — DSPy signatures are few-shot prompts. If the distribution of input queries drifts from the few-shot examples, quality degrades. Invariant: `∀query q: min_example_similarity(q) ≥ τ` — measure embedding distance to nearest few-shot example.
- `pkg/grpo` — Group Relative Policy Optimization compares model outputs against a reference. Covariate shift in the prompt distribution breaks the comparison. Invariant: `∀prompt p: P_train(p) ≈ P_serve(p) within ε_ps`.
- `pkg/modelmerging` — Merging models trained on different distributions produces unpredictable behavior. Invariant: `∀model M_i in merge: D_KL(P_i(output) || P_merged(output)) ≤ ε_merge`.
- `pkg/featurestore` — Feature store drift detection: `∀feature f: |μ_current(f) - μ_historical(f)| ≤ ε_feature` computes at read time, flagged in metadata.

---

## 3. Completeness (Missing Values, Nullability)

**Principle:** Every required column must have a value in every row. Missing values must be explicitly
tracked, and imputation must be logged. Silent missing values are the most common data quality bug.

**Formal invariants:**
```
∀row ∈ dataset: ∀column c ∈ required_columns: row[c] ≠ null
∀imputation I: I(row, c) → log_imputation(row_id, c, method, timestamp)
∀column c: null_rate(c) = count(null(row[c])) / total_rows
∀required column c: null_rate(c) = 0
```

**Detection patterns:**
```
# Pandas
null_counts = df.isnull().sum()
null_rate = df.isnull().mean()

# TFX / TFDV
# tfdv.generate_statistics automatically computes:
# - num_missing for each feature (per feature)
# - null ratio (count of null / count of total)
anomalies = tfdv.validate_statistics(stats, schema)

# PySpark
from pyspark.sql.functions import col, isnan, when, count
df.select([count(when(isnan(c) | col(c).isNull(), c)).alias(c) for c in df.columns])

# Great Expectations
import great_expectations as ge
df_ge = ge.dataset.PandasDataset(df)
df_ge.expect_column_values_to_not_be_null('user_id')
df_ge.expect_column_values_to_not_be_null('timestamp')
```

**Imputation taxonomy:**
| Method | Type | When to use | Risk |
|--------|------|-------------|------|
| Drop row | Deletion | Missing < 5% random | Can bias if not MCAR |
| Mean/median | Univariate | Numerical, low missing | Reduces variance |
| Mode | Univariate | Categorical | Most common category |
| Forward fill | Time series | Ordered data | Hides structural breaks |
| KNN imputation | Multivariate | Numerical, correlated | Computationally expensive |
| MICE | Multivariate | Any | Multiple models, high cost |
| Model-based | Predictive | Any | Can overfit, requires validation |

**Orbit-specific applications:**
- `pkg/featurestore` — Feature values are float64 slices. Null features = zero vector. Invariant: `∀f ∈ FeatureStore: if f.Values == nil then f.Expires <= now` — nil features must be expired.
- `pkg/neuralnet` — Tensor values must be finite (no NaN, no Inf). Invariant: `∀t ∈ Tensor: ∀v ∈ t.Data: isFinite(v)`. Missing values propagate through gradients as NaN — a silent failure mode.
- `pkg/grpo` — Reference policy outputs must be complete. Invariant: `∀batch ∈ training: ∀response ∈ batch: response != nil ∧ len(response) > 0`.
- `pkg/loraqlora` — Quantized weights cannot be null. Invariant: `∀q ∈ QLoRAWeights: q.codebook != nil ∧ q.indices != nil`.
- `pkg/evalmetrics` — Reference and hypothesis lists must be non-empty and equal length. Invariant: `∀(refs, hyps): len(refs) > 0 ∧ len(refs) == len(hyps)`.

---

## 4. Lineage (Provenance)

**Principle:** Every data point must trace back to its source — when it was created, which system
produced it, and what transformations were applied. Without lineage, you cannot debug, reproduce,
or audit ML pipelines.

**Formal invariants:**
```
∀datum d: provenance(d) = (source, timestamp, transformation_chain, version)
∀datum d: source(d) is known
∀datum d: timestamp(d) is known
∀datum d: transformation_chain(d) is enumerable as a DAG of (op, params, input_hash)
```

**Lineage tracking patterns:**
```
# ML Metadata (TFX)
# tfx.components use MLMD for automatic lineage:
# Artifact + Execution + Event = provenance graph
# artifact = artifact_type, uri, properties
# execution = execution_type, last_known_state
# event = artifact_id, execution_id, type (INPUT/OUTPUT)

# DVC (Data Version Control)
# dvc.yaml tracks pipeline stages
# dvc.lock hashes inputs/outputs
# dvc commit records data version in git
# dvc diff shows what changed between versions

# Custom (any framework)
class LineageRecord:
    row_id: str
    source: str          # database, API, file, stream
    source_timestamp: datetime
    ingested_at: datetime
    transformation_chain: list[Transformation]
    version: str          # dataset version or pipeline run ID

# Feature store pattern (Feast / Tecton)
# Every feature value has:
# - feature_name, feature_version
# - entity_key, event_timestamp
# - created_timestamp
# - source (which pipeline job produced it)
```

**Orbit-specific applications:**
- `pkg/featurestore` — Features have `Version` (uint64) and `Expires` (time.Time). Lineage invariant: `∀f ∈ FeatureStore: f.Version > 0 ∧ f.Expires.IsZero() == false`. Each feature value must trace to a version + timestamp.
- `pkg/federatedsgd` — Federated training aggregates client updates. Lineage invariant: `∀update u: provenance(u) = (client_id, round_number, local_epoch)`. Without per-client lineage, you can't attribute adversarial updates.
- `pkg/medusa` — Speculative decoding uses a draft model + target model. Lineage invariant: `∀token t: provenance(t) = (draft | target, model_version, temperature)`. Knowing which model produced each token is essential for debugging acceptance rates.
- `pkg/modelmerging` — Model merging combines weights from multiple source models. Lineage invariant: `∀weight w in merged_model: provenance(w) = (source_model, merge_method, merge_weight)`. Each weight must trace to its source.
- `pkg/lorafinetuner` — LoRA adapters are additive to base weights. Lineage invariant: `∀adapter A: provenance(A) = (base_model, rank, dataset_hash, training_run_id)`. The adapter alone is useless without knowing what base model it was trained on.
- `pkg/grpo` — GRPO compares model outputs against a reference. Lineage invariant: `∀comparison c: provenance(c) = (student_model_version, reference_model_version, prompt_hash, batch_id)`.

---

## 5. Freshness (Data Staleness)

**Principle:** Data has a shelf life. If a model is trained on last week's data and deployed on
today's data, it will fail. Every data source must have a freshness SLA, and every pipeline must
monitor that SLA.

**Formal invariants:**
```
∀data source s: current_timestamp - max_timestamp(s) ≤ freshness_sla(s)
∀model m: training_data_timestamp(m) ≥ min_accepted_timestamp(m)
∀prediction p: feature_timestamp(p) ≥ model_training_timestamp(p)
∀ML pipeline p: pipeline_freshness(p) = min(freshness(s) for s in sources(p))
```

**Freshness monitoring patterns:**
```
# Timestamp comparison
def check_freshness(source, sla_hours=24):
    max_ts = db.query(f"SELECT MAX(timestamp) FROM {source}")
    age = datetime.now() - max_ts
    assert age.total_seconds() < sla_hours * 3600, f"Data stale: {age} hours"

# SLI/SLO pattern (Google SRE book)
# SLI: freshness of data = max(now - data_timestamp)
# SLO: freshness < 24h for 99.9% of queries
# Burn rate: how fast we're consuming the error budget

# Feature store (Feast)
# Feast auto-expires features based on ttl:
# FeatureView(..., ttl=timedelta(hours=24))
# Querying expired features returns an error or stale flag

# Apache Airflow / Dagster
# DAG-level freshness check:
# @daily_sla(hours=2)
# def my_pipeline(): ...
# PagerDuty alert if pipeline hasn't completed in 2 hours
```

**Freshness by data type (typical SLAs):**

| Data type | Typical SLA | Why |
|-----------|-------------|-----|
| Real-time features (clickstream, sensor) | Seconds | Model output depends on current state |
| Near-real-time (user activity, transactions) | Minutes | Feature engineering delay |
| Batch features (aggregates, embeddings) | Hours | Batch processing window |
| Static features (demographics, metadata) | Days-Weeks | Slow-changing, periodic refresh |
| Training labels | Hours-Days | Label lag is inherent |
| Model weights | Days-Months | Retraining cycle |

**Orbit-specific applications:**
- `pkg/featurestore` — `Expires` field enforces freshness. Invariant: `∀f ∈ FeatureStore: f.Expires > now ∨ f.Version = 0` (version 0 = expired). Queries must check `Expires` before returning a feature.
- `pkg/sampler` — Sampler configuration (temperature, top-k) may be stale. Invariant: `∀sampler S: S.config_freshness ≤ config_sla`. If the sampling strategy was optimized for a different model version, it's stale.
- `pkg/medusa` — Draft model weights must be fresh. Invariant: `∀draft_model M: M.training_timestamp ≥ target_model.training_timestamp`. A stale draft model produces bad draft tokens, reducing acceptance rate.
- `pkg/federatedsgd` — Client updates have a staleness window. Invariant: `∀client update u: now - u.round_timestamp ≤ max_round_staleness`. Stale updates are dropped or decayed.
- `pkg/dspy` — DSPy few-shot examples may go stale if the underlying model changes. Invariant: `∀demo d in signature: d.model_version = current_model_version` or re-optimize.

---

## 6. Privacy (PII Masking, k-Anonymity, Differential Privacy)

**Principle:** ML models can memorize and leak private information from their training data.
Privacy is not optional — it must be enforced at the data level (PII masking, k-anonymity),
the training level (differential privacy), and the deployment level (model cards, access controls).

**Formal invariants:**
```
∀datum d: if d contains PII then d is masked or excluded
∀dataset D: k-anonymity(D) ≥ k_min                           (k-anonymity across quasi-identifiers)
∀dataset D: l-diversity(D) ≥ l_min                            (l-diversity within equivalence classes)
∀mechanism M: M is ε-differentially private                   (DP guarantee)
∀query q: |Pr[M(q) ∈ S] - Pr[M(q') ∈ S]| ≤ ε                (ε-DP definition)
∀budget B: ε_spent(B) ≤ ε_budget                              (privacy budget tracking)
```

**Differential privacy (Dwork & Roth) — core concepts:**

| Concept | Definition | Implementation |
|---------|------------|----------------|
| ε-DP | Two neighboring datasets produce similar outputs | Clipping + noise |
| (ε, δ)-DP | Relaxed: δ probability of failure | Gaussian noise |
| Privacy budget | Total ε available across all queries | Composition theorems |
| Rényi DP | Tight composition for deep learning | Moments accountant |
| Sensitivity | Maximum change from one row | `S(f) = max_{x,x'} ||f(x) - f(x')||` |
| Laplace mechanism | Count queries | `M(x) = f(x) + Lap(S(f)/ε)` |
| Gaussian mechanism | Numeric queries | `M(x) = f(x) + N(0, S(f)²·ln(1/δ)/ε²)` |
| DP-SGD | Deep learning with DP | Per-example gradients, clipping, noise |

**DP-SGD training pattern (any framework):**
```
for each batch:
    1. Compute per-example gradients (not averaged)
    2. Clip each gradient to L2 norm C: g_i = g_i · min(1, C/||g_i||₂)
    3. Aggregate: g' = 1/batch_size * (Σg_i + N(0, σ²C²I))
    4. Gradient descent step with g'
    5. Track ε spent via RDP accountant (Abadi et al., 2016)
```

**k-Anonymity (Sweeney, 2002):**
```
∀dataset D, ∀quasi-identifier set Q:
  k-anonymity(D, Q) = min over equivalence classes of |class|
  Equivalent to: no group of (q1, q2, ..., qn) has fewer than k rows

Generalization: Replace specific values with ranges (e.g., age 32 → age 30-35)
Suppression: Remove rows that cannot achieve k-anonymity
```

**PII detection patterns:**
```
# regex-based detection (first pass)
PII_PATTERNS = {
    'email': r'[\w.+-]+@[\w-]+\.[\w.-]+',
    'phone': r'\+?1?\d{10,15}',
    'ssn': r'\d{3}-\d{2}-\d{4}',
    'credit_card': r'\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}',
    'ip_address': r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',
    'street_address': r'\d{1,5}\s\w+\s\w+(St|Ave|Rd|Blvd|Dr|Ln|Way)',
}
# Second pass: NER-based detection for names, locations, orgs
# Third pass: Statistical (unusual shingling, high-entropy tokens)
```

**Orbit-specific applications:**
- `pkg/neuralnet` — Neural network weights can memorize training data. DP-SGD enforcement: `∀training step t: gradient_norm(g) ≤ C ∧ noise_scale(g) = σ`. Without clipping, one outlier gradient can dominate the update (and leak).
- `pkg/federatedsgd` — Federated learning without DP is not private. Invariant: `∀client update u: u is either (a) clipped to norm C + noise, or (b) secured via secure aggregation`. The server must not be able to infer individual client data from model updates.
- `pkg/lorafinetuner` — LoRA adapters can memorize fine-tuning data. Invariant: `∀LoRA adapter A: if A was trained on private data, then A must be DP-trained`. A LoRA adapter is small enough to be reconstructed — leakage is higher per parameter.
- `pkg/grpo` — GRPO uses a reward model trained on human preferences. Invariant: `∀prompt p in preference data: p contains no PII`. Human-annotated preference data is a common PII leak vector.
- `pkg/rlhfdpo` — RLHF/DPO trains on human feedback. Invariant: `∀feedback sample s: s.user_id is pseudonymized, s.content is PII-scrubbed`. Feedback data is notoriously under-scrubbed.
- `pkg/sampler` — Sampling parameters can be used for membership inference (does the model generate a specific string?). Invariant: `∀query q: if q is a membership inference query, the response distribution must be indistinguishable from the holdout distribution`.
- `pkg/featurestore` — Features may contain PII (e.g., user embeddings). Invariant: `∀feature f: if f is derived from PII, then f.access_level ≥ PRIVATE ∧ f.retention_days ≤ max_retention`.

---

## 7. Training Invariants (Gradient Correctness, Loss Monotonicity, Overfitting Detection)

**Principle:** Training is not just "run the optimizer and hope." Each step must be verified:
gradients must be finite and correct, loss must decrease (monotonic in expectation), validation
must not diverge, and hyperparameters must be stable.

**Formal invariants:**
```
∀training step t: ||∇L(θ_t)||₂ is finite                              (gradient finiteness)
∀training step t: ∇L(θ_t) ≈ ∇_num L(θ_t) within τ                     (gradient correctness, gradient check)
∀training step t: E[L(θ_{t+1})] ≤ E[L(θ_t)] + ε                      (loss monotonicity in expectation)
∀epoch e: L_val(e) - L_val(e-1) ≤ ε_val                               (validation loss not diverging)
∀epoch e: if L_val(e) >> L_train(e) then early_stop                   (overfitting detection)
∀parameter p: |p| ≤ max_norm                                          (parameter norm stability)
```

**Gradient checking (numerical gradient verification):**
```
// Two-sided finite difference: f'(x) ≈ (f(x+h) - f(x-h)) / (2h)
// Relative error: ||numerical - analytical|| / (||numerical|| + ||analytical||)
// Threshold: relative error < 1e-7 for float64, < 1e-4 for float16/quantized

Given by: torch.autograd.gradcheck, jax.lax.check_grad, tf.GradientTape.gradient
We must enforce: Per-example gradient clipping requires per-example gradients (not just batch averages)
```

**Loss monotonicity monitoring:**
```
// Training loss should decrease (moving average, not raw — noise is expected)
// Validation loss should not increase for N consecutive checkpoints
// Exceptions: Warmup phase (loss may spike), adversarial training (loss may increase)

Sliding window pattern:
  window = losses[-window_size:]
  trend = (window[-1] - window[0]) / len(window)
  if trend > 0 and len(window) >= min_epochs:
    log("Loss increasing: trend = {trend}")
  if val_loss best > latest_val_loss + patience_tolerance:
    early_stop()
```

**Hyperparameter stability checks:**
```
// Invariant: Hyperparameters should not cause NaN, Inf, or vanishing gradients
// Runtime checks:
//   - Learning rate: lr ≤ max_lr (no explosion)
//   - Batch norm: running_mean, running_var are finite
//   - Weight decay: parameter values stay bounded
//   - Adam epsilon: prevents division by zero
//   - Gradient clipping: ||g|| ≤ max_grad_norm
```

**Multi-framework enforcement:**
```
# PyTorch
torch.autograd.set_detect_anomaly(True)  # detects NaN/Inf in backward
torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm)

# JAX
jax.debug.check_finite(grads)  # asserts all gradients are finite
import optax
optax.clip_by_global_norm(max_norm)  # gradient clipping

# TFX / TF
tf.debugging.check_numerics(tensor, "gradient check")
tf.clip_by_global_norm(gradients, max_norm)

# scikit-learn
# sklearn.linear_model.SGDClassifier has built-in tol-based convergence
# sklearn.exceptions.ConvergenceWarning for non-convergence
```

**Orbit-specific applications:**
- `pkg/neuralnet` — Tensor operations must produce finite gradients. Invariant: `∀forward pass: all intermediate tensors are finite ∧ ∀backward pass: all gradients are finite`. Gradient checking: `∀step: ||∇L - ∇_num_L|| / (||∇L|| + ||∇_num_L||) < 1e-7`.
- `pkg/grpo` — Policy gradient training. Invariant: `∀update step: ||∇θ J(π_θ)|| is finite ∧ advantage_estimates are bounded`. Clipping: `clip(importance_ratio, 1-ε, 1+ε)`.
- `pkg/rlhfdpo` — DPO loss has no explicit reward model but still needs gradient stability. Invariant: `∀batch: π_θ(y_w | x) / π_ref(y_w | x) > 0 ∧ π_θ(y_l | x) / π_ref(y_l | x) > 0` (log probabilities finite).
- `pkg/federatedsgd` — Client updates must be bounded. Invariant: `∀client update u: ||u||₂ ≤ C` (clipping) OR `parallel work: aggregate has bounded norm`.
- `pkg/lorafinetuner` — LoRA weights are initialized to zero (or near-zero). Invariant: `∀LoRA weight W: if t=0, then W = 0` (initialization constraint). Gradients must be finite: `∀step: ||∇W|| is finite`.
- `pkg/loraqlora` — Quantization adds noise to gradients. Invariant: `∀step: ||∇quantized - ∇full_precision|| ≤ ε_quant` (quantization error bound). NF4 quantization must not cause rank collapse.
- `pkg/flashkmeans` — K-means convergence. Invariant: `∀iteration i: inertia(i) ≤ inertia(i-1) + ε` (monotonic decrease). Cluster assignments must not be NaN.
- `pkg/ringattention` — Ring attention distributes sequence across devices. Invariant: `∀device d: gradient_sync(d) is complete before optimizer step`. Partial sync = stale gradients.
- `pkg/mambassm` — SSM state space models can suffer from vanishing gradients across long sequences. Invariant: `∀layer l: ||∇state||₂ > ε_min` (gradient not vanished). `∀layer l: ||∇state||₂ < C` (gradient not exploded).
- `pkg/ropeattention` — Rotary Position Embeddings must not cause gradient explosion. Invariant: `∀attention head h: ||∇Q(h)||₂ ≈ ||∇K(h)||₂ ≈ ||∇V(h)||₂` (balanced gradients across heads).

---

## 8. Model Evaluation (Held-Out Test Set, Slice-Based Evaluation, Fairness)

**Principle:** Aggregate metrics lie. A model with 99% accuracy can be 100% wrong on a critical
subgroup. Evaluation must be slice-based, fairness-aware, and statistically rigorous.

**Formal invariants:**
```
∀test set T: T is disjoint from training set (no data leakage)          (held-out test)
∀slice s ∈ slices: |metric(T_s) - metric(T_global)| ≤ ε_slice          (slice consistency)
∀group g₁, g₂: |metric(g₁) - metric(g₂)| ≤ ε_fairness                  (fairness across groups)
∀metric m: reported_CI(m) = (m - z*σ/√n, m + z*σ/√n)                  (confidence intervals)
∀model m: model_card(m) is complete and current                         (model card requirement)
```

**Evaluation metrics by task type:**

| Task | Metrics | Slice considerations |
|------|---------|---------------------|
| Classification | Accuracy, precision, recall, F1, AUC-ROC | Per-class F1, per-demographic group |
| Regression | MSE, MAE, R², MAPE | Per-decile error, per-segment MAE |
| Ranking | NDCG, MAP, MRR | Per-query type, per-user segment |
| Generation | BLEU, ROUGE, METEOR, Perplexity | Per-domain, per-length bucket |
| Detection | mAP, IoU, F1@IoU | Per-object size, per-category |
| Reinforcement | Reward, episode return, success rate | Per-environment, per-task difficulty |

**Slice-based evaluation pattern:**
```
def evaluate_slices(model, test_data, slices):
    results = {}
    for slice_name, slice_fn in slices.items():
        slice_data = test_data.filter(slice_fn)
        if len(slice_data) < min_sample_size:
            results[slice_name] = {'error': 'insufficient_samples'}
            continue
        y_pred = model.predict(slice_data.X)
        y_true = slice_data.y
        results[slice_name] = compute_metrics(y_true, y_pred)
    return results

slices = {
    'overall': lambda df: df,
    'by_age:0-18': lambda df: df[df['age'] < 18],
    'by_age:65+': lambda df: df[df['age'] >= 65],
    'by_gender:F': lambda df: df[df['gender'] == 'F'],
    'by_gender:M': lambda df: df[df['gender'] == 'M'],
    'by_region:us': lambda df: df[df['region'] == 'US'],
    'by_region:non-us': lambda df: df[df['region'] != 'US'],
    'by_device:mobile': lambda df: df[df['device'] == 'mobile'],
    'by_device:desktop': lambda df: df[df['device'] == 'desktop'],
}
```

**Fairness metrics (Barocas, Hardt, Narayanan):**

| Metric | Definition | When to use |
|--------|------------|-------------|
| Demographic parity | P(ŷ=1 | A=a) = P(ŷ=1) | Equal selection rate |
| Equal opportunity | P(ŷ=1 | Y=1, A=a) = P(ŷ=1 | Y=1) | Equal true positive rate |
| Equalized odds | P(ŷ=1 | Y=y, A=a) = P(ŷ=1 | Y=y) | Equal TPR + FPR |
| Predictive parity | P(Y=1 | ŷ=1, A=a) = P(Y=1 | ŷ=1) | Equal precision |
| Statistical parity difference | max diff in positive prediction rate | Quick audit |
| Disparate impact | P(ŷ=1 | A=unprivileged) / P(ŷ=1 | A=privileged) | Legal threshold (80% rule) |

**Model cards (Mitchell et al., 2019) — required sections:**
```
Model Card:
  Model Details: developer, version, architecture, training date
  Intended Use: primary use cases, out-of-scope uses
  Factors: demographic groups, environmental conditions, technical factors
  Metrics: evaluation metrics, thresholds, confidence intervals
  Evaluation Data: datasets, preprocessing, sample selection
  Training Data: provenance, size, preprocessing, labeling process
  Quantitative Analyses: aggregate + slice metrics, fairness analysis
  Ethical Considerations: impact on groups, potential for harm
  Caveats and Recommendations: deployment constraints, known limitations
```

**Data leakage detection:**
```
// Temporal leakage: test data before training data
// Row-level leakage: duplicate rows across train/test
// Feature leakage: features that contain label information
// Aggregation leakage: group statistics that include test rows

Invariant: ∀train_row r, test_row s: timestamp(r) ≤ timestamp(s)
Invariant: ∀train_row r, test_row s: r.id ≠ s.id
Invariant: ∀feature f in test: f is computable from test-time data only
```

**Orbit-specific applications:**
- `pkg/evalmetrics` — BLEU, ROUGE, METEOR, Perplexity, accuracy, precision, recall, F1 implementations. Invariant: `∀metric m: m(refs, hyps) returns [0, 1] for normalized metrics ∧ m is deterministic for same input`. BLEU score must not panic on input length mismatch.
- `pkg/dspy` — DSPy signatures are evaluated on held-out test sets. Invariant: `∀train_example, test_example: no overlap in input/output pairs`. DSPy optimizers must not leak test data into few-shot examples.
- `pkg/grpo` — GRPO uses a reward model to compare outputs. Invariant: `∀batch: reward_model is evaluated on held-out prompts (not training prompts)`. Reward model overfitting = false signal.
- `pkg/rlhfdpo` — Preference data is split into train/test. Invariant: `∀preference p in test set: p is not in training set ∧ p was not used to compute reward model`. Leakage in preference data is a P0 bug.
- `pkg/modelmerging` — Model merging evaluation must be per-task. Invariant: `∀task t: merged_model_metric(t) ≥ min(source_model_metric(t)) ∨ tradeoff is documented`. Merging should not silently degrade performance on any task.
- `pkg/sampler` — Sampling strategies affect output quality. Invariant: `∀sampler S: S.eval_metric ≥ baseline_metric within ε` (sampling not degrading quality). Temperature, top-k, top-p, and min-p must be evaluated on held-out data.
- `pkg/medusa` — Medusa acceptance rate is a key metric. Invariant: `∀model: acceptance_rate ≥ α_threshold` (otherwise draft model is ineffective). Evaluation must be slice-based: per-length bucket, per-domain.
- `pkg/federatedsgd` — Federated model evaluation must be per-client. Invariant: `∀client c: local_model_metric(c) ≥ global_model_metric(c) - ε` (federated averaging should not hurt any client significantly). No client should be silently degraded.
- `pkg/flashkmeans` — Clustering evaluation: inertia, silhouette score, Davies-Bouldin index. Invariant: `∀iteration i: inertia(i) decreasing ∧ silhouette_score ≥ baseline`. Evaluation must be per-cluster.
- `pkg/neuralnet` — Per-layer activation statistics. Invariant: `∀layer l: mean_activation(l) ≈ 0 ∧ std_activation(l) ≈ 1` (healthy layer). Dead neurons: `P(activation(l) > 0) > τ_dead`.

---

## 9. Cross-Cutting: Data Pipeline Integrity

**Principle:** Data pipelines are the most common source of ML failures. A pipeline that silently
drops rows, duplicates data, or corrupts features produces a model that fails silently in production.

**Formal invariants:**
```
∀pipeline P: row_count(P.output) = row_count(P.input) - explicitly_dropped    (row count integrity)
∀pipeline P: ∀feature f: f.output = transform(f.input)                        (feature computation integrity)
∀pipeline P: hash(P.output) = deterministic function of hash(P.input)          (reproducibility)
∀pipeline P: if P fails, P.state = FAILED (not partial)                        (atomicity)
```

**Pipeline integrity patterns:**
```
# Row count checks
assert len(output) == len(input) - len(explicit_drops)

# Checksum/checksum across stages
stage1_hash = hash(stage1_output)
stage2_hash = hash(stage2_output)
assert stage2_hash == expected_hash  # or compute from stage1_hash

# Schema enforcement at every stage
def etl_pipeline(input_path, output_path):
    df = read_csv(input_path)
    validate_schema(schema, df)                    # gate 1: ingress
    df = transform(df)
    validate_schema(intermediate_schema, df)       # gate 2: transform
    df = aggregate(df)
    validate_schema(output_schema, df)             # gate 3: egress
    df.to_parquet(output_path)

# Break-glass pattern: allow schema violations with explicit override
# Logged and audited, not silently accepted
```

**Orbit-specific applications:**
- `pkg/featurestore` — FeatureStore is a pipeline endpoint. Invariant: `∀feature f: f.Version is monotonic across updates ∧ f.Expires > f.Created`. Version must not decrease.
- `pkg/dspy` — DSPy optimizers transform few-shot examples. Invariant: `∀optimizer O: O.input_examples ⊆ O.output_examples` (optimizer adds, doesn't remove). Demo selection must not drop the best examples.
- `pkg/grpo` — GRPO pipeline: prompt → generate → compare → update. Invariant: `∀step in pipeline: step completes fully or rolls back`. Partial generation corrupts the reward signal.
- `pkg/rlhfdpo` — Preference data pipeline: collect → filter → train. Invariant: `∀preference p: p is valid (chosen != rejected) ∧ p is complete (all fields present)`. Invalid preferences are dropped, not silently included.

---

## 10. ML Test Score (Breck et al., 2016) — The Checklist

The ML Test Score paper defines a 28-test battery across 4 areas. Each test is a pass/fail gate.
A score of 1-4 is a "needs improvement" area; 5+ is a "passing" area.

### Area 1: Tests for Features and Data (max 7 points)

| # | Test | Score | How to enforce |
|---|------|-------|----------------|
| 1 | Feature expectations are captured in a schema | 1 | TFDV, Great Expectations |
| 2 | Feature are quantified (range, distribution) | 1 | TFDV statistics |
| 3 | Each feature is tested against the schema | 1 | TFDV validation |
| 4 | Features are manually reviewed for correctness | 1 | Human review + code review |
| 5 | Data pipeline has integration tests | 1 | CI/CD pipeline tests |
| 6 | Data pipeline that produces features is tested | 1 | End-to-end test |
| 7 | Data quality is monitored in production | 1 | Dashboard + alerting |

### Area 2: Tests for Model Development (max 7 points)

| # | Test | Score | How to enforce |
|---|------|-------|----------------|
| 1 | Every model specification undergoes code review | 1 | PR review |
| 2 | Offline evaluation on held-out data | 1 | Train/test split |
| 3 | Metrics are tracked and compared across runs | 1 | Experiment tracking |
| 4 | Hyperparameters are tested (not using defaults blindly) | 1 | Hyperparameter search |
| 5 | Model's behavior on slices is evaluated | 1 | Slice-based evaluation |
| 6 | Model is tested for invariance to irrelevant features | 1 | Feature importance analysis |
| 7 | Model is tested for appropriate behavior on edge cases | 1 | Adversarial evaluation |

### Area 3: Tests for ML Infrastructure (max 7 points)

| # | Test | Score | How to enforce |
|---|------|-------|----------------|
| 1 | Training is reproducible (same code + data → same model) | 1 | Seeded random + deterministic ops |
| 2 | Model specification is unit-tested | 1 | Test each component |
| 3 | Training pipeline is integration-tested | 1 | End-to-end test on small data |
| 4 | Model is loaded correctly in production | 1 | Load test + smoke test |
| 5 | Model serving is tested (latency, throughput) | 1 | Performance test |
| 6 | Model can be rolled back to a previous version | 1 | Versioned model registry |
| 7 | Model can be shadow-tested (traffic mirrored to new model) | 1 | A/B test infrastructure |

### Area 4: Tests for Monitoring (max 7 points)

| # | Test | Score | How to enforce |
|---|------|-------|----------------|
| 1 | Prediction serving latency is monitored | 1 | p50/p95/p99 dashboards |
| 2 | Prediction serving throughput is monitored | 1 | RPS dashboards |
| 3 | Model is monitored for staleness (data freshness) | 1 | Freshness SLA monitoring |
| 4 | Model is monitored for training-serving skew | 1 | Drift detection |
| 5 | Model is monitored for prediction drift | 1 | Output distribution monitoring |
| 6 | Model is monitored for performance degradation | 1 | Live metric tracking |
| 7 | Model is monitored for outliers in predictions | 1 | Anomaly detection |

**Target score: 16+ out of 28. Below 10 = high risk of failure in production.**

---

## 11. Framework-Specific Data Quality Patterns

### TFX (TensorFlow Extended)

```
Components:
  ExampleGen → StatisticsGen → SchemaGen → ExampleValidator → Transform → Trainer → Evaluator → Pusher

Data quality gates:
  StatisticsGen: computes min, max, mean, std, null count, unique values per feature
  SchemaGen: infers schema from statistics (types, domains, presence)
  ExampleValidator: compares new data against schema, produces anomalies
    - Schema drift: new column, missing column, type change
    - Distribution drift: KS test, chi-squared, L-infinity
    - Value range violation: value outside domain
  
Key invariant: ∀component C: C.output is validated against schema before C completes
```

### PyTorch

```
Data quality enforcement:
  torchdata: SchemaValidator, Filter, Map transforms
  torch.utils.data.DataLoader: collate_fn can validate batch schema
  torch.autograd.set_detect_anomaly(True): NaN/Inf detection in backward
  
Key invariant: ∀batch in DataLoader: batch tensors are finite ∧ batch sizes match
```

### JAX

```
Data quality enforcement:
  jax.debug.check_finite: runtime NaN/Inf check
  jax.lax.check_grad: gradient verification
  jax.numpy.where: safe division (avoid div-by-zero)
  jax.vmap: automatic vectorization preserves shape invariants
  
Key invariant: ∀operation in jit: input/output tensors are finite ∧ shapes are compatible
```

### scikit-learn

```
Data quality enforcement:
  sklearn.preprocessing: StandardScaler, MinMaxScaler, RobustScaler
  sklearn.impute: SimpleImputer, KNNImputer, IterativeImputer
  sklearn.pipeline: Pipeline ensures consistent transform chain
  sklearn.compose: ColumnTransformer for per-column schemas
  
Key invariant: ∀pipeline step S: S.transform(X) preserves row count ∧ defined for all X values
```

---

## Property Summary

| # | Property | Invariant | Detection method | Enforcement in orbit |
|---|----------|-----------|-----------------|---------------------|
| 1 | Schema validation | `∀row: row ∈ schema` | TFDV, Great Expectations | `pkg/dspy` sig field check, `pkg/featurestore` type validation, `pkg/neuralnet` shape check |
| 2 | Distribution drift | `P_train ≈ P_serve` | KS test, PSI, evidently.ai | `pkg/sampler` output distribution check, `pkg/featurestore` drift monitoring |
| 3 | Completeness | `∀required: non-null` | Null counts, imputation tracking | `pkg/featurestore` nil values, `pkg/neuralnet` NaN check, `pkg/evalmetrics` length check |
| 4 | Lineage | `∀datum: provenance known` | MLMD, DVC, custom metadata | `pkg/featurestore` version+expiry, `pkg/medusa` per-token attribution, `pkg/modelmerging` per-weight source |
| 5 | Freshness | `max(now - ts) ≤ SLA` | Timestamp comparison | `pkg/featurestore` Expires enforcement, `pkg/federatedsgd` staleness window |
| 6 | Privacy | `PII masked, ε ≤ budget` | DP-SGD, k-anonymity, PII regex | `pkg/neuralnet` gradient clipping, `pkg/federatedsgd` DP updates, `pkg/rlhfdpo` PII scrubbing |
| 7 | Training invariants | `∇L finite, loss ↓, val stable` | Gradient check, loss monitoring, NaN detection | `pkg/grpo` importance clipping, `pkg/lorafinetuner` zero init, `pkg/ringattention` gradient sync |
| 8 | Model evaluation | `slice metrics ≤ baseline, fair` | Slice evaluation, fairness metrics, model cards | `pkg/evalmetrics` per-slice metrics, `pkg/sampler` eval guard, `pkg/federatedsgd` per-client eval |
| 9 | Pipeline integrity | `row count preserved, deterministic` | Checksums, row count checks, schema gates | `pkg/featurestore` monotonic versions, `pkg/grpo` atomic pipeline |
| 10 | ML Test Score | `score ≥ 16/28` | Breck et al. checklist | All orbit ML packages |

---

## Orbit-Specific: All 15 ML Packages Mapped

| Package | Data quality properties | Key invariants |
|---------|------------------------|----------------|
| `pkg/dspy` | Schema, Drift, Lineage, Evaluation | `∀field in sig: field ∈ input map`; `∀demo: model_version = current`; `∀train/test: no overlap` |
| `pkg/grpo` | Drift, Completeness, Training, Evaluation | `∀prompt: P_train ≈ P_serve`; `∀response: non-empty`; `∀gradient: finite`; `∀batch: reward on held-out` |
| `pkg/rlhfdpo` | Privacy, Training, Evaluation | `∀feedback: PII-scrubbed`; `∀preference: chosen != rejected`; `∀logprob: finite` |
| `pkg/sampler` | Drift, Freshness, Evaluation | `∀S: P(S.output) ≈ P_train`; `∀S: config_freshness ≤ SLA`; `∀S: eval ≥ baseline` |
| `pkg/promptopt` | Schema, Drift, Evaluation | `∀prompt: valid format`; `∀optimization: held-out eval`; `∀iteration: metric improves` |
| `pkg/ringattention` | Training | `∀device: gradient sync complete`; `∀step: gradients finite`; `∀layer: activations balanced` |
| `pkg/mambassm` | Training | `∀layer: ||∇state|| > ε_min`; `∀layer: ||∇state|| < C`; `∀step: state finite` |
| `pkg/ropeattention` | Training | `∀head: ||∇Q|| ≈ ||∇K|| ≈ ||∇V||`; `∀position: encoding bounded` |
| `pkg/loraqlora` | Completeness, Training | `∀weight: codebook != nil`; `∀step: ||∇quantized - ∇full|| ≤ ε`; `∀rank: no collapse` |
| `pkg/lorafinetuner` | Schema, Privacy, Training | `∀r: target_module ∈ model`; `∀adapter: provenance known`; `∀t=0: W=0`; `∀step: gradient finite` |
| `pkg/modelmerging` | Drift, Lineage, Evaluation | `∀M_i: D_KL(M_i || merged) ≤ ε`; `∀weight: provenance known`; `∀task: metric ≥ min(source)` |
| `pkg/neuralnet` | Schema, Completeness, Training, Privacy | `∀layer: shapes match`; `∀tensor: finite`; `∀gradient: ||∇|| < 1e-7`; `∀weight: clipped` |
| `pkg/federatedsgd` | Lineage, Freshness, Privacy, Training, Evaluation | `∀update: provenance known`; `∀update: staleness ≤ max`; `∀update: DP-clipped`; `∀client: eval ≥ global - ε` |
| `pkg/flashkmeans` | Training, Evaluation | `∀iteration: inertia ↓`; `∀cluster: silhouette ≥ baseline`; `∀assignment: non-NaN` |
| `pkg/medusa` | Lineage, Freshness, Evaluation | `∀token: provenance = (draft|target)`; `∀draft: M.training ≤ target.training`; `∀model: acceptance_rate ≥ α` |

---

## References

1. Breck, E. et al. (2016). "ML Test Score: A Rubric for ML Production Readiness and Technical Debt Reduction." Google. — The 28-test battery for ML production readiness.
2. Breck, E. et al. (2017). "TFX: A Production ML Pipeline." Google. — TensorFlow Extended architecture, including TFDV for schema and drift detection.
3. Baylor, D. et al. (2017). "Continuous Training for Production ML in the TensorFlow Extended (TFX) Platform." Google. — ML pipeline components and their interactions.
4. Mitchell, M. et al. (2019). "Model Cards for Model Reporting." — The model card specification for transparent ML model documentation.
5. Gebru, T. et al. (2018). "Datasheets for Datasets." — Framework for documenting dataset provenance, motivation, and composition.
6. Dwork, C. & Roth, A. (2014). "The Algorithmic Foundations of Differential Privacy." Foundations and Trends in Theoretical Computer Science. — The comprehensive reference for differential privacy theory and mechanisms.
7. Sweeney, L. (2002). "k-Anonymity: A Model for Protecting Privacy." International Journal on Uncertainty, Fuzziness and Knowledge-based Systems. — The k-anonymity framework for privacy protection.
8. Abadi, M. et al. (2016). "Deep Learning with Differential Privacy." ACM CCS. — DP-SGD: per-example gradient clipping + noise for deep learning.
9. Barocas, S., Hardt, M. & Narayanan, A. (2019). "Fairness and Machine Learning." fairmlbook.org. — The reference for fairness metrics and algorithmic fairness.
10. Doshi-Velez, F. & Kim, B. (2017). "Towards A Rigorous Science of Interpretable Machine Learning." — Evaluation beyond aggregate metrics.
11. Polyzotis, N. et al. (2019). "Data Validation for Machine Learning." SysML. — TFDV validation patterns for production ML.
12. Sugiyama, M. et al. (2012). "Machine Learning in Non-Stationary Environments." MIT Press. — Covariate shift, concept drift, and domain adaptation theory.
13. evidently.ai documentation. — Open-source drift detection and model monitoring.
14. NannyML documentation. — Post-deployment model monitoring (confidence-based performance estimation).
15. Sculley, D. et al. (2015). "Hidden Technical Debt in Machine Learning Systems." NeurIPS. — The ML engineering debt framework.