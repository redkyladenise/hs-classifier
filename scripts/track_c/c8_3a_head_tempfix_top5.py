import duckdb
import pandas as pd
import numpy as np

def generate_m1_top5_with_ci():
    con = duckdb.connect()
    
    scenarios = {
        'unseen': 'year IN (2023, 2024)',
        'y1': 'year = 2024',
        'y2': 'year = 2025'
    }
    
    sc_paths = {
        'unseen': 'unseen',
        'y1': 'y1',
        'y2': 'y2'
    }
    
    for display_name, test_years in scenarios.items():
        sc_file = sc_paths[display_name]
        
        # We group by group_l2 just like your main script to allow cluster bootstrapping
        query = f"""
        WITH truth_base AS (
            SELECT 
                group_l1,
                ahtn8,
                SUBSTRING(ahtn8, 1, 6) as sh6,
                SUBSTRING(ahtn8, 1, 4) as hd4,
                SUM(tx_count) as tx_count
            FROM read_parquet('data/processed/desc_code_counts.parquet')
            WHERE {test_years}
            GROUP BY group_l1, ahtn8
        ),
        predictions AS (
            SELECT * FROM read_parquet('data/processed/predictions_{sc_file}/*.parquet')
        ),
        scored AS (
            SELECT 
                ds.group_l2,
                -- M1 Top-5 Partial Credit Logic (Transaction Weighted)
                (SELECT COALESCE(SUM(tb.tx_count), 0) FROM truth_base tb WHERE tb.group_l1 = p.group_l1 AND tb.ahtn8 IN (p.pred_1, p.pred_2, p.pred_3, p.pred_4, p.pred_5)) as top5_l8_tx,
                (SELECT COALESCE(SUM(tb.tx_count), 0) FROM truth_base tb WHERE tb.group_l1 = p.group_l1 AND tb.sh6 IN (SUBSTRING(p.pred_1,1,6), SUBSTRING(p.pred_2,1,6), SUBSTRING(p.pred_3,1,6), SUBSTRING(p.pred_4,1,6), SUBSTRING(p.pred_5,1,6))) as top5_l6_tx,
                (SELECT COALESCE(SUM(tb.tx_count), 0) FROM truth_base tb WHERE tb.group_l1 = p.group_l1 AND tb.hd4 IN (SUBSTRING(p.pred_1,1,4), SUBSTRING(p.pred_2,1,4), SUBSTRING(p.pred_3,1,4), SUBSTRING(p.pred_4,1,4), SUBSTRING(p.pred_5,1,4))) as top5_l4_tx,
                
                -- Total volume for the description
                (SELECT COALESCE(SUM(tx_count), 0) FROM truth_base tb WHERE tb.group_l1 = p.group_l1) as total_tx
            FROM predictions p
            LEFT JOIN read_parquet('data/processed/description_status.parquet') ds ON p.group_l1 = ds.group_l1
        )
        SELECT 
            group_l2,
            SUM(top5_l8_tx) as top5_l8_sum,
            SUM(top5_l6_tx) as top5_l6_sum,
            SUM(top5_l4_tx) as top5_l4_sum,
            SUM(total_tx) as total_tx_sum
        FROM scored
        GROUP BY group_l2
        """
        
        try:
            df = con.execute(query).df()
            
            # 200-Resample Cluster Bootstrap (Exactly matching Code 1)
            n_resamples = 200
            n_clusters = len(df)
            
            arr_totals = df['total_tx_sum'].values
            sums = {
                'top5_l8': df['top5_l8_sum'].values,
                'top5_l6': df['top5_l6_sum'].values,
                'top5_l4': df['top5_l4_sum'].values
            }
            
            boot_results = {'top5_l8': [], 'top5_l6': [], 'top5_l4': []}
            
            np.random.seed(42) # Match your main script's seed for perfect replication
            for _ in range(n_resamples):
                idx = np.random.randint(0, n_clusters, size=n_clusters)
                sum_tx = np.sum(arr_totals[idx])
                
                if sum_tx > 0:
                    for level in boot_results.keys():
                        boot_results[level].append(np.sum(sums[level][idx]) / sum_tx)
            
            print(f"\n=== {display_name.upper()} CSV ROWS ===")
            for level in ['top5_l8', 'top5_l6', 'top5_l4']:
                mean = np.mean(boot_results[level])
                ci_lower = np.percentile(boot_results[level], 2.5)
                ci_upper = np.percentile(boot_results[level], 97.5)
                print(f"{display_name},{level},{mean},{ci_lower},{ci_upper}")
                
        except Exception as e:
            print(f"Error processing {display_name}: {e}")

if __name__ == "__main__":
    generate_m1_top5_with_ci()