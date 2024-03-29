from pathlib import Path
from typing import Optional

from core.dependence.assets import AssetsService, AssetsCouldNotFound
from core.services.players.services import PlayerInfoService
from gram_core.dependence.redisdb import RedisDB
from gram_core.plugin import Plugin
from utils.log import logger


class HeadIconService(Plugin):
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
        self.qname = "plugins:head_icon"

    def get_default_head_icon(self) -> Optional[Path]:
        try:
            return self.assets.head_icon.icon(200001)
        except AssetsCouldNotFound as e:
            logger.warning(str(e))
            return None

    async def get_from_cache(self, player_id: int) -> Optional[int]:
        key = f"{self.qname}:{player_id}"
        data = await self.redis.get(key)
        if data is None:
            return None
        return int(data)

    async def set_to_cache(self, player_id: int, head_icon: int) -> None:
        key = f"{self.qname}:{player_id}"
        await self.redis.set(key, head_icon, ex=self.expire)

    async def get_from_sql(self, player_id: int) -> Optional[int]:
        player_info = await self.player_info_service.get_by_player_id(player_id)
        if player_info is None:
            return None
        return player_info.hand_image

    async def get_from_mihomo(self, player_id: int) -> Optional[int]:
        player_info = await self.player_info_service.get_player_info_from_mihomo(player_id)
        if player_info is None:
            return None
        return player_info.headIcon

    async def get_head_icon_id(self, player_id: int) -> Optional[int]:
        head_icon = await self.get_from_cache(player_id)
        if head_icon is not None:
            return head_icon
        head_icon = await self.get_from_sql(player_id)
        if head_icon is not None:
            await self.set_to_cache(player_id, head_icon)
            return head_icon
        head_icon = await self.get_from_mihomo(player_id)
        if head_icon is not None:
            await self.set_to_cache(player_id, head_icon)
            return head_icon
        return None

    async def get_head_icon(self, player_id: int):
        try:
            head_icon = await self.get_head_icon_id(player_id)
            return self.assets.head_icon.icon(head_icon)
        except AssetsCouldNotFound as e:
            logger.warning(str(e))
            return self.get_default_head_icon()
