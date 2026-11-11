
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path


def generate_fig1():
    print("--- Generating Figure 1: Hierarchical First-Error Distribution ---")

    tables_dir = Path("reports/tables")
    figs_dir = Path("reports/figures")
    figs_dir.mkdir(parents=True, exist_ok=True)

    sns.set_theme(style="whitegrid")

    # Load hierarchical error results
    df_err = pd.read_csv(tables_dir / "c8_hierarchical_errors.csv")

    # Filter scenarios
    df_err = df_err[df_err["scenario"].isin(["unseen", "y2"])]

    # Set scenario order
    df_err["scenario"] = pd.Categorical(
        df_err["scenario"],
        categories=["unseen", "y2"],
        ordered=True
    )

    # Pivot data for stacked bar chart
    df_err_pivot = df_err.pivot(
        index="scenario",
        columns="first_error_level",
        values="share_of_total"
    )

    # Generate figure
    ax = df_err_pivot.plot(
        kind="bar",
        stacked=True,
        figsize=(10, 6),
        colormap="viridis"
    )

    ax.tick_params(axis="x", labelrotation=0)

    plt.title(
        "Hierarchical First-Error Distribution: Unseen vs Y2",
        fontsize=14
    )
    plt.ylabel("Share of Total Descriptions")
    plt.xlabel("Evaluation Scenario")

    plt.legend(
        title="Error Point / Outcome",
        bbox_to_anchor=(1.05, 1),
        loc="upper left"
    )

    plt.tight_layout()

    output_path = figs_dir / "fig1_b_hierarchical_errors.png"
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"Figure generated: {output_path.resolve()}")


if __name__ == "__main__":
    generate_fig1()
