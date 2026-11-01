import duckdb
import pandas as pd
from sklearn.metrics import f1_score
from pathlib import Path

def patch_macro_f1_inline():
    print("--- Patching and Sorting Missing Macro-F1 Scores ---")
    metrics_path = Path('reports/tables/c8_headline_metrics.csv')
    df_head = pd.read_csv(metrics_path)

    con = duckdb.connect()
    new_f1_data = {}

    # 1. Calculate the missing metrics
    for scen in ['unseen', 'y1', 'y2']:
        query = f"""
        WITH truth AS (
            SELECT group_l1, ahtn8 as true_l8 
            FROM read_parquet('data/processed/desc_code_counts.parquet') 
            QUALIFY ROW_NUMBER() OVER(PARTITION BY group_l1 ORDER BY tx_count DESC) = 1
        )
        SELECT t.true_l8, p.pred_1 as pred_l8
        FROM read_parquet('data/processed/predictions_{scen}/*.parquet') p
        JOIN truth t ON p.group_l1 = t.group_l1
        WHERE t.true_l8 IS NOT NULL AND p.pred_1 IS NOT NULL
        """
        try:
            df = con.execute(query).df()
            new_f1_data[scen] = [
                {'scenario': scen, 'metric': 'macro_f1_l6', 'mean': f1_score(df['true_l8'].str[:6], df['pred_l8'].str[:6], average='macro', zero_division=0), 'ci_lower': None, 'ci_upper': None},
                {'scenario': scen, 'metric': 'macro_f1_l4', 'mean': f1_score(df['true_l8'].str[:4], df['pred_l8'].str[:4], average='macro', zero_division=0), 'ci_lower': None, 'ci_upper': None},
                {'scenario': scen, 'metric': 'macro_f1_l2', 'mean': f1_score(df['true_l8'].str[:2], df['pred_l8'].str[:2], average='macro', zero_division=0), 'ci_lower': None, 'ci_upper': None}
            ]
            print(f" Calculated Macro-F1s for {scen}...")
        except Exception as e:
            print(f" Skipping {scen}: {e}")

    # 2. Rebuild the CSV with inline insertion
    rebuilt_rows = []
    for _, row in df_head.iterrows():
        # If it's one of our patched rows from a previous run, skip it to avoid duplicates
        if row['metric'] in ['macro_f1_l6', 'macro_f1_l4', 'macro_f1_l2', 'macro_f1_l8']:
            continue
            
        if row['metric'] == 'macro_f1':
            # Rename the original to l8
            row_dict = row.to_dict()
            row_dict['metric'] = 'macro_f1_l8'
            rebuilt_rows.append(row_dict)
            
            # Slide the new L6, L4, L2 rows directly underneath it
            scen = row['scenario']
            if scen in new_f1_data:
                rebuilt_rows.extend(new_f1_data[scen])
        else:
            rebuilt_rows.append(row.to_dict())

    # 3. Save the perfectly ordered file
    df_new = pd.DataFrame(rebuilt_rows)
    df_new.to_csv(metrics_path, index=False)
    print(f" Success! {metrics_path.resolve()} updated with inline Macro-F1s.")

if __name__ == "__main__":
    patch_macro_f1_inline()