import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import numpy as np

def setup_style():
    sns.set_theme(style="whitegrid")
    plt.rcParams.update({'font.size': 12, 'axes.labelsize': 13, 'axes.titlesize': 15})

def plot_test_accuracy(df, out_dir):
    overall = df[(df['set'] == 'overall') & (df['level'] == 8) & (df['metric'] == 'M2_top1')]
    
    main_rate = overall[overall['model'] == 'main']['rate'].values[0] * 100
    h3_rate = overall[overall['model'] == 'main_h3']['rate'].values[0] * 100

    fig, ax = plt.subplots(figsize=(8, 6))
    bars = ax.bar(['Raw Historical Data\n(Baseline)', 'Modified Data\n(H3 Down-weighted)'], 
                  [main_rate, h3_rate], color=['#2c3e50', '#e74c3c'])
    
    ax.set_ylabel('Predictive Accuracy (%)')
    ax.set_title('Overall Classification Accuracy: Raw Baseline vs. Modified Data')
    ax.set_ylim(35, 41)
    
    for bar in bars:
        yval = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, yval + 0.1, f"{yval:.2f}%", 
                ha='center', va='bottom', fontweight='bold', fontsize=12)
        
    plt.tight_layout()
    plt.savefig(out_dir / 'd6_1_accuracy_by_method.png', dpi=300)
    plt.close()

def plot_conflict_splits(df, out_dir):
    splits = df[(df['set'].isin(['conflict_prone', 'consistent'])) & (df['level'] == 8) & (df['metric'] == 'M2_top1')].copy()
    splits['rate'] = splits['rate'] * 100
    splits['set'] = splits['set'].map({'conflict_prone': 'Products with Past\nLabel Conflicts', 'consistent': 'Products with\nConsistent Labels'})
    splits['model'] = splits['model'].map({'main': 'Raw Historical Data', 'main_h3': 'Modified Data (H3 Down-weighted)'})

    fig, ax = plt.subplots(figsize=(9, 6))
    sns.barplot(data=splits, x='set', y='rate', hue='model', palette=['#2c3e50', '#e74c3c'], ax=ax)
    
    ax.set_ylabel('Predictive Accuracy (%)')
    ax.set_xlabel('Product History Type')
    ax.set_title('Model Performance on Conflicting vs. Consistent Declarations')
    ax.set_ylim(35, 45)
    
    for container in ax.containers:
        ax.bar_label(container, fmt='%.2f%%', padding=3, fontweight='bold')
        
    plt.legend(title='Training Data Setup', loc='upper right')
    plt.tight_layout()
    plt.savefig(out_dir / 'd6_2_conflict_vs_consistent.png', dpi=300)
    plt.close()

def plot_synthetic_results(out_dir):
    scenarios = ['Clean\nBaseline', 'Noisy\nBaseline', 'Majority\nRule (H1)', 'Drop\nConflicts (H2)', 'Down-weight\n(H3)']
    accuracies = [65.63, 65.51, 65.29, 64.08, 65.17]
    colors = ["#527A65", "#C96A5D", "#536F91", "#B88A4B", "#D8CF75"]
    
    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(scenarios, accuracies, color=colors)
    
    ax.set_ylabel('Predictive Accuracy (%)')
    ax.set_title('Synthetic Laboratory Test: Accuracy by Handling Method')
    ax.set_ylim(60, 67)
    
    for bar in bars:
        yval = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, yval + 0.1, f"{yval:.2f}%", 
                ha='center', va='bottom', fontweight='bold')
        
    plt.tight_layout()
    plt.savefig(out_dir / 'd6_3_synthetic_accuracy.png', dpi=300)
    plt.close()

def main():
    print("Generating clean stakeholder figures...")
    out_dir = Path("reports/figures")
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv("reports/tables/d6_test.csv")
    
    setup_style()
    plot_test_accuracy(df, out_dir)
    plot_conflict_splits(df, out_dir)
    plot_synthetic_results(out_dir)
    
    print(f"Success! Figures saved to {out_dir}")

if __name__ == "__main__":
    main()