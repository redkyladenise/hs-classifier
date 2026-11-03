# Track E: Retrieval Log
**Gate E0: Readiness and Resource Verification**
- **Status:** Passed
- **Date:** November 2026
- **System Memory Ceiling:** 0.68 GB
- **Track F Code List:** `data/reference/ahtn_2022_scope_reference.parquet` (Column: `code8`)
- **Note on Training Pool:** Raw pool holds 3.69M rows. E1 script will filter this down to the N=200 cap (~364k rows) by joining with `train_pairs_main.parquet` to respect the RAM ceiling.
- **Dataset License:** Unresolved. `show_examples` is set to `false`. Masks will be applied, but plain text examples will be hidden in UI until resolved.

**Pre-commitments (from params.yaml):**
- `retrieval_k`: 5
- `split_share`: 0.60
- `min_example_tx`: 20

# Retrieval Engine Log

## E2 Benchmarks (200 queries)
- **Peak RAM Usage:** 93.33 MB (Well below the 680 MB / 0.68 GB constraint)
- **Time per query:** 0.0870 seconds
- **Evidence Text used:** "How others declared similar goods. Unverified, and may include errors."