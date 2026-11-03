# Handoff to Track G (App Integration)

**1. Search Function**
* **Function:** `engine.search_query(text, routed_chapters)` from `src/hsclf/retrieval/search.py`
* **Returned Fields (Dictionary):**
  * `neighbor_count`: Number of historical neighbors found (max 5).
  * `distribution`: The declaration-weighted distribution of codes at `display_level`.
  * `max_similarity`: The cosine similarity of the closest neighbor.
  * `no_close_match`: Boolean (`True` if `max_similarity < 0.5`).
  * `split_notice`: Boolean (`True` if the top code in the distribution has `< 0.60` share).

**2. Frozen Settings (`params.yaml`)**
* `retrieval_k`: 5
* `display_level`: 4
* `min_similarity`: 0.5
* `split_share`: 0.60
* `show_examples`: false
* `min_example_tx`: 20
* `vague_max_words`: 2 / `vague_low_share_max`: 0.40 / `vague_min_gap`: 5.0

**3. Hardware Profile (from E2)**
* **Latency:** ~0.087 seconds per query.
* **RAM usage:** Operates strictly under `memory_ceiling_gb: 0.68` (requires sorting by routed chapter for bulk processing, but single queries easily fit within memory limits).

**4. Evidence Text Strategy**
* Because `show_examples` is false, the app UI should present the **distribution percentages** at the 4-digit level. It must **never** show the raw text of the historical neighbors.