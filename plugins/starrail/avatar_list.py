from typing import List, Optional, TYPE_CHECKING

from pydantic import BaseModel
from simnet.models.starrail.chronicle.characters import StarRailDetailCharacter
from telegram.constants import ChatAction
from telegram.ext import filters

from core.dependence.assets import AssetsService, AssetsCouldNotFound
from core.plugin import Plugin, handler
from core.services.cookies import CookiesService
from core.services.template.models import FileType
from core.services.template.services import TemplateService
from core.services.wiki.services import WikiService
from plugins.tools.genshin import GenshinHelper
from utils.log import logger

if TYPE_CHECKING:
    from simnet import StarRailClient
    from telegram.ext import ContextTypes
    from telegram import Update


class EquipmentData(BaseModel):
    id: int
    name: str
    level: int
    eidolon: int
    rarity: int
    icon: str


class AvatarData(BaseModel):
    id: int
    name: str
    level: int
    eidolon: int
    rarity: int
    icon: str = ""
    equipment: Optional[EquipmentData] = None


class AvatarListPlugin(Plugin):
    """练度统计"""

    def __init__(
        self,
        cookies_service: CookiesService = None,
        assets_service: AssetsService = None,
        template_service: TemplateService = None,
        wiki_service: WikiService = None,
        helper: GenshinHelper = None,
    ) -> None:
        self.cookies_service = cookies_service
        self.assets_service = assets_service
        self.template_service = template_service
        self.wiki_service = wiki_service
        self.helper = helper

    @staticmethod
    async def get_avatars_data(client: "StarRailClient") -> List[StarRailDetailCharacter]:
        task_results = (await client.get_starrail_characters()).avatar_list
        return sorted(
            list(filter(lambda x: x, task_results)),
            key=lambda x: (
                x.level,
                x.rarity,
                sum([i.is_unlocked for i in x.ranks]),
            ),
            reverse=True,
        )

    def get_light_cone_star(self, name: str) -> int:
        light_cone = self.wiki_service.light_cone.get_by_name(name)
        return light_cone.rarity if light_cone else 3

    async def get_final_data(self, characters: List[StarRailDetailCharacter]) -> List[AvatarData]:
        data = []
        for character in characters:
            try:
                equip = (
                    EquipmentData(
                        id=character.equip.id,
                        name=character.equip.name,
                        level=character.equip.level,
                        eidolon=character.equip.rank,
                        rarity=self.get_light_cone_star(character.equip.name),
                        icon=self.assets_service.light_cone.icon(character.equip.id, character.equip.name).as_uri(),
                    )
                    if character.equip
                    else None
                )
                avatar = AvatarData(
                    id=character.id,
                    name=character.name,
                    level=character.level,
                    eidolon=sum([i.is_unlocked for i in character.ranks]),
                    rarity=character.rarity,
                    icon=self.assets_service.avatar.icon(character.id, character.name).as_uri(),
                    equipment=equip,
                )
                data.append(avatar)
            except AssetsCouldNotFound as e:
                logger.warning("未找到角色 %s[%s] 的资源: %s", character.name, character.id, e)
        return data

    @handler.command("avatars", block=False)
    @handler.message(filters.Regex(r"^(全部)?练度统计$"), block=False)
    async def avatar_list(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE"):
        user = update.effective_user
        message = update.effective_message
        all_avatars = "全部" in message.text or "all" in message.text  # 是否发送全部角色
        logger.info("用户 %s[%s] [bold]练度统计[/bold]: all=%s", user.full_name, user.id, all_avatars, extra={"markup": True})
        await message.reply_chat_action(ChatAction.TYPING)

        async with self.helper.genshin(user.id) as client:
            characters: List[StarRailDetailCharacter] = await self.get_avatars_data(client)
            record_card = await client.get_record_card()
            nickname = record_card.nickname

        has_more = (not all_avatars) and len(characters) > 20
        if has_more:
            characters = characters[:20]
        avatar_datas = await self.get_final_data(characters)

        render_data = {
            "uid": client.player_id,  # 玩家uid
            "nickname": nickname,  # 玩家昵称
            "avatar_datas": avatar_datas,  # 角色数据
            "has_more": has_more,  # 是否显示了全部角色
        }

        as_document = all_avatars and len(characters) > 20
        await message.reply_chat_action(ChatAction.UPLOAD_DOCUMENT if as_document else ChatAction.UPLOAD_PHOTO)
        image = await self.template_service.render(
            "starrail/avatar_list/main.html",
            render_data,
            viewport={"width": 1040, "height": 500},
            full_page=True,
            query_selector=".container",
            file_type=FileType.DOCUMENT if as_document else FileType.PHOTO,
            ttl=30 * 24 * 60 * 60,
        )
        if as_document:
            await image.reply_document(message, filename="练度统计.png")
        else:
            await image.reply_photo(message)
        logger.info(
            "用户 %s[%s] [bold]练度统计[/bold]发送%s成功",
            user.full_name,
            user.id,
            "文件" if all_avatars else "图片",
            extra={"markup": True},
        )
