import pytest
from sqlalchemy.exc import IntegrityError, StatementError
import uuid
from datetime import datetime
from packages.core.db.models import Organization, Project, Dataset, DatasetVersion, Model, ModelVersion, ForecastRun, ForecastPoint, PredictionInterval

def test_prediction_interval_bounds(db_session):
    org = Organization(id=uuid.uuid4(), name="O", slug="o")
    proj = Project(id=uuid.uuid4(), organization_id=org.id, name="P", slug="p")
    db_session.add_all([org, proj])
    db_session.commit()

    ds = Dataset(id=uuid.uuid4(), organization_id=org.id, project_id=proj.id, name="DS")
    mod = Model(id=uuid.uuid4(), organization_id=org.id, name="M", provider="P")
    db_session.add_all([ds, mod])
    db_session.commit()

    dsv = DatasetVersion(id=uuid.uuid4(), dataset_id=ds.id, organization_id=org.id, version=1, content_hash="h")
    modv = ModelVersion(id=uuid.uuid4(), model_id=mod.id, version=1)
    db_session.add_all([dsv, modv])
    db_session.commit()

    run = ForecastRun(id=uuid.uuid4(), organization_id=org.id, project_id=proj.id, dataset_version_id=dsv.id, model_version_id=modv.id, horizon=1)
    db_session.add(run)
    db_session.commit()
    
    pt = ForecastPoint(id=uuid.uuid4(), forecast_run_id=run.id, timestamp=datetime(2026,1,1), target="sales", predicted_value=100.0)
    db_session.add(pt)
    db_session.commit()
    
    # Valid
    interval = PredictionInterval(forecast_point_id=pt.id, level=0.9, lower_value=90.0, upper_value=110.0)
    db_session.add(interval)
    db_session.commit()
    
    # Invalid
    bad_interval = PredictionInterval(forecast_point_id=pt.id, level=0.9, lower_value=120.0, upper_value=110.0)
    db_session.add(bad_interval)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
