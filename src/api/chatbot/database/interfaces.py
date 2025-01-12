from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseRepository(ABC):
    @abstractmethod
    def save(self, data: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def fetch(self, query: str, parameters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        pass
