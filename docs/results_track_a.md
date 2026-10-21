# Track A: Data Engineering & Preprocessing — Final Results

## 1. Executive Summary & Thesis Numbers

* **Raw Population:** 26,889,707 total import declaration transactions (2023–2025).
* **Lexical Cardinality:**
  * Raw distinct descriptions: 16,757,438
  * Normalized distinct descriptions (Level 1): 15,869,694 (5.30% reduction from normalization).
* **Commodity Scope (Chapters 84, 85, 39, 73, 87):**
  * Scope transactions: 13,509,223 (50.24% of national transaction volume).
  * In-scope unique Level-1 descriptions: 7,925,933.
  * Skeleton groups (Level 2): 4,617,638.
  * Skeleton reduction ratio: 1.7164 (41.74% reduction in distinct entities; 52.64% of descriptions grouped in multi-item clusters).
* **Sparsity & Ambiguity Dynamics:**
  * Singleton descriptions: 86.36% of Level-1 descriptions appear exactly once in the entire multi-year corpus.
  * Multi-code ambiguity: 20.39% of transactions belong to descriptions declared under multiple conflicting HS codes.
  * Cluster dominance: The single largest Level-2 skeleton group contains only 0.53% of transactions, ensuring balanced cluster sizes without partition skew.
* **Dataset Splitting & Leakage Audit (A8):**
  * Group-based deterministic split: 70% Train, 15% Validation, 15% Test.
  * Split assignments: 4,617,638 groups mapped with 0.00% entity overlap (exact zero-leakage verified).
* **Class Eligibility & Theoretical Accuracy Ceilings (A9):**
  * Evaluated across 4 hierarchical tiers under `main` (2023–2024 train groups) and `y1` (2023 train groups):
    * 2-digit (Chapter): 5/5 eligible (100.0% coverage; ceiling: 100.0%).
    * 4-digit (Heading): 202/202 eligible (100.0% coverage; ceiling: 100.0%).
    * 6-digit (Subheading): 1,083/1,184 eligible (99.98% coverage; ceiling: 99.98%).
    * 8-digit (Tariff Line): 2,522/3,351 eligible (75.26% of codes; 99.83% transaction coverage; ceiling: 99.83%).
  * Ineligible classes: 829 codes account for only 0.17% of transactions; largest excluded code (`8456.40.10`) comprises only 1,254 declarations (0.0093% volume).
* **Training Pool & Capacity Capping (A9b):**
  * Full uncapped candidate pool: 3,693,073 descriptions.
  * Standard capped training pool ($N=200$ per class): 364,761 descriptions (90.12% reduction).
  * Monotonically nested ladder sizes: $N=10$ (27,889), $N=20$ (54,234), $N=50$ (121,775), $N=100$ (214,636), $N=200$ (364,761), $N=500$ (683,525).
* **Lexical Leakage Probe Findings:**
  * 2,000 stratified samples evaluated with intra-chapter TF-IDF cosine similarity against the training pool.
  * `test_vs_train`: Mean max similarity = 0.7841; 10.90% share $\ge 0.95$.
  * `val_vs_train`: Mean max similarity = 0.7961; 12.80% share $\ge 0.95$.
  * `train_vs_train` (Internal Baseline): Mean max similarity = 0.9990; 99.90% share $\ge 0.95$.

---

## 2. Infrastructure & Compute Log

* **DuckDB Version:** 1.5.6
* **Bucket Architecture:** 16 hash buckets (`norm_bucket` = 0 to 15) using 64-bit BLAKE2b hash partitioning.
* **Execution Environment:**
  * **Local Workstation:** Stages A1, A2, A3 (bucketing & counts), A4 (code standardization), A5 (normalization), A6 (scope extraction & ambiguity aggregation), A7 (skeleton grouping), A8 (group-based splitting), A9 (class eligibility), A9b (hierarchical capping & leakage probe), and A10 (validation & wrap-up).
  * **Cloud Compute:** None required; complete Track A pipeline executed successfully within local memory and storage limits using DuckDB out-of-core and partitioned execution.

---

## 3. Formally Stated Limitations

1. **Trade Scope Limitation:** The scope is intentionally restricted to Chapters 84, 85, 39, 73, and 87. While this covers 50.24% of all Philippine declaration transactions, findings may not generalize to agricultural products (Chapters 1–24), textiles (Chapters 50–63), or base metals outside Chapter 73.
2. **Extreme Empirical Sparsity:** 86.36% of Level-1 descriptions occur only once across the 2023–2025 corpus. The long tail is predominantly composed of single-transaction phrasing.
3. **Pervasive Real-World Ambiguity:** 20.39% of transactions belong to descriptions associated with conflicting HS codes, reflecting genuine commercial practices and administrative classification differences.
4. **Residual Lexical Proximity (Pre-Training Probe):** While strict group partitioning guarantees 0.00% exact text leakage between splits, 10.90% of test descriptions share $\ge 0.95$ TF-IDF similarity with training phrases due to minor numerical, dimension, or boiler-plate differences (e.g., bolt dimensions or part serials). Full MinHash clustering was omitted locally due to computational constraints.
5. **Stratified Capacity Capping:** Models trained on the standard budget ($N=200$ per class) observe at most 200 descriptions per tariff line, which caps exposure to high-volume generic commodity categories to preserve class balance and memory bounds.

---

## 4. Track B & Track C Handoff Specification

The downstream tracks require the following primary artifacts and schema contracts:

| Required Artifact | Primary Columns | Purpose / Downstream Consumer |
| :--- | :--- | :--- |
| `data/processed/transactions_grouped.parquet` | `row_id`, `year`, `month`, `group_l1`, `group_l2`, `ch2`, `hd4`, `sh6`, `ahtn8`, `ends_00` | Track B (conflict typology) & Track C (evaluation transactions) |
| `data/processed/unique_descriptions.parquet` | `desc_norm_id`, `majority_ahtn8`, `n_transactions`, `n_codes_*` | Track B (majority code assignment) & Track C (feature lookup) |
| `data/processed/split_assignments.parquet` | `group_l2`, `split` | Track C (dataset partition routing) |
| `data/processed/description_status.parquet` | `group_l1`, `group_l2`, `split`, `seen_y1`, `seen_y2` | Track C (seen vs. unseen test segmentation) |
| `data/processed/class_eligibility.parquet` | `scenario`, `level`, `class`, `eligible_at_20`, `n_train_desc_*` | Track C (evaluation target filtering & theoretical ceilings) |
| `data/processed/training_pool.parquet` | `group_l1`, `cap_key`, `rank_main`, `rank_y1` | Track C (model training samples by ladder budget) |
| `data/interim/code_map.parquet` | `raw_code`, `clean_code`, `right_padded` | Track B (conflict analysis: padding vs. true conflict) |