from pathlib import Path
from typing import Optional

from core.dependence.assets import AssetsService, AssetsCouldNotFound
from core.services.players.services import PlayerInfoService
from gram_core.dependence.redisdb import RedisDB
from gram_core.plugin import Plugin
from utils.log import logger


class PhoneThemeService(Plugin):
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
        self.qname = "plugins:phone_theme"

    def get_default_phone_theme(self) -> Optional[Path]:
        try:
            return self.assets.phone_theme.icon(221000)
        except AssetsCouldNotFound as e:
            logger.warning(str(e))
            return None

    async def get_from_cache(self, player_id: int) -> Optional[int]:
        key = f"{self.qname}:{player_id}"
        data = await self.redis.get(key)
        if data is None:
            return None
        return int(data)

    async def set_to_cache(self, player_id: int, phone_theme: int) -> None:
        key = f"{self.qname}:{player_id}"
        await self.redis.set(key, phone_theme, ex=self.expire)

    async def get_from_sql(self, player_id: int) -> Optional[int]:
        player_info = await self.player_info_service.get_by_player_id(player_id)
        if player_info is None:
            return None
        return player_info.name_card

    async def get_phone_theme_id(self, player_id: int) -> Optional[int]:
        phone_theme = await self.get_from_cache(player_id)
        if phone_theme is not None:
            return phone_theme
        phone_theme = await self.get_from_sql(player_id)
        if phone_theme is not None:
            await self.set_to_cache(player_id, phone_theme)
            return phone_theme
        return None

    async def get_phone_theme(self, player_id: int):
        try:
            phone_theme = await self.get_phone_theme_id(player_id)
            return self.assets.phone_theme.icon(phone_theme)
        except AssetsCouldNotFound as e:
            logger.warning(str(e))
            return self.get_default_phone_theme()
