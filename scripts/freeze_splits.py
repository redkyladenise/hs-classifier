import hashlib
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
import duckdb

ROOT = Path(".").resolve()
processed_dir = ROOT / "data" / "processed"
split_file = processed_dir / "split_assignments.parquet"
desc_status_file = processed_dir / "description_status.parquet"


def get_sha256(file_path: Path) -> str:
  hasher = hashlib.sha256()
  with open(file_path, "rb") as f:
    while chunk := f.read(1024 * 1024):
      hasher.update(chunk)
  return hasher.hexdigest()


split_sha = get_sha256(split_file)
desc_sha = get_sha256(desc_status_file)

con = duckdb.connect()

split_counts = con.execute(f"""
    SELECT 
        split, 
        count(*) AS n_groups, 
        sum(n_transactions)::BIGINT AS n_tx
    FROM read_parquet('{split_file.as_posix()}')
    GROUP BY split
    ORDER BY split
""").df()

desc_counts = con.execute(f"""
    SELECT 
        split, 
        count(*) AS n_descriptions
    FROM read_parquet('{desc_status_file.as_posix()}')
    GROUP BY split
    ORDER BY split
""").df()

manifest_content = f"""# Dataset Split Manifest (Track A8)

- **Date Generated:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}
- **Random Seed:** 42
- **Partitioning Unit:** Level-2 Skeleton Group (`group_l2`)
- **Stratum Key:** Group-level Majority 8-digit Code (`majority_ahtn8_l2`)
- **Target Proportions:** 70% Train / 15% Val / 15% Test ($\pm 0.5\%$)

## 1. Frozen Artifact Checksums (SHA-256)
- `data/processed/split_assignments.parquet`: `{split_sha}`
- `data/processed/description_status.parquet`: `{desc_sha}`

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
"""

with open(ROOT / "docs" / "split_manifest.md", "w", encoding="utf-8") as f:
  f.write(manifest_content)
print("Wrote docs/split_manifest.md")

# Append to data_log.md
data_log_path = ROOT / "docs" / "data_log.md"
with open(data_log_path, "a", encoding="utf-8") as f:
  f.write(f"""
## Frozen Splits Log (Track A8) - {datetime.now(timezone.utc).strftime("%Y-%m-%d")}
- `data/processed/split_assignments.parquet`: SHA-256 `{split_sha}` (READ-ONLY)
- `data/processed/description_status.parquet`: SHA-256 `{desc_sha}` (READ-ONLY)
- Partition policy: Level-2 skeleton grouping with stratified position-based assignment (seed 42).
""")
print("Updated docs/data_log.md")

# Mark files read-only
os.chmod(split_file, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
os.chmod(desc_status_file, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
print("Marked split files as READ-ONLY.")