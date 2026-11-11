import pandas as pd
from src.hsclf.pipeline import HSPipeline

def test_oos_on_verified_set():
    print("Loading HSPipeline (loading models & TF-IDF weights)...")
    pipeline = HSPipeline(scenario='main')
    
    print("\nLoading Track B Verified Set...")
    try:
        df = pd.read_parquet('data/audit/verified_set.parquet')
    except FileNotFoundError:
        print("Error: Could not find 'data/audit/verified_set.parquet'")
        return
        
    text_col = 'goods_description_raw'
    if text_col not in df.columns:
        print(f"Could not find {text_col}. Available columns: {df.columns.tolist()}")
        return

    rejected_items = []
    passed_items = []
    
    # Save the real threshold so we can manually evaluate it
    real_t_oos = pipeline.t_oos
    
    # Temporarily drop the pipeline's internal threshold to 0 
    # so it returns the full prediction payload instead of early-exiting
    pipeline.t_oos = 0.0
    
    print(f"Testing {len(df)} verified items against the t_oos threshold ({real_t_oos})...\n")
    
    for idx, row in df.iterrows():
        text = str(row[text_col])
        verified_code = str(row.get('verified_label_8', 'Unknown'))
        
        # With t_oos=0, this will return the full prediction dictionary
        result = pipeline.predict(text)
        
        # If it failed the basic character length check
        if result.get("status") == "out_of_scope":
            rejected_items.append({
                "text": text,
                "pred": "N/A",
                "verified": verified_code,
                "conf": 0.0
            })
            continue
            
        pred_code = result.get("predicted_code", "None")
        conf = result.get("calibrated_confidence", 0.0)
        
        # Now manually enforce your REAL threshold
        if conf < real_t_oos:
            rejected_items.append({
                "text": text,
                "pred": pred_code,
                "verified": verified_code,
                "conf": conf
            })
        else:
            passed_items.append(text)
            
    # Print the final report
    print("="*80)
    print(f" TRACK B GOLD SET vs. T_OOS THRESHOLD ({real_t_oos})")
    print("="*80)
    print(f" PASSED (Routed to UI):        {len(passed_items)}")
    print(f" FAILED (Blocked as Garbage):  {len(rejected_items)}")
    print("="*80)
    
    if rejected_items:
        fail_rate = round((len(rejected_items) / len(df)) * 100, 1)
        print(f"\nWARNING: {fail_rate}% of your perfectly valid Track B items were rejected!")
        print("Here is a sample of what got blocked, comparing predictions to truth:\n")
        
        for item in rejected_items[:15]: # Print first 15 failures
            print(f"- TEXT:     {item['text']}")
            print(f"  VERIFIED: {item['verified']}")
            print(f"  PREDICT:  {item['pred']} (Confidence: {round(item['conf'], 3)})")
            
            # Add a flag if the model was actually correct but got blocked
            if str(item['pred']) == str(item['verified']):
                print("  -> (THE MODEL WAS 100% CORRECT BUT GOT BLOCKED!)")
            elif str(item['pred'])[:4] == str(item['verified'])[:4]:
                print("  -> (THE MODEL GOT THE CORRECT 4-DIGIT HEADING BUT GOT BLOCKED!)")
            print()

if __name__ == '__main__':
    test_oos_on_verified_set()