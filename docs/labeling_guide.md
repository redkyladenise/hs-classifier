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
## 5. Example Bank & Adjudication Rules (Frozen v1.0)

### 5.1 Core Edge-Case Rules

#### Rule 1: Missing Material, Size, or End-Use Specifications
* **Rule:** If a description clearly identifies a physical item, but the declared 8-digit tariff line depends on a material composition (e.g., plastic vs. metal), physical dimension (e.g., diameter $\le 16\text{ mm}$), or specific vehicle/machine end-use that is NOT stated in the raw text:
  * Assign **`Ambiguous`** (Confidence: 2 or 3).
  * Do **NOT** assign `Match` by assuming or guessing unstated parameters.
  * Do **NOT** assign `Mismatch` unless the text explicitly contradicts the statutory scope of the heading/subheading.

#### Rule 2: Statutory Precedence & Legal Exclusions (Section XVII Note 2)
* **Rule:** The vehicle parts headings of Chapter 87 (`8708` for motor vehicles, `8714` for motorcycles) legally **exclude** the following items pursuant to Section XVII Note 2, even when declared for specific automotive brands (e.g., Yamaha, Honda, Hino, Kia):
  * **Note 2(a) — Parts of General Use:** Fasteners, screws, bolts, nuts, rivets, and springs of base metal (Chapter 73) or plastics (Chapter 39).
  * **Note 2(e) — Machinery & Mechanical Appliances:** Engine pumps (Heading 84.13), air/liquid intake filters (Heading 84.21), mechanical valves (Heading 84.81), and gears, camshafts, or transmissions (Heading 84.83).
  * **Note 2(f) — Electrical Machinery & Equipment:** Electric motors (Heading 85.01), rectifiers and static converters (Heading 85.04), vehicle lighting/wiper units (Heading 85.12), and electrical switches or relays (Heading 85.36).
  * **Note 2(g) — Instruments & Apparatus:** Speedometers, tachometers, instrument clusters, and measuring sensors (Chapter 90).
* **Adjudication:** Any declared code in Chapter 87 for an article legally excluded under Note 2 is an automatic, unambiguous **`Mismatch`**.

#### Rule 3: Basket / Residual Clause Subordination (GRI 3(a))
* **Rule:** Residual basket clauses (e.g., `3926.90.99`, `7326.90.99`, `8479.90.90`) are clauses of last resort. If the tariff contains a more specific heading or subheading naming the article (e.g., gloves, boxes, plates, valves, or machine tools), the residual basket code is legally subordinate and must be labeled **`Mismatch`**.

#### Rule 4: Commodity Form & Hierarchy Contradictions
* **Rule:** A code must be labeled **`Mismatch`** if there is a fundamental structural mismatch in commodity form:
  * **Apparatus vs. Part:** The shipment is a loose replacement part or fastener, but the declared code is for a complete apparatus or complete vehicle (e.g., a washer declared as a 5-ton cargo truck).
  * **Part vs. Apparatus:** The shipment is a complete finished apparatus, but the declared code is strictly for sub-parts (e.g., a complete relief valve declared under valve parts `8481.90`).
  * **Workpiece vs. Machine Tool:** The shipment is an article or material, but the declared code is for an industrial machine tool designed to fabricate that article (e.g., a printed circuit board declared under board-deburring machines `8465.99.50`).

#### Rule 5: Non-Identified Commodities (`kind_identified = no`)
* **Rule:** If the description lacks an identifiable physical noun or commercial identity—consisting solely of generic process terms (`"ASSY"`), vague labels (`"SPARE PARTS"`, `"ELECTRONICS PACKED"`), unanchored nouns (`"BALL"`, `"ORIFICE"`), or raw alphanumeric codes without context (`"LED-R-FP Z09"`):
  * Set `kind_identified = no`.
  * Assign **`Cannot check`** across all code columns.
  * Do **NOT** assign `Ambiguous` or attempt to evaluate candidate codes.

---

### 5.2 Example Bank

#### A. Missing Parameter & Ambiguity Cases
1. **Unspecified Material:**
   * *Text:* `"meal box, brand laiwosi"`
   * *Declared Code:* `3924.90.90` (Household articles of plastics)
   * *Verdict:* `Ambiguous`
   * *Reason:* Plausible if made of plastic, but equally plausible under `7323.99.90` (iron or steel). Material is unstated.
2. **Unspecified Dimension / Threshold:**
   * *Text:* `"ring nut"`
   * *Declared Code:* `7318.16.90` (Threaded nuts of iron/steel: Other)
   * *Verdict:* `Ambiguous`
   * *Reason:* Threaded nut under `7318.16`, but cannot verify whether inner diameter is $\le 16\text{ mm}$ (`.10`) or $> 16\text{ mm}$ (`.90`).
3. **Unspecified Electrical Rating:**
   * *Text:* `"1 PC EMERGENCY STOP SWITCH"`
   * *Declared Code:* `8536.50.69` (Push-button switch $\ge 16\text{ A}$)
   * *Verdict:* `Ambiguous`
   * *Reason:* Push-button switch under `8536.50`, but text lacks the current rating needed to distinguish $< 16\text{ A}$ (`.61`) from $\ge 16\text{ A}$ (`.69`).
4. **Multi-Heading Application:**
   * *Text:* `"MOUNTING BRACKET"`
   * *Declared Code:* `8708.29.99` (Motor vehicle body parts)
   * *Verdict:* `Ambiguous`
   * *Reason:* Could legitimately be an automotive bracket (8708), base metal hardware (8302), or plastic fitting (3926).

#### B. Statutory Exclusion Cases (Section XVII Note 2)
1. **Mechanical Appliance on a Vehicle:**
   * *Text:* `"2PCE OIL PUMP ASSY"`
   * *Declared Code:* `8714.10.90` (Motorcycle parts)
   * *Verdict:* `Mismatch`
   * *Reason:* Liquid pumps have a dedicated statutory heading under `8413.30`. Section XVII Note 2(e) expressly excludes Chapter 84 machinery from Chapter 87.
2. **Gears & Transmission Elements on a Vehicle:**
   * *Text:* `"9 PCE GEAR, PUMP DRIVE"` (or `"SHIFT CAM ASSEMBLY (YAMAHA BRAND)"`)
   * *Declared Code:* `8714.10.40` or `8714.10.90` (Motorcycle parts)
   * *Verdict:* `Mismatch`
   * *Reason:* Gears, cams, and shafts classify under Heading `84.83` and are legally barred from Chapter 87 by Section XVII Note 2(e).
3. **Parts of General Use on a Vehicle:**
   * *Text:* `"5 PCS RIVET"` (or `"140PCE BOLT A,STPR.ARM"`)
   * *Declared Code:* `8708.99.99` or `8714.10.90` (Vehicle parts)
   * *Verdict:* `Mismatch`
   * *Reason:* Rivets and threaded bolts are fasteners of general use under Heading `73.18`. Section XVII Note 2(a) strictly excludes them from vehicle chapters.
4. **Electrical Equipment on a Vehicle:**
   * *Text:* `"RECTIFIER & REGULATOR ASSY"`
   * *Declared Code:* `8714.10.90` (Motorcycle parts)
   * *Verdict:* `Mismatch`
   * *Reason:* Static electrical converters classify under `8504.40` and are excluded from vehicle parts by Section XVII Note 2(f).

#### C. Specificity & Basket Subordination Cases (GRI 3(a))
1. **Specific Apparel vs. General Household:**
   * *Text:* `"MR DIY SILICONE DISH GLOVE Polyvinyl chloride 100%"`
   * *Declared Code:* `3924.90.90` (Household articles of plastics)
   * *Verdict:* `Mismatch`
   * *Reason:* Gloves have a dedicated statutory subheading under `3926.20`. General household articles under 3924 are disqualified under GRI 3(a).
2. **Specific Semi-Finished Shape vs. Plastic Basket:**
   * *Text:* `"PTFE PLATE"`
   * *Declared Code:* `3926.90.99` (Other articles of plastics)
   * *Verdict:* `Mismatch`
   * *Reason:* Flat plastic plates and sheets classify under Heading `39.20`. Residual basket 3926.90 is subordinate under GRI 3(a).

#### D. Commodity Form Contradictions
1. **Machine Tool vs. Commodity:**
   * *Text:* `"PRINTED BOARD"`
   * *Declared Code:* `8465.99.50` (Deburring and laminating machine tools for printed boards)
   * *Verdict:* `Mismatch`
   * *Reason:* The imported commodity is the circuit board itself, not an industrial factory machine tool used to fabricate it.
2. **Finished Unit vs. Sub-Parts:**
   * *Text:* `"VALVE, PRESSURE RELIEF 100 PCS"`
   * *Declared Code:* `8481.90.90` (Parts of valves)
   * *Verdict:* `Mismatch`
   * *Reason:* The shipment consists of complete pressure relief valves (Heading `8481.40`), not disassembled valve parts.
3. **Fastener vs. Complete Vehicle:**
   * *Text:* `"WASHER, SPR"`
   * *Declared Code:* `8704.90.91` (Motor vehicles for transport of goods $\le 5\text{ t}$)
   * *Verdict:* `Mismatch`
   * *Reason:* A spring lock washer (Heading `7318.21`) cannot be classified as an entire 5-ton commercial cargo truck.

#### E. Non-Identified Descriptions (`kind_identified = no`)
1. **Bare Functional Word:**
   * *Text:* `"ASSY"`
   * *Declared Codes:* `8507.80.99`, `8536.90.29`
   * *Verdict:* `Cannot check` (All codes)
   * *Reason:* Truncated abbreviation with no noun, material, or system context.
2. **Unanchored Noun:**
   * *Text:* `"10PCS. BALL"`
   * *Declared Codes:* `8482.10.00`, `8482.91.00`
   * *Verdict:* `Cannot check` (All codes)
   * *Reason:* Completely unanchored noun. Could be bearing balls (8482), valve spheres (8481), toy balls (9503), or sports balls (9506).