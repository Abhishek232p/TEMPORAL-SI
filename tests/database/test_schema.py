import pytest
from sqlalchemy import inspect
from packages.core.db.models import Base

def test_required_tables_exist(engine):
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    required = [
        'users', 'organizations', 'memberships', 'projects',
        'datasets', 'dataset_versions', 'data_sources', 'data_profiles',
        'data_quality_reports', 'features', 'experiments', 'models',
        'model_versions', 'evaluations', 'forecast_runs', 'forecast_points',
        'prediction_intervals', 'evidence', 'proof_objects', 'provenance_records',
        'graph_nodes', 'graph_edges', 'alerts', 'audit_logs', 'usage_records'
    ]
    for table in required:
        assert table in tables, f"Missing required table: {table}"

def test_indexes_exist(engine):
    inspector = inspect(engine)
    indexes = inspector.get_indexes('graph_edges')
    index_names = [idx['name'] for idx in indexes]
    assert any('source_node_id' in name for name in index_names)
    assert any('target_node_id' in name for name in index_names)
