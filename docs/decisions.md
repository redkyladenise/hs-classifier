## 0.12 Memory Stress Test

**Date:** 2026-10-20

**Decision:** Proceed with local processing using per-year or partitioned operations.

**Configuration:** DuckDB memory limit of 0.6 GB, 1 thread, and insertion-order preservation disabled.

**Results:**
- 2023, 2024, and 2025 each completed both stress-test queries successfully.
- Individual-year queries completed in under 10 seconds each.
- The lowest available system RAM during individual-year tests ranged from 2.92 GB to 3.14 GB for Query A.
- The combined all-years distinct-description query failed with `DuckDB OutOfMemoryException` at approximately 572 MiB of the 572.2 MiB memory limit.
- The temporary directory was 0 MB after each successful query.

**Rationale:** Individual-year processing is feasible under the tested configuration, but the combined distinct-description query exceeds the configured DuckDB memory limit.

**Implementation implications:** Process data per year or in manageable partitions for memory-intensive operations. Combine intermediate results where necessary. Reassess memory usage during A3–A9 because this test covers only two queries.

**Limitations:** These results do not establish the memory requirements of every future processing step. Cloud processing is not currently necessary based on this test alone. Confirm dataset licensing before considering cloud processing.