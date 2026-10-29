# Step B7: Audit Analysis & Label Noise Findings

**Date:** 2026-10-29  
**Dataset Source:** `data/audit/labels_frozen.csv` ($N = 180$)  
**Target Population:** Bureau of Customs Import Declarations Test Frame ($N = 790,058$)  

---

## 1. Executive Summary

This report analyzes the manual audit of 180 customs commodity descriptions to measure the true rate of label noise and ambiguity in Philippine import declarations. All estimates are weighted to reflect the full test population of 790,058 import items.

### Key Takeaways
1. **Plausibility Ceiling is Low (37.78%):** In cases where importers declared different HS codes for identical descriptions, only **37.78%** had at least one correct tariff code declared. In the remaining **62.22%**, all declared codes were either legally wrong (11.11%) or missing critical details needed to decide (43.33%).
2. **High Hidden Noise in "Clean" Declarations (36.51%):** Among imports that seemed clean (singletons and repeated imports without visible conflict), **36.51%** (weighted) were misclassified by customs brokers. Historical customs declarations cannot be trusted as pure ground truth.
3. **Ambiguity Dominates Conflicts (43.33%):** Most multi-code conflicts happen not because brokers choose different valid options, but because descriptions omit required technical specs (e.g., material composition, voltage, dimensions).
4. **Verified Gold Benchmark:** 66 descriptions had exactly one indisputable, legally valid HS code and have been exported to `data/audit/verified_set.parquet` for downstream model evaluation.

---

## 2. Population Weights & Sampling Design

Because difficult, conflicting items were intentionally oversampled for auditing, all population estimates use stratification weights:

| Stratum | Description Type | Test Frame Population ($N_h$) | Population Weight ($W_h$) | Sample Audited ($n_h$) |
|:---|:---|:---:|:---:|:---:|
| **Stratum A** | Conflicting descriptions | 16,587 | **2.10%** | 90 |
| **Stratum B** | Repeated clean descriptions | 88,387 | **11.19%** | 45 |
| **Stratum C** | Singleton imports | 685,084 | **86.71%** | 45 |
| **Total** | | **790,058** | **100.00%** | **180** |

---

## 3. Detailed Audit Findings

### Finding 1: Breakdown of Conflicting Descriptions (Stratum A, $n = 90$)
When different brokers assign conflicting HS codes to identical goods, what is actually happening?

| Verdict Category | Count | Sample Share | 95% Wilson CI | Plain Meaning |
|:---|:---:|:---:|:---:|:---|
| **Ambiguous between codes** | 39 | **43.33%** | [33.58%, 53.64%] | Text lacks technical details needed to pick between the codes. |
| **One plausible, others wrong** | 34 | **37.78%** | [28.46%, 48.10%] | Exactly one declared code was legally correct; others were errors. |
| **All implausible** | 10 | **11.11%** | [6.15%, 19.26%] | Every declared code was legally wrong under statutory rules. |
| **Undecidable / Unusable** | 7 | **7.78%** | [3.82%, 15.19%] | Text consists of bare codes or vague words (`kind_identified = no`). |
| **Multiple plausible** | 0 | **0.00%** | [0.00%, 4.09%] | Descriptions with multiple genuinely legal classifications. |
| **One plausible (alone)** | 0 | **0.00%** | [0.00%, 4.09%] | N/A for multi-code conflicts. |

**Insight:** 0% of conflicts represented "Multiple plausible" codes. Conflicts are not valid alternative interpretations; they are caused by missing invoice specs or outright broker filing errors.

---

### Finding 2: Hidden Error Rate in Seemingly Clean Filings (Strata B & C)
Do clean, non-conflicting declarations represent clean data?

| Stratum | Total Audited ($n$) | Mismatches Found ($k$) | Sample Error Rate | 95% Wilson CI |
|:---|:---:|:---:|:---:|:---:|
| **Stratum B (Repeated Clean)** | 45 | 12 | 26.67% | [15.96%, 41.04%] |
| **Stratum C (Singletons)** | 45 | 17 | 37.78% | [25.11%, 52.37%] |
| **Weighted Strata B + C** | 90 | 29 | **36.51%** | — |

**Insight:** Over **36% of non-conflicting imports contain label errors**. Relying only on conflict detection will miss most errors, because 86.7% of the real customs database consists of singletons (Stratum C) where conflicts never appear.

---

### Finding 3: Conflict Plausibility Ceiling (Upper Bound)
* **Plausibility Ceiling:** **37.78%** (95% CI: `[28.46%, 48.10%]`)
* Out of 90 conflicting items, only 34 contained at least one legally valid code. 
* This sets an absolute ceiling: any automated system trained directly on raw conflicted declarations cannot exceed ~38% legal correctness without filtering out label noise.

---

### Finding 4: Verified Benchmark Set (`verified_set.parquet`)
To evaluate downstream machine learning models in Track D, rows with **exactly one plausible code (`Match`)** were isolated into a verified gold benchmark:

* **Total Verified Descriptions:** **66** (36.67% of the audited sample)
  * Stratum A (Conflicts): 34 descriptions
  * Stratum B (Clean repeated): 15 descriptions
  * Stratum C (Singletons): 17 descriptions
* **Selection Bias Note:** Because ambiguous and undecidable rows are excluded, this verified benchmark naturally over-represents clear, specific product descriptions compared to raw trade data.

---

## 4. Gate G2 Review & Path Selection

Applying the pre-registered decision rules in priority order:

1. **Gate B3 Status:** **Failed** ($P_o = 61.11\%$, $\kappa = 0.4564$; self-consistency retest waived).
2. **Selected Path:** **Path C (Inconclusive / Directional)**.
3. **Implications for Track D:**
   * Downstream evaluation cannot claim absolute gold-standard accuracy against real-world trade data.
   * Model evaluation will focus on **synthetic label noise experiments**, **relative model rankings**, and **drift analysis**.
   * The 66-row verified set serves as a directional validation set, reported alongside raw test set metrics.

## 5. Methodological Limitations & Handoff to Tracks C & D

1. **Gate B3 Reliability & Path C Constraint:**
   * Due to inter-round consistency metrics failing pre-registered thresholds ($P_o = 61.11\%$, $\kappa = 0.4564$) and the retest being waived, this audit dataset carries a **Low-Confidence** designation.
   * **Constraint:** Track D cannot cite absolute accuracy against this audit set as a definitive gold standard. All downstream claims must be restricted to relative model ranking, directional effects, and synthetic label noise experiments (Gate G2 Path C).

2. **Selection Bias in `verified_set.parquet`:**
   * Filtering strictly for rows with exactly one legal `Match` retained 66 out of 180 descriptions (36.67%).
   * By construction, this gold set excludes ambiguous descriptions, biasing evaluation toward clearly specified, verbose, or branded commodities compared to the noisy real-world import stream.

3. **Near-Twin Leakage Note:**
   * Text descriptions in the audit sample that share near-identical strings ($\ge 0.95$ similarity) with training splits must be partitioned during Track D evaluation to avoid reporting inflated memorization accuracy.