from datetime import datetime, timedelta
from typing import List, Optional

from core.base_service import BaseService
from core.basemodel import RegionEnum
from core.dependence.redisdb import RedisDB
from core.services.players.models import PlayersDataBase as Player, PlayerInfoSQLModel, PlayerInfo
from core.services.players.repositories import PlayersRepository, PlayerInfoRepository
from modules.apihelper.client.components.player_cards import PlayerCards, PlayerBaseInfo
from utils.log import logger

__all__ = ("PlayersService", "PlayerInfoService")


class PlayersService(BaseService):
    def __init__(self, players_repository: PlayersRepository) -> None:
        self._repository = players_repository

    async def get(
        self,
        user_id: int,
        player_id: Optional[int] = None,
        account_id: Optional[int] = None,
        region: Optional[RegionEnum] = None,
        is_chosen: Optional[bool] = None,
    ) -> Optional[Player]:
        return await self._repository.get(user_id, player_id, account_id, region, is_chosen)

    async def get_player(self, user_id: int, region: Optional[RegionEnum] = None) -> Optional[Player]:
        return await self._repository.get(user_id, region=region, is_chosen=True)

    async def add(self, player: Player) -> None:
        await self._repository.add(player)

    async def update(self, player: Player) -> None:
        await self._repository.update(player)

    async def get_all_by_user_id(self, user_id: int) -> List[Player]:
        return await self._repository.get_all_by_user_id(user_id)

    async def remove_all_by_user_id(self, user_id: int):
        players = await self._repository.get_all_by_user_id(user_id)
        for player in players:
            await self._repository.delete(player)

    async def delete(self, player: Player):
        await self._repository.delete(player)


class PlayerInfoService(BaseService):
    def __init__(self, redis: RedisDB, players_info_repository: PlayerInfoRepository):
        self.cache = redis.client
        self._players_info_repository = players_info_repository
        self.client = PlayerCards(redis)
        self.qname = "players_info"

    async def get_form_cache(self, player: Player):
        qname = f"{self.qname}:{player.user_id}:{player.player_id}"
        data = await self.cache.get(qname)
        if data is None:
            return None
        json_data = str(data, encoding="utf-8")
        return PlayerInfo.parse_raw(json_data)

    async def set_form_cache(self, player: PlayerInfo):
        qname = f"{self.qname}:{player.user_id}:{player.player_id}"
        await self.cache.set(qname, player.json(), ex=60)

    async def get_player_info_from_mihomo(self, player_id: int) -> Optional[PlayerBaseInfo]:
        try:
            response = await self.client.get_player_base_info(player_id)
            return response
        except Exception as exc:
            logger.error("Mihomo 请求失败: %s", exc_info=exc)
        return None

    async def get(self, player: Player) -> Optional[PlayerInfo]:
        player_info = await self.get_form_cache(player)
        if player_info is not None:
            return player_info
        player_info = await self._players_info_repository.get(player.user_id, player.player_id)
        if player_info is None:
            player_info_mihomo = await self.get_player_info_from_mihomo(player.player_id)
            if player_info_mihomo is None:
                return None
            player_info = PlayerInfo(
                user_id=player.user_id,
                player_id=player.player_id,
                nickname=player_info_mihomo.nickname,
                signature=player_info_mihomo.signature,
                name_card=None,
                hand_image=player_info_mihomo.headIcon,
                create_time=datetime.now(),
                last_save_time=datetime.now(),
                is_update=True,
            )
            await self._players_info_repository.add(PlayerInfoSQLModel.from_orm(player_info))
            await self.set_form_cache(player_info)
            return player_info
        if player_info.is_update:
            expiration_time = datetime.now() - timedelta(days=7)
            if player_info.last_save_time is None or player_info.last_save_time <= expiration_time:
                player_info_mihomo = await self.get_player_info_from_mihomo(player.player_id)
                if player_info_mihomo is None:
                    player_info.last_save_time = datetime.now()
                    await self._players_info_repository.update(player_info)
                    await self.set_form_cache(player_info)
                    return player_info
                player_info.nickname = player_info_mihomo.nickname
                player_info.name_card = None
                player_info.signature = player_info_mihomo.signature
                player_info.hand_image = player_info_mihomo.headIcon
                player_info.nickname = player_info_mihomo.nickname
                player_info.last_save_time = datetime.now()
                await self._players_info_repository.update(player_info)
        await self.set_form_cache(player_info)
        return player_info

    async def update_from_mihomo(self, player: Player) -> bool:
        player_info = await self._players_info_repository.get(player.user_id, player.player_id)
        if player_info is not None:
            player_info_mihomo = await self.get_player_info_from_mihomo(player.player_id)
            if player_info_mihomo is None:
                return False
            player_info.nickname = player_info_mihomo.nickname
            player_info.name_card = None
            player_info.signature = player_info_mihomo.signature
            player_info.hand_image = player_info_mihomo.headIcon
            player_info.nickname = player_info_mihomo.nickname
            player_info.last_save_time = datetime.now()
            await self._players_info_repository.update(player_info)
            return True
        return False

    async def add_from_mihomo(self, player: Player) -> bool:
        player_info = await self._players_info_repository.get(player.user_id, player.player_id)
        if player_info is None:
            player_info_enka = await self.get_player_info_from_mihomo(player.player_id)
            if player_info_enka is None:
                return False
            player_info = PlayerInfoSQLModel(
                user_id=player.user_id,
                player_id=player.player_id,
                nickname=player_info_enka.nickname,
                signature=player_info_enka.signature,
                name_card=None,
                hand_image=player_info_enka.headIcon,
                create_time=datetime.now(),
                last_save_time=datetime.now(),
                is_update=True,
            )
            await self._players_info_repository.add(player_info)
            return True
        return False

    async def get_form_sql(self, player: Player):
        return await self._players_info_repository.get(player.user_id, player.player_id)

    async def delete_form_player(self, player: Player):
        await self._players_info_repository.delete_by_id(user_id=player.user_id, player_id=player.player_id)

    async def add(self, player_info: PlayerInfo):
        await self._players_info_repository.add(PlayerInfoSQLModel.from_orm(player_info))

    async def delete(self, player_info: PlayerInfoSQLModel):
        await self._players_info_repository.delete(player_info)
