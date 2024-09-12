from typing import Optional

from core.dependence.assets import AssetsService
from core.services.players.services import PlayerInfoService
from gram_core.dependence.redisdb import RedisDB
from gram_core.plugin import Plugin


class NickNameService(Plugin):
    def __init__(
        self,
        player_info_service: PlayerInfoService,
        asset_service: AssetsService,
        redis: RedisDB,
    ) -> None:
        self.player_info_service = player_info_service
        self.assets = asset_service
        self.redis = redis.client
        self.expire = 60 * 60
        self.qname = "plugins:nick_name"

    @staticmethod
    def get_default_nickname() -> str:
        return "Unknown"

    async def get_from_cache(self, player_id: int) -> Optional[str]:
        key = f"{self.qname}:{player_id}"
        data = await self.redis.get(key)
        if data is None:
            return None
        return str(data, encoding="utf-8")

    async def set_to_cache(self, player_id: int, nick_name: str) -> None:
        key = f"{self.qname}:{player_id}"
        await self.redis.set(key, nick_name, ex=self.expire)

    async def get_from_sql(self, player_id: int) -> Optional[str]:
        player_info = await self.player_info_service.get_by_player_id(player_id)
        if player_info is None:
            return None
        return player_info.nickname

    async def get_from_mihomo(self, player_id: int) -> Optional[str]:
        player_info = await self.player_info_service.get_player_info_from_mihomo(player_id)
        if player_info is None:
            return None
        return player_info.nickname

    async def get_nick_name(self, player_id: int) -> Optional[str]:
        nickname = await self.get_from_cache(player_id)
        if nickname is not None:
            return nickname
        nickname = await self.get_from_sql(player_id)
        if nickname is not None:
            await self.set_to_cache(player_id, nickname)
            return nickname
        nickname = await self.get_from_mihomo(player_id)
        if nickname is not None:
            await self.set_to_cache(player_id, nickname)
            return nickname
        return None
