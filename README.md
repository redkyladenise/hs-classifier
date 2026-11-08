
## Running the Website
To run the web application locally:
1. Activate your virtual environment.
2. Run: `flask --app app run --debug`
3. Open `http://127.0.0.1:5000` in your browser.

## Pipeline Execution Order (Track A: Data Engineering)

1. `scripts/a1_slim_transactions.py` -> Ingests raw data to `transactions_slim.parquet`.
2. `scripts/a2_standardize_codes.py` -> Builds `code_map.parquet` and `codes_standardized.parquet`.
3. `scripts/a3_count_raw_descriptions.py` -> Generates partitioned raw description counts.
4. `scripts/a5_normalize_descriptions.py` -> Produces `raw_to_norm.parquet` and `norm_descriptions.parquet`.
5. `scripts/a6_scope_unique_descriptions.py` -> Filters in-scope trade (Chapters 84, 85, 39, 73, 87) to `unique_descriptions.parquet`.
6. `scripts/a7_group_descriptions.py` -> Builds skeleton clusters (`group_l2`) and `transactions_grouped.parquet`.
7. `scripts/a8_group_split.py` -> Creates zero-leakage `split_assignments.parquet` and `description_status.parquet`.
8. `scripts/a9_class_eligibility.py` -> Computes `class_eligibility.parquet` and ceiling metrics.
9. `scripts/a9b_training_pool.py` -> Produces hierarchical `training_pool.parquet` and conducts leakage probe.
10. `scripts/a10_spot_check.py` -> Generates checksum manifest and audits pipeline determinism.

## Pipeline Execution Order (Track B: Label Quality Audit & Benchmark)

1. `scripts/b0_readiness_check.py` -> Validates prerequisites and verifies test frame readiness.
2. `scripts/track_b/b1_build_test_frame.py` -> Extracts test partition and builds `frame_test.parquet`.
3. `scripts/track_b/b1_population_conflicts.py` -> Identifies population-level code conflicts and stratifies into Strata A, B, and C.
4. `scripts/track_b/b2_create_template.py` -> Generates audit data schema and blank labeling templates.
5. `scripts/track_b/b3_draw_sample.py` -> Draws stratified main audit sample (N=180) into `labels_main_blank.csv`.
6. `docs/labeling_guide.md` -> Defines and freezes classification protocol (Guide v1.0).
7. Manual Audit (Step B5) -> Completes adjudication under Guide v1.0 to produce `labels_main.csv`.
8. `scripts/track_b/b6_draw_40_samples.py` -> Extracts blind 40-item consistency sample into `labels_relabel_blank.csv`.
9. `scripts/track_b/b6_label_comparison.py` -> Evaluates Gate B3 inter-round reliability, outputs `disagreements_b6.csv`, and freezes `labels_frozen.csv`.
10. `scripts/track_b/b7_analysis.py` -> Quantifies hidden noise, conflict ceilings, and extracts gold `verified_set.parquet`.
11. Step B8 Finalization -> Generates SHA-256 manifests, updates `docs/decisions.md`, and creates `track-b-complete` tag.

## Pipeline Execution Order (Track C: Hierarchical Model Training & Pipeline Construction)

1. Step C0 (Readiness & Rules) -> Enforces 0.76 GB RAM limit and software versions, updating `config/params.yaml`, `requirements.txt`, `docs/decisions.md`, and `docs/model_log.md`.
2. Step C1 (Data Tables) -> Sorts raw data into flashcards, practice tests, and family trees, generating `data/processed/train_pairs_main.parquet`, `hierarchy_main.parquet`, `val_tune`, `val_cal`, and `test_unseen.parquet` files.
3. Step C2 (Feature & Architecture Setup) -> Builds the Hashing Trick extractor, rulebook, and node logic in `src/hsclf/models/features.py`, `hierarchy.py`, and `node.py`, and extracts importance weights into `data/processed/idf_main.npy`.
4. `scripts/track_c/c3_train_baseline.py` & `c3_evaluate_baseline.py` -> Trains and evaluates the massive "Flat" Logistic Regression baseline, saving the deprecating model to `models/track_c/baselines/main/flat_logistic.pkl`.
5. `scripts/track_c/c3_report_baselines.py` -> Calculates Fallback strategies and Exact Match dictionary metrics, outputting to `reports/tables/c3_baselines_main.csv`.
6. `scripts/track_c/c4_1_tune_regularization.py` -> Executes search for optimal strictness settings per hierarchical level, saving to `config/best_c_grid.json`.
7. `scripts/track_c/c4_2_train_ladder.py` & `c4_3_evaluate_ladder.py` -> Fixes alpha math and active columns bloat, trains the hierarchy at N=50 and N=200, and evaluates hardware constraints into `reports/tables/c4_ladder_hardware_stats.csv`.
8. Step C5 (Factory Train & Inference) -> Mass-produces 32-bit compressed nodes into `models/v1/main/*.pkl` with `manifest.json`, and tests the LRU Cache and Beam-5 search, generating `reports/tables/c5_speed.csv` and `c5_val_cal.csv`.
9. Step C6 (Calibration & Confidence) -> Fixes overconfidence using Isotonic Regression, producing `models/v1/calibration_main.json`, bias trackers, risk-coverage curves, and setting traffic lights in `reports/tables/c6_confidence_bands.csv`.
10. Step C7 (Out-of-Scope Check) -> Establishes $t\_oos = 0.3788$, tests gibberish and unchosen chapters for leakage into `reports/tables/c7_oos.csv`, and executes the Gate C2 model freeze. Later changed to 0.05 after testing against Track B Verified Set.
11. Step C8 (Final Evaluation) -> Tests the frozen model against unseen, Y1, and Y2 sets, outputting tables (`headline_metrics.csv`, `c8_hierarchical_errors.csv`) and charts (`fig4_risk_coverage_curve.png`) to `reports/c8_results.md`.
12. Step C9 (Verified Set Eval) -> Grades the AI against Track B's 66-item gold standard, applying Wilson Score Intervals and population weights into `reports/tables/c9_verified.csv`.
13. `src/hsclf/pipeline.py` & `scripts/track_c/c11_gate_g3.py` -> Unifies the extraction and engine code, tests 20 UI-routed examples, outputs SHA-256 checksums to `docs/data_log.md`, creates `docs/model_card.md`, and tags `track-c-complete` (Gate G3).