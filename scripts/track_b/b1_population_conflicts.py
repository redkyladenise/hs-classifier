"""
scripts/track_b/b1_population_conflicts.py

Executes Track B1 Population View (Items 1-5):
1. Multi-code conflict rates across levels (2, 4, 6, 8) and chapters.
2. Divergence typing (D2, D4, D6, D8).
3. The .00 convention conflict check against Track F findings.
4. Dominance band breakdown (dominant >=90%, moderate 60-90%, split <60%).
5. Number of declared codes per description.
"""

from pathlib import Path
import pandas as pd
from hsclf.data.io import get_connection

OUTPUT_DIR = Path("reports/tables/track_b")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_population_conflict_analysis():
    res = get_connection()
    con = res[0] if isinstance(res, tuple) else res

    print("\n--- 1. Multi-Code Rates across Levels & Chapters (Population) ---")
    
    level_query = """
    SELECT 
        COUNT(DISTINCT desc_norm_id) AS total_desc,
        COUNT(DISTINCT CASE WHEN n_codes_ahtn8 >= 2 THEN desc_norm_id END) AS desc_with_mult_codes,
        COUNT(DISTINCT CASE WHEN n_transactions >= 2 THEN desc_norm_id END) AS desc_repeated,
        COUNT(DISTINCT CASE WHEN n_transactions >= 2 AND n_codes_ch2 > 1 THEN desc_norm_id END) AS mult_ch2,
        COUNT(DISTINCT CASE WHEN n_transactions >= 2 AND n_codes_hd4 > 1 THEN desc_norm_id END) AS mult_hd4,
        COUNT(DISTINCT CASE WHEN n_transactions >= 2 AND n_codes_sh6 > 1 THEN desc_norm_id END) AS mult_sh6,
        COUNT(DISTINCT CASE WHEN n_transactions >= 2 AND n_codes_ahtn8 > 1 THEN desc_norm_id END) AS mult_ahtn8
    FROM 'data/processed/unique_descriptions.parquet';
    """
    df_level = con.execute(level_query).df()
    
    rep = df_level["desc_repeated"].iloc[0]
    total = df_level["total_desc"].iloc[0]
    summary_levels = [
        {
            "level": "2-digit (Chapter)",
            "conflicting_desc": df_level["mult_ch2"].iloc[0],
            "share_on_repeated_pct": round(100.0 * df_level["mult_ch2"].iloc[0] / rep, 2),
            "share_on_all_desc_pct": round(100.0 * df_level["mult_ch2"].iloc[0] / total, 2),
        },
        {
            "level": "4-digit (Heading)",
            "conflicting_desc": df_level["mult_hd4"].iloc[0],
            "share_on_repeated_pct": round(100.0 * df_level["mult_hd4"].iloc[0] / rep, 2),
            "share_on_all_desc_pct": round(100.0 * df_level["mult_hd4"].iloc[0] / total, 2),
        },
        {
            "level": "6-digit (Subheading)",
            "conflicting_desc": df_level["mult_sh6"].iloc[0],
            "share_on_repeated_pct": round(100.0 * df_level["mult_sh6"].iloc[0] / rep, 2),
            "share_on_all_desc_pct": round(100.0 * df_level["mult_sh6"].iloc[0] / total, 2),
        },
        {
            "level": "8-digit (AHTN)",
            "conflicting_desc": df_level["mult_ahtn8"].iloc[0],
            "share_on_repeated_pct": round(100.0 * df_level["mult_ahtn8"].iloc[0] / rep, 2),
            "share_on_all_desc_pct": round(100.0 * df_level["mult_ahtn8"].iloc[0] / total, 2),
        },
    ]
    df_level_summary = pd.DataFrame(summary_levels)
    out_level_path = OUTPUT_DIR / "b1_population_conflict_by_level.csv"
    df_level_summary.to_csv(out_level_path, index=False)
    print(df_level_summary.to_string(index=False))

    print("\n--- 2. Item 3: .00 Convention Conflict Check ---")
    check_00_query = """
    WITH code_endings AS (
        SELECT 
            group_l1,
            MAX(CASE WHEN ends_00 = 1 THEN 1 ELSE 0 END) AS has_00,
            MAX(CASE WHEN ends_00 = 0 THEN 1 ELSE 0 END) AS has_non_00
        FROM 'data/processed/transactions_grouped.parquet'
        GROUP BY group_l1
    )
    SELECT 
        COUNT(*) AS total_descriptions,
        COUNT(CASE WHEN has_00 = 1 AND has_non_00 = 1 THEN 1 END) AS descriptions_with_00_and_non_00_codes,
        ROUND(100.0 * COUNT(CASE WHEN has_00 = 1 AND has_non_00 = 1 THEN 1 END) / COUNT(*), 4) AS share_pct
    FROM code_endings;
    """
    df_00 = con.execute(check_00_query).df()
    out_00_path = OUTPUT_DIR / "b1_00_check.csv"
    df_00.to_csv(out_00_path, index=False)
    print(df_00.to_string(index=False))

    print("\n--- 3. Items 2, 4, 5: Divergence Typing, Dominance & Code Counts ---")
    div_query = """
    WITH desc_codes AS (
        SELECT 
            group_l1,
            ch2,
            hd4,
            sh6,
            ahtn8,
            COUNT(*) AS tx_count
        FROM 'data/processed/transactions_grouped.parquet'
        GROUP BY group_l1, ch2, hd4, sh6, ahtn8
    ),
    desc_agg AS (
        SELECT 
            group_l1,
            COUNT(DISTINCT ahtn8) AS n_codes,
            SUM(tx_count) AS total_tx,
            MAX(tx_count) AS max_tx,
            CASE 
                WHEN COUNT(DISTINCT ch2) > 1 THEN 'D2'
                WHEN COUNT(DISTINCT hd4) > 1 THEN 'D4'
                WHEN COUNT(DISTINCT sh6) > 1 THEN 'D6'
                ELSE 'D8'
            END AS divergence_type
        FROM desc_codes
        GROUP BY group_l1
        HAVING COUNT(DISTINCT ahtn8) > 1
    )
    SELECT 
        divergence_type,
        COUNT(*) AS n_descriptions,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) AS share_pct,
        COUNT(CASE WHEN (1.0 * max_tx / total_tx) >= 0.90 THEN 1 END) AS dominant_ge_90,
        COUNT(CASE WHEN (1.0 * max_tx / total_tx) >= 0.60 AND (1.0 * max_tx / total_tx) < 0.90 THEN 1 END) AS moderate_60_90,
        COUNT(CASE WHEN (1.0 * max_tx / total_tx) < 0.60 THEN 1 END) AS split_lt_60,
        COUNT(CASE WHEN n_codes = 2 THEN 1 END) AS codes_2,
        COUNT(CASE WHEN n_codes = 3 THEN 1 END) AS codes_3,
        COUNT(CASE WHEN n_codes >= 4 THEN 1 END) AS codes_4_plus
    FROM desc_agg
    GROUP BY divergence_type
    ORDER BY divergence_type;
    """
    df_div = con.execute(div_query).df()
    out_div_path = OUTPUT_DIR / "b1_divergence_and_dominance.csv"
    df_div.to_csv(out_div_path, index=False)
    print(df_div.to_string(index=False))

    print(f"\n[SUCCESS] Reports exported to: {OUTPUT_DIR}")


if __name__ == "__main__":
    run_population_conflict_analysis()