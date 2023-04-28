from typing import Optional

from genshin import Client, GenshinException, types
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import CallbackContext, filters
from telegram.helpers import create_deep_linked_url

from core.plugin import Plugin, handler
from core.services.cookies.error import TooManyRequestPublicCookies
from core.services.template.models import RenderResult
from core.services.template.services import TemplateService
from plugins.tools.genshin import GenshinHelper, PlayerNotFoundError, CookiesNotFoundError
from utils.log import logger

__all__ = ("PlayerStatsPlugins",)


class PlayerStatsPlugins(Plugin):
    """玩家统计查询"""

    def __init__(
        self,
        template: TemplateService,
        helper: GenshinHelper,
    ):
        self.template_service = template
        self.helper = helper

    @handler.command("stats", block=False)
    @handler.message(filters.Regex("^玩家统计查询(.*)"), block=False)
    async def command_start(self, update: Update, context: CallbackContext) -> Optional[int]:
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] 查询游戏用户命令请求", user.full_name, user.id)
        uid: Optional[int] = None
        try:
            args = context.args
            if args is not None and len(args) >= 1:
                uid = int(args[0])
        except ValueError as exc:
            logger.warning("获取 uid 发生错误！ 错误信息为 %s", str(exc))
            await message.reply_text("输入错误")
            return
        try:
            try:
                client = await self.helper.get_genshin_client(user.id)
            except CookiesNotFoundError:
                client, uid = await self.helper.get_public_genshin_client(user.id)
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
            if exc.retcode == 1034 and uid:
                await message.reply_text("出错了呜呜呜 ~ 请稍后重试")
                return
            raise exc
        except TooManyRequestPublicCookies:
            await message.reply_text("用户查询次数过多 请稍后重试")
            return
        except AttributeError as exc:
            logger.error("角色数据有误")
            logger.exception(exc)
            await message.reply_text("角色数据有误 估计是彦卿晕了")
            return
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        await render_result.reply_photo(message, filename=f"{client.uid}.png", allow_sending_without_reply=True)

    async def render(self, client: Client, uid: Optional[int] = None) -> RenderResult:
        if uid is None:
            uid = client.uid

        user_info = await client.get_starrail_user(uid)
        record_cards = await client.get_record_cards()
        record_card = record_cards[0]
        for card in record_cards:
            if card.game == types.Game.STARRAIL:
                record_card = card
                break
        logger.debug(user_info)

        # 因为需要替换线上图片地址为本地地址，先克隆数据，避免修改原数据
        user_info = user_info.copy(deep=True)

        data = {
            "uid": uid,
            "info": record_card,
            "stats": user_info.stats,
            "stats_labels": [
                ("活跃天数", "active_days"),
                ("成就达成数", "achievement_num"),
                ("获取角色数", "avatar_num"),
                ("忘却之庭", "abyss_process"),
                ("战利品开启数", "chest_num"),
            ],
            "style": "xianzhou",  # nosec
        }

        return await self.template_service.render(
            "starrail/stats/stats.html",
            data,
            {"width": 650, "height": 440},
            full_page=True,
        )
