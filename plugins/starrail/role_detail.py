import os
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from simnet.errors import BadRequest as SimnetBadRequest, DataNotPublic
from simnet.models.starrail.diary import StarRailDiary
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import filters, CallbackContext

from core.plugin import Plugin, handler
from core.services.cookies import CookiesService
from core.services.template.models import RenderResult
from core.services.template.services import TemplateService
from plugins.tools.genshin import GenshinHelper
from utils.log import logger
from utils.uid import mask_number

if TYPE_CHECKING:
    from simnet import StarRailClient


__all__ = ("RoleDetailPlugin",)


class RoleDetailPlugin(Plugin):
    """角色详细信息查询"""

    def __init__(
        self,
        helper: GenshinHelper,
        cookies_service: CookiesService,
        template_service: TemplateService,
    ):
        self.template_service = template_service
        self.cookies_service = cookies_service
        self.current_dir = os.getcwd()
        self.helper = helper

    @handler.command(command="role_detail", block=False)
    async def command_start(self, update: Update, context: CallbackContext) -> None:
        user = update.effective_user
        message = update.effective_message

        logger.info("用户 %s[%s] 查询角色详细信息", user.full_name, user.id)
        await message.reply_chat_action(ChatAction.TYPING)
        async with self.helper.genshin(user.id) as client:
            client: "StarRailClient"
            data = await client.get_starrail_characters()
            char = data.avatar_list[3].dict()
            char["skills_map"] = [[j.dict() for j in i] for i in data.avatar_list[3].skills_map]
            char["skills_main"] = [i.dict() for i in data.avatar_list[3].skills_main]
            char["skills_single"] = [i.dict() for i in data.avatar_list[3].skills_single]
            final = {"char": char}
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        render_result = await self.template_service.render(
            "starrail/role_detail/main.jinja2", final, {"width": 960, "height": 770}, query_selector=".pc-role-detail-num",
        )
        await render_result.reply_photo(message, filename=f"{client.player_id}.png", allow_sending_without_reply=True)
