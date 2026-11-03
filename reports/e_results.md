# Track E Results: Retrieval Engine Evaluation

## Plain-Language Summary
The retrieval engine matches new item descriptions against a capped historical index to retrieve the most semantically similar past declarations. Across heading, subheading, and tariff code levels, the retrieved declarations contained the declared code more often than a frequency baseline. The engine’s hit rate heavily depends on semantic similarity; results with a cosine similarity above 0.5 show substantially higher hit rates. Because the dataset license is unresolved, the engine returns statistical distributions of past codes rather than raw example texts.

## Headline Hit-Rate Table (Overall)
| AHTN Level | Hit@5 Rate | 95% CI | Frequency Baseline | Paired Diff (Retrieval - Freq) | 95% CI (Paired Diff) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 2-Digit (Chapter) | 84.58% | [84.26%, 84.90%] | 87.22% | -0.026 | [-0.028, -0.024] |
| 4-Digit (Heading) | 64.27% | [63.85%, 64.69%] | 37.21% | +0.270 | [+0.265, +0.276] |
| 6-Digit (Subheading) | 50.61% | [50.17%, 51.05%] | 17.10% | +0.335 | [+0.329, +0.340] |
| 8-Digit (Tariff Code) | 41.46% | [41.03%, 41.89%] | 7.06% | +0.344 | [+0.339, +0.348] |

*At levels 4, 6, and 8, the paired difference interval is strictly above zero, confirming the retrieved declarations contained the declared code more often than a frequency baseline.*

## Similarity-Band Hit Rate (Level 6)
| Cosine Similarity Band | Hit@5 Rate | 95% CI |
| :--- | :--- | :--- |
| < 0.3 | 27.74% | [26.46%, 29.05%] |
| 0.3 - 0.5 | 40.32% | [39.62%, 41.02%] |
| 0.5 - 0.7 | 54.51% | [53.75%, 55.27%] |
| 0.7 - 0.9 | 72.11% | [71.17%, 73.02%] |
| >= 0.9 | 83.71% | [81.53%, 85.69%] |

## Near-Twins Influence
Near-twins (queries with a maximum similarity >= 0.95) make up 0.61% of the test set. 
* **With near-twins (>= 0.95):** Level 8 Hit@5 is 82.89%.
* **Without near-twins (< 0.95):** Level 8 Hit@5 is 41.20%.

## Verified-Set Result (n=66)
When evaluated against the 66 manually audited items, the engine demonstrated strong agreement with plausibility-checked labels. The Hit@5 agreement was 71.2% at Level 4, 60.6% at Level 6, and 53.0% at Level 8.

## Limitations
* The index is a capped sample containing 367,085 descriptions, so the returned distributions represent shares among the nearest descriptions, not true population shares.
* The retrieved declarations are unverified and can repeat past filing errors (the Track B audit explicitly found hidden errors in the historical data).
* Hit@5 is a lenient metric because it accepts any code from the five nearest neighbors.
* The presence of near-twins in the data can raise the average hit rate.
* No example texts are shown in the final output because the dataset license is unresolved.