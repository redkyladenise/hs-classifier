import duckdb
import yaml
from pathlib import Path

def build_desc_code_counts():
    # Load settings from params.yaml
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
    
    norm_buckets = params["norm_buckets"]
    
    # Create temporary folder for our buckets
    temp_dir = Path("data/processed/temp_counts")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Start DuckDB with our strict memory ceiling
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='0.75GB'")
    con.execute("PRAGMA threads=1")
    
    print("Counting transactions per description, code, and year...")
    
    # Process one bucket at a time to save RAM
    for i in range(norm_buckets):
        print(f"Processing bucket {i} of {norm_buckets - 1}...")
        # desc_code_counts.parquet : Column Names
        query = f"""
        COPY (
            SELECT group_l1, ahtn8, year, count(*) as tx_count      
            FROM read_parquet('data/processed/transactions_grouped.parquet')
            WHERE norm_bucket = {i}
            GROUP BY group_l1, ahtn8, year
        ) TO '{temp_dir}/part_{i}.parquet' (FORMAT PARQUET)
        """
        con.execute(query)
        
    print("Combining buckets into final file...")
    
    # Combine all parts into one final dataset
    con.execute("""
        COPY (
            SELECT * FROM read_parquet('data/processed/temp_counts/part_*.parquet')
        ) TO 'data/processed/desc_code_counts.parquet' (FORMAT PARQUET)
    """)
    
    print("Done! desc_code_counts.parquet is ready.")

def build_training_pairs():
    import duckdb
    
    # Start DuckDB with our strict memory ceiling
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='0.75GB'")
    con.execute("PRAGMA threads=1")
    
    # We will loop over both our scenarios (main and y1)
    scenarios = {
        'main': {'years': '(2023, 2024)', 'rank_col': 'rank_main'},
        'y1': {'years': '(2023)', 'rank_col': 'rank_y1'}
    }
    
    for scenario, conf in scenarios.items():
        print(f"Building training pairs for scenario: {scenario}...")
        
        # This big query calculates the weights and extracts the parent codes
        query = f"""
        COPY (
            WITH base_counts AS (
                SELECT 
                    group_l1, 
                    ahtn8, 
                    SUM(tx_count) as total_tx
                FROM read_parquet('data/processed/desc_code_counts.parquet')
                WHERE year IN {conf['years']}
                GROUP BY group_l1, ahtn8
            ),
            capped AS (
                SELECT 
                    b.group_l1,
                    b.ahtn8,
                    b.total_tx * 1.0 / SUM(b.total_tx) OVER (PARTITION BY b.group_l1) AS weight,
                    substring(b.ahtn8, 1, 2) AS ch2,
                    substring(b.ahtn8, 1, 4) AS hd4,
                    substring(b.ahtn8, 1, 6) AS sh6
                FROM base_counts b
                JOIN read_parquet('data/processed/training_pool.parquet') p
                  ON b.group_l1 = p.group_l1
                WHERE p.{conf['rank_col']} <= 200
                  AND p.{conf['rank_col']} IS NOT NULL
            )
            SELECT 
                c.group_l1,
                c.ahtn8,
                c.ch2,
                c.hd4,
                c.sh6,
                c.weight,
                COALESCE(e2.eligible_at_20, false) AS elig_ch2,
                COALESCE(e4.eligible_at_20, false) AS elig_hd4,
                COALESCE(e6.eligible_at_20, false) AS elig_sh6,
                COALESCE(e8.eligible_at_20, false) AS elig_ahtn8
            FROM capped c
            LEFT JOIN read_parquet('data/processed/class_eligibility.parquet') e2
              ON e2.scenario = '{scenario}' AND e2.level = 2 AND e2.class = c.ch2
            LEFT JOIN read_parquet('data/processed/class_eligibility.parquet') e4
              ON e4.scenario = '{scenario}' AND e4.level = 4 AND e4.class = c.hd4
            LEFT JOIN read_parquet('data/processed/class_eligibility.parquet') e6
              ON e6.scenario = '{scenario}' AND e6.level = 6 AND e6.class = c.sh6
            LEFT JOIN read_parquet('data/processed/class_eligibility.parquet') e8
              ON e8.scenario = '{scenario}' AND e8.level = 8 AND e8.class = c.ahtn8
        ) TO 'data/processed/train_pairs_{scenario}.parquet' (FORMAT PARQUET)
        """
        con.execute(query)
        
    print("Done! Training pairs built successfully.")

