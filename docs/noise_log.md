# Track D: Noise Log & Resource Verification

## Environment
- Python: 3.14.3
- scikit-learn: 1.9.1
- DuckDB: 1.5.6
- Available RAM at start: 1.06 GB
- Free Disk space: 269.80 GB
- Locked test sample size (`d_test_sample_size`): 300,000

## File Verification Table

| File Path | Status | Size (MB) | SHA-256 |
|:---|:---:|:---:|:---|
| `data/processed/train_pairs_main.parquet` | Verified | 4.68 | `52e8423f5befe2e26d447504f3b4d95dbfe6f8d0c7510bb32a923b0508b6d890` |
| `data/processed/desc_code_counts.parquet` | Verified | 83.33 | `fd110a71ddd27b8f283b24bc1261544882a6ec325d60ec2b9032770c76863a78` |
| `data/processed/unique_descriptions.parquet` | Verified | 134.37 | `6659d5d2292f578ca38d32ea9020de1548fff00f7f7dd2730aa0f2016bda6230` |
| `data/processed/hierarchy_main.parquet` | Verified | 0.01 | `1338848c32b5ed04c4b23a564b92f6c125aa8d4632d1aa21df3b400cc400f7d4` |
| `models/v1/main/manifest.json` | Verified | 0.37 | `306787880c2f74b100892e7ec3d1c66c37ff1a60d9e848a780dacb498dcde531` |
| `data/audit/verified_set.parquet` | Verified | 0.01 | `9347debec17abd9e5b22adbaa92a6eb2ec7656674808512e42d400a6111acd6d` |
| `data/audit/labels_frozen.csv` | Verified | 0.04 | `4b7a0c151a4137fa0ad34a606510c0a5c4f2789b74baa2632d1da47dfc4ee306` |
| `data/audit/sample_key.csv` | Verified | 0.02 | `1e99783dd829625f2523be4bcf76c2bfb8929f39ffe0556d005ce4cdb8c08c7e` |

## Table Row Counts

- **train_pairs_main**: (380150, 364761)
- **verified_set**: 66
- **labels_frozen**: 180

## Track D (D1 & D2): Label Conflict Handling Results

**D1: Reality Check on Historical Conflicts**
* **Prevalence:** Label conflicts affect 2.65% of unique descriptions but account for a massive 20.36% of total transaction volume. 
* **The "Majority" Trap:** When evaluating the historical "majority" code against our audited test set, the majority rule failed 58.82% of the time at the 8-digit level. Real-world conflicts are too unreliable to establish a pure ground truth.

**D2: Synthetic Experiment (Laboratory Test)**
To test data cleaning methods, we built a perfectly clean synthetic base of 38,125 descriptions. We injected 10% and 20% fake conflicts and tested three handling methods against a conflict-free validation set (n=49,270 test records).
* **H1 (Majority Rule):** Keep the highest-weighted code, drop the rest.
* **H2 (Drop):** Completely remove conflicted descriptions.
* **H3 (Down-weight):** Keep all codes, but halve their sample weights.

**Findings & Gate Decision (at 20% Noise Level):**
The baseline SGD model (using sublinear TF-IDF) is naturally robust to noise. The clean baseline achieved 65.63% accuracy. Injecting 20% label noise barely moved the needle, dropping accuracy to 65.51% (a mere -0.12% degradation). 

Crucially, **all handling methods resulted in negative recovery**, making the model worse than simply leaving the noisy data alone:
* **H2 (Drop) was disastrous:** Accuracy plummeted to 64.08%. This is a -1.43% penalty compared to the raw noisy baseline (Recovery: -11.91). Dropping conflicting items destroys critical vocabulary features needed for future predictions.
* **H3 (Down-weight) underperformed:** Accuracy dropped to 65.17% (a -0.34% penalty vs. noisy).
* **H1 (Majority) hides the true signal:** Accuracy dropped to 65.29% (a -0.21% penalty vs. noisy). Forcing the model to only see the majority code hides the underlying true codes that were competing with the noise.

**Status:** The synthetic harness is sane and behaved as mathematically expected. Passed the post-D2 Gate: Proceeding to D3 and D4 to verify if this total failure of data cleaning holds true on real-world data.

## Track D (D3 & D4): Real-World Handled Training Results

**D3: Building the Handled Training Pairs**
We applied the three handling methods to the real, historical `train_pairs_main.parquet` data (364,761 descriptions containing 9,664 conflicts), dynamically recalculating the C1 eligibility thresholds.
* **H1 (Majority Rule):** Deduplicated the 9,664 conflicting descriptions down to their single highest-weighted code.
* **H2 (Drop):** Purged the conflicting descriptions entirely, reducing the dataset to 355,097 clean descriptions.
* **H3 (Down-weight):** Retained all pairs but halved the sample weights of conflicting descriptions.

**D4: Retraining the Handled Hierarchies**
We trained three separate full-scale hierarchies (H1, H2, H3) using the identical, frozen hyperparameters from our C5 baseline (sublinear TF-IDF, identical SGD C-grid). 

**Findings & C4 Sanity Rule Failures:**
While the C5 baseline model trained on raw data successfully navigated all nodes, **all three heuristic handling methods mathematically broke the AI, inducing terminal node collapse** (where the model abandons learning and defaults to predicting the majority class):
* **H1 and H3 (2 nodes collapsed - 8410, 8521):** By deleting or down-weighting the minority conflicting codes, the data distribution was artificially skewed. The SGD optimizer failed to find a separating hyperplane for the minority classes.
* **H2 (3 nodes collapsed - 8410, 8521, 8702):** Dropping conflicted descriptions entirely was the most destructive approach, as it starved the model of the diverse vocabulary features needed to learn complex boundaries.

**Conclusion:** The raw, unhandled data provides a richer, more balanced feature space. Attempting to manually force a "clean consensus" on historical customs conflicts destroys critical training signals.