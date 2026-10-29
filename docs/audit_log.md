### B0 Readiness Recount (2023-2024 Window in Test Split)

| total_descriptions | singleton_descriptions | repeated_descriptions | conflicting_repeated_descriptions | non_conflicting_repeated_descriptions | conflict_rate_on_repeated_pct |
| --- | --- | --- | --- | --- | --- |
| 795303.0 | 690202.0 | 105101.0 | 13977.0 | 91124.0 | 13.3 |

## B6: Self-Consistency Audit & Reliability Evaluation (Gate B3)

**Date:** 2026-10-29  
**Protocol:** Blind re-labeling of 40 randomly sampled descriptions ($N = 40$; 10 from Stratum A, 30 from Strata B/C) under frozen Guide v1.0.  
**Raw Evaluation File:** `data/audit/labels_relabel.csv`  

---

### 1. Pre-Adjudication Gate B3 Reliability Metrics

| Metric | Overall ($N = 54$ pairs) | Stratum A ($N = 24$ pairs) | Strata B/C ($N = 30$ pairs) | Gate B3 Target | Verdict |
|---|---|---|---|---|---|
| **Raw Agreement ($P_o$)** | **61.11%** | 79.17% | 46.67% | $\ge 80.0\%$ | **FAIL** |
| **Cohen’s Kappa ($\kappa$)** | **0.4564** | 0.7080 | 0.2092 | $\ge 0.600$ | **FAIL** |

#### Diagnostic Analysis
* **Stratum A (Conflicts):** Exhibited substantial inter-round stability ($\kappa = 0.7080$, $P_o = 79.17\%$), demonstrating consistent adjudication across competing broker filings.
* **Strata B/C (Singletons & Clean Repeated):** Experienced acute reliability degradation ($\kappa = 0.2092$, $P_o = 46.67\%$). 
* **Primary Root Cause:** Leniency drift and auditor fatigue during the Round 2 blind pass. Specifically:
  1. *Softening of Legal Exclusions:* Declared Chapter 87 codes for fans (8414), pumps, and general fasteners were erroneously accepted as `Match` instead of being disqualified under Section XVII Note 2.
  2. *Benefit of the Doubt:* General/residual baskets (`3926`, `8414`, `8714`) were labeled `Match` despite unstated material, dimensions, or application parameters that legally demand `Ambiguous`.
  3. *Over-Skepticism on Definite Specs:* A small subset of fully grounded brand/model matches (e.g., Apple Watch, Philips LED) were conservatively flipped to `Ambiguous`.

---

### 2. Disagreement Audit & Statutory Adjudication Table ($N = 21$)

| Sample ID | Code Evaluated | Round 1 (Main) | Round 2 (Relabel) | Final Adjudicated | Statutory Basis & Adjudication Rationale |
|---|---|---|---|---|---|
| `MAIN_011` | `8517.62.92` | `Match` | `Mismatch` | **`Match`** | Dedicated line for voice/data transmission apparatus matches confirmed device specs. |
| `MAIN_023` | `8413.70.42` | `Mismatch` | `Ambiguous` | **`Mismatch`** | Technical pump parameters contradict submersible/centrifugal sub-split; legally barred. |
| `MAIN_056` | `8483.90.19` | `Mismatch` | `Ambiguous` | **`Mismatch`** | Transmission gear component excluded from declared sub-line scope. |
| `MAIN_066` | `8536.69.99` | `Mismatch` | `Match` | **`Mismatch`** | Modular terminal block is a wire connection element (`8536.90`), not a plug or socket (`8536.69`). |
| `MAIN_066` | `8536.90.19` | `Ambiguous` | `Mismatch` | **`Ambiguous`** | Terminal block fits `8536.90`; rated current omitted between sibling subheadings. |
| `MAIN_117` | `8517.62.69` | `Mismatch` | `Match` | **`Mismatch`** | Passive optical attenuator is not an active data transmission/regeneration machine of `8517.62`. |
| `MAIN_119` | `8517.62.53` | `Match` | `Ambiguous` | **`Match`** | Smartwatch transmitting radio-telephony/data fits dedicated statutory line `8517.62.53`. |
| `MAIN_122` | `8503.00.90` | `Cannot check`| `Ambiguous` | **`Cannot check`** | "V10C Frame" lacks machine/system context; `kind_identified = no` under Guide Rule 5. |
| `MAIN_126` | `8536.90.99` | `Ambiguous` | `Match` | **`Ambiguous`** | Crimp contact fits `8536.90`, but specific contact sub-lines compete; current rating unstated. |
| `MAIN_131` | `8714.10.90` | `Ambiguous` | `Match` | **`Ambiguous`** | Exhaust joint collar under `8714`; general-use base metal clamp status (Ch. 73) unverified. |
| `MAIN_135` | `8714.10.90` | `Ambiguous` | `Match` | **`Ambiguous`** | Bare noun "LID" lacks component identity (airbox 8421 vs body 8714) and material. |
| `MAIN_140` | `3926.90.99` | `Mismatch` | `Ambiguous` | **`Mismatch`** | Electrical connector housing belongs under `8538`; excluded from Ch. 39 by Note 2(p). |
| `MAIN_153` | `8438.40.00` | `Mismatch` | `Match` | **`Mismatch`** | Commercial espresso machine classifies under `8419.81`; `8438.40` is strictly brewery machinery. |
| `MAIN_157` | `8466.10.10` | `Ambiguous` | `Match` | **`Ambiguous`** | Tool collet fits `8466.10`; machine tool model unstated between specialized (.10) and other (.90). |
| `MAIN_160` | `8414.90.29` | `Ambiguous` | `Match` | **`Ambiguous`** | Louver material/application unstated; can be architectural steel `7308` or fan part `8414`. |
| `MAIN_161` | `8450.90.20` | `Match` | `Ambiguous` | **`Match`** | Samsung DV5000T is a domestic washer $\le 10\text{ kg}$; parts match dedicated line `8450.90.20`. |
| `MAIN_164` | `8517.79.99` | `Mismatch` | `Ambiguous` | **`Mismatch`** | Optical transceivers are complete apparatus (`8517.62`); parts line `8517.79` is a legal mismatch. |
| `MAIN_166` | `8539.52.90` | `Match` | `Ambiguous` | **`Match`** | Complete Philips screw-in LED bulb satisfies all terms of dedicated statutory line `8539.52.90`. |
| `MAIN_167` | `8523.51.21` | `Mismatch` | `Match` | **`Mismatch`** | External optical DVD drive is an ADP storage unit (`8471.70`); not solid-state media `8523.51`. |
| `MAIN_172` | `8504.40.90` | `Match` | `Ambiguous` | **`Match`** | Omron industrial DC power supply is a static converter under dedicated line `8504.40.90`. |
| `MAIN_177` | `8708.99.80` | `Mismatch` | `Match` | **`Mismatch`** | Engine cooling fans belong to `8414`; legally excluded from Chapter 87 by Section XVII Note 2(e). |

---

### 3. Protocol Remediation Plan (per Roadmap B6)

Because initial metrics fell below the $\ge 80\%$ / $\ge 0.60$ thresholds:
1. **Guide Alignment:** Confirmed that Round 1 decisions adhered strictly to statutory notes (Section XVII Note 2, Chapter 39 Note 2(p), GRI 3(a)) and Guide v1.0 rules.
2. **Retest Quota:** Draw a fresh random subset of **20 descriptions** from the remaining un-retested records in `labels_main.csv` to conduct a targeted verification pass.
3. **Contingency Flag:** If retest agreement meets thresholds ($\ge 80\%$, $\kappa \ge 0.60$), freeze `labels_frozen.csv`. If it remains below, formally tag the audit labels as **low-confidence**, restricting Gate G2 to **Path C**.