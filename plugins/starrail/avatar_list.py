from typing import List, Optional, TYPE_CHECKING

from genshin import Client, InvalidCookies, Game
from genshin.models.starrail.chronicle import StarRailDetailCharacter
from pydantic import BaseModel
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction, ParseMode
from telegram.ext import filters
from telegram.helpers import create_deep_linked_url

from core.dependence.assets import AssetsService, AssetsCouldNotFound
from core.plugin import Plugin, handler
from core.services.cookies import CookiesService
from core.services.template.models import FileType
from core.services.template.services import TemplateService
from plugins.tools.genshin import CookiesNotFoundError, GenshinHelper, PlayerNotFoundError
from utils.log import logger

if TYPE_CHECKING:
    from telegram.ext import ContextTypes
    from telegram import Update


class EquipmentData(BaseModel):
    id: int
    name: str
    level: int
    eidolon: int
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
        helper: GenshinHelper = None,
    ) -> None:
        self.cookies_service = cookies_service
        self.assets_service = assets_service
        self.template_service = template_service
        self.helper = helper

    async def get_user_client(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> Optional[Client]:
        message = update.effective_message
        user = update.effective_user
        try:
            return await self.helper.get_genshin_client(user.id)
        except PlayerNotFoundError:  # 若未找到账号
            buttons = [[InlineKeyboardButton("点我绑定账号", url=create_deep_linked_url(context.bot.username, "set_cookie"))]]
            if filters.ChatType.GROUPS.filter(message):
                reply_message = await message.reply_text(
                    "未查询到您所绑定的账号信息，请先私聊彦卿绑定账号", reply_markup=InlineKeyboardMarkup(buttons)
                )
                self.add_delete_message_job(reply_message, delay=30)
                self.add_delete_message_job(message, delay=30)
            else:
                await message.reply_text("未查询到您所绑定的账号信息，请先绑定账号", reply_markup=InlineKeyboardMarkup(buttons))
        except CookiesNotFoundError:
            buttons = [[InlineKeyboardButton("点我绑定账号", url=create_deep_linked_url(context.bot.username, "set_cookie"))]]
            if filters.ChatType.GROUPS.filter(message):
                reply_message = await message.reply_text(
                    "此功能需要绑定<code>cookie</code>后使用，请先私聊彦卿绑定账号",
                    reply_markup=InlineKeyboardMarkup(buttons),
                    parse_mode=ParseMode.HTML,
                )
                self.add_delete_message_job(reply_message, delay=30)
                self.add_delete_message_job(message, delay=30)
            else:
                await message.reply_text(
                    "此功能需要绑定<code>cookie</code>后使用，请先私聊彦卿进行绑定",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(buttons),
                )

    @staticmethod
    async def get_avatars_data(client: Client) -> List[StarRailDetailCharacter]:
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

    async def get_final_data(self, characters: List[StarRailDetailCharacter]) -> List[AvatarData]:
        data = []
        for character in characters:
            try:
                equip = EquipmentData(
                    id=character.equip.id,
                    name=character.equip.name,
                    level=character.equip.level,
                    eidolon=character.equip.rank,
                    icon=self.assets_service.light_cone.icon(character.equip.id, character.equip.name).as_uri(),
                ) if character.equip else None
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
    async def avatar_list(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        user = update.effective_user
        message = update.effective_message
        args = [i.lower() for i in context.match.groups() if i]
        all_avatars = "全部" in args or "all" in message.text  # 是否发送全部角色
        logger.info("用户 %s[%s] [bold]练度统计[/bold]: all=%s", user.full_name, user.id, all_avatars, extra={"markup": True})
        client = await self.get_user_client(update, context)
        if not client:
            return
        await message.reply_chat_action(ChatAction.TYPING)
        try:
            characters: List[StarRailDetailCharacter] = await self.get_avatars_data(client)
            record_cards = await client.get_record_cards()
            record_card = record_cards[0]
            for card in record_cards:
                if card.game == Game.STARRAIL:
                    record_card = card
                    break
            nickname = record_card.nickname
        except InvalidCookies as exc:
            await client.get_genshin_user(client.uid)
            logger.warning("用户 %s[%s] 无法请求角色数数据 API返回信息为 [%s]%s", user.full_name, user.id, exc.retcode, exc.original)
            reply_message = await message.reply_text("出错了呜呜呜 ~ 当前访问令牌无法请求角色数数据，请尝试重新获取Cookie。")
            if filters.ChatType.GROUPS.filter(message):
                self.add_delete_message_job(reply_message, delay=30)
                self.add_delete_message_job(message, delay=30)
            return

        has_more = (not all_avatars) and len(characters) > 20
        if has_more:
            characters = characters[:20]
        avatar_datas = await self.get_final_data(characters)

        render_data = {
            "uid": client.uid,  # 玩家uid
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
