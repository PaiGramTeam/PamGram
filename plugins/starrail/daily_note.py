import datetime
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from simnet.errors import DataNotPublic
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import ConversationHandler, filters, CallbackContext
from telegram.helpers import create_deep_linked_url

from core.plugin import Plugin, handler
from core.services.template.models import RenderResult
from core.services.template.services import TemplateService
from plugins.tools.genshin import GenshinHelper, CookiesNotFoundError, PlayerNotFoundError
from utils.log import logger

if TYPE_CHECKING:
    from simnet import StarRailClient


__all__ = ("DailyNotePlugin",)


class DailyNotePlugin(Plugin):
    """每日便签"""

    def __init__(
        self,
        template: TemplateService,
        helper: GenshinHelper,
    ):
        self.template_service = template
        self.helper = helper

    async def _get_daily_note(self, client: "StarRailClient") -> RenderResult:
        daily_info = await client.get_starrail_notes(client.player_id)

        day = datetime.now().strftime("%m-%d %H:%M") + " 星期" + "一二三四五六日"[datetime.now().weekday()]
        resin_recovery_time = (
            (datetime.now() + daily_info.stamina_recover_time).strftime("%m-%d %H:%M")
            if daily_info.max_stamina - daily_info.current_stamina
            else None
        )

        remained_time = None
        for i in daily_info.expeditions:
            if remained_time:
                if remained_time < i.remaining_time:
                    remained_time = i.remaining_time
            else:
                remained_time = i.remaining_time
        if remained_time:
            remained_time = (datetime.now().astimezone() + remained_time).strftime("%m-%d %H:%M")

        render_data = {
            "uid": client.player_id,
            "day": day,
            "resin_recovery_time": resin_recovery_time,
            "current_resin": daily_info.current_stamina,
            "max_resin": daily_info.max_stamina,
            "expeditions": bool(daily_info.expeditions),
            "remained_time": remained_time,
            "current_expeditions": len(daily_info.expeditions),
            "max_expeditions": daily_info.total_expedition_num,
        }
        render_result = await self.template_service.render(
            "starrail/daily_note/daily_note.html",
            render_data,
            {"width": 600, "height": 220},
            full_page=False,
            ttl=8 * 60,
        )
        return render_result

    @handler.command("dailynote", block=False)
    @handler.message(filters.Regex("^当前状态(.*)"), block=False)
    async def command_start(self, update: Update, _: CallbackContext) -> Optional[int]:
        message = update.effective_message
        user = update.effective_user
        logger.info("用户 %s[%s] 每日便签命令请求", user.full_name, user.id)

        try:
            async with self.helper.genshin(user.id) as client:
                render_result = await self._get_daily_note(client)
        except (CookiesNotFoundError, PlayerNotFoundError):
            buttons = [
                [
                    InlineKeyboardButton(
                        "点我绑定账号", url=create_deep_linked_url(self.application.bot.username, "set_cookie")
                    )
                ]
            ]
            if filters.ChatType.GROUPS.filter(message):
                reply_message = await message.reply_text(
                    "未查询到您所绑定的账号信息，请先私聊彦卿绑定账号", reply_markup=InlineKeyboardMarkup(buttons)
                )
                self.add_delete_message_job(reply_message, delay=30)
                self.add_delete_message_job(message, delay=30)
            else:
                await message.reply_text("未查询到您所绑定的账号信息，请先绑定账号", reply_markup=InlineKeyboardMarkup(buttons))
            return
        except DataNotPublic:
            reply_message = await message.reply_text("查询失败惹，可能是便签功能被禁用了？请尝试通过米游社或者 hoyolab 获取一次便签信息后重试。")
            if filters.ChatType.GROUPS.filter(message):
                self.add_delete_message_job(reply_message, delay=30)
                self.add_delete_message_job(message, delay=30)
            return ConversationHandler.END

        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        await render_result.reply_photo(message, filename=f"{client.player_id}.png", allow_sending_without_reply=True)
