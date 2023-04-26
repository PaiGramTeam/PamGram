from typing import NoReturn

from core.base_service import BaseService
from modules.wiki.character import Character
from modules.wiki.material import Material
from modules.wiki.monster import Monster
from modules.wiki.relic import Relic
from modules.wiki.light_cone import LightCone
from modules.wiki.raider import Raider
from utils.log import logger

__all__ = ["WikiService"]


class WikiService(BaseService):
    def __init__(self):
        self.character = Character()
        self.material = Material()
        self.monster = Monster()
        self.relic = Relic()
        self.light_cone = LightCone()
        self.raider = Raider()

    async def initialize(self) -> None:
        logger.info("正在加载 Wiki 数据")
        await self.character.read()
        await self.material.read()
        await self.monster.read()
        await self.relic.read()
        await self.light_cone.read()
        await self.raider.read()
        logger.info("加载 Wiki 数据完成")

    async def refresh_wiki(self) -> NoReturn:
        logger.info("正在重新获取Wiki")
        logger.info("正在重新获取角色信息")
        await self.character.refresh()
        logger.info("正在重新获取材料信息")
        await self.material.refresh()
        logger.info("正在重新获取敌对生物信息")
        await self.monster.refresh()
        logger.info("正在重新获取遗器信息")
        await self.relic.refresh()
        logger.info("正在重新获取光锥信息")
        await self.light_cone.refresh()
        logger.info("正在重新获取攻略信息")
        await self.raider.refresh()
        logger.info("刷新成功")
