"""Track A6: Chapter Selection, Attrition Waterfall, and Scope Filtering Pipeline.

Builds transactions_clean.parquet via 16 bucketed joins, computes exact per-chapter
metrics, filters to chosen scope chapters, and outputs attrition tables.
"""

import sys
import time
from pathlib import Path
import duckdb
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.hsclf.data.io import get_connection, load_params

# Tariff Book 2-digit Chapter Official Headings (Chapters 01 to 97)
CHAPTER_NAMES = {
    "01": "Live animals",
    "02": "Meat and edible meat offal",
    "03": "Fish and crustaceans, molluscs and other aquatic invertebrates",
    "04": "Dairy produce; birds' eggs; natural honey; edible products of animal origin",
    "05": "Products of animal origin, not elsewhere specified or included",
    "06": "Live trees and other plants; bulbs, roots and the like; cut flowers",
    "07": "Edible vegetables and certain roots and tubers",
    "08": "Edible fruit and nuts; peel of citrus fruit or melons",
    "09": "Coffee, tea, maté and spices",
    "10": "Cereals",
    "11": "Products of the milling industry; malt; starches; inulin; wheat gluten",
    "12": "Oil seeds and oleaginous fruits; miscellaneous grains, seeds and fruit",
    "13": "Lac; gums, resins and other vegetable saps and extracts",
    "14": "Vegetable plaiting materials; vegetable products not elsewhere specified",
    "15": "Animal, vegetable or microbial fats and oils and their cleavage products",
    "16": "Preparations of meat, of fish, crustaceans, molluscs or other aquatic invertebrates",
    "17": "Sugars and sugar confectionery",
    "18": "Cocoa and cocoa preparations",
    "19": "Preparations of cereals, flour, starch or milk; pastrycooks' products",
    "20": "Preparations of vegetables, fruit, nuts or other parts of plants",
    "21": "Miscellaneous edible preparations",
    "22": "Beverages, spirits and vinegar",
    "23": "Residues and waste from the food industries; prepared animal fodder",
    "24": "Tobacco and manufactured tobacco substitutes",
    "25": "Salt; sulphur; earths and stone; plastering materials, lime and cement",
    "26": "Ores, slag and ash",
    "27": "Mineral fuels, mineral oils and products of their distillation; bituminous substances",
    "28": "Inorganic chemicals; organic or inorganic compounds of precious metals",
    "29": "Organic chemicals",
    "30": "Pharmaceutical products",
    "31": "Fertilisers",
    "32": "Tanning or dyeing extracts; tannins and their derivatives; dyes, pigments, paints",
    "33": "Essential oils and resinoids; perfumery, cosmetic or toilet preparations",
    "34": "Soap, organic surface-active agents, washing preparations, lubricating preparations",
    "35": "Albuminoidal substances; modified starches; glues; enzymes",
    "36": "Explosives; pyrotechnic products; matches; pyrophoric alloys",
    "37": "Photographic or cinematographic goods",
    "38": "Miscellaneous chemical products",
    "39": "Plastics and articles thereof",
    "40": "Rubber and articles thereof",
    "41": "Raw hides and skins (other than furskins) and leather",
    "42": "Articles of leather; saddlery and harness; travel goods, handbags",
    "43": "Furskins and artificial fur; manufactures thereof",
    "44": "Wood and articles of wood; wood charcoal",
    "45": "Cork and articles of cork",
    "46": "Manufactures of straw, of esparto or of other plaiting materials; basketware",
    "47": "Pulp of wood or of other fibrous cellulosic material; recovered paper or paperboard",
    "48": "Paper and paperboard; articles of paper pulp, of paper or of paperboard",
    "49": "Printed books, newspapers, pictures and other products of the printing industry",
    "50": "Silk",
    "51": "Wool, fine or coarse animal hair; horsehair yarn and woven fabric",
    "52": "Cotton",
    "53": "Other vegetable textile fibres; paper yarn and woven fabrics of paper yarn",
    "54": "Man-made filaments; strip and the like of man-made textile materials",
    "55": "Man-made staple fibres",
    "56": "Wadding, felt and nonwovens; special yarns; twine, cordage, ropes and cables",
    "57": "Carpets and other textile floor coverings",
    "58": "Special woven fabrics; tufted textile fabrics; lace; tapestries; trimmings; embroidery",
    "59": "Impregnated, coated, covered or laminated textile fabrics; textile articles for industrial use",
    "60": "Knitted or crocheted fabrics",
    "61": "Articles of apparel and clothing accessories, knitted or crocheted",
    "62": "Articles of apparel and clothing accessories, not knitted or crocheted",
    "63": "Other made up textile articles; sets; worn clothing and worn textile articles; rags",
    "64": "Footwear, gaiters and the like; parts of such articles",
    "65": "Headgear and parts thereof",
    "66": "Umbrellas, sun umbrellas, walking-sticks, seat-sticks, whips, riding-crops",
    "67": "Prepared feathers and down and articles made of feathers or of down; artificial flowers",
    "68": "Articles of stone, plaster, cement, asbestos, mica or similar materials",
    "69": "Ceramic products",
    "70": "Glass and glassware",
    "71": "Natural or cultured pearls, precious or semi-precious stones, precious metals",
    "72": "Iron and steel",
    "73": "Articles of iron or steel",
    "74": "Copper and articles thereof",
    "75": "Nickel and articles thereof",
    "76": "Aluminium and articles thereof",
    "78": "Lead and articles thereof",
    "79": "Zinc and articles thereof",
    "80": "Tin and articles thereof",
    "81": "Other base metals; cermets; articles thereof",
    "82": "Tools, implements, cutlery, spoons and forks, of base metal; parts thereof",
    "83": "Miscellaneous articles of base metal",
    "84": "Nuclear reactors, boilers, machinery and mechanical appliances; parts thereof",
    "85": "Electrical machinery and equipment and parts thereof; sound and television recorders",
    "86": "Railway or tramway locomotives, rolling-stock and parts thereof; track fixtures",
    "87": "Vehicles other than railway or tramway rolling-stock, and parts and accessories thereof",
    "88": "Aircraft, spacecraft, and parts thereof",
    "89": "Ships, boats and floating structures",
    "90": "Optical, photographic, cinematographic, measuring, checking, precision, medical instruments",
    "91": "Clocks and watches and parts thereof",
    "92": "Musical instruments; parts and accessories of such articles",
    "93": "Arms and ammunition; parts and accessories thereof",
    "94": "Furniture; bedding, mattresses, mattress supports, cushions and similar stuffed furnishings",
    "95": "Toys, games and sports requisites; parts and accessories thereof",
    "96": "Miscellaneous manufactured articles",
    "97": "Works of art, collectors' pieces and antiques"
}


