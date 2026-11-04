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

## E7: Masked Examples & Leak Review
**Sample:** 100 single-chapter queries randomly selected from the evaluation set (`part_0000.parquet`).
**Output:** Generated 123 masked nearest-neighbor examples.
**Review Findings & Fixes:**
1. **Measurement Over-masking:** Valid measurements like `25kgs` and `60mmx20mm` were initially being destroyed by the alphanumeric model regex. *Fix:* Updated the `[model]` rule to use a custom evaluation function (`mask_model`) that recognizes and explicitly spares valid unit sequences (kgs, mm, cm, m, pcs, etc.) while still catching part numbers.
2. **Address Collisions:** The generic address regex falsely flagged words like "floor" (e.g., "22 pkgs of floor covering"). *Fix:* Stripped the generic address regex entirely and restricted `[address]` masking strictly to safe Philippine location markers (brgy, purok, sitio, etc.) to prevent product term false positives.
3. **Brand Additions:** Added `sekisui` and `qingdao` to `brands.txt` and created a multi-word override for `mr diy`.
**Final Leak Count:** 0 leaks detected in the final review output.
**Performance Impact:** Matrix operations initially caused severe latency. Matrices are now converted to Compressed Sparse Row (`.tocsr()`) format upon load, dropping the average query time to **< 0.10s**, successfully meeting the performance requirement with masking enabled.