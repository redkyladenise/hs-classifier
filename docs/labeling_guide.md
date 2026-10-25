# HS Classification Labeling Guide

**Version:** 0.1 (Draft for Pilot)  
**Date:** October 2026  
**Scope:** Human audit of customs goods descriptions against declared 8-digit AHTN 2022 codes across Chapters 39, 73, 84, 85, and 87.

---

## 1. Golden Rules
1. **Rely only on what is written:** Base your judgment strictly on the text shown. Do not guess unmentioned details.
2. **Read the full tree, not just the leaf:** Never look at an 8-digit code in isolation (especially vague names like "Other" or "Parts"). Always read its parent 4-digit Heading and 6-digit Subheading to understand the full category.
3. **When in doubt, choose Ambiguous:** If the description lacks technical details (material, voltage, size) needed to decide, label it `Ambiguous`.
4. **Blind audit:** You must judge the product without knowing how many times it was declared, who imported it, or what any machine learning model predicted.

---

## 2. The 4 Labels for Each Code
For every code attached to a description, pick exactly one label:

| Label | Plain English Meaning | When to Use |
|---|---|---|
| **Match** | Plausible (Fits) | The product matches the tariff line. Nothing written in the text contradicts the official rules. |
| **Mismatch** | Clearly Wrong | The item is an entirely different product, or its written attributes directly violate the tariff definition. |
| **Ambiguous** | Not Enough Information | The description is too short, broad, or vague to confirm or reject the code (e.g., missing material or power rating). |
| **Cannot check** | Broken / Unusable | The description is total gibberish, empty, or the code does not exist in the official tariff book. |

---

## 3. Product-Level Checks
* **`kind_identified` (`yes` / `no`):** Can you tell what the physical item actually is?
  * `yes`: You know the product (e.g., "hydraulic pump", "steel flange"), even if specific sub-models or sizes are missing.
  * `no`: The text is completely generic (e.g., "spare parts", "assorted items", "samples") or unreadable.
* **`invalid_code` (`yes` / `no`):** Marked `yes` if the code is not in the official AHTN 2022 reference list.

---

## 4. Final Verdict for the Description
After labeling each individual code, a single overall verdict is determined automatically by these rules:

| Overall Verdict | Condition |
|---|---|
| **Multiple plausible** | 2 or more declared codes are labeled `Match`. |
| **One plausible, others wrong** | Exactly 1 code is labeled `Match`, and at least 1 other code is labeled `Mismatch`. |
| **One plausible** | Exactly 1 code is labeled `Match`, and all other codes are `Ambiguous` or `Cannot check`. |
| **All implausible** | 0 codes are labeled `Match`, and at least 1 code is labeled `Mismatch`. |
| **Ambiguous between codes** | 0 `Match`, 0 `Mismatch`, but `kind_identified == 'yes'`. |
| **Undecidable (unusable)** | 0 `Match`, 0 `Mismatch`, and `kind_identified == 'no'`. |

---

## 5. Example Bank
*(Concrete examples will be added here during the Step B4 pilot run.)*