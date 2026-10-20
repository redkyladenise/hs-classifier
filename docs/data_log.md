# Data Log

## Project Specifications
- Task/objective: HS Classifier using BOC 2023-2024 import records. Windows 11, 8 GB RAM
- Classification levels: 2 to 8 digit 
- Data source: Open Customs Data from BetterGov.ph
- Evaluation requirements: [From 0.1]

## Raw Files

| Filename | Size (bytes) | Size (MB) |
|---|---:|---:|
| 2023.parquet | 735,684,212 | 701.56 |
| 2024.parquet | 762,909,055 | 727.45 |
| 2025.parquet | 799,659,139 | 762.37 |

Checksums and license: To be documented in A1.

## HSCODE Stored Data Types
- 2023: BIGINT
- 2024: BIGINT
- 2025: BIGINT

## 0.12 Memory Stress Test — 2026-10-20

**Input data:** `data/raw/2023.parquet`, `data/raw/2024.parquet`, `data/raw/2025.parquet`

**Environment:** Python 3.14.3; DuckDB 1.5.6; available RAM before individual-year tests: 3.82–3.84 GB.

**DuckDB settings:** Memory limit = 0.6 GB (572.2 MiB applied); threads = 1; insertion-order preservation disabled.

### Query A — Count distinct goods descriptions

| Dataset | Distinct descriptions | Elapsed time | Peak Python-process memory | Lowest available RAM |
|---|---:|---:|---:|---:|
| 2023 | 5,617,466 | 0.10 min | 590.6 MB | 3.14 GB |
| 2024 | 5,958,882 | 0.13 min | 620.5 MB | 2.92 GB |
| 2025 | 6,217,526 | 0.12 min | 631.4 MB | 2.96 GB |
| All years | Failed with `DuckDB OutOfMemoryException` | Not recorded | Not recorded | Not recorded |

### Query B — Count rows by HSCODE digit length

| Dataset | 10-digit codes | 11-digit codes | Elapsed time |
|---|---:|---:|---:|
| 2023 | 114,774 | 8,352,315 | 0.01 min |
| 2024 | 130,375 | 8,861,762 | 0.01 min |
| 2025 | 147,588 | 9,282,893 | 0.01 min |

**Temporary storage:** The `data/interim/duckdb_tmp` directory measured 0.00 MB after each successful query. Peak temporary-disk usage was not measured.

**Outcome:** Individual-year tests passed the proposed time and available-RAM criteria. The combined all-years distinct-description query failed at approximately 572.0 MiB / 572.2 MiB of DuckDB memory.

**Data handling:** Raw Parquet files were read without intentional modification.

**Next action:** Use per-year or partitioned processing for memory-intensive operations and monitor resource usage during A3–A9.