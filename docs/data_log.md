# Data Log & Provenance

## 1. Project Specifications

- **Objective:** Develop an HS Code classifier using BOC import records.
- **Data source:** Bureau of Customs (BOC) import declarations, obtained through BetterGov.PH / Open Customs Data.
- **Source repository:** [Hugging Face — bettergovph/open-customs-data](https://huggingface.co/datasets/bettergovph/open-customs-data)
- **Years covered:** 2023–2025
- **Classification levels:** 2–8 digits
- **Environment:** Windows 11, 8 GB RAM
- **Evaluation requirements:** Refer to Track 0.1.
- **File format:** Parquet; CSV source files excluded per project rules.

## 2. Raw Dataset Inventory

- **Storage location:** `data/raw/`
- **Source repository:** [Hugging Face — bettergovph/open-customs-data](https://huggingface.co/datasets/bettergovph/open-customs-data)
- **Download date:** 10-20-2026
- **Dataset revision:** Updated 9 months ago.

| File | Size (Bytes) | Size (MB) | SHA-256 Checksum |
|---|---:|---:|---|
| `2023.parquet` | 735,684,212 | 701.56 | 042094f8e98bb88d1ad5889cb53060d98b287f064ddedb12a3c95fc9089826b1 |
| `2024.parquet` | 762,909,055 | 727.45 | b7125910a025d0a615d0fa96aecf3bc90cb72b58103d039cf4702f08ff479626 |
| `2025.parquet` | 799,659,139 | 762.37 | be8cf3353682243db488ce4b488d045843ca677c07c1a3f541a460c49c829a9d |

- **Raw data handling:** Raw Parquet files were read without intentional modification.

## 3. Data Characteristics and Identified Issues

### 3.1 Required fields

The environment check confirmed that all three files contain:

- `HSCODE`
- `GOODSDESCRIPTION`
- `year`
- `month`

### 3.2 HS code storage

| Year | Stored type |
|---|---|
| 2023 | `BIGINT` |
| 2024 | `BIGINT` |
| 2025 | `BIGINT` |

- HS codes contain 10- and 11-digit values in the inspected data.
- Numeric storage cannot preserve leading zeros. During preprocessing, HS codes must be converted to strings and normalized according to the intended classification level.
- The original code representation and any leading-zero recovery assumptions should be documented and validated.

### 3.3 Record identification
- No `uid` column was found.
- A deterministic surrogate `row_id` may be generated using the configured format: `{year}-{row_position:08d}`.
- Row position must be assigned consistently during extraction to maintain traceability to the source records.

## 4. License and Provenance Status
- **License status:** Unresolved.
- **Current finding:** Explicit open-license terms have not yet been verified for the downloaded dataset.
- **Pending actions:** Confirm the dataset's applicable license or obtain clarification from the maintainers.
- **Release consideration:** Resolve licensing requirements before publicly distributing the dataset, derived files, or a deployed demonstration.

## 5. Memory Stress Test

**Date:** 2026-10-20

### Environment and configuration

- Python 3.14.3 (64-bit)
- DuckDB 1.5.6
- Available RAM before individual-year tests: 3.82–3.84 GB
- DuckDB memory limit: 0.6 GB (approximately 572.2 MiB)
- Threads: 1
- Insertion-order preservation: Disabled

**Input files:** `data/raw/2023.parquet`, `data/raw/2024.parquet`, `data/raw/2025.parquet`

### Query A — Count distinct goods descriptions

| Dataset | Distinct descriptions | Runtime | Peak process memory | Lowest available RAM |
|---|---:|---:|---:|---:|
| 2023 | 5,617,466 | 0.10 min | 590.6 MB | 3.14 GB |
| 2024 | 5,958,882 | 0.13 min | 620.5 MB | 2.92 GB |
| 2025 | 6,217,526 | 0.12 min | 631.4 MB | 2.96 GB |
| All years | Failed: `DuckDB OutOfMemoryException` | Not recorded | Not recorded | Not recorded |

### Query B — Count rows by HSCODE digit length

| Dataset | 10-digit codes | 11-digit codes | Runtime |
|---|---:|---:|---:|
| 2023 | 114,774 | 8,352,315 | 0.01 min |
| 2024 | 130,375 | 8,861,762 | 0.01 min |
| 2025 | 147,588 | 9,282,893 | 0.01 min |

### Results and decision

- Both queries completed successfully when run separately for each year.
- The all-years distinct-description query exceeded DuckDB's configured memory limit of approximately 572 MiB.
- The lowest observed free system RAM during individual-year Query A runs was 2.92 GB.
- The temporary directory measured 0 MB after successful queries; peak temporary-disk usage was not measured.

**Decision:** Borderline overall under the predefined criteria. Use per-year or partitioned processing for memory-intensive operations. Monitor resource usage during subsequent preprocessing and model training.

## Frozen Splits Log (Track A8) - 2026-10-21
- `data/processed/split_assignments.parquet`: SHA-256 `8d7204ab0b2f1d2eec2d286a2c03d2d65b54301268f43d1a5d5f513c98d63c7d` (READ-ONLY)
- `data/processed/description_status.parquet`: SHA-256 `067e7b98c00975759cae99ae12510e7031f65f427cc279cf360fe841174e163a` (READ-ONLY)
- Partition policy: Level-2 skeleton grouping with stratified position-based assignment (seed 42).
