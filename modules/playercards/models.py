from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel


class SkillTreePoint(BaseModel):
    pointId: int
    level: int


class Equipment(BaseModel):
    tid: Optional[int] = 0
    level: Optional[int] = 0
    promotion: Optional[int] = 3
    """星级"""
    rank: Optional[int] = 0
    """叠影"""


class SubAffix(BaseModel):
    cnt: Optional[int] = 1
    step: Optional[int] = 0
    affixId: int


class Relic(BaseModel):
    tid: int
    level: Optional[int] = 0
    mainAffixId: int
    subAffixList: Optional[List[SubAffix]] = None
    type: int


class Property(BaseModel):
    name: str
    base: float = 0.0
    addition: float = 0.0
    percent: bool

    @property
    def total(self):
        total_num = (Decimal(self.base) + Decimal(self.addition)) * (Decimal(100.0) if self.percent else Decimal(1.0))
        total_num = round(total_num, 2)
        return f"{total_num}{'%' if self.percent else ''}"


class Avatar(BaseModel):
    avatarId: int
    skillTreeList: List[SkillTreePoint]
    equipment: Optional[Equipment] = None
    level: int
    promotion: Optional[int] = 4
    rank: Optional[int] = 0
    relicList: Optional[List[Relic]] = None
    property: Optional[List[Property]] = None


class RecordInfo(BaseModel):
    achievementCount: Optional[int] = 0
    avatarCount: Optional[int] = 0
    bookCount: Optional[int] = 0
    equipmentCount: Optional[int] = 0
    maxRogueChallengeScore: Optional[int] = 0
    musicCount: Optional[int] = 0
    relicCount: Optional[int] = 0


class PlayerBaseInfo(BaseModel):
    platform: Optional[str] = None
    friendCount: Optional[int] = None
    headIcon: Optional[int] = None
    isDisplayAvatar: bool
    level: int
    worldLevel: Optional[int] = None
    nickname: str
    recordInfo: RecordInfo
    signature: Optional[str] = None
    uid: int


class PlayerInfo(PlayerBaseInfo):
    avatarList: List[Avatar]


class PlayerInfoRaw(PlayerBaseInfo):
    avatarDetailList: Optional[List[Avatar]] = None
    assistAvatarList: Optional[List[Avatar]] = None
