# Track D Results: Label Conflict Handling

## Plain-Language Summary
This track evaluated whether heuristic data-cleaning methods (resolving historical label conflicts via majority rule, dropping, or down-weighting) yield better model performance than training on raw, unhandled historical data. Across both synthetic laboratory tests and real-world evaluations, no handling method improved on raw labels in these experiments. The unhandled baseline maintains the best relative ranking across all splits, and the raw model remains frozen for final testing.

## D1: Direct Checks on Historical Data
Historical label conflicts affect a small minority of the distinct vocabulary but account for a large share of volume: conflicts exist in 2.65% of pool descriptions and 20.36% of total transactions. Of these conflicts, 56.46% are closely contested splits (the majority code holds less than 60% of the volume). 
Comparing historical dominance to human audit data reveals that the historical majority code is a weak proxy for ground truth: the majority code matched the verified code in only 14 of 34 stratum-A records (41.18%, 95% interval 26.37–57.78%) at the line level.

## D2: Synthetic Laboratory Results
To evaluate the model's native robustness, we tested it against a synthetic dataset with an assumed noise shape. The model tolerates injected noise natively: the clean baseline scored 65.63%, and when injected with 20% noise, it scored 65.51%. Because the degradation gap was only 0.12 points (well below the 0.5 threshold), recovery metrics were not computed.

## D4b: Pipeline Control
Handled models were trained using the frozen hyperparameters and class eligibility thresholds from the C5 baseline. The H0 control run established that nodes 8410 and 8521 naturally collapse due to extreme class imbalance. However, the H2 variant (Drop) caused a third node (8702) to collapse. This suggests H2 actively discards useful training data.

## D5: Validation Ranking
The models were evaluated on the 100,000-record `val_cal` dataset. The raw baseline established a clear directional advantage over all handled variants. 
At Level 8 (M2 Top-1), the scores and paired intervals were:
* **Raw (`main`)**: 0.3827
* **H1 (`main_h1`)**: 0.3642 (95% CI: [-1.98%, -1.73%])
* **H2 (`main_h2`)**: 0.3628 (95% CI: [-2.13%, -1.85%])
* **H3 (`main_h3`)**: 0.3686 (95% CI: [-1.50%, -1.26%])

## D6: Audit and Test Confirmation
The relative ranking established in validation was confirmed on a locked 300,000-record test sample. The raw baseline (0.3897) outperformed the highest-ranked handled variant, H3 (0.3772), with negative paired cluster-bootstrap differences across overall, consistent, and conflict-prone splits. Furthermore, audit-sample evaluations indicated that heuristic data handling reduced agreement with plausibility-checked labels compared to the raw baseline.

## Explanatory Hypotheses
The failure of heuristic handling methods to improve upon the raw baseline can be explained by several hypotheses:
1. **Conflicts are few:** They represent only 2.65% of pool descriptions, limiting the theoretical ceiling of any conflict-resolution strategy.
2. **Majority rules are flawed:** The majority code matched the verified code in only 14 of 34 stratum-A records at the line level, meaning "cleaning" by majority often reinforces the wrong label.
3. **Hidden errors are untouched:** Heuristics only target visible 1-to-N conflicts, leaving systematic 1-to-1 hidden historical errors entirely unhandled.
4. **The architecture is robust:** The SGD model natively tolerates injected noise, making aggressive external data-cleaning unnecessary.
5. **Data loss:** Methods like H2 discard valuable training data, starving the model of diverse vocabulary features.

## Caveats and Limitations
* Inherited limitations from Path C regarding low-confidence labels remain present.
* The verified set (N=66) holds only clear, unequivocal cases and is not perfectly representative of all edge cases.
* Declared test labels carry the exact same natural noise distribution as the training data.
* Conflicts affect only about 2% of descriptions.
* Hidden errors are not handled by these heuristics.
* Data handling was tested on one specific architectural scenario.
* The synthetic noise test relies on an assumed mathematical shape.
* The handled models (H1, H2, H3) are uncalibrated.
* Results are bound by the control limits established in D4b.
* Due to resource constraints and predefined validation ranking, H1 and H2 underwent audit-only scoring in D6, while only H3 was evaluated against the full test sample.

## Logged Deviations
1. **Gate D1 Override:** We ran all handling methods (H1, H2, H3) for complete observational data despite the Gate D1 rule stipulating we could stop at H1 due to the small noise gap.
2. **Reduced D6 Scope:** To optimize resources, the 300,000-record test sample evaluated only the raw baseline and H3 (the best-ranked variant), whereas H1 and H2 were limited to the audit sample.
3. **Eligibility:** Handled models strictly inherited the raw baseline's C1 eligibility thresholds rather than recalculating them, to preserve structural parity.
4. **Resource Constraints:** Time and RAM profiles for handled variants differed marginally from the baseline but remained within hardware limits.