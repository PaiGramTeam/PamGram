import datetime
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from simnet.errors import DataNotPublic
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ConversationHandler, filters, CallbackContext

from core.plugin import Plugin, handler
from core.services.template.models import RenderResult
from core.services.template.services import TemplateService
from plugins.tools.genshin import GenshinHelper
from utils.log import logger
from utils.uid import mask_number

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
            "uid": mask_number(client.player_id),
            "day": day,
            "resin_recovery_time": resin_recovery_time,
            "current_resin": daily_info.current_stamina,
            "max_resin": daily_info.max_stamina,
            "expeditions": bool(daily_info.expeditions),
            "remained_time": remained_time,
            "current_expeditions": len(daily_info.expeditions),
            "max_expeditions": daily_info.total_expedition_num,
            "current_train_score": daily_info.current_train_score,
            "max_train_score": daily_info.max_train_score,
            "remaining_weekly_discounts": daily_info.remaining_weekly_discounts,
            "max_weekly_discounts": daily_info.max_weekly_discounts,
            "current_rogue_score": daily_info.current_rogue_score,
            "max_rogue_score": daily_info.max_rogue_score,
        }
        render_result = await self.template_service.render(
            "starrail/daily_note/daily_note.html",
            render_data,
            {"width": 600, "height": 444},
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
        except DataNotPublic:
            reply_message = await message.reply_text("查询失败惹，可能是便签功能被禁用了？请尝试通过米游社或者 hoyolab 获取一次便签信息后重试。")
            if filters.ChatType.GROUPS.filter(message):
                self.add_delete_message_job(reply_message, delay=30)
                self.add_delete_message_job(message, delay=30)
            return ConversationHandler.END

        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        await render_result.reply_photo(message, filename=f"{client.player_id}.png", allow_sending_without_reply=True)
