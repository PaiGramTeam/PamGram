from typing import Optional, List, Dict

from genshin import Client, GenshinException
from genshin.models import StarRailMuseumBasic, StarRailMuseumDetail
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

__all__ = ("PlayerMuseumPlugins",)


class NotSupport(Exception):
    """不支持的服务器"""


class NotHaveData(Exception):
    """没有数据"""


class PlayerMuseumPlugins(Plugin):
    """玩家冬城博物珍奇簿查询"""

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

    @handler.command("museum", block=False)
    @handler.message(filters.Regex("^博物馆信息查询(.*)"), block=False)
    async def command_start(self, update: Update, context: CallbackContext) -> Optional[int]:
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] 查询博物馆信息命令请求", user.full_name, user.id)
        try:
            uid = await self.get_uid(user.id, context.args, message.reply_to_message)
            if uid and str(uid)[0] not in ["1", "2", "5"]:
                # todo: 支持国际服
                raise NotSupport
            try:
                client = await self.helper.get_genshin_client(user.id)
                if client.uid != uid:
                    raise CookiesNotFoundError(uid)
            except CookiesNotFoundError:
                client, _ = await self.helper.get_public_genshin_client(user.id)
            render_result = await self.render(client, uid)
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
        except GenshinException as exc:
            if exc.retcode == 1034:
                await message.reply_text("出错了呜呜呜 ~ 请稍后重试")
                return
            raise exc
        except TooManyRequestPublicCookies:
            await message.reply_text("用户查询次数过多 请稍后重试")
            return
        except AttributeError as exc:
            logger.error("冬城博物珍奇簿数据有误")
            logger.exception(exc)
            await message.reply_text("冬城博物珍奇簿数据有误 估计是彦卿晕了")
            return
        except NotSupport:
            reply_message = await message.reply_text("暂不支持该服务器查询冬城博物珍奇簿数据")
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        except NotHaveData:
            reply_message = await message.reply_text("没有查找到冬城博物珍奇簿数据")
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        await render_result.reply_photo(message, filename=f"{client.uid}.png", allow_sending_without_reply=True)

    async def get_rander_data(self, uid: int, basic: StarRailMuseumBasic, detail: StarRailMuseumDetail) -> Dict:
        exhibitions = []
        for region in detail.regions:
            for exhibition in region.exhibitions:
                exhibitions.append(exhibition)
        all_exhibitions = [exhibitions[i : i + 7] for i in range(0, len(exhibitions), 7)]
        return {
            "uid": uid,
            "basic": basic,
            "all_exhibitions": all_exhibitions,
            "directors": detail.director,
        }

    async def render(self, client: Client, uid: Optional[int] = None) -> RenderResult:
        if uid is None:
            uid = client.uid

        basic = await client.get_starrail_museum_info(uid)
        try:
            detail = await client.get_starrail_museum_detail(uid)
        except GenshinException as e:
            if e.retcode == 10301:
                raise NotHaveData from e
            raise e
        data = await self.get_rander_data(uid, basic, detail)

        return await self.template_service.render(
            "starrail/museum/museum.html",
            data,
            {"width": 1000, "height": 1000},
            full_page=True,
            query_selector="#main-container",
        )
