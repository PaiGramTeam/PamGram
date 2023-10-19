from decimal import Decimal
from typing import List, Optional, Union, Dict

import ujson
from httpx import AsyncClient, TimeoutException
from pydantic import BaseModel

from core.config import config
from modules.playercards.fight_prop import EquipmentsStats
from modules.wiki.base import WikiModel
from modules.wiki.models.relic_affix import RelicAffixAll
from utils.enkanetwork import RedisCache
from modules.playercards.file import PlayerCardsFile


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
    subAffixList: Optional[List[SubAffix]]
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
    equipment: Optional[Equipment]
    level: int
    promotion: Optional[int] = 4
    rank: Optional[int] = 0
    relicList: Optional[List[Relic]]
    property: Optional[List[Property]]


class ChallengeInfo(BaseModel):
    scheduleGroupId: Optional[int]
    noneScheduleMaxLevel: Optional[int]
    scheduleMaxLevel: Optional[int]


class RecordInfo(BaseModel):
    achievementCount: Optional[int] = 0
    avatarCount: Optional[int] = 0
    challengeInfo: ChallengeInfo
    equipmentCount: Optional[int] = 0
    maxRogueChallengeScore: Optional[int] = 0


class PlayerBaseInfo(BaseModel):
    platform: Optional[str]
    friendCount: Optional[int]
    headIcon: Optional[int]
    isDisplayAvatar: bool
    level: int
    worldLevel: Optional[int]
    nickname: str
    recordInfo: RecordInfo
    signature: Optional[str]
    uid: int


class PlayerInfo(PlayerBaseInfo):
    avatarList: List[Avatar]


class PlayerCardsError(Exception):
    def __init__(self, msg):
        self.msg = msg


class PlayerCards:
    url = "https://api.mihomo.me/sr_info/"
    url2 = "https://api.mihomo.me/sr_info_parsed/"
    prop_url = f"{WikiModel.BASE_URL}relic_config.json"

    def __init__(self, redis):
        self.cache = RedisCache(redis.client, key="plugin:player_cards:fake_enka_network", ex=60)
        self.headers = {"User-Agent": config.enka_network_api_agent}
        self.client = AsyncClient()
        self.player_cards_file = PlayerCardsFile()
        self.init = False
        self.relic_datas_map: Dict[int, RelicAffixAll] = {}

    async def async_init(self):
        if self.init:
            return
        self.relic_datas_map.clear()
        req = await self.client.get(self.prop_url)
        data = req.json()
        for i in data:
            self.relic_datas_map[i["id"]] = RelicAffixAll(**i)
        self.init = True

    async def get_property(self, uid: str) -> Dict[int, List[Dict]]:
        final_data: Dict[int, List[Dict]] = {}
        try:
            user = await self.client.get(self.url2 + uid, timeout=30, headers=self.headers)
            if user.status_code != 200:
                raise PlayerCardsError("请求异常")
            data = ujson.loads(user.text)
            characters = data.get("characters", [])
            for character in characters:
                cid = int(character.get("id", 0))
                if not cid:
                    continue
                datas = []
                datas_map = {}
                for attr in character.get("attributes", []):
                    prop = Property(
                        name=attr["name"],
                        base=attr["value"],
                        percent=attr["percent"],
                    )
                    datas.append(prop)
                    datas_map[prop.name] = prop
                for attr in character.get("additions", []):
                    prop = datas_map.get(attr["name"])
                    if prop:
                        prop.addition = attr["value"]
                    else:
                        prop = Property(
                            name=attr["name"],
                            addition=attr["value"],
                            percent=attr["percent"],
                        )
                        datas.append(prop)
                        datas_map[prop.name] = prop
                final_data[cid] = [i.dict() for i in datas]
        except (TimeoutException, PlayerCardsError):
            pass
        return final_data

    async def update_data(self, uid: str) -> Union[PlayerInfo, str]:
        try:
            data = await self.cache.get(uid)
            if data is not None:
                return PlayerInfo.parse_obj(data)
            user = await self.client.get(self.url + uid, timeout=30, headers=self.headers)
            if user.status_code != 200:
                raise PlayerCardsError(f"请求异常，错误代码 {user.status_code}")
            data = ujson.loads(user.text)
            error_code = data.get("ErrCode", 0)
            if error_code:
                raise PlayerCardsError(f"请求异常，错误代码 {error_code}")
            data = data.get("detailInfo", {})
            props = await self.get_property(uid)
            data = await self.player_cards_file.merge_info(uid, data, props)
            await self.cache.set(uid, data)
            return PlayerInfo.parse_obj(data)
        except TimeoutException:
            error = "服务请求超时，请稍后重试"
        except PlayerCardsError as e:
            error = e.msg
        return error

    async def get_player_base_info(self, uid: int) -> PlayerBaseInfo:
        try:
            user = await self.client.get(f"{self.url}{uid}", timeout=30, headers=self.headers)
            if user.status_code != 200:
                raise PlayerCardsError(f"请求异常，错误代码 {user.status_code}")
            data = ujson.loads(user.text)
            error_code = data.get("ErrCode", 0)
            if error_code:
                raise PlayerCardsError(f"请求异常，错误代码 {error_code}")
            return PlayerBaseInfo.parse_obj(data["detailInfo"])
        except TimeoutException as e:
            raise PlayerCardsError("服务请求超时，请稍后重试") from e

    def get_affix_by_id(self, cid: int) -> RelicAffixAll:
        return self.relic_datas_map.get(cid)

    def get_set_by_id(self, cid: int) -> int:
        if affix := self.get_affix_by_id(cid):
            return affix.set_id
        return 101

    def get_affix(self, relic: Relic, main: bool = True, sub: bool = True) -> List[EquipmentsStats]:
        affix = self.get_affix_by_id(relic.tid)
        if not affix:
            return []
        main_affix = affix.main_affix[str(relic.mainAffixId)]
        datas = (
            [
                EquipmentsStats(
                    prop_id=main_affix.property,
                    prop_value=main_affix.get_value(relic.level),
                )
            ]
            if main
            else []
        )
        if not sub:
            return datas
        if relic.subAffixList:
            for sub_a in relic.subAffixList:
                sub_affix = affix.sub_affix[str(sub_a.affixId)]
                datas.append(
                    EquipmentsStats(
                        prop_id=sub_affix.property,
                        prop_value=sub_affix.get_value(sub_a.step, sub_a.cnt),
                    )
                )
        return datas