def stage_1_build_clean_parts(con, slim_file: Path, codes_file: Path, raw_to_norm_file: Path, clean_dir: Path):
    """Build clean partition parts one raw-description bucket at a time."""
    print("\n--- Stage 1: Building transactions_clean Parts (16 Buckets) ---")
    clean_dir.mkdir(parents=True, exist_ok=True)

    for b in range(16):
        part_path = clean_dir / f"b{b:02d}.parquet"
        if part_path.exists():
            print(f"  Bucket {b:02d} already exists: {part_path.name}. Skipping.")
            continue

        start_b = time.time()
        print(f"  Processing Bucket {b:02d}...")

        # Join slim + codes_standardized on row_id, then join raw_to_norm within bucket b
        query = f"""
            COPY (
                WITH slim_b AS (
                    SELECT row_id, year, month, goods_description
                    FROM read_parquet('{slim_file.as_posix()}')
                    WHERE abs(hash(goods_description)) % 16 = {b}
                ),
                r2n_b AS (
                    SELECT desc_raw, desc_norm_id, norm_bucket, desc_status
                    FROM read_parquet('{raw_to_norm_file.as_posix()}')
                    WHERE abs(hash(desc_raw)) % 16 = {b}
                )
                SELECT 
                    s.row_id,
                    s.year,
                    s.month,
                    r.desc_norm_id,
                    r.norm_bucket,
                    r.desc_status,
                    c.code_flag,
                    c.ch2,
                    c.hd4,
                    c.sh6,
                    c.ahtn8,
                    c.ends_00
                FROM slim_b s
                INNER JOIN read_parquet('{codes_file.as_posix()}') c
                    ON s.row_id = c.row_id
                INNER JOIN r2n_b r
                    ON s.goods_description = r.desc_raw
            ) TO '{part_path.as_posix()}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
        """
        con.execute(query)
        elapsed = time.time() - start_b
        print(f"  Saved {part_path.name} in {elapsed:.1f}s.")


def stage_2_combine_clean(con, clean_dir: Path, clean_file: Path):
    """Stream-combine bucket parts into transactions_clean.parquet."""
    print("\n--- Stage 2: Combining Parts into transactions_clean.parquet ---")
    if clean_file.exists():
        print(f"  {clean_file.name} already exists. Skipping.")
        return

    start_t = time.time()
    glob_pattern = (clean_dir / "b*.parquet").as_posix()
    con.execute(f"""
        COPY (
            SELECT * FROM read_parquet('{glob_pattern}')
        ) TO '{clean_file.as_posix()}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
    """)
    print(f"  Created {clean_file.name} in {time.time() - start_t:.1f}s.")


def stage_3_rank_chapters(con, clean_file: Path, report_path: Path) -> pd.DataFrame:
    """Compute exact distinct normalized descriptions and transactions per chapter."""
    print("\n--- Stage 3: Computing Chapter Ranking (2023-2025 Valid Data) ---")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    # Global total of valid transactions across 2023-2025
    valid_tx_total = con.execute(f"""
        SELECT count(*)
        FROM read_parquet('{clean_file.as_posix()}')
        WHERE code_flag = 'valid' AND desc_status = 'ok'
    """).fetchone()[0]

    # Global distinct valid normalized descriptions across all valid rows
    valid_desc_total = con.execute(f"""
        SELECT count(DISTINCT desc_norm_id)
        FROM read_parquet('{clean_file.as_posix()}')
        WHERE code_flag = 'valid' AND desc_status = 'ok'
    """).fetchone()[0]

    print(f"Valid dataset baseline: {valid_tx_total:,} transactions, {valid_desc_total:,} distinct descriptions.")

    # Distinct descriptions and transaction counts grouped by ch2
    ranking_df = con.execute(f"""
        SELECT 
            ch2 AS chapter,
            count(DISTINCT desc_norm_id) AS n_unique_norm_desc,
            count(*) AS n_transactions
        FROM read_parquet('{clean_file.as_posix()}')
        WHERE code_flag = 'valid' AND desc_status = 'ok'
        GROUP BY ch2
        ORDER BY n_unique_norm_desc DESC, n_transactions DESC
    """).df()

    ranking_df["share_unique_desc"] = (ranking_df["n_unique_norm_desc"] / valid_desc_total * 100.0).round(4)
    ranking_df["share_transactions"] = (ranking_df["n_transactions"] / valid_tx_total * 100.0).round(4)
    ranking_df["rank"] = range(1, len(ranking_df) + 1)
    ranking_df["chapter_name"] = ranking_df["chapter"].map(lambda c: CHAPTER_NAMES.get(c, "Unknown"))

    ranking_df.to_csv(report_path, index=False)
    print(f"Saved chapter rankings to {report_path.name}.")
    return ranking_df


def stage_4_evaluate_scope(ranking_df: pd.DataFrame, min_coverage: float = 50.0):
    """Determine top 5 to 8 chapters satisfying coverage threshold."""
    print("\n--- Stage 4: Evaluating Scope Coverage ---")
    selected_chapters = ranking_df.iloc[:5]["chapter"].tolist()
    top5_cov = ranking_df.iloc[:5]["share_transactions"].sum()
    print(f"Top 5 Chapters: {selected_chapters} -> Cumulative Transaction Share: {top5_cov:.2f}%")

    if top5_cov < min_coverage:
        print(f"Coverage {top5_cov:.2f}% is below threshold {min_coverage}%. Adding next-ranked chapters...")
        for i in range(5, min(8, len(ranking_df))):
            selected_chapters.append(ranking_df.iloc[i]["chapter"])
            current_cov = ranking_df[ranking_df["chapter"].isin(selected_chapters)]["share_transactions"].sum()
            print(f"  Added Chapter {ranking_df.iloc[i]['chapter']} ({ranking_df.iloc[i]['chapter_name']}): Coverage now {current_cov:.2f}%")
            if current_cov >= min_coverage:
                break
    else:
        print(f"Coverage threshold {min_coverage}% met with top 5 chapters.")

    return selected_chapters


def stage_5_build_scope_and_attrition(
    con,
    clean_file: Path,
    scope_file: Path,
    attrition_path: Path,
    selected_chapters: list,
):
    """Build transactions_scope.parquet and generate reconciliation waterfall table."""
    print("\n--- Stage 5: Building Scope Dataset and Reconciling Attrition ---")
    ch_list_sql = ", ".join(f"'{c}'" for c in selected_chapters)

    # 1. Export in-scope dataset
    if not scope_file.exists():
        print(f"Exporting in-scope dataset to {scope_file.name}...")
        start_s = time.time()
        con.execute(f"""
            COPY (
                SELECT *
                FROM read_parquet('{clean_file.as_posix()}')
                WHERE code_flag = 'valid'
                  AND desc_status = 'ok'
                  AND ch2 IN ({ch_list_sql})
            ) TO '{scope_file.as_posix()}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
        """)
        print(f"Saved {scope_file.name} in {time.time() - start_s:.1f}s.")
    else:
        print(f"{scope_file.name} already exists. Skipping.")

    # 2. Reconcile Attrition Waterfall Table
    print("Computing attrition counts...")
    attrition_df = con.execute(f"""
        WITH raw_cat AS (
            SELECT 
                row_id,
                CASE 
                    WHEN code_flag = 'bad_format' THEN 'bad_format'
                    WHEN code_flag = 'odd_length' THEN 'odd_length'
                    WHEN code_flag = 'bad_chapter' THEN 'bad_chapter'
                    WHEN desc_status = 'placeholder' THEN 'placeholder_description'
                    WHEN desc_status = 'blank' THEN 'blank_description'
                    WHEN ch2 NOT IN ({ch_list_sql}) THEN 'outside_chosen_chapters'
                    ELSE 'valid_in_scope'
                END AS category
            FROM read_parquet('{clean_file.as_posix()}')
        )
        SELECT 
            category,
            count(*) AS n_transactions,
            round(count(*) * 100.0 / 26889707, 4) AS pct_of_total
        FROM raw_cat
        GROUP BY category
    """).df()

    # Reorder table for standard waterfall reporting
    category_order = [
        "valid_in_scope",
        "outside_chosen_chapters",
        "blank_description",
        "placeholder_description",
        "bad_format",
        "odd_length",
        "bad_chapter",
    ]
    attrition_df["order"] = attrition_df["category"].map(lambda x: category_order.index(x) if x in category_order else 99)
    attrition_df = attrition_df.sort_values("order").drop(columns=["order"])

    attrition_df.to_csv(attrition_path, index=False)
    print(f"Saved {attrition_path.name}:")
    print(attrition_df.to_string(index=False))

    total_accounted = attrition_df["n_transactions"].sum()
    print(f"\nWaterfall Total Accounted: {total_accounted:,} (Expected: 26,889,707)")
    assert total_accounted == 26889707, f"Attrition does not reconcile! Sum = {total_accounted}"

    # 3. Log descriptions crossing inside/outside chosen scope
    print("\nAuditing cross-scope descriptions...")
    cross_df = con.execute(f"""
        SELECT count(DISTINCT desc_norm_id) AS n_cross_desc
        FROM (
            SELECT 
                desc_norm_id,
                count(DISTINCT CASE WHEN ch2 IN ({ch_list_sql}) THEN 'IN' ELSE 'OUT' END) AS scope_splits
            FROM read_parquet('{clean_file.as_posix()}')
            WHERE code_flag = 'valid' AND desc_status = 'ok'
            GROUP BY desc_norm_id
            HAVING count(DISTINCT CASE WHEN ch2 IN ({ch_list_sql}) THEN 'IN' ELSE 'OUT' END) > 1
        )
    """).fetchone()[0]
    print(f"Descriptions appearing in BOTH chosen and unchosen chapters: {cross_df:,}")

    return cross_df


def stage_6_update_params_and_docs(params_path: Path, docs_path: Path, selected_chapters: list, cross_desc_count: int, ranking_df: pd.DataFrame):
    """Update config/params.yaml and docs/decisions.md with selected chapters."""
    print("\n--- Stage 6: Updating Configuration and Decisions Documentation ---")

    # 1. Update params.yaml
    with open(params_path, "r", encoding="utf-8") as f:
        params_data = yaml.safe_load(f)

    params_data["chapters"] = [int(c) for c in selected_chapters]
    params_data["n_chapters"] = len(selected_chapters)
    params_data["coverage_threshold"] = 50.0

    with open(params_path, "w", encoding="utf-8") as f:
        yaml.dump(params_data, f, sort_keys=False)
    print(f"Updated {params_path.name} with chapters: {params_data['chapters']}")

    # 2. Append chosen chapter descriptions to docs/decisions.md
    with open(docs_path, "a", encoding="utf-8") as f:
        f.write("\n### 3. Track A6 Results & Selected Chapters\n")
        f.write(f"- **Selected Chapters Count:** {len(selected_chapters)}\n")
        f.write(f"- **Selected Chapters:** {', '.join(selected_chapters)}\n")
        f.write("- **Official Tariff Book Chapter Headings:**\n")
        for c in selected_chapters:
            name = CHAPTER_NAMES.get(c, "Unknown")
            stats = ranking_df[ranking_df["chapter"] == c].iloc[0]
            f.write(f"  - **Chapter {c}**: {name} ({stats['n_transactions']:,} tx, {stats['n_unique_norm_desc']:,} unique desc, rank #{stats['rank']})\n")
        f.write(f"- **Cross-Scope Descriptions:** {cross_desc_count:,} normalized descriptions appeared in both chosen and unchosen chapters. For modeling, only transaction rows under chosen chapters are retained in `transactions_scope.parquet`.\n")
    print(f"Appended results to {docs_path.name}.")


def main():
    params = load_params()
    con, _ = get_connection(params)

    interim_dir = ROOT / params["paths"]["interim_dir"]
    tables_dir = ROOT / params["paths"]["reports_dir"] / "tables"
    params_file = ROOT / "config" / "params.yaml"
    docs_file = ROOT / "docs" / "decisions.md"

    slim_file = interim_dir / "transactions_slim.parquet"
    codes_file = interim_dir / "codes_standardized.parquet"
    raw_to_norm_file = interim_dir / "raw_to_norm.parquet"

    clean_dir = interim_dir / "clean_parts"
    clean_file = interim_dir / "transactions_clean.parquet"
    scope_file = interim_dir / "transactions_scope.parquet"

    ranking_csv = tables_dir / "a6_chapter_ranking.csv"
    attrition_csv = tables_dir / "a6_attrition.csv"

    try:
        stage_1_build_clean_parts(con, slim_file, codes_file, raw_to_norm_file, clean_dir)
        stage_2_combine_clean(con, clean_dir, clean_file)
        ranking_df = stage_3_rank_chapters(con, clean_file, ranking_csv)
        selected_chapters = stage_4_evaluate_scope(ranking_df, min_coverage=50.0)
        cross_count = stage_5_build_scope_and_attrition(con, clean_file, scope_file, attrition_csv, selected_chapters)
        stage_6_update_params_and_docs(params_file, docs_file, selected_chapters, cross_count, ranking_df)
        print("\nTrack A6 pipeline execution complete.")
    finally:
        con.close()


if __name__ == "__main__":
    main()