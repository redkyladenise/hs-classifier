import re
from pathlib import Path

def load_brands():
    brand_file = Path('data/reference/brands.txt')
    if not brand_file.exists():
        return set()
    with open(brand_file, 'r', encoding='utf-8') as f:
        return {line.strip().lower() for line in f if line.strip()}

BRANDS = load_brands()
COMPANY_SUFFIXES = {'co', 'corp', 'inc', 'ltd', 'llc', 'gmbh', 'pte', 'sdn', 'bhd', 'plc'}

def mask_description(text):
    if not isinstance(text, str):
        return None
        
    text = text.lower().strip()
    
    # 0. Multi-word brand overrides
    text = re.sub(r'\bmr\.?\s*diy\b', '[brand]', text)
    
    # 1. Contacts & Web
    text = re.sub(r'\S*@\S*', '[contact]', text)
    text = re.sub(r'\S*www\.\S*|\S*\.com\b|\S*\.ph\b', '[web]', text)
    
    # 2. Addresses (Strictly safe Philippine markers)
    text = re.sub(r'\b(?:brgy|barangay|sitio|purok|subd|subdivision|metro manila|p\.o\. box)\b', '[address]', text)
    
    # 3. Models (Mask mixed alphanumeric strings, but explicitly spare valid measurements)
    def mask_model(match):
        word = match.group(0)
        valid_units = r'(?:kgs?|g|mg|lbs?|oz|pcs?|mm|cm|m[23]?|ml|l|inch|mil|mic|v|w|kw|hz)'
        if re.fullmatch(rf'(?:\d+(?:\.\d+)?{valid_units}?x?)+', word):
            return word
        return '[model]'

    text = re.sub(r'\b(?:[a-z]+[-_]*\d+[\w-]*|\d+[-_]*[a-z]+[\w-]*)\b', mask_model, text)
    text = re.sub(r'\b\d{5,}\b', '[number]', text)
    
    # 5. Names
    text = re.sub(r'\b(?:mr|mrs|ms|dr)\.?\s+\w+\b', '[name]', text)
    
    words = text.split()
    
    # 6 & 7. Brands & Companies (Greedy chaining for multiple suffixes like "co ltd")
    i = len(words) - 1
    while i >= 0:
        clean_word = re.sub(r'[^\w\s]', '', words[i])
        
        if clean_word in COMPANY_SUFFIXES:
            suffix_start = i
            while suffix_start > 0 and re.sub(r'[^\w\s]', '', words[suffix_start - 1]) in COMPANY_SUFFIXES:
                suffix_start -= 1
            
            start = max(0, suffix_start - 2)
            words[start:i+1] = ['[company]']
            i = start - 1
        else:
            if clean_word in BRANDS:
                words[i] = '[brand]'
            i -= 1
            
    masked_text = ' '.join(words)
    if len(masked_text) > 120:
        masked_text = masked_text[:120].rsplit(' ', 1)[0]
        
    # 7. Over-masking check
    real_words = [w for w in masked_text.split() if not (w.startswith('[') and w.endswith(']'))]
    if len(real_words) < 2:
        return None
        
    return masked_text