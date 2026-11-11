# Website Result Contract

The stub and the real service both return this dictionary. No raw probabilities are shown to the user.

- `status`: "success" or "out_of_scope"
- `raw_text`: The user's input string.
- `predicted_code`: The top 8-digit string.
- `deepest_confident_level`: 2, 4, 6, 8, or null.
- `verification_required`: Boolean.
- `ui_flag`: Summary text for the banner.
- `bands_out`: Dictionary with keys "8", "6", "4", "2" mapping to "High", "Medium", or "Low".
- `alternatives`: List of dictionaries containing "code" and "prob" (used for the Other Candidates list).
- `retrieval`: Dictionary containing:
  - `distribution`: List of dicts with "code", "declaration_count", "share".
  - `total_declarations`: Float or int.
  - `total_descriptions`: Int.
  - `max_similarity`: Float.
  - `no_close_match`: Boolean.
  - `split_notice`: Boolean.
  - `examples`: List of dicts with "example_id", "text", "similarity", "codes".