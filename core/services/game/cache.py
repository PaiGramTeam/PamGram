from typing import List

from core.base_service import BaseService
from core.dependence.redisdb import RedisDB

__all__ = [
    "GameCache",
    "GameCacheForAvatar",
    "GameCacheForStrategy",
    "GameCacheForMaterial",
    "GameCacheForLightCone",
    "GameCacheForRelics",
]


class GameCache:
    qname: str

    def __init__(self, redis: RedisDB, ttl: int = 3600):
        self.client = redis.client
        self.ttl = ttl

    async def get_url_list(self, character_name: str):
        qname = f"{self.qname}:{character_name}"
        return [str(str_data, encoding="utf-8") for str_data in await self.client.lrange(qname, 0, -1)][::-1]

    async def set_url_list(self, character_name: str, str_list: List[str]):
        qname = f"{self.qname}:{character_name}"
        await self.client.ltrim(qname, 1, 0)
        await self.client.lpush(qname, *str_list)
        await self.client.expire(qname, self.ttl)
        return await self.client.llen(qname)

    async def get_file(self, character_name: str):
        qname = f"{self.qname}:{character_name}"
        return await self.client.get(qname)

    async def set_file(self, character_name: str, file: str):
        qname = f"{self.qname}:{character_name}"
        await self.client.set(qname, file)
        await self.client.expire(qname, self.ttl)


class GameCacheForAvatar(BaseService.Component, GameCache):
    qname = "game:avatar"


class GameCacheForStrategy(BaseService.Component, GameCache):
    qname = "game:strategy"


class GameCacheForMaterial(BaseService.Component, GameCache):
    qname = "game:material"


class GameCacheForLightCone(BaseService.Component, GameCache):
    qname = "game:lightcone"


class GameCacheForRelics(BaseService.Component, GameCache):
    qname = "game:relics"
