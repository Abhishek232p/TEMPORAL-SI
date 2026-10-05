import pytest
from packages.core.data.connectors.rest import RESTConnector, SecurityError
from packages.core.data.connectors.postgres import PostgreSQLConnector
import os

def test_rest_ssrf_protection():
    os.environ["ALLOW_LOCAL_REST"] = "0"
    connector = RESTConnector()
    
    # File scheme rejection
    with pytest.raises(SecurityError):
        connector.validate_config({"url": "file:///etc/passwd"})
        
    # Loopback rejection
    with pytest.raises(SecurityError):
        connector.validate_config({"url": "http://127.0.0.1:8000"})
        
    # Valid url
    assert connector.validate_config({"url": "https://api.weather.gov"}) == True

def test_postgres_readonly_protection():
    connector = PostgreSQLConnector()
    
    with pytest.raises(Exception, match="Unsafe operation detected: UPDATE "):
        connector.validate_config({
            "connection_string": "sqlite:///:memory:",
            "query": "UPDATE users SET active=1"
        })
        
    with pytest.raises(Exception, match="Unsafe operation detected: DROP "):
        connector.validate_config({
            "connection_string": "sqlite:///:memory:",
            "query": "DROP TABLE datasets"
        })
        
    assert connector.validate_config({
        "connection_string": "sqlite:///:memory:",
        "query": "SELECT * FROM data"
    }) == True
