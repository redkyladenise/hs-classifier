"""
src/hsclf/audit/sampling.py

Stratified sampling functions for Track B audit.
Enforces seed reproducibility and single-item-per-group_l2 constraints.
"""

from typing import Dict, List, Tuple
import pandas as pd
import numpy as np


def draw_stratified_unique_l2(
    df: pd.DataFrame,
    stratum_col: str,
    strata_config: Dict[str, dict],
    seed: int = 42,
    excluded_l2: set = None,
) -> Tuple[pd.DataFrame, set]:
    """
    Draws a stratified sample ensuring at most 1 item per group_l2.
    """
    rng = np.random.RandomState(seed)
    used_l2 = set() if excluded_l2 is None else set(excluded_l2)
    selected_indices = []

    for strat_val, cfg in strata_config.items():
        target_n = cfg["target_n"]
        sub_cols = cfg["cols"]

        sub_df = df[df[stratum_col] == strat_val].copy()

        # Exclude already used group_l2
        sub_df = sub_df[~sub_df["group_l2"].isin(used_l2)]

        # Prepare sub-strata keys safely
        group_keys = [c for c in sub_cols if c in sub_df.columns]
        for c in group_keys:
            sub_df[c] = sub_df[c].astype(str).fillna("UNKNOWN")

        grouped = sub_df.groupby(group_keys, observed=False)

        # Proportional allocation
        counts = grouped.size()
        counts = counts[counts > 0]
        weights = counts / counts.sum()
        raw_alloc = weights * target_n
        alloc = raw_alloc.round().astype(int)

        # Reconcile rounding to target_n
        diff = target_n - alloc.sum()
        if diff != 0:
            top_frac = (raw_alloc - alloc).sort_values(ascending=(diff < 0))
            for idx in top_frac.index[: abs(diff)]:
                alloc[idx] += 1 if diff > 0 else -1

        # Draw items ensuring strictly 1 per group_l2
        for key, group_data in grouped:
            lookup_key = key[0] if isinstance(key, tuple) and len(key) == 1 else key
            n_to_pick = alloc.get(lookup_key, 0)
            if n_to_pick <= 0:
                continue

            shuffled = group_data.sample(frac=1.0, random_state=rng.randint(0, 1000000))
            picked_count = 0
            for idx, row in shuffled.iterrows():
                l2 = row["group_l2"]
                if l2 not in used_l2:
                    used_l2.add(l2)
                    selected_indices.append(idx)
                    picked_count += 1
                    if picked_count == n_to_pick:
                        break
    return df.loc[selected_indices].copy(), used_l2