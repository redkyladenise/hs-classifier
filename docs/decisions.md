## 0.12 Memory Stress Test

**Date:** 2026-10-20

**Pass:** Both queries finish in under 10 minutes per run, the computer does not freeze or run out of memory, and at least 20% of the free RAM measured before the run remains available at the lowest point.

**Borderline:** Queries finish but exceed 10 minutes, or processing all years together is unreliable while per-year processing works.

**Fail:** A query crashes, freezes the computer, or causes memory exhaustion.

**Results:**
- Both queries passed for each individual year (2023, 2024, and 2025), finishing in under 10 seconds.
- The lowest free system RAM during the distinct-description queries was approximately 2.92 GB, above the 20% reserve threshold.
- The all-years distinct-description query failed because it exceeded DuckDB's 0.6 GB memory limit.

**Decision:** Borderline overall. Use per-year or partitioned processing for memory-intensive operations. Reassess if later preprocessing or model training exceeds available resources.