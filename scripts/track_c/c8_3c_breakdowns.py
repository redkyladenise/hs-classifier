import duckdb
import pandas as pd
from pathlib import Path

def run_c8_3c():
    print("--- Phase 3C: Breakdowns & Drift ---")
    con = duckdb.connect()
    
    scenarios = {
        'unseen': {'test_years': 'year IN (2023, 2024)', 'seen_col': "'Seen_in_Train'"}, # Unseen test set is drawn from the train timeframe
        'y1': {'test_years': 'year = 2024', 'seen_col': 'ds.seen_y1'},
        'y2': {'test_years': 'year = 2025', 'seen_col': 'ds.seen_y2'}
    }
    
    dfs_seen, dfs_conflict, dfs_repeat, dfs_chapter = [], [], [], []
    
    for sc_name, sc_info in scenarios.items():
        print(f"Processing Breakdowns for: {sc_name.upper()}")
        
        query = f"""
        WITH truth_base AS (
            SELECT group_l1, ahtn8, SUBSTRING(ahtn8, 1, 2) as ch2, SUM(tx_count) as tx_count
            FROM read_parquet('data/processed/desc_code_counts.parquet')
            WHERE {sc_info['test_years']}
            GROUP BY group_l1, ahtn8
        ),
        -- The 3A Fix: Calculate true chapter majority
        ch2_maj AS (
            SELECT group_l1, ch2 as maj_ch2, SUM(tx_count) as tx 
            FROM truth_base GROUP BY 1, 2 
            QUALIFY ROW_NUMBER() OVER(PARTITION BY group_l1 ORDER BY tx DESC) = 1
        ),
        desc_profiles AS (
            SELECT 
                group_l1,
                SUM(tx_count) as total_tx,
                COUNT(DISTINCT ahtn8) as unique_codes,
                (ARRAY_AGG(ahtn8 ORDER BY tx_count DESC))[1] as maj_l8
            FROM truth_base
            GROUP BY group_l1
        ),
        scored AS (
            SELECT 
                p.group_l1,
                dp.total_tx,
                ch2_maj.maj_ch2 as chapter,
                
                COALESCE({sc_info['seen_col']}, 'Unknown') as seen_status,
                CASE WHEN dp.unique_codes > 1 THEN 'Conflict (>1 Code)' ELSE 'Clean (1 Code)' END as conflict_status,
                CASE WHEN dp.total_tx = 1 THEN 'Single Transaction' ELSE 'Repeated (>1 Tx)' END as repeat_status,
                
                (SELECT COALESCE(SUM(tb.tx_count), 0) FROM truth_base tb WHERE tb.group_l1 = p.group_l1 AND tb.ahtn8 = p.pred_1) as m1_tx_correct,
                CASE WHEN p.pred_1 = dp.maj_l8 THEN 1 ELSE 0 END as m2_correct
                
            FROM read_parquet('data/processed/predictions_{sc_name}/*.parquet') p
            JOIN desc_profiles dp ON p.group_l1 = dp.group_l1
            JOIN ch2_maj ON p.group_l1 = ch2_maj.group_l1
            LEFT JOIN read_parquet('data/processed/description_status.parquet') ds ON p.group_l1 = ds.group_l1
        )
        
        SELECT '{sc_name}' as scenario, 'Seen_Status' as dimension, seen_status as category, COUNT(*) as desc_count, SUM(total_tx) as tx_count, SUM(m1_tx_correct)/SUM(total_tx) as m1_acc, SUM(m2_correct)/COUNT(*) as m2_acc FROM scored GROUP BY 1, 2, 3
        UNION ALL
        SELECT '{sc_name}' as scenario, 'Conflict_Status' as dimension, conflict_status as category, COUNT(*) as desc_count, SUM(total_tx) as tx_count, SUM(m1_tx_correct)/SUM(total_tx) as m1_acc, SUM(m2_correct)/COUNT(*) as m2_acc FROM scored GROUP BY 1, 2, 3
        UNION ALL
        SELECT '{sc_name}' as scenario, 'Repeat_Status' as dimension, repeat_status as category, COUNT(*) as desc_count, SUM(total_tx) as tx_count, SUM(m1_tx_correct)/SUM(total_tx) as m1_acc, SUM(m2_correct)/COUNT(*) as m2_acc FROM scored GROUP BY 1, 2, 3
        UNION ALL
        SELECT '{sc_name}' as scenario, 'Chapter' as dimension, chapter as category, COUNT(*) as desc_count, SUM(total_tx) as tx_count, SUM(m1_tx_correct)/SUM(total_tx) as m1_acc, SUM(m2_correct)/COUNT(*) as m2_acc FROM scored GROUP BY 1, 2, 3
        """
        
        df_all = con.execute(query).df()
        
        dfs_seen.append(df_all[df_all['dimension'] == 'Seen_Status'])
        dfs_conflict.append(df_all[df_all['dimension'] == 'Conflict_Status'])
        dfs_repeat.append(df_all[df_all['dimension'] == 'Repeat_Status'])
        dfs_chapter.append(df_all[df_all['dimension'] == 'Chapter'])

    # Save to disk
    out_dir = Path("reports/tables")
    pd.concat(dfs_seen).to_csv(out_dir / "c8_breakdown_seen.csv", index=False)
    pd.concat(dfs_conflict).to_csv(out_dir / "c8_breakdown_conflict.csv", index=False)
    pd.concat(dfs_repeat).to_csv(out_dir / "c8_breakdown_repeat.csv", index=False)
    pd.concat(dfs_chapter).to_csv(out_dir / "c8_breakdown_chapter.csv", index=False)
    
    print(f"\n Phase 3C Complete! All breakdown matrices saved to {out_dir}")

if __name__ == "__main__":
    run_c8_3c()