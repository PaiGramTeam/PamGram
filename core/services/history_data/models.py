import enum

from pydantic import BaseModel
from simnet.models.starrail.chronicle.challenge import StarRailChallenge

from gram_core.services.history_data.models import HistoryData

__all__ = (
    "HistoryData",
    "HistoryDataTypeEnum",
    "HistoryDataAbyss",
)


class HistoryDataTypeEnum(int, enum.Enum):
    ABYSS = 0  # 混沌回忆


class HistoryDataAbyss(BaseModel):
    abyss_data: StarRailChallenge

    @classmethod
    def from_data(cls, data: HistoryData):
        return cls.parse_obj(data.data)
