# Dataset Split Manifest (Track A8)

- **Date Generated:** 2026-10-21 01:17:48 UTC
- **Random Seed:** 42
- **Partitioning Unit:** Level-2 Skeleton Group (`group_l2`)
- **Stratum Key:** Group-level Majority 8-digit Code (`majority_ahtn8_l2`)
- **Target Proportions:** 70% Train / 15% Val / 15% Test ($\pm 0.5\%$)

## 1. Frozen Artifact Checksums (SHA-256)
- `data/processed/split_assignments.parquet`: `8d7204ab0b2f1d2eec2d286a2c03d2d65b54301268f43d1a5d5f513c98d63c7d`
- `data/processed/description_status.parquet`: `067e7b98c00975759cae99ae12510e7031f65f427cc279cf360fe841174e163a`

## 2. Partition Summary
| Split | Level-2 Groups | % Early Groups | Transactions | % Early Tx | Level-1 Descriptions |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **train** | 2,224,421 | 69.9952% | 7,963,825 | 70.1865% | 4,267,533 |
| **val** | 476,805 | 15.0035% | 1,667,738 | 14.6980% | 908,559 |
| **test** | 476,734 | 15.0013% | 1,715,102 | 15.1155% | 912,322 |
| **only_2025** | 1,439,678 | N/A (held out) | 2,162,558 | N/A (2025 only) | 1,837,519 |
| **Total** | **4,617,638** | **100.00%** | **13,509,223** | **100.00%** | **7,925,933** |

## 3. Evaluation Scenario Matrix
| Scenario | Train Transactions (Years) | Val Transactions (Years) | Test Transactions (Years) | % New in Test |
| :--- | :--- | :--- | :--- | :--- |
| **`unseen`** | 6,137,119 (2023–2024) | 1,292,833 (2023–2024) | 1,325,533 (2023–2024) | 100.00% |
| **`y1`** | 2,986,625 (2023) | 633,239 (2023) | 4,488,289 (2024) | 65.59% |
| **`y2`** | 6,137,119 (2023–2024) | 1,292,833 (2023–2024) | 4,753,738 (2025) | 61.57% |

## 4. Sampling Feasibility for Track B (Test Conflicts)
Conflicting descriptions ($\ge 2$ transactions, $> 1$ 8-digit code) available in the frozen test split:
- Chapter 39: 3,939
- Chapter 73: 4,245
- Chapter 84: 10,216
- Chapter 85: 9,711
- Chapter 87: 4,133
- **Total Track B Pool:** 32,244 descriptions
