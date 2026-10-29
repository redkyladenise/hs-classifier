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