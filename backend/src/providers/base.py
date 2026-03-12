from abc import ABC, abstractmethod
from typing import Iterable

class BaseDataProvider(ABC):
    @abstractmethod
    def load(self):
        raise NotImplementedError

    @abstractmethod
    def get_matches(self, formats: Iterable[str] | None = None):
        raise NotImplementedError

    @abstractmethod
    def get_player_events(self, player_name: str):
        raise NotImplementedError
