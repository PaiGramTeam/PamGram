from typing import List, Optional, Union, Dict

import ujson
from httpx import AsyncClient, TimeoutException
from pydantic import BaseModel

from modules.playercards.fight_prop import EquipmentsStats
from modules.wiki.base import WikiModel
from modules.wiki.models.relic_affix import RelicAffixAll
from utils.enkanetwork import RedisCache
from modules.playercards.file import PlayerCardsFile


class Behavior(BaseModel):
    BehaviorID: int
    Level: int


class Equipment(BaseModel):
    ID: Optional[int] = 0
    Level: Optional[int] = 0
    Promotion: Optional[int] = 3
    """星级"""
    Rank: Optional[int] = 0
    """叠影"""


class SubAffix(BaseModel):
    Cnt: Optional[int] = 1
    Step: Optional[int] = 0
    SubAffixID: int


class Relic(BaseModel):
    ID: int
    Level: Optional[int] = 0
    MainAffixID: int
    RelicSubAffix: Optional[List[SubAffix]]
    Type: int


class Avatar(BaseModel):
    AvatarID: int
    BehaviorList: List[Behavior]
    EquipmentID: Optional[Equipment]
    Level: int
    Promotion: Optional[int] = 4
    Rank: Optional[int] = 0
    RelicList: Optional[List[Relic]]


class ChallengeData(BaseModel):
    MazeGroupID: Optional[int]
    MazeGroupIndex: Optional[int]
    PreMazeGroupIndex: Optional[int]


class PlayerSpaceInfo(BaseModel):
    AchievementCount: int
    AvatarCount: int
    ChallengeData: ChallengeData
    LightConeCount: int
    PassAreaProgress: int


class PlayerInfo(BaseModel):
    Birthday: Optional[int]
    CurFriendCount: Optional[int]
    AvatarList: List[Avatar]
    HeadIconID: Optional[int]
    IsDisplayAvatarList: bool
    Level: int
    NickName: str
    PlayerSpaceInfo: PlayerSpaceInfo
    Signature: Optional[str]
    UID: int
    WorldLevel: Optional[int]


class PlayerCardsError(Exception):
    def __init__(self, msg):
        self.msg = msg


class PlayerCards:
    url = "http://127.0.0.1:8080/"
    prop_url = f"{WikiModel.BASE_URL}relic_config.json"

    def __init__(self, redis):
        self.cache = RedisCache(redis.client, key="plugin:player_cards:fake_enka_network", ex=60)
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

    async def update_data(self, uid: str) -> Union[PlayerInfo, str]:
        try:
            data = await self.cache.get(uid)
            if data is not None:
                return PlayerInfo.parse_obj(data)
            user = await self.client.get(self.url + uid, timeout=15)
            if user.status_code != 200:
                raise PlayerCardsError(f"请求异常，错误代码 {user.status_code}")
            data = ujson.loads(user.text)
            error_code = data.get("ErrCode", 0)
            if error_code:
                raise PlayerCardsError(f"请求异常，错误代码 {error_code}")
            data = data.get("PlayerDetailInfo", {})
            data = await self.player_cards_file.merge_info(uid, data)
            await self.cache.set(uid, data)
            return PlayerInfo.parse_obj(data)
        except TimeoutException:
            error = "服务请求超时，请稍后重试"
        except PlayerCardsError as e:
            error = e.msg
        return error

    def get_affix_by_id(self, cid: int) -> RelicAffixAll:
        return self.relic_datas_map.get(cid, None)

    def get_set_by_id(self, cid: int) -> int:
        if affix := self.get_affix_by_id(cid):
            return affix.set_id
        return 101

    def get_affix(self, relic: Relic, main: bool = True, sub: bool = True) -> List[EquipmentsStats]:
        affix = self.get_affix_by_id(relic.ID)
        if not affix:
            return []
        main_affix = affix.main_affix[str(relic.MainAffixID)]
        datas = (
            [
                EquipmentsStats(
                    prop_id=main_affix.property,
                    prop_value=main_affix.get_value(relic.Level),
                )
            ]
            if main
            else []
        )
        if not sub:
            return datas
        if relic.RelicSubAffix:
            for sub in relic.RelicSubAffix:
                sub_affix = affix.sub_affix[str(sub.SubAffixID)]
                datas.append(
                    EquipmentsStats(
                        prop_id=sub_affix.property,
                        prop_value=sub_affix.get_value(sub.Step, sub.Cnt),
                    )
                )
        return datas
