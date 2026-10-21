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