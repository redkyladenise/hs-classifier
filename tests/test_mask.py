from src.hsclf.retrieval.mask import mask_description

def test_model_and_brand():
    assert mask_description("yamaha motorcycle spare parts model xj-250") == "[brand] motorcycle spare parts model [model]"

def test_company_greedy():
    assert mask_description("abc trading co ltd water pump") == "[company] water pump"    
    assert mask_description("heavy duty pump sony inc") == "heavy duty [company]"

def test_names_and_contacts():
    assert mask_description("mr santos water pump info@test.com") == "[name] water pump [contact]"

def test_addresses():
    assert mask_description("deliver to warehouse brgy san antonio") == "deliver to warehouse [address] san antonio"

def test_number_protection():
    assert mask_description("mobile phone upc 1234567890") == "mobile phone upc [number]"

def test_measurement_protection():
    assert mask_description("steel pipe 60mmx20mm model a20043b4") == "steel pipe 60mmx20mm model [model]"
    assert mask_description("resin 25kgs") == "resin 25kgs"

def test_over_masking_drop():
    assert mask_description("abc trading co pump") is None