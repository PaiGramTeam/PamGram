import enum

from pydantic import BaseModel
from simnet.models.starrail.chronicle.challenge import StarRailChallenge
from simnet.models.starrail.chronicle.challenge_boss import StarRailChallengeBoss, StarRailChallengeBossGroup
from simnet.models.starrail.chronicle.challenge_peak import StarRailChallengePeak, StarRailChallengePeakRecord
from simnet.models.starrail.chronicle.challenge_story import StarRailChallengeStory, StarRailChallengeStoryGroup
from simnet.models.starrail.diary import StarRailDiary

from gram_core.services.history_data.models import HistoryData

__all__ = (
    "HistoryData",
    "HistoryDataTypeEnum",
    "HistoryDataAbyss",
    "HistoryDataChallengeStory",
    "HistoryDataChallengeBoss",
    "HistoryDataLedger",
    "HistoryDataChallengePeak",
)


class HistoryDataTypeEnum(int, enum.Enum):
    ABYSS = 0  # 混沌回忆
    CHALLENGE_STORY = 1  # 虚构叙事
    LEDGER = 2  # 开拓月历
    CHALLENGE_BOSS = 3  # 末日幻影
    CHALLENGE_PEAK = 4  # 异相仲裁


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


class HistoryDataChallengeBoss(BaseModel):
    boss_data: StarRailChallengeBoss
    group: StarRailChallengeBossGroup

    @classmethod
    def from_data(cls, data: HistoryData) -> "HistoryDataChallengeBoss":
        return cls.parse_obj(data.data)


class HistoryDataLedger(BaseModel):
    diary_data: StarRailDiary

    @classmethod
    def from_data(cls, data: HistoryData) -> "HistoryDataLedger":
        return cls.parse_obj(data.data)


class HistoryDataChallengePeak(BaseModel):
    peak_data: StarRailChallengePeak
    record: StarRailChallengePeakRecord

    @classmethod
    def from_data(cls, data: HistoryData) -> "HistoryDataChallengePeak":
        return cls.parse_obj(data.data)
