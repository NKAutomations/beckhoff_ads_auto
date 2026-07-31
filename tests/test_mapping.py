from custom_components.beckhoff_ads_auto.ads_client import classify_type, normalize_type

def test_type_mapping():
    assert classify_type("BOOL").boolean
    assert classify_type("LREAL").numeric
    assert classify_type("STRING(80)").string
    assert normalize_type("STRING(80)") == "STRING"
