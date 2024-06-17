import datetime

from typing import TYPE_CHECKING

from gram_core.plugin import Plugin, job, handler
from plugins.tools.action_log_system import ActionLogSystem
from utils.log import logger

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes


class ImportActionLogJob(Plugin):
    def __init__(self, action_log_system: ActionLogSystem = None):
        self.action_log_system = action_log_system

    @job.run_daily(time=datetime.time(hour=12, minute=1, second=0), name="ImportActionLogJob")
    async def refresh(self, _: "ContextTypes.DEFAULT_TYPE"):
        await self.action_log_system.daily_import_login(_)

    @handler.command(command="action_log_import_all", block=False, admin=True)
    async def action_log_import_all(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        user = update.effective_user
        logger.info("用户 %s[%s] action_log_import_all 命令请求", user.full_name, user.id)
        message = update.effective_message
        reply = await message.reply_text("正在执行导入登录记录任务，请稍后...")
        await self.refresh(context)
        await reply.edit_text("全部账号导入登录记录任务完成")
