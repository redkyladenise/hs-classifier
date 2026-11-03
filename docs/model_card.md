# HS Classifier Model Card (Track C, Phase 11)

## 1. Intended Use & Scope
* **Primary Use Case:** High-precision, human-in-the-loop decision support system for hierarchical customs tariff classification (AHTN 2022).
* **Scope:** Geographically constrained to Philippine Bureau of Customs import declarations. Categorically constrained to 5 specific chapters (39, 73, 84, 85, 87) based on Track A filtering.
* **Target Audience:** Customs brokers, tariff analysts, and warehouse routers.

## 2. Model Architecture & Size
* **Architecture:** Hierarchical Local Classifier Per Node (LCPN) Logistic Regression with Beam-5 Search.
* **Why Flat 8-Digit Was Rejected:** A single "flat" multinomial model classifying directly to the 8-digit level generated an estimated 3.78 GB of coefficients, which catastrophically exceeded the 0.76 GB hardware RAM limit.
* **Compression (Alpha Conversion Rule):** To resolve memory limits, coefficients were cast from 64-bit to 32-bit floats and empty TF-IDF columns (Inactive Columns architecture) were explicitly sliced out.
* **Storage Footprint:**
  * **Main Model (N=200):** 1,135 MB total across all nodes.
  * **Y1/2024 Model (N=200):** [To be recorded upon future full-retraining].

## 3. Inference Memory, Speed & Pipeline
* **Memory Management:** The `HSInferenceEngine` utilizes an LRU (Least Recently Used) Cache to load node binaries on-demand dynamically, preventing memory spikes and strictly enforcing the 0.76 GB RAM ceiling.
* **Speed:** Validated in Phase C5 to process bulk inferences well within the 12-hour batch SLA constraint.
* **Inference Pipeline:** Executes raw text normalization -> feature extraction -> Beam-5 search -> Track F validity check -> confidence calibration -> out-of-scope routing -> deepest confident level selection. 

## 4. Training Data & Hardware Settings
* **Ground Truth Source:** Historical Bureau of Customs declarations (2023–2024).
* **Schedule:** AHTN 2022.
* **Versions:** Python 3.10+, scikit-learn 1.3+, DuckDB 0.10+, Polars.
* **Reproducibility:** Seed=42 enforced globally across all splits, random states, and bootstraps. Training pool hashed and locked with SHA-256 checksums in the data log.

## 5. Metrics & Thresholds
* **Evaluation Baseline:** Evaluated primarily on Unseen test sets for calibration, with Y1/Y2 sets utilized to measure temporal concept drift.
* **Thresholds:** Model implements frozen calibration bands (Platt Scaling) and predefined Out-of-Scope (OOS) rules. Predictions falling below the accepted confidence band are routed for human review.

## 6. Known Caveats & Limitations
1. **Noisy Labels:** The model learns from historical *declared* codes (what brokers filed), which are not strictly verified. The target variable represents the historical "majority declared code," meaning the model replicates broker consensus, including historical broker biases.
2. **Capped Training Pool:** The training data is explicitly capped at N=200 examples per class due to hardware limits, leaving potential minority variations unlearned.
3. **Black-Box Features:** Using Hashing/TF-IDF limits semantic explainability (we cannot extract simple "if-this-then-that" word rules).
4. **Near-Twin Leakage:** As documented in the A9b probe, highly repetitive commercial terminology creates unavoidable high-similarity leakage (~10.9%) between training and test sets.
5. **Temporal Drift:** The model's baseline accuracy degrades on subsequent years (2024, 2025) due to shifting supply chain vocabulary.
6. **Local Hardware Constraints:** All architectural decisions (N=200 cap, caching, 32-bit floats) were artificially forced by local RAM limitations, meaning the mathematical ceiling of this dataset has not been reached.
7. **Note on Handled Models:** Track D handled models (H1, H2, H3) were strictly experimental, were not recalibrated, and do not replace the frozen baseline model.