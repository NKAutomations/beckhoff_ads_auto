from custom_components.beckhoff_ads_auto.ads_client import SymbolDescriptor, classify_type

def test_root_path_filter_shape():
    info = classify_type("DINT")
    descriptor = SymbolDescriptor("GVL_HA.Status.Counter", "DINT", info, True)
    assert descriptor.path.startswith("GVL_HA.")
    assert descriptor.info.numeric
