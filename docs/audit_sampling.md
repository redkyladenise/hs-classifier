# Audit Sampling Record (Step B3)

- **Date:** October 2026
- **Sampling Seeds:**
  - Main Sample: `seed=42`
  - Reserve Pool: `seed=43`
- **Total Tested Frame Size:** 790,058 descriptions

## Sample Sizes
- **Main Audit Sample (N=180):**
  - Stratum A (Conflicting): 90
  - Stratum B (Repeated Clean): 45
  - Stratum C (Singletons): 45
- **Reserve Pool (N=40):**
  - Stratum A: 20
  - Stratum B: 10
  - Stratum C: 10

## Constraints & Integrity Verification
1. **L2 Skeleton Uniqueness:** 
   - Total items across main + reserve: 220
   - Unique `group_l2` count: 220
   - Zero duplicate `group_l2` occurrences.
2. **Shortfalls:** None. All target stratum allocations fully satisfied.

## Checksums (SHA-256)
- `data/audit/sample_main.csv`: `5674bc6eef047c676e65f76823f7218266b67dcd2f4c1d78447dbc8bae3dd60c`
- `data/audit/sample_reserve.csv`: `7fa1c72d11268631c150f2df2e3735cfb558d84d26350466bf8b0f5634f1db4d`
- `data/audit/sample_key.csv`: `1e99783dd829625f2523be4bcf76c2bfb8929f39ffe0556d005ce4cdb8c08c7e`
