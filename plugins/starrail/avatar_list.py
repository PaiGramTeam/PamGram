import asyncio
import math
from typing import List, Optional, TYPE_CHECKING, Dict, Union, Tuple, Any

from arkowrapper import ArkoWrapper
from pydantic import BaseModel
from telegram.constants import ChatAction
from telegram.ext import filters

from core.dependence.assets import AssetsService, AssetsCouldNotFound
from core.plugin import Plugin, handler
from core.services.cookies import CookiesService
from core.services.template.models import FileType
from core.services.template.services import TemplateService
from core.services.wiki.services import WikiService
from gram_core.services.template.models import RenderGroupResult
from plugins.tools.genshin import GenshinHelper, CharacterDetails
from plugins.tools.head_icon import HeadIconService
from plugins.tools.phone_theme import PhoneThemeService
from utils.log import logger
from utils.uid import mask_number

if TYPE_CHECKING:
    from simnet import StarRailClient
    from simnet.models.starrail.calculator import StarrailCalculatorCharacterDetails
    from simnet.models.starrail.chronicle.characters import StarRailDetailCharacter
    from telegram.ext import ContextTypes
    from telegram import Update
    from gram_core.services.template.models import RenderResult

MAX_AVATAR_COUNT = 40


class EquipmentData(BaseModel):
    id: int
    name: str
    level: int
    eidolon: int
    rarity: int
    icon: str


class SkillData(BaseModel):
    id: int
    level: int
    max_level: int


class AvatarData(BaseModel):
    id: int
    name: str
    level: int
    eidolon: int
    rarity: int
    icon: str = ""
    skills: List[SkillData]
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
        character_details: CharacterDetails = None,
        head_icon: HeadIconService = None,
        phone_theme: PhoneThemeService = None,
    ) -> None:
        self.cookies_service = cookies_service
        self.assets_service = assets_service
        self.template_service = template_service
        self.wiki_service = wiki_service
        self.helper = helper
        self.character_details = character_details
        self.head_icon = head_icon
        self.phone_theme = phone_theme

    async def get_avatar_data(
        self, character_id: int, client: "StarRailClient"
    ) -> Optional["StarrailCalculatorCharacterDetails"]:
        return await self.character_details.get_character_details(client, character_id)

    @staticmethod
    async def get_avatars_data(client: "StarRailClient") -> List["StarRailDetailCharacter"]:
        task_info_results = (await client.get_starrail_characters()).avatar_list

        return sorted(
            list(filter(lambda x: x, task_info_results)),
            key=lambda x: (
                x.level,
                x.rarity,
                sum([i.is_unlocked for i in x.ranks]),
            ),
            reverse=True,
        )

    def get_light_cone_star(self, name: str) -> int:
        light_cone = self.wiki_service.light_cone.get_by_name(name)
        return light_cone.rank if light_cone else 3

    async def get_avatars_details(
        self, characters: List["StarRailDetailCharacter"], client: "StarRailClient"
    ) -> Dict[int, "StarrailCalculatorCharacterDetails"]:
        async def _task(cid):
            return await self.get_avatar_data(cid, client)

        task_detail_results = await asyncio.gather(*[_task(character.id) for character in characters])
        return {character.id: detail for character, detail in zip(characters, task_detail_results)}

    @staticmethod
    def get_skill_data(character: Optional["StarrailCalculatorCharacterDetails"]) -> List[SkillData]:
        if not character:
            return [SkillData(id=i, level=1, max_level=10) for i in range(1, 5)]
        return [SkillData(id=skill.id, level=skill.cur_level, max_level=skill.max_level) for skill in character.skills]

    async def get_final_data(
        self, characters: List["StarRailDetailCharacter"], client: "StarRailClient"
    ) -> List[AvatarData]:
        details = await self.get_avatars_details(characters, client)
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
                detail = details.get(character.id)
                avatar = AvatarData(
                    id=character.id,
                    name=character.name,
                    level=character.level,
                    eidolon=sum([i.is_unlocked for i in character.ranks]),
                    rarity=character.rarity,
                    icon=self.assets_service.avatar.icon(character.id, character.name).as_uri(),
                    skills=self.get_skill_data(detail),
                    equipment=equip,
                )
                data.append(avatar)
            except AssetsCouldNotFound as e:
                logger.warning("未找到角色 %s[%s] 的资源: %s", character.name, character.id, e)
        return data

    async def avatar_list_render(
        self,
        base_render_data: Dict,
        avatar_datas: List[AvatarData],
        only_one_page: bool,
    ) -> Union[Tuple[Any], List["RenderResult"], None]:
        def render_task(start_id: int, c: List[AvatarData]):
            _render_data = {
                "avatar_datas": c,  # 角色数据
                "start_id": start_id,  # 开始序号
            }
            _render_data.update(base_render_data)
            return self.template_service.render(
                "starrail/avatar_list/main.html",
                _render_data,
                viewport={"width": 1040, "height": 500},
                full_page=True,
                query_selector=".container",
                file_type=FileType.PHOTO,
                ttl=30 * 24 * 60 * 60,
            )

        if only_one_page:
            return [await render_task(0, avatar_datas)]
        image_count = len(avatar_datas)
        while image_count > MAX_AVATAR_COUNT:
            image_count /= 2
        image_count = math.ceil(image_count)
        avatar_datas_group = [avatar_datas[i : i + image_count] for i in range(0, len(avatar_datas), image_count)]
        tasks = [render_task(i * image_count, c) for i, c in enumerate(avatar_datas_group)]
        return await asyncio.gather(*tasks)

    @handler.command("avatars", cookie=True, block=False)
    @handler.message(filters.Regex(r"^(全部)?练度统计$"), cookie=True, block=False)
    async def avatar_list(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE"):
        user_id = await self.get_real_user_id(update)
        message = update.effective_message
        all_avatars = "全部" in message.text or "all" in message.text  # 是否发送全部角色
        self.log_user(update, logger.info, "[bold]练度统计[/bold]: all=%s", all_avatars, extra={"markup": True})
        await message.reply_chat_action(ChatAction.TYPING)

        async with self.helper.genshin(user_id) as client:
            notice = await message.reply_text("彦卿需要收集整理数据，还请耐心等待哦~")
            self.add_delete_message_job(notice, delay=60)
            characters: List["StarRailDetailCharacter"] = await self.get_avatars_data(client)
            record_card = await client.get_record_card()
            nickname = record_card.nickname
            has_more = (not all_avatars) and len(characters) > MAX_AVATAR_COUNT
            if has_more:
                characters = characters[:MAX_AVATAR_COUNT]
            avatar_datas = await self.get_final_data(characters, client)

        base_render_data = {
            "uid": mask_number(client.player_id),  # 玩家uid
            "nickname": nickname,  # 玩家昵称
            "has_more": has_more,  # 是否显示了全部角色
            "avatar": (await self.head_icon.get_head_icon(client.player_id)).as_uri(),
            "background": (await self.phone_theme.get_phone_theme(client.player_id)).as_uri(),
        }

        images = await self.avatar_list_render(base_render_data, avatar_datas, has_more)

        for group in ArkoWrapper(images).group(10):  # 每 10 张图片分一个组
            await RenderGroupResult(results=group).reply_media_group(message, write_timeout=60)

        self.log_user(
            update,
            logger.info,
            "[bold]练度统计[/bold]发送图片成功",
            extra={"markup": True},
        )
