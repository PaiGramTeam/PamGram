from typing import List, Union, TYPE_CHECKING

import ujson
from httpx import AsyncClient, TimeoutException

from core.config import config
from core.dependence.redisdb import RedisDB
from core.services.wiki.services import WikiService
from gram_core.base_service import BaseService
from modules.playercards.fight_prop import EquipmentsStats
from modules.playercards.file import PlayerCardsFile
from modules.playercards.models import PlayerInfo, PlayerBaseInfo, Relic
from modules.playercards.parse_data import MihomoApiDataParser
from modules.playercards.to_mihomo import SimnetApiDataParser
from modules.wiki.models.relic_affix import RelicAffixAll
from utils.enkanetwork import RedisCache

if TYPE_CHECKING:
    from modules.wiki.mihomo_map import MihomoMap


class PlayerCardsError(Exception):
    def __init__(self, msg):
        self.msg = msg


class PlayerCards(MihomoApiDataParser, SimnetApiDataParser, BaseService):

    url = "https://api.mihomo.me/sr_info/"

    def __init__(self, redis: RedisDB, wiki: WikiService):
        self.cache = RedisCache(redis.client, key="plugin:player_cards:fake_enka_network", ex=60)
        self.headers = {"User-Agent": config.enka_network_api_agent}
        self.client = AsyncClient()
        self.player_cards_file = PlayerCardsFile()
        self.mihomo_map = wiki.mihomo_map

    def get_mihomo_map(self) -> "MihomoMap":
        return self.mihomo_map

    async def update_data(self, uid: str) -> Union[PlayerInfo, str]:
        try:
            data = await self.cache.get(uid)
            if data is not None:
                return PlayerInfo.model_validate(data)
            user = await self.client.get(self.url + uid, timeout=30, headers=self.headers)
            if user.status_code != 200:
                raise PlayerCardsError(f"请求异常，错误代码 {user.status_code}")
            data = ujson.loads(user.text)
            error_code = data.get("ErrCode", 0)
            if error_code:
                raise PlayerCardsError(f"请求异常，错误代码 {error_code}")
            data = data.get("detailInfo", {})
            props = await self.get_property(data)
            data = await self.player_cards_file.merge_info(uid, data, props)
            await self.cache.set(uid, data)
            return PlayerInfo.model_validate(data)
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
            return PlayerBaseInfo.model_validate(data["detailInfo"])
        except TimeoutException as e:
            raise PlayerCardsError("服务请求超时，请稍后重试") from e

    def get_affix_by_id(self, cid: int) -> RelicAffixAll:
        return self.mihomo_map.get_affix_by_id(cid)

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
