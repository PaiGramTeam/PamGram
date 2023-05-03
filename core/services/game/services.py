from core.base_service import BaseService
from core.services.game.cache import GameCacheForStrategy, GameCacheForMaterial, GameCacheForLightCone

__all__ = "GameCacheService"


class GameCacheService(BaseService):
    def __init__(
        self,
        strategy_cache: GameCacheForStrategy,
        material_cache: GameCacheForMaterial,
        light_cone_cache: GameCacheForLightCone,
    ):
        self.strategy_cache = strategy_cache
        self.material_cache = material_cache
        self.light_cone_cache = light_cone_cache

    async def get_strategy_cache(self, character_name: str) -> str:
        cache = await self.strategy_cache.get_file(character_name)
        if cache is not None:
            return cache.decode("utf-8")

    async def set_strategy_cache(self, character_name: str, file: str) -> None:
        await self.strategy_cache.set_file(character_name, file)

    async def get_material_cache(self, character_name: str) -> str:
        cache = await self.material_cache.get_file(character_name)
        if cache is not None:
            return cache.decode("utf-8")

    async def set_material_cache(self, character_name: str, file: str) -> None:
        await self.material_cache.set_file(character_name, file)

    async def get_light_cone_cache(self, light_cone_name: str) -> str:
        cache = await self.light_cone_cache.get_file(light_cone_name)
        if cache is not None:
            return cache.decode("utf-8")

    async def set_light_cone_cache(self, light_cone_name: str, file: str) -> None:
        await self.light_cone_cache.set_file(light_cone_name, file)
