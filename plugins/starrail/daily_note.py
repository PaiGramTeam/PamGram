import datetime
from datetime import datetime
from typing import Optional, TYPE_CHECKING, List

from simnet.errors import DataNotPublic
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ChatAction
from telegram.ext import ConversationHandler, filters
from telegram.helpers import create_deep_linked_url

from core.plugin import Plugin, handler
from core.services.template.models import RenderResult
from core.services.template.services import TemplateService
from gram_core.plugin.methods.inline_use_data import IInlineUseData
from plugins.tools.genshin import GenshinHelper
from utils.log import logger
from utils.uid import mask_number

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes
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
            "current_reserve_stamina": daily_info.current_reserve_stamina,
            "is_reserve_stamina_full": daily_info.is_reserve_stamina_full,
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
            {"width": 600, "height": 530},
            full_page=False,
            ttl=8 * 60,
        )
        return render_result

    @staticmethod
    def get_task_button(bot_username: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton(">> 设置状态提醒 <<", url=create_deep_linked_url(bot_username, "daily_note_tasks"))]]
        )

    @handler.command("dailynote", cookie=True, block=False)
    @handler.message(filters.Regex("^当前状态(.*)"), cookie=True, block=False)
    async def command_start(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> Optional[int]:
        user_id = await self.get_real_user_id(update)
        message = update.effective_message
        uid, offset = self.get_real_uid_or_offset(update)
        self.log_user(update, logger.info, "每日便签命令请求")

        try:
            async with self.helper.genshin(user_id, player_id=uid, offset=offset) as client:
                render_result = await self._get_daily_note(client)
        except DataNotPublic:
            reply_message = await message.reply_text(
                "查询失败惹，可能是便签功能被禁用了？请尝试通过米游社或者 hoyolab 获取一次便签信息后重试。"
            )
            if filters.ChatType.GROUPS.filter(message):
                self.add_delete_message_job(reply_message, delay=30)
                self.add_delete_message_job(message, delay=30)
            return ConversationHandler.END

        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        await render_result.reply_photo(
            message,
            filename=f"{client.player_id}.png",
            reply_markup=self.get_task_button(context.bot.username),
        )

    async def daily_note_use_by_inline(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        callback_query = update.callback_query
        user = update.effective_user
        user_id = user.id
        uid = IInlineUseData.get_uid_from_context(context)
        self.log_user(update, logger.info, "每日便签命令请求")

        try:
            async with self.helper.genshin(user_id, player_id=uid) as client:
                render_result = await self._get_daily_note(client)
        except DataNotPublic:
            await callback_query.answer(
                "查询失败惹，可能是便签功能被禁用了？请尝试通过米游社或者 hoyolab 获取一次便签信息后重试。",
                show_alert=True,
            )
            return ConversationHandler.END

        await render_result.edit_inline_media(callback_query)

    async def get_inline_use_data(self) -> List[Optional[IInlineUseData]]:
        return [
            IInlineUseData(
                text="当前状态",
                hash="dailynote",
                callback=self.daily_note_use_by_inline,
                cookie=True,
                player=True,
            )
        ]