def build_validation_halves():
    import duckdb
    import yaml
    
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
        
    tune_size = params["val_tune_size"]
    cal_size = params["val_cal_size"]
    
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='0.75GB'")
    con.execute("PRAGMA threads=1")
    
    # We do this for both main and y1 scenarios
    scenarios = {
        'main': "split = 'val'",
        'y1': "split = 'val' AND first_year_l2 = 2023 AND last_year_l2 = 2023"
    }
    
    for scenario, filter_cond in scenarios.items():
        print(f"Building validation halves for {scenario}...")
        
        # 1. Join split_assignments to unique_descriptions to get all validation IDs
        # 2. Use hash(group_l2) to randomly (but permanently) assign to Tune or Cal
        # 3. Limit to the exact size requested in params.yaml
        
        # Tuning Half
        query_tune = f"""
        COPY (
            WITH val_groups AS (
                SELECT group_l2 FROM read_parquet('data/processed/split_assignments.parquet')
                WHERE {filter_cond}
            ),
            val_descs AS (
                SELECT u.desc_norm_id as group_l1, u.group_l2
                FROM read_parquet('data/processed/unique_descriptions.parquet') u
                JOIN val_groups v ON u.group_l2 = v.group_l2
            ),
            shuffled AS (
                SELECT group_l1 
                FROM val_descs 
                WHERE hash(group_l2) % 2 = 0 
                ORDER BY hash(group_l1)
                LIMIT {tune_size}
            )
            SELECT * FROM shuffled
        ) TO 'data/processed/val_tune_{scenario}.parquet' (FORMAT PARQUET)
        """
        con.execute(query_tune)
        
        # Calibration Half
        query_cal = f"""
        COPY (
            WITH val_groups AS (
                SELECT group_l2 FROM read_parquet('data/processed/split_assignments.parquet')
                WHERE {filter_cond}
            ),
            val_descs AS (
                SELECT u.desc_norm_id as group_l1, u.group_l2
                FROM read_parquet('data/processed/unique_descriptions.parquet') u
                JOIN val_groups v ON u.group_l2 = v.group_l2
            ),
            shuffled AS (
                SELECT group_l1 
                FROM val_descs 
                WHERE hash(group_l2) % 2 = 1 
                ORDER BY hash(group_l1)
                LIMIT {cal_size}
            )
            SELECT * FROM shuffled
        ) TO 'data/processed/val_cal_{scenario}.parquet' (FORMAT PARQUET)
        """
        con.execute(query_cal)
        
    print("Done! Validation halves are ready.")

def list_test_descriptions():
    import duckdb
    
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='0.75GB'")
    con.execute("PRAGMA threads=1")
    
    print("Building test set lists...")
    
    # 1. Unseen scenario (2023-2024 holdout)
    # The 'split' column contains 'test' for the unseen descriptions. 
    # Since these are in the test split, they are by definition "new" to the training set.
    query_unseen = """
    COPY (
        SELECT group_l1, 'new' as seen_status 
        FROM read_parquet('data/processed/description_status.parquet')
        WHERE split = 'test'
    ) TO 'data/processed/test_unseen.parquet' (FORMAT PARQUET)
    """
    con.execute(query_unseen)
    
    # 2. y1 scenario (2024 Rollout)
    query_y1 = """
    COPY (
        SELECT group_l1, seen_y1 as seen_status 
        FROM read_parquet('data/processed/description_status.parquet')
        WHERE seen_y1 IS NOT NULL
    ) TO 'data/processed/test_y1.parquet' (FORMAT PARQUET)
    """
    con.execute(query_y1)
    
    # 3. y2 scenario (2025 Rollout)
    query_y2 = """
    COPY (
        SELECT group_l1, seen_y2 as seen_status 
        FROM read_parquet('data/processed/description_status.parquet')
        WHERE seen_y2 IS NOT NULL
    ) TO 'data/processed/test_y2.parquet' (FORMAT PARQUET)
    """
    con.execute(query_y2)
    
    print("Done! Test sets (unseen, y1, y2) are ready.")

def build_hierarchy_tables():
    import duckdb
    
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='0.75GB'")
    con.execute("PRAGMA threads=1")
    
    scenarios = ['main', 'y1']
    
    for scenario in scenarios:
        print(f"Building hierarchy map for {scenario}...")
        
        # We use our train_pairs table to map out the parents and children
        query = f"""
        COPY (
            WITH root_nodes AS (
                SELECT 0 as parent_level, 'root' as parent_code, 2 as child_level, 
                       count(DISTINCT ch2) as n_children, count(DISTINCT group_l1) as n_train_desc
                FROM read_parquet('data/processed/train_pairs_{scenario}.parquet')
                WHERE elig_ch2 = true
            ),
            chapter_nodes AS (
                SELECT 2 as parent_level, ch2 as parent_code, 4 as child_level, 
                       count(DISTINCT hd4) as n_children, count(DISTINCT group_l1) as n_train_desc
                FROM read_parquet('data/processed/train_pairs_{scenario}.parquet')
                WHERE elig_ch2 = true AND elig_hd4 = true
                GROUP BY ch2
            ),
            heading_nodes AS (
                SELECT 4 as parent_level, hd4 as parent_code, 6 as child_level, 
                       count(DISTINCT sh6) as n_children, count(DISTINCT group_l1) as n_train_desc
                FROM read_parquet('data/processed/train_pairs_{scenario}.parquet')
                WHERE elig_hd4 = true AND elig_sh6 = true
                GROUP BY hd4
            ),
            subheading_nodes AS (
                SELECT 6 as parent_level, sh6 as parent_code, 8 as child_level, 
                       count(DISTINCT ahtn8) as n_children, count(DISTINCT group_l1) as n_train_desc
                FROM read_parquet('data/processed/train_pairs_{scenario}.parquet')
                WHERE elig_sh6 = true AND elig_ahtn8 = true
                GROUP BY sh6
            )
            SELECT * FROM root_nodes
            UNION ALL SELECT * FROM chapter_nodes
            UNION ALL SELECT * FROM heading_nodes
            UNION ALL SELECT * FROM subheading_nodes
        ) TO 'data/processed/hierarchy_{scenario}.parquet' (FORMAT PARQUET)
        """
        con.execute(query)
        
    print("Done! Hierarchy maps are ready.")

if __name__ == "__main__":
    # build_desc_code_counts()
    build_training_pairs()
    # build_validation_halves()
    # list_test_descriptions()
    build_hierarchy_tables()
