## TRACK 0.12: Memory Stress Test

**Date:** 2026-10-20
**Pass:** Both queries finish in under 10 minutes per run, the computer does not freeze or run out of memory, and at least 20% of the free RAM measured before the run remains available at the lowest point.
**Borderline:** Queries finish but exceed 10 minutes, or processing all years together is unreliable while per-year processing works.
**Fail:** A query crashes, freezes the computer, or causes memory exhaustion.
**Results:**
- Both queries passed for each individual year (2023, 2024, and 2025), finishing in under 10 seconds.
- The lowest free system RAM during the distinct-description queries was approximately 2.92 GB, above the 20% reserve threshold.
- The all-years distinct-description query failed because it exceeded DuckDB's 0.6 GB memory limit.
**Decision:** Borderline overall. Use per-year or partitioned processing for memory-intensive operations. Reassess if later preprocessing or model training exceeds available resources.

## Track A2: Reference Checks & Nomenclature Ground Truth

### 1. AHTN 2022 Effective Date
- **Status:** Confirmed
- **Finding:** The ASEAN Harmonized Tariff Nomenclature 2022 (AHTN 2022) was approved by the NEDA Board on May 27, 2022, and formally took effect in the Philippines on **July 01, 2022**. Starting July 01, 2022, advance rulings based on AHTN 2017 were invalidated.
- **Source:** Bureau of Customs / Tariff Commission Letters dated June 24, 2022, pursuant to Section 1100 of the Customs Modernization and Tariff Act (CMTA).
- **Impact on Project:** All transaction records in our dataset (2023, 2024, 2025) fall entirely within the AHTN 2022 lifecycle. No legacy mapping from AHTN 2017 is required.

### 2. Tariff Book 2022 (AHTN 2022) Source
- **Status:** Confirmed
- **Finding:** The official Philippine Tariff Book 2022 is published by the Tariff Commission, organized into 21 Sections and 97 active Chapters, with chapter-level PDF documents hosted via the official portal.
- **Columns in Official Schedule:** Heading Number (`Hdg. No.`), `AHTN 2022 Code` (6, 8, or national extension digits), `Description`, and `MFN Rates of Duty (%)`.
- **Source:** [Tariff Commission — Tariff Book 2022](https://tariffcommission.gov.ph/tariff-book/) (Accessed: October 2026).
- **Impact on Project:** Provides the official hierarchical ground truth for Chapters 01–97, headings (4-digit), subheadings (6-digit), and regional tariff lines (8-digit).

### 3. Digits 9–11 Structure (National Subdivisions)
- **Status:** Confirmed
- **Finding:** 
  - Digits 1–2: Chapter (WCO international)
  - Digits 3–4: Heading (WCO international)
  - Digits 5–6: Subheading (WCO international)
  - Digits 7–8: AHTN Regional Tariff Lines (ASEAN Harmonized Tariff Nomenclature)
  - Digits 9–11: Fifth level — Philippine Standard Commodity Classification (PSCC) statistical/commodity subdivisions appended when national requirements are not in one-to-one correspondence with the 8-digit AHTN code.
- **Source:** 2022 Philippine Standard Commodity Classification (PSCC) / Tariff Commission.
- **Impact on Project:** Confirms that digits 9–11 represent purely domestic administrative/statistical sub-items. Truncating or ignoring digits 9–11 and targeting the 8-digit level (AHTN 2022) maintains strict alignment with ASEAN regional nomenclature standards without loss of tariff classification validity.

## Track A3: Profiling & Bucket Partitioning

- **Processing Rule:** Aggregating distinct descriptions and calculating top-N across all 26.89M rows exceeded the 0.6 GB memory ceiling during Track 0 stress testing.
- **Implementation:** Used 16 hash buckets (`abs(hash(goods_description)) % 16`). Each description maps to exactly one bucket part (`part_00.parquet` to `part_15.parquet`).
- **Bucket Count:** 16 buckets. No bucket exceeded memory or failed; doubling bucket count was unnecessary.
- **Memory & Disk Usage:** Peak memory per bucket stayed well under the 0.6 GB ceiling. Each bucket file wrote cleanly to `data/interim/raw_desc_counts/`.
- **Validation Outcome:** Sum of distinct counts equals 16,757,438, satisfying the bounds $\max(\text{yearly}) \le \text{total} \le \sum(\text{yearly})$.

## Track A4: HS Code Standardization

- **Strategy:** Built an intermediate lookup table `data/interim/code_map.parquet` mapping distinct original codes to standardized fields (`ahtn8`, `sh6`, `hd4`, `ch2`, `hs_extra`, `code_fix`, `code_flag`, `ends_00`, `right_padded`). This was joined back to `transactions_slim.parquet` in yearly streaming passes.
- **Memory Compliance:** Avoided executing Python row-by-row on 26.89M records. Peak memory remained well below 0.6 GB RAM.
- **Data Quality & Findings:**
  - 100% of rows (26,889,707) mapped to `valid` codes.
  - Zero rows flagged as `bad_format`, `odd_length`, or `bad_chapter`.
  - Fix breakdown: 98.54% `trim_extra` (11 digits -> 8 digits + 3 digits in `hs_extra`), 1.46% `left_pad` (10 digits with dropped leading zero -> padded to 11 digits -> 8 digits + 3 digits in `hs_extra`).
  - Total output row counts preserved: 2023 = 8,467,089; 2024 = 8,992,137; 2025 = 9,430,481 (Total: 26,889,707).


## Track A5: Goods Description Normalization

- **Deduplication & Mapping:**
  - Input: 16,757,438 distinct raw descriptions sourced directly from A3 bucket count tables (`data/interim/raw_desc_counts/part_*.parquet`).
  - Output Mapping: `data/interim/raw_to_norm.parquet` retains the full 16,757,438 mappings.
  - Normalized Dictionary: `data/interim/norm_descriptions.parquet` deduplicates into 15,869,694 unique normalized descriptions (reduction of 887,744 redundant variations).
- **ID Strategy:** Generated stable 63-bit integers via `blake2b(digest_size=8) & 0x7FFFFFFFFFFFFFFF`. Audit verified zero hash collisions across all 16 norm buckets.
- **Data Quality & Status Distribution:**
  - `ok`: 16,757,162 descriptions (99.9984%).
  - `placeholder`: 2 descriptions (0.0000%).
  - `blank`: 274 descriptions (0.0016%, consisting of empty strings, pure symbols, or digit-only entries).