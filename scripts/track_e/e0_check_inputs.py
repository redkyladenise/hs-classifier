import os
import duckdb

def check_file(name, filepath, expect_rows=False):
    """Checks if a file exists and safely counts its rows if it's a parquet file."""
    if not os.path.exists(filepath):
        print(f" MISSING: {name} (Expected at {filepath})")
        return False
    
    print(f" FOUND: {name}")
    
    if expect_rows and filepath.endswith('.parquet'):
        try:
            # DuckDB safely counts rows without loading the whole file into RAM
            conn = duckdb.connect(database=':memory:')
            count = conn.execute(f"SELECT COUNT(*) FROM read_parquet('{filepath}')").fetchone()[0]
            print(f"   -> Row count: {count:,}")
        except Exception as e:
            print(f"   ->  Could not count rows: {e}")
    
    return True

def run_checks():
    print("--- Starting Track E Input Checks ---\n")
    
    # 1. Training & Text Data
    check_file("Training Pool", "data/processed/training_pool.parquet", expect_rows=True)
    check_file("Train Pairs Main", "data/processed/train_pairs_main.parquet", expect_rows=True)
    check_file("Normalized Descriptions", "data/interim/norm_descriptions.parquet", expect_rows=True)
    check_file("Desc Code Counts", "data/processed/desc_code_counts.parquet", expect_rows=True)
    check_file("Unique Descriptions", "data/processed/unique_descriptions.parquet", expect_rows=True)
    
    # 2. Model & Features
    check_file("IDF Main Weights", "data/processed/idf_main.npy")
    check_file("Feature Extractor Script", "src/hsclf/models/features.py")
    
    # 3. Validation & Test
    check_file("Validation Set (val_cal_main)", "data/processed/val_cal_main.parquet", expect_rows=True)
    check_file("Calibration Map", "models/v1/calibration_main.json")
    
    # 4. Audit Data (Track B)
    check_file("Verified Set (66 rows)", "data/audit/verified_set.parquet", expect_rows=True)
    
    # Note: We will check the Track F valid codes and predictions once you confirm their names/paths!
    print("\n--- Check Complete ---")
    print("If any files say 'MISSING', we need to locate them before building the index.")

if __name__ == "__main__":
    run_checks()