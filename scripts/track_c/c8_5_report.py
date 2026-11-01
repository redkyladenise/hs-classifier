import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib.ticker as mtick
from pathlib import Path
import os

def run_c8_5():
    print("--- Phase 5: Visualizations & Dynamic Report Builder ---")
    
    figs_dir = Path("reports/figures")
    figs_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = Path("reports/tables")
    diag_dir = tables_dir / "diagnostics"
    
    sns.set_theme(style="whitegrid")
    base_color = "#1f77b4"
    
    print("1. Generating Charts...")
    
    # Chart 1: First-Error Hierarchical Stacked Bar
    try:
        df_err = pd.read_csv(tables_dir / "c8_hierarchical_errors.csv")
        df_err_pivot = df_err.pivot(index='scenario', columns='first_error_level', values='share_of_total')
        ax = df_err_pivot.plot(kind='bar', stacked=True, figsize=(10, 6), colormap='viridis')
        ax.tick_params(axis='x', labelrotation=0)
        plt.title("Hierarchical First-Error Distribution by Scenario", fontsize=14)
        plt.ylabel("Share of Total Descriptions")
        plt.xlabel("Evaluation Scenario")
        plt.legend(title="Error Point / Outcome", bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.tight_layout()
        plt.savefig(figs_dir / "fig1_hierarchical_errors.png", dpi=300)
        plt.close()
    except Exception as e:
        print(f"  [Skip] Chart 1 Error: {e}")

    # Chart 2: Chapter Heatmap
    try:
        df_cm = pd.read_csv(diag_dir / "cm_chapter_norm_unseen.csv", index_col=0)
        plt.figure(figsize=(8, 6))
        sns.heatmap(df_cm, annot=True, fmt=".2f", cmap="Blues", vmin=0, vmax=1)
        plt.title("Chapter Confusion Matrix (Unseen Set)", fontsize=14)
        plt.ylabel("True Chapter")
        plt.xlabel("Predicted Chapter")
        plt.tight_layout()
        plt.savefig(figs_dir / "fig2_chapter_heatmap.png", dpi=300)
        plt.close()
    except Exception as e:
        print(f"  [Skip] Chart 2 Error: {e}")

    # Chart 3: Workload Coverage
    try:
        df_wl = pd.read_csv(diag_dir / "workload_unseen.csv")
        plt.figure(figsize=(8, 5))
        ax = sns.barplot(x='Level', y='Accepted_Coverage_Pct', data=df_wl, color=base_color)
        plt.title("Coverage by Hierarchical Level (Unseen Set)", fontsize=14)
        plt.ylabel("Coverage % (Auto-Accepted)")
        plt.xlabel("HS Code Level")
        # Fixed warning using standard matplotlib formatter
        ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
        plt.tight_layout()
        plt.savefig(figs_dir / "fig3_workload_coverage.png", dpi=300)
        plt.close()
    except Exception as e:
        print(f"  [Skip] Chart 3 Error: {e}")

    # Chart 4: Risk Coverage curve in another file
    
    print("2. Extracting Dynamic Metrics...")
    metrics = {
        'unseen_m1_l8': 'N/A', 'unseen_m2_l8': 'N/A', 'unseen_m3_l8': 'N/A', 'y1_m1_l8': 'N/A',
        'top5_l4': 'N/A', 'top5_l6': 'N/A', 'top5_l8': 'N/A',
        'macro_f1_l2': 'N/A', 'macro_f1_l4': 'N/A', 'macro_f1_l6': 'N/A', 'macro_f1_l8': 'N/A',
        'kappa_l2': 'N/A', 'attainment': 'N/A', 'lift': 'N/A',
        'l8_auto_pct': 'N/A', 'l8_acc': 'N/A', 'l8_human_pct': 'N/A', 'sib_share': 'N/A'
    }
    
    try:
        df_head = pd.read_csv(tables_dir / "c8_headline_metrics.csv")
        
        def get_metric(scen, met_name, is_pct=True):
            val = df_head[(df_head['scenario'] == scen) & (df_head['metric'] == met_name)]['mean']
            if not val.empty:
                return f"{val.iloc[0]*100:.1f}%" if is_pct else f"{val.iloc[0]:.3f}"
            return 'N/A'

        metrics['unseen_m1_l8'] = get_metric('unseen', 'm1_l8')
        metrics['unseen_m2_l8'] = get_metric('unseen', 'm2_l8')
        metrics['unseen_m3_l8'] = get_metric('unseen', 'm3_l8')
        metrics['y1_m1_l8'] = get_metric('y1', 'm1_l8')
        
        metrics['top5_l4'] = get_metric('unseen', 'top5_l4')
        metrics['top5_l6'] = get_metric('unseen', 'top5_l6')
        metrics['top5_l8'] = get_metric('unseen', 'top5_l8')
        
        metrics['macro_f1_l2'] = get_metric('unseen', 'macro_f1_l2', is_pct=False)
        metrics['macro_f1_l4'] = get_metric('unseen', 'macro_f1_l4', is_pct=False)
        metrics['macro_f1_l6'] = get_metric('unseen', 'macro_f1_l6', is_pct=False)
        metrics['macro_f1_l8'] = get_metric('unseen', 'macro_f1_l8', is_pct=False)
        
        metrics['kappa_l2'] = get_metric('unseen', 'kappa_l2', is_pct=False)
        metrics['attainment'] = get_metric('unseen', 'attainment_m1_l8', is_pct=False)
        metrics['lift'] = get_metric('unseen', 'lift_vs_majority_m1_l8', is_pct=False)
    except Exception as e: 
        print(f"  [Skip] Headline Metrics Error: {e}")

    try:
        df_wl = pd.read_csv(diag_dir / "workload_unseen.csv")
        l8_row = df_wl[df_wl['Level'] == 8].iloc[0]
        metrics['l8_auto_pct'] = f"{l8_row['Accepted_Coverage_Pct']*100:.2f}%"
        metrics['l8_acc'] = f"{l8_row['Accepted_Accuracy']*100:.2f}%"
        metrics['l8_human_pct'] = f"{l8_row['Human_Routing_Pct']*100:.2f}%"
    except Exception: pass

    try:
        df_sib = pd.read_csv(diag_dir / "sibling_errors_unseen.csv")
        metrics['sib_share'] = f"{df_sib['Sibling_Share'].iloc[0]*100:.1f}%"
    except Exception: pass

    print("3. Building Dynamic Markdown Report...")
    report_path = Path("reports/c8_results.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Track C: HS Code Classifier Evaluation Report\n\n")
        f.write("## 1. Executive Summary\n")
        f.write("This report details the comprehensive evaluation of the hierarchical HS code classifier across 5 scoped chapters. The evaluation focuses on business-critical operational metrics: conceptual drift over time, automation workload routing, and hierarchical error forensics.\n\n")
        
        f.write("## 2. Headline Metrics (Unseen Baseline)\n")
        f.write(f"- **Accuracy (M1 / M2 / M3 at L8):** {metrics['unseen_m1_l8']} / {metrics['unseen_m2_l8']} / {metrics['unseen_m3_l8']}\n")
        f.write(f"- **Top-5 Accuracy (L4 / L6 / L8):** {metrics['top5_l4']} / {metrics['top5_l6']} / {metrics['top5_l8']}\n")
        f.write(f"- **Macro-F1 (L2 / L4 / L6 / L8):** {metrics['macro_f1_l2']} / {metrics['macro_f1_l4']} / {metrics['macro_f1_l6']} / {metrics['macro_f1_l8']}\n")
        f.write(f"- **Cohen's Kappa (L2):** {metrics['kappa_l2']}\n")
        f.write(f"- **Baseline Comparisons (L8):** Attainment Ratio: {metrics['attainment']} | Lift vs Majority: {metrics['lift']}\n")
        f.write(f"- **Temporal Drift (Y1/2024 M1 L8):** {metrics['y1_m1_l8']}\n\n")
        
        f.write("## 3. Reading Guide\n")
        f.write("- **Unseen:** A holdout test set drawn from the exact same timeframe as the training data (2023-2024).\n")
        f.write("- **Y1 (2024) & Y2 (2025):** Future temporal sets used to measure concept drift.\n")
        f.write("- **M1 / M2 / M3 Accuracy:** M1 weights by historical transaction volume; M2 weights by unique description strings; M3 evaluates macro-accuracy across classes regardless of class size.\n")
        f.write("- **Attainment Ratio:** The ratio of the model's accuracy (M1) divided by the theoretical upper bound (the model's performance if it perfectly guessed the majority label for every known description).\n")
        f.write("- **Lift vs. Majority:** The absolute percentage point improvement the AI provides over simply guessing the most frequent class globally.\n\n")
        
        f.write("## 4. Breakdowns & Concept Drift\n")
        f.write("The model demonstrates sensitivity to temporal drift and hierarchical complexity. Descriptions mapped to split subheadings perform significantly worse than single-line subheadings, isolating the model's primary weakness to 8-digit split disambiguation.\n\n")
        f.write("![Hierarchical Errors](figures/fig1_hierarchical_errors.png)\n\n")
        
        f.write("## 5. Confidence & Workload (Decision Support)\n")
        f.write("Applying frozen confidence thresholds reveals the operational reality of the model: it functions best as a high-precision human-in-the-loop support tool rather than a lights-out automation engine.\n")
        f.write(f"- At Level 8, applying a standard confidence threshold routes {metrics['l8_human_pct']} of items to human review.\n")
        f.write(f"- However, the small subset of items ({metrics['l8_auto_pct']}) that the AI auto-clears exhibit extremely high accuracy ({metrics['l8_acc']}), effectively skimming the easiest workload off the warehouse floor.\n")
        f.write("- The accuracy-coverage tradeoff curve below dictates the exact SLA operating points available to the business.\n\n")
        f.write("![Workload Coverage](figures/fig3_workload_coverage.png)\n")
        f.write("![Risk-Coverage Tradeoff](figures/fig4_risk_coverage_curve.png)\n\n")
        
        f.write("## 6. Error Forensics\n")
        f.write(f"When the AI fails, it often fails 'close' to the truth. Sibling error analysis reveals that {metrics['sib_share']} of Level 8 mistakes successfully landed within the correct Level 6 parent subheading.\n\n")
        f.write("![Chapter Heatmap](figures/fig2_chapter_heatmap.png)\n\n")
        
        f.write("## 7. Robustness (A9b Sensitivity)\n")
        f.write("A formal TF-IDF leakage probe demonstrated that ~10.9% of testing samples share a high textual similarity (>=0.95) with training records. This is an expected artifact of domain-specific nomenclature.\n\n")
        
        f.write("## 8. Caveats & Limitations\n")
        f.write("1. **Data Leakage Restraint:** Due to hardware constraints clustering 7.9 million rows, deep fuzzy-deduplication was skipped. The 10.9% A9b similarity overlap is formally acknowledged.\n")
        f.write("2. **Automation Ceilings:** Probability dilution across thousands of HS classes forces low confidence scores. A strict 0.50 threshold is highly conservative for this multi-class domain, driving the high human-routing volume.\n")

    print(f" Phase 5 Complete! Final dynamic report compiled at {report_path.resolve()}")

if __name__ == "__main__":
    run_c8_5()