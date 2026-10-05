from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class DataConnector(ABC):
    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> bool:
        pass
        
    @abstractmethod
    def fetch(self, config: Dict[str, Any], checkpoint: Optional[Dict[str, Any]] = None) -> Any:
        # Should return raw bytes or an iterator of chunks/rows
        pass
        
    @abstractmethod
    def get_connector_type(self) -> str:
        pass
