# A3 Data Profile Summary

## 1. Overview & Transaction Volumes
- **Total Transactions:** 26,889,707 across 2023–2025.
  - 2023: 8,467,089
  - 2024: 8,992,137
  - 2025: 9,430,481
- **Temporal Continuity:** All 12 calendar months are present in all three years without gaps.
- **Missing & Anomalous Values:** 0 null descriptions, 0 null codes, 0 zero codes, and 0 negative codes across all years.

## 2. Code Digit-Length Distribution
- **Observed Lengths:** Only 10-digit and 11-digit codes exist in the raw data:
  - **11 digits:** 98.54% overall (2023: 98.64%, 2024: 98.55%, 2025: 98.44%).
  - **10 digits:** 1.46% overall (2023: 1.36%, 2024: 1.45%, 2025: 1.57%).
- **Reason:** The original numeric `BIGINT` storage dropped leading zeros on Chapters 01–09 (e.g., Chapter 01 stored as a 10-digit number instead of 11). Restoring the leading zero produces standard 11-digit codes (8-digit AHTN 2022 + 3-digit PSCC).

## 3. Description Characteristics & Lengths
- **Distinct Raw Descriptions:**
  - 2023: 5,617,466
  - 2024: 5,958,882
  - 2025: 6,217,526
  - **Total Overall:** 16,757,438 distinct descriptions across the 16 hash buckets.
  - **Sanity Check:** Passed ($6,217,526 \le 16,757,438 \le 17,793,874$).
- **Length Quantiles (Approximate):**
  - Character length: Min 1, Median 43–45, P95 119–127, Max 256.
  - Word count: Min 1, Median 7, P95 18–19, Max 76–82.
  - Share with $\le 2$ words: 10.3%–11.4%.

## 4. Repetition, Placeholders & Word Frequencies
- **Repetition:** The top 1,000 distinct descriptions account for 1,504,743 transactions (**5.60%** of total volume). The dataset has a very long tail; over 62% of descriptions appear only once or twice.
- **Short Descriptions / Placeholders:** Inspected strings with $\le 3$ characters. The most frequent are valid electronics/hardware abbreviations (`IC`, `NUT`, `LED`, `PIN`, `PCB`, `CAP`, `FAN`, `DIE`, `JIG`). No pure junk placeholders (e.g., `N/A`, `-`, `.`) were identified among high-frequency entries. Inconsistent padding was observed (e.g., `' IC'` vs `'IC '`), confirming the need for whitespace trimming.
- **Top Words:** Word frequencies were computed across distinct descriptions and weighted by transaction frequency (`n_transactions`).