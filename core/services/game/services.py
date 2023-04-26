from core.base_service import BaseService
from core.services.game.cache import GameCacheForStrategy

__all__ = "GameStrategyService"


class GameStrategyService(BaseService):
    def __init__(self, cache: GameCacheForStrategy):
        self._cache = cache

    async def get_strategy_cache(self, character_name: str) -> str:
        cache = await self._cache.get_file(character_name)
        if cache is not None:
            return cache

    async def set_strategy_cache(self, character_name: str, file: str) -> None:
        await self._cache.set_file(character_name, file)
