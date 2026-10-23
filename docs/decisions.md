## TRACK 0.12: Memory Stress Test

**Date:** 2026-10-20
**Pass:** Both queries finish in under 10 minutes per run, the computer does not freeze or run out of memory, and at least 20% of the free RAM measured before the run remains available at the lowest point.
**Borderline:** Queries finish but exceed 10 minutes, or processing all years together is unreliable while per-year processing works.
**Fail:** A query crashes, freezes the computer, or causes memory exhaustion.
**Results:**
- Both queries passed for each individual year (2023, 2024, and 2025), finishing in under 10 seconds.
- The lowest free system RAM during the distinct-description queries was approximately 2.92 GB, above the 20% reserve threshold.
- The all-years distinct-description query failed because it exceeded DuckDB's 0.6 GB memory limit.
**Decision:** Borderline overall. Use per-year or partitioned processing for memory-intensive operations. Reassess if later preprocessing or model training exceeds available resources.

## Track A2: Reference Checks & Nomenclature Ground Truth

### 1. AHTN 2022 Effective Date
- **Status:** Confirmed
- **Finding:** The ASEAN Harmonized Tariff Nomenclature 2022 (AHTN 2022) was approved by the NEDA Board on May 27, 2022, and formally took effect in the Philippines on **July 01, 2022**. Starting July 01, 2022, advance rulings based on AHTN 2017 were invalidated.
- **Source:** Bureau of Customs / Tariff Commission Letters dated June 24, 2022, pursuant to Section 1100 of the Customs Modernization and Tariff Act (CMTA).
- **Impact on Project:** All transaction records in our dataset (2023, 2024, 2025) fall entirely within the AHTN 2022 lifecycle. No legacy mapping from AHTN 2017 is required.

