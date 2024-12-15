from typing import TYPE_CHECKING, Dict, List, Optional

from telegram.constants import ChatAction
from telegram.ext import filters

from simnet import Region

from core.services.self_help.services import ActionLogService
from gram_core.plugin import Plugin, handler
from gram_core.plugin.methods.inline_use_data import IInlineUseData
from gram_core.services.template.services import TemplateService
from modules.action_log.client import ActionLogAnalyse
from plugins.tools.action_log_system import ActionLogSystem
from plugins.tools.genshin import GenshinHelper
from plugins.tools.head_icon import HeadIconService
from plugins.tools.phone_theme import PhoneThemeService
from utils.log import logger
from utils.uid import mask_number

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

    from simnet import StarRailClient

    from gram_core.services.template.models import RenderResult


class NotSupport(Exception):
    """不支持的服务器"""

    def __init__(self, msg: str = None):
        self.msg = msg


class ActionLogPlugins(Plugin):
    """登录记录信息查询"""

    def __init__(
        self,
        helper: GenshinHelper,
        action_log_service: ActionLogService,
        action_log_system: ActionLogSystem,
        template_service: TemplateService,
        head_icon: HeadIconService,
        phone_theme: PhoneThemeService,
    ):
        self.helper = helper
        self.action_log_service = action_log_service
        self.action_log_system = action_log_system
        self.template_service = template_service
        self.head_icon = head_icon
        self.phone_theme = phone_theme

    @handler.command(command="action_log_import", filters=filters.ChatType.PRIVATE, cookie=True, block=False)
    async def action_log_import(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE") -> None:
        user_id = await self.get_real_user_id(update)
        message = update.effective_message
        uid, offset = self.get_real_uid_or_offset(update)
        self.log_user(update, logger.info, "导入登录记录")
        await message.reply_chat_action(ChatAction.TYPING)

        try:
            async with self.helper.genshin(user_id, player_id=uid, offset=offset) as client:
                client: "StarRailClient"
                if client.region != Region.CHINESE:
                    raise NotSupport("不支持的服务器")
                try:
                    authkey = await client.get_authkey_by_stoken("csc")
                except ValueError as e:
                    raise NotSupport("未绑定 stoken") from e

                notice = await message.reply_text("彦卿需要收集整理数据，还请耐心等待哦~")

                bo = await self.action_log_system.import_action_log(client, authkey, True)
                text = "导入登录记录成功" if bo else "导入登录记录失败，可能没有新记录"
                await notice.edit_text(text)
                self.log_user(update, logger.success, text)
        except NotSupport as e:
            msg = await message.reply_text(e.msg)
            if filters.ChatType.GROUPS.filter(message):
                self.add_delete_message_job(message, delay=60)
                self.add_delete_message_job(msg, delay=60)

    async def get_render_data(self, uid: int):
        r = await self.action_log_service.get_data(uid, 63)
        r2 = await self.action_log_service.count_uptime_period(uid)
        if not r or not r2:
            raise NotSupport("未查询到登录记录")
        d = ActionLogAnalyse(r, r2)
        data = d.get_data()
        line_data = d.get_line_data()
        records = d.get_record_data()
        return {
            "uid": mask_number(uid),
            "datas": data,
            "line_data": line_data,
            "records": records,
        }

    async def add_theme_data(self, data: Dict, player_id: int):
        data["avatar"] = (await self.head_icon.get_head_icon(player_id)).as_uri()
        data["background"] = (await self.phone_theme.get_phone_theme(player_id)).as_uri()
        return data

    async def render(self, client: "StarRailClient") -> "RenderResult":
        data = await self.get_render_data(client.player_id)
        return await self.template_service.render(
            "starrail/action_log/action_log.html",
            await self.add_theme_data(data, client.player_id),
            full_page=True,
            query_selector=".container",
        )

    @handler.command(command="action_log", cookie=True, block=False)
    async def action_log(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE") -> None:
        user_id = await self.get_real_user_id(update)
        message = update.effective_message
        uid, offset = self.get_real_uid_or_offset(update)
        self.log_user(update, logger.info, "查询登录记录")

        try:
            async with self.helper.genshin(user_id, player_id=uid, offset=offset) as client:
                client: "StarRailClient"
                render = await self.render(client)
                await render.reply_photo(message)
        except NotSupport as e:
            msg = await message.reply_text(e.msg)
            if filters.ChatType.GROUPS.filter(message):
                self.add_delete_message_job(message, delay=60)
                self.add_delete_message_job(msg, delay=60)

    async def action_log_use_by_inline(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        callback_query = update.callback_query
        user = update.effective_user
        user_id = user.id
        uid = IInlineUseData.get_uid_from_context(context)
        self.log_user(update, logger.info, "查询登录记录")

        try:
            async with self.helper.genshin(user_id, player_id=uid) as client:
                client: "StarRailClient"
                render = await self.render(client)
        except NotSupport as e:
            await callback_query.answer(e.msg, show_alert=True)
            return
        await render.edit_inline_media(callback_query)

    async def get_inline_use_data(self) -> List[Optional[IInlineUseData]]:
        return [
            IInlineUseData(
                text="登录统计",
                hash="action_log",
                callback=self.action_log_use_by_inline,
                cookie=True,
                player=True,
            )
        ]
