from typing import TYPE_CHECKING

from telegram.constants import ChatAction
from telegram.ext import filters

from simnet import Region

from core.services.self_help.services import ActionLogService
from gram_core.plugin import Plugin, handler
from plugins.tools.genshin import GenshinHelper
from utils.log import logger

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

    from simnet import StarRailClient


class NotSupport(Exception):
    """不支持的服务器"""

    def __str__(self, msg: str = None):
        self.msg = msg
        return self.msg


class ActionLogPlugins(Plugin):
    """玩家活动信息查询"""

    def __init__(self, helper: GenshinHelper, action_log_service: ActionLogService):
        self.helper = helper
        self.action_log_service = action_log_service

    async def import_action_log(self, client: "StarRailClient", authkey: str) -> bool:
        data = await client.get_starrail_action_log(authkey=authkey)
        # 确保第一个数据为登出、最后一条数据为登入
        if data[0].status == 1:
            data.pop(0)
        if data[-1].status == 0:
            data.pop(-1)
        return await self.action_log_service.add(data)

    @handler.command(command="action_log_import", filters=filters.ChatType.PRIVATE, cookie=True, block=False)
    async def command_start(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE") -> None:
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

                bo = await self.import_action_log(client, authkey)
                text = "导入登录记录成功" if bo else "导入登录记录失败，可能没有新记录"
                await notice.edit_text(text)
                self.log_user(update, logger.success, text)
        except NotSupport as e:
            msg = await message.reply_text(e.msg)
            if filters.ChatType.GROUPS.filter(message):
                self.add_delete_message_job(message, delay=60)
                self.add_delete_message_job(msg, delay=60)

    @handler.command(command="test_get", block=False)
    async def t(self, _, __):
        r = await self.action_log_service.test_query()
        breakpoint()
