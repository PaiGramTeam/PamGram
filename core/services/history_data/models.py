import enum

from pydantic import BaseModel
from simnet.models.starrail.chronicle.challenge import StarRailChallenge
from simnet.models.starrail.chronicle.challenge_story import StarRailChallengeStory, StarRailChallengeStoryGroup

from gram_core.services.history_data.models import HistoryData

__all__ = (
    "HistoryData",
    "HistoryDataTypeEnum",
    "HistoryDataAbyss",
    "HistoryDataChallengeStory",
)


class HistoryDataTypeEnum(int, enum.Enum):
    ABYSS = 0  # 混沌回忆
    CHALLENGE_STORY = 1  # 虚构叙事


class HistoryDataAbyss(BaseModel):
    abyss_data: StarRailChallenge

    @classmethod
    def from_data(cls, data: HistoryData) -> "HistoryDataAbyss":
        return cls.parse_obj(data.data)


class HistoryDataChallengeStory(BaseModel):
    story_data: StarRailChallengeStory
    group: StarRailChallengeStoryGroup

    @classmethod
    def from_data(cls, data: HistoryData) -> "HistoryDataChallengeStory":
        return cls.parse_obj(data.data)