### 2. Tariff Book 2022 (AHTN 2022) Source
- **Status:** Confirmed
- **Finding:** The official Philippine Tariff Book 2022 is published by the Tariff Commission, organized into 21 Sections and 97 active Chapters, with chapter-level PDF documents hosted via the official portal.
- **Columns in Official Schedule:** Heading Number (`Hdg. No.`), `AHTN 2022 Code` (6, 8, or national extension digits), `Description`, and `MFN Rates of Duty (%)`.
- **Source:** [Tariff Commission — Tariff Book 2022](https://tariffcommission.gov.ph/tariff-book/) (Accessed: October 2026).
- **Impact on Project:** Provides the official hierarchical ground truth for Chapters 01–97, headings (4-digit), subheadings (6-digit), and regional tariff lines (8-digit).

### 3. Digits 9–11 Structure (National Subdivisions)
- **Status:** Confirmed
- **Finding:** 
  - Digits 1–2: Chapter (WCO international)
  - Digits 3–4: Heading (WCO international)
  - Digits 5–6: Subheading (WCO international)
  - Digits 7–8: AHTN Regional Tariff Lines (ASEAN Harmonized Tariff Nomenclature)
  - Digits 9–11: Fifth level — Philippine Standard Commodity Classification (PSCC) statistical/commodity subdivisions appended when national requirements are not in one-to-one correspondence with the 8-digit AHTN code.
- **Source:** 2022 Philippine Standard Commodity Classification (PSCC) / Tariff Commission.
- **Impact on Project:** Confirms that digits 9–11 represent purely domestic administrative/statistical sub-items. Truncating or ignoring digits 9–11 and targeting the 8-digit level (AHTN 2022) maintains strict alignment with ASEAN regional nomenclature standards without loss of tariff classification validity.

## Track A3: Profiling & Bucket Partitioning

- **Processing Rule:** Aggregating distinct descriptions and calculating top-N across all 26.89M rows exceeded the 0.6 GB memory ceiling during Track 0 stress testing.
- **Implementation:** Used 16 hash buckets (`abs(hash(goods_description)) % 16`). Each description maps to exactly one bucket part (`part_00.parquet` to `part_15.parquet`).
- **Bucket Count:** 16 buckets. No bucket exceeded memory or failed; doubling bucket count was unnecessary.
- **Memory & Disk Usage:** Peak memory per bucket stayed well under the 0.6 GB ceiling. Each bucket file wrote cleanly to `data/interim/raw_desc_counts/`.
- **Validation Outcome:** Sum of distinct counts equals 16,757,438, satisfying the bounds $\max(\text{yearly}) \le \text{total} \le \sum(\text{yearly})$.

## Track A4: HS Code Standardization

- **Strategy:** Built an intermediate lookup table `data/interim/code_map.parquet` mapping distinct original codes to standardized fields (`ahtn8`, `sh6`, `hd4`, `ch2`, `hs_extra`, `code_fix`, `code_flag`, `ends_00`, `right_padded`). This was joined back to `transactions_slim.parquet` in yearly streaming passes.
- **Memory Compliance:** Avoided executing Python row-by-row on 26.89M records. Peak memory remained well below 0.6 GB RAM.
- **Data Quality & Findings:**
  - 100% of rows (26,889,707) mapped to `valid` codes.
  - Zero rows flagged as `bad_format`, `odd_length`, or `bad_chapter`.
  - Fix breakdown: 98.54% `trim_extra` (11 digits -> 8 digits + 3 digits in `hs_extra`), 1.46% `left_pad` (10 digits with dropped leading zero -> padded to 11 digits -> 8 digits + 3 digits in `hs_extra`).
  - Total output row counts preserved: 2023 = 8,467,089; 2024 = 8,992,137; 2025 = 9,430,481 (Total: 26,889,707).


## Track A5: Goods Description Normalization

- **Deduplication & Mapping:**
  - Input: 16,757,438 distinct raw descriptions sourced directly from A3 bucket count tables (`data/interim/raw_desc_counts/part_*.parquet`).
  - Output Mapping: `data/interim/raw_to_norm.parquet` retains the full 16,757,438 mappings.
  - Normalized Dictionary: `data/interim/norm_descriptions.parquet` deduplicates into 15,869,694 unique normalized descriptions (reduction of 887,744 redundant variations).
- **ID Strategy:** Generated stable 63-bit integers via `blake2b(digest_size=8) & 0x7FFFFFFFFFFFFFFF`. Audit verified zero hash collisions across all 16 norm buckets.
- **Data Quality & Status Distribution:**
  - `ok`: 16,757,162 descriptions (99.9984%).
  - `placeholder`: 2 descriptions (0.0000%).
  - `blank`: 274 descriptions (0.0016%, consisting of empty strings, pure symbols, or digit-only entries).


## Track A6: Chapter Scope Selection & Dataset Cleaning

### 1. Chapter Ranking Rule & Scope Criteria
- **Ranking Metric:** Distinct normalized descriptions (`desc_norm_id`) declared under each chapter (`ch2`) across 2023–2025 among valid transactions (`code_flag == 'valid'` and `desc_status == 'ok'`). 
- **Counting Policy:** A description counts once for every chapter it appears under. Distinct counts are evaluated globally per chapter across 2023–2025; yearly distinct counts are never summed.
- **Top-N Selection:** Select the top five chapters ranked by unique normalized descriptions.
- **Coverage Threshold:** Set a defensible cumulative transaction coverage threshold of **50.0%** of all valid transactions. If the top five chapters cover less than 50.0% of valid transactions, add the next-highest-ranked chapters one at a time up to a hard ceiling of eight chapters.
- **Cross-Chapter Descriptions:** If a `desc_norm_id` appears across both chosen and unchosen chapters, only rows mapped to in-scope chapters are retained in `transactions_scope.parquet`. The count of cross-chapter descriptions is logged in pipeline reports.

### 2. Low-Memory Chunked Join Architecture
- `transactions_clean.parquet` is constructed by partitioning `transactions_slim` across 16 hash buckets (`abs(hash(goods_description)) % 16`).
- For each bucket, `codes_standardized` is joined on `row_id`, and `raw_to_norm` is joined on text within that hash partition. All raw text is dropped to produce a compact, memory-safe integer schema (`row_id`, `year`, `month`, `desc_norm_id`, `norm_bucket`, `desc_status`, `code_flag`, `ch2`, `hd4`, `sh6`, `ahtn8`, `ends_00`).
### 3. Track A6 Results & Selected Chapters
- **Selected Chapters Count:** 5
- **Selected Chapters:** 84, 85, 39, 73, 87
- **Official Tariff Book Chapter Headings:**
  - **Chapter 84**: Nuclear reactors, boilers, machinery and mechanical appliances; parts thereof (3,920,818 tx, 2,562,757 unique desc, rank #1)
  - **Chapter 85**: Electrical machinery and equipment and parts thereof; sound and television recorders (4,343,029 tx, 2,263,559 unique desc, rank #2)
  - **Chapter 39**: Plastics and articles thereof (1,855,296 tx, 1,120,376 unique desc, rank #3)
  - **Chapter 73**: Articles of iron or steel (1,678,925 tx, 1,078,611 unique desc, rank #4)
  - **Chapter 87**: Vehicles other than railway or tramway rolling-stock, and parts and accessories thereof (1,711,155 tx, 957,460 unique desc, rank #5)
- **Cross-Scope Descriptions:** 63,713 normalized descriptions appeared in both chosen and unchosen chapters. For modeling, only transaction rows under chosen chapters are retained in `transactions_scope.parquet`.

## Track A7: Description Grouping & Conflict Preview

- **Hierarchical Levels Defined:**
  - **Level 1 (`group_l1`):** Direct alias for `desc_norm_id` (identical normalized text).
  - **Level 2 (`group_l2`):** Skeleton representation (near-duplicates). Strips digits and punctuation symbols, tokenizes words, sorts alphabetically, deduplicates tokens, and hashes to a non-negative 63-bit integer via `blake2b(digest_size=8) & 0x7FFFFFFFFFFFFFFF`.
- **Scope & Cardinality:**
  - Distinct Level-1 descriptions in scope: **7,925,933**.
  - Distinct Level-2 skeleton groups in scope: **4,617,638**.
  - Reduction ratio: **1.7164** (52.64% of Level-1 descriptions share a skeleton with at least one other description).
- **Ambiguity & Conflict Rates:**
  - Overall conflicting descriptions: 0.64% at `ch2`, 1.15% at `hd4`, 1.79% at `sh6`, and 2.24% at `ahtn8`.
  - Non-singleton descriptions ($\ge 2$ transactions): 4.72% conflict at `ch2`, 8.43% at `hd4`, 13.11% at `sh6`, and **16.42%** at `ahtn8`.
  - Transaction impact: **20.39% of in-scope transactions** have descriptions declared under multiple 8-digit AHTN codes.
- **Transaction Frequency Profile:**
  - Extreme long-tail: 86.36% of unique descriptions appear exactly once, representing 50.67% of all transactions.
  - Frequent items ($\ge 6$ transactions) comprise only 2.22% of descriptions but drive 32.03% of transactions.
- **Split Hazard Check:**
  - The largest Level-2 skeleton group accounts for **0.5322%** of in-scope transactions (71,890 declarations), safely below the 1.0% threshold for cluster-based train/test splitting.


## Track A8: Leakage-Free Grouped Data Splitting & Scenarios

### 1. Partitioning Unit & Rules
- **Unit of Partition:** The Level-2 skeleton group (`group_l2`). A group is atomic and is never divided across splits. All lexical variants sharing a skeleton are co-located in the same partition.
- **Early vs. Future Groups:**
  - **Early Groups:** Any group having $\ge 1$ transaction in 2023 or 2024. These groups form the candidate pool for train, validation, and test splits.
  - **`only_2025` Groups:** Groups whose declarations occur solely in 2025 (`first_year_l2 == 2025`). These groups are held out exclusively as test cases for full-production evaluation (`y2`) and are never used for model training or hyperparameter tuning.
- **Deterministic Stratification:**
  - Grouping Stratum: Group-level majority 8-digit tariff code (`majority_ahtn8_l2`), computed strictly across `group_l2` partitions.
  - Integer-Mixing Hash: Within each majority code, groups are sorted deterministically using a fixed integer-mixing function (`blake2b` digest of `group_l2` concatenated with the random seed `42`). This replaces platform- or engine-dependent hashing to guarantee byte-for-byte reproducibility across local and cloud environments.
  - Stratum Position Formula:
    $$\text{pos} = \frac{\text{rank} - 0.5}{N_{\text{groups}}}$$
    - $\text{pos} < 0.70 \implies \text{\textbf{train}}$
    - $0.70 \le \text{pos} < 0.85 \implies \text{\textbf{val}}$
    - $\text{pos} \ge 0.85 \implies \text{\textbf{test}}$
- **Split Tolerance:** Target ratio among early groups is 70% train / 15% val / 15% test within a tolerance of $\pm 0.5\%$ of groups.

### 2. Evaluation Scenarios & Temporal Alignment
- **`unseen` Scenario:**
  - Train: 2023–2024 transactions of `train` groups.
  - Validation: 2023–2024 transactions of `val` groups.
  - Test: 2023–2024 transactions of `test` groups (evaluates model generalization to completely unseen product concepts).
- **`y1` Scenario (1-Year Rollout):**
  - Train: 2023 transactions of `train` groups.
  - Validation: 2023 transactions of `val` groups.
  - Test: All 2024 transactions across all groups.
- **`y2` Scenario (Full Production):**
  - Train: 2023–2024 transactions of `train` groups.
  - Validation: 2023–2024 transactions of `val` groups.
  - Test: All 2025 transactions (including `only_2025` groups).
  - *Note:* The `unseen` and `y2` scenarios evaluate the same trained model checkpoint. Data from 2025 is never seen during training or tuning.

### 3. Description "Seen" Status Definitions
For any description (`group_l1`) evaluated in scenario test sets:
- **`seen_exact`:** The description's group is in `train` AND the description's individual `first_year` is $\le$ the scenario's final training year.
- **`seen_near`:** The description's group is in `train` AND the group's `first_year_l2` is $\le$ the scenario's final training year, but the specific `group_l1` text was first observed later.
- **`new`:** The description's group was assigned to `val`, `test`, or `only_2025` (zero lexical overlap with training groups). In the `unseen` scenario, 100% of test descriptions are strictly `new`.

### 4. Integrity & Freeze Policy
- Checksums (SHA-256) are generated for `split_assignments.parquet` and `description_status.parquet` and recorded in `docs/split_manifest.md` and `data_log.md`.
- Both artifacts are treated as immutable and read-only.
- Cherry-picking via seed re-rolling is prohibited.

## Track A9: Class Eligibility by Hierarchical Level

- **Rule & Purpose:**
  - Evaluated training description diversity across hierarchical levels (2, 4, 6, and 8) to establish which tariff lines have sufficient distinct training examples for supervised machine learning models to learn without rote memorization.
  - Primary eligibility criterion: $\ge 20$ distinct Level-1 descriptions in training data (`eligible_at_20`).
  - Sensitivity checks: tested $\ge 10$ (`eligible_at_10`) and $\ge 50$ (`eligible_at_50`) distinct descriptions.
  - Ambiguity check: evaluated primary counts (`n_train_desc_any`) versus majority counts (`n_train_desc_majority`) to monitor inflation caused by the 20.39% multi-code transaction ambiguity.

- **Empirical Eligibility & Coverage Findings:**
  - **Main Scenario (2023–2024 Train Groups — used by `unseen` and `y2`):**
    - **Chapter (2-digit):** 5/5 codes eligible (100.0% coverage).
    - **Heading (4-digit):** 202/202 codes eligible (100.0% coverage).
    - **Subheading (6-digit):** 1,083/1,184 codes eligible (91.47% of codes; **99.98% transaction coverage**). Only 3 codes shifted eligibility under majority counting.
    - **Tariff Line (8-digit):** 2,522/3,351 codes eligible (75.26% of codes; **99.83% transaction coverage** and **99.85% unique description coverage**). Only 37 codes shifted eligibility under majority counting.
  - **Y1 Scenario (2023 Train Groups only):**
    - **8-digit:** 2,213/3,221 codes eligible (68.71% of codes; **99.56% transaction coverage**). 47 codes shifted under majority counting.

- **Theoretical Accuracy Ceilings:**
  - Established the mathematical upper bound for closed-set classifiers restricted to eligible classes:
    - **`unseen` Test Scenario:** **99.83%** maximum reachable accuracy at 8 digits (100.0% at chapters and headings, 99.98% at subheadings).
    - **`y2` Production Test Scenario (2025):** **99.83%** maximum reachable accuracy at 8 digits.
    - **`y1` Test Scenario (2024):** **99.55%** maximum reachable accuracy at 8 digits.

- **Excluded Codes Analysis:**
  - In the `main` scenario, the 829 excluded 8-digit codes together account for less than **0.17%** of in-scope transactions.
  - The single largest excluded code (`8456.40.10` — plasma arc machine tools) comprises only 1,254 transactions (0.0093% of in-scope volume). No other excluded code exceeds 0.0045% of volume.

- **Decision & Downstream Policy:**
  - Non-destructive execution: zero records or classes were dropped. Eligibility flags are stored in `data/processed/class_eligibility.parquet` for downstream filtering, fallback routing, or threshold calibration in Track C.

## Track A9b: Training Pool, Cap Rule & Pre-Training Leakage Probe

- **Temporal Group Dynamics:**
  - Evaluated training groups across years: 79.16% of 2023 groups never recurred in 2024–2025, while 83.28% of 2024 groups were newly introduced. Multi-year pooling is necessary to capture dynamic phrasing turnover.
- **Hierarchical Cap Rule:**
  - Descriptions are assigned a `cap_key` by falling back hierarchically (`majority_ahtn8` -> `majority_sh6` -> `majority_hd4` -> `majority_ch2`) to retain tail examples for coarse-level training.
  - Deterministic integer mix hashing (`seed = 42`) yields strictly nested pools:
    - N=10: 27,889 descriptions
    - N=20: 54,234 descriptions
    - N=50: 121,775 descriptions
    - N=100: 214,636 descriptions
    - N=200: 364,761 descriptions (standard default training budget)
    - N=500: 683,525 descriptions
    - Full uncapped: 3,693,073 descriptions
- **Pre-Training Leakage Probe & Limitation:**
  - Evaluated intra-chapter TF-IDF cosine similarity for 2,000 stratified samples.
  - Findings: `test_vs_train` exhibits 10.90% share at $\ge 0.95$ similarity (mean max similarity 0.7841), compared to 99.90% internal `train_vs_train` similarity.
  - Decision: Rather than rebuilding splits via cloud-scale MinHash, this 10.9% residual near-duplicate lexical overlap is formally recorded as an empirical project limitation. All group-level zero-leakage constraints remain fully intact.


## Track F: Architectural & Governance Decisions Log

### Legislative Amendment Audit (2023–2025)
- **Date Checked:** October 2026
- **Scope:** Chapters 39, 73, 84, 85, and 87.
- **Findings:** 
  - Reviewed key post-2022 Philippine Executive Orders affecting the in-scope chapters, including **EO No. 12 (s. 2023)** (Electric Vehicles and components under Chapter 87) and broader tariff schedules like **EO No. 62 (s. 2024)** and **EO No. 80 (s. 2024)**.
  - Confirmed that these issuances modified **Most Favored Nation (MFN) rates of duty** or introduced 10/11-digit national subheadings for domestic policy, but **did not structurally delete or invalidate the core 8-digit AHTN 2022 leaf codes**.
- **Decision:** AHTN 2022 is formally adopted as the immutable 8-digit validity baseline for the 2023–2025 transaction dataset. Rate modifications and national sub-tier expansions are treated as orthogonal to 8-digit code existence.

## Comparative Analysis of Transaction Records against Reference Data
- **Date Verified:** October 2026
- **Analysis Outcome:** Confirmed that total mismatch volume across Chapters 39, 73, 84, 85, and 87 is ~0.0047% overall (373 out of 7,908,996 transactions), satisfying the < 1.0% governance ceiling by two full orders of magnitude.
- **Formal Decision:** 
  - The AHTN 2022 baseline is formally certified as the authoritative validity standard for the 2023–2025 dataset window.
  - Unlisted codes are classified as non-systemic anomalies (minor typographical errors or edge-case national extensions) and are retained in raw transaction tables without deletion, allowing downstream training modules (Track C) to determine inclusion based on frequency thresholds.
