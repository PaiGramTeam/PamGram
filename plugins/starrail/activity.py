from typing import Optional, List, Dict, TYPE_CHECKING

from simnet.errors import BadRequest as SimnetBadRequest
from simnet.models.starrail.chronicle.activity import StarRailStarFight
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.constants import ChatAction
from telegram.ext import CallbackContext, filters
from telegram.helpers import create_deep_linked_url

from core.dependence.assets import AssetsService
from core.plugin import Plugin, handler
from core.services.cookies.error import TooManyRequestPublicCookies
from core.services.template.models import RenderResult
from core.services.template.services import TemplateService
from plugins.tools.genshin import GenshinHelper, PlayerNotFoundError, CookiesNotFoundError
from utils.log import logger

if TYPE_CHECKING:
    from simnet import StarRailClient


__all__ = ("PlayerActivityPlugins",)


class NotSupport(Exception):
    """不支持的服务器"""


class NotHaveData(Exception):
    """没有数据"""


class PlayerActivityPlugins(Plugin):
    """玩家活动信息查询"""

    def __init__(
        self,
        template: TemplateService,
        assets: AssetsService,
        helper: GenshinHelper,
    ):
        self.template_service = template
        self.assets = assets
        self.helper = helper

    async def get_uid(self, user_id: int, args: List[str], reply: Optional[Message]) -> int:
        """通过消息获取 uid，优先级：args > reply > self"""
        uid, user_id_ = None, user_id
        if args:
            for i in args:
                if i is not None:
                    if i.isdigit() and len(i) == 9:
                        uid = int(i)
        if reply:
            try:
                user_id_ = reply.from_user.id
            except AttributeError:
                pass
        if not uid:
            player_info = await self.helper.players_service.get_player(user_id_)
            if player_info is not None:
                uid = player_info.player_id
            if (not uid) and (user_id_ != user_id):
                player_info = await self.helper.players_service.get_player(user_id)
                if player_info is not None:
                    uid = player_info.player_id
        return uid

    @handler.command("star_fight", block=False)
    @handler.message(filters.Regex("^星芒战幕信息查询(.*)"), block=False)
    async def star_fight_command_start(self, update: Update, context: CallbackContext) -> Optional[int]:
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] 查询星芒战幕信息命令请求", user.full_name, user.id)
        try:
            uid = await self.get_uid(user.id, context.args, message.reply_to_message)
            try:
                async with self.helper.genshin(user.id) as client:
                    if client.player_id != uid:
                        raise CookiesNotFoundError(uid)
                    render_result = await self.star_fight_render(client, uid)
            except CookiesNotFoundError:
                async with self.helper.public_genshin(user.id) as client:
                    render_result = await self.star_fight_render(client, uid)
        except PlayerNotFoundError:
            buttons = [[InlineKeyboardButton("点我绑定账号", url=create_deep_linked_url(context.bot.username, "set_cookie"))]]
            if filters.ChatType.GROUPS.filter(message):
                reply_message = await message.reply_text(
                    "未查询到您所绑定的账号信息，请先私聊彦卿绑定账号", reply_markup=InlineKeyboardMarkup(buttons)
                )
                self.add_delete_message_job(reply_message, delay=30)
                self.add_delete_message_job(message, delay=30)
            else:
                await message.reply_text("未查询到您所绑定的账号信息，请先绑定账号", reply_markup=InlineKeyboardMarkup(buttons))
            return
        except SimnetBadRequest as exc:
            if exc.retcode == 1034:
                await message.reply_text("出错了呜呜呜 ~ 请稍后重试")
                return
            raise exc
        except TooManyRequestPublicCookies:
            await message.reply_text("用户查询次数过多 请稍后重试")
            return
        except AttributeError as exc:
            logger.error("活动数据有误")
            logger.exception(exc)
            await message.reply_text("活动数据有误 估计是彦卿晕了")
            return
        except NotSupport:
            reply_message = await message.reply_text("暂不支持该服务器查询活动数据")
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        except NotHaveData:
            reply_message = await message.reply_text("没有查找到此活动数据")
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        await render_result.reply_photo(message, filename=f"{user.id}.png", allow_sending_without_reply=True)

    async def get_star_fight_rander_data(self, uid: int, data: StarRailStarFight) -> Dict:
        if not data.exists_data:
            raise NotHaveData
        avatar_icons = {}
        for record in data.records:
            for avatar in record.lineup:
                avatar_icons[avatar.id] = self.assets.avatar.square(avatar.id).as_uri()
        return {
            "uid": uid,
            "records": data.records,
            "avatar_icons": avatar_icons,
        }

    async def star_fight_render(self, client: "StarRailClient", uid: Optional[int] = None) -> RenderResult:
        if uid is None:
            uid = client.player_id

        act_data = await client.get_starrail_activity(uid)
        try:
            star_fight_data = act_data.star_fight
        except ValueError:
            raise NotHaveData
        data = await self.get_star_fight_rander_data(uid, star_fight_data)

        return await self.template_service.render(
            "starrail/activity/star_fight.html",
            data,
            {"width": 500, "height": 1200},
            full_page=True,
            query_selector="#container",
        )
