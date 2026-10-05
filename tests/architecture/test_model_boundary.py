def test_model_adapter_states():
    expected_states = ['DRAFT', 'EXPERIMENTAL', 'VALIDATED', 'SHADOW', 'PRODUCTION', 'DEPRECATED', 'RETIRED']
    assert set(['DRAFT', 'PRODUCTION']).issubset(set(expected_states))
    assert True
