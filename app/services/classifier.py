from src.hsclf.pipeline import HSPipeline
from app.services import stub

# Initialize the pipeline once when the module loads
# (Note: If your pipeline takes a long time to load, we might need to lazy-load this)
try:
    pipeline = HSPipeline()
    PIPELINE_READY = True
except Exception as e:
    print(f"Failed to load HSPipeline: {e}")
    pipeline = None
    PIPELINE_READY = False

def classify(text):
    """
    Calls the real pipeline and translates its output into the 
    Result Contract expected by the frontend.
    """
    if not PIPELINE_READY:
        return {"status": "error", "reason": "Backend pipeline failed to load."}

    # 1. Get the raw prediction from your pipeline
    raw_res = pipeline.predict(text)

    # 2. Handle Out of Scope
    if raw_res.get("status") == "out_of_scope":
        return {
            "status": "out_of_scope",
            "raw_text": text,
            "ui_flag": raw_res.get("reason", "This description is out of scope."),
            "retrieval": {"no_close_match": True, "distribution": [], "examples": []}
        }

    # 3. Translate the Success payload
    if raw_res.get("status") == "success":
        # Map integer keys to string keys for the frontend JSON
        bands = raw_res.get("bands_out", {})
        bands_str_keys = {str(k): v for k, v in bands.items()}

        # Format the candidates (alternatives)
        alternatives = []
        for alt in raw_res.get("alternatives", []):
            alternatives.append({
                "code": alt["code"],
                "prob": alt["prob"]
            })

        # Format retrieval distribution
        retrieval_data = raw_res.get("retrieval", {})
        dist = []
        if "distribution" in retrieval_data:
            for item in retrieval_data["distribution"]:
                dist.append({
                    "code": item["code"],
                    "declaration_count": item.get("declaration_count", 0),
                    "share": item.get("share", 0)
                })

        # Check for vagueness
        is_vague = retrieval_data.get("is_vague", False)

        return {
            "status": "success",
            "raw_text": text,
            "predicted_code": raw_res.get("predicted_code"),
            "deepest_confident_level": raw_res.get("deepest_confident_level"),
            "verification_required": raw_res.get("verification_required", True),
            "ui_flag": raw_res.get("ui_flag", "Please verify this code."),
            "bands_out": bands_str_keys,
            "alternatives": alternatives,
            "retrieval": {
                "distribution": dist,
                "total_declarations": retrieval_data.get("total_declarations", 0),
                "total_descriptions": retrieval_data.get("total_descriptions", 0),
                "max_similarity": retrieval_data.get("max_similarity", 0),
                "no_close_match": retrieval_data.get("no_close_match", False),
                "split_notice": retrieval_data.get("split_notice", False),
                "is_vague": is_vague,
                "examples": retrieval_data.get("examples", [])
            }
        }

    # Fallback for errors
    return {
        "status": "error",
        "ui_flag": raw_res.get("reason", "An unknown error occurred during prediction.")
    }