import contextlib

from telegram import Update, ChatMemberAdministrator
from telegram.ext import CallbackContext, filters

from core.plugin import Plugin, handler
from utils.log import logger


class TitlePlugin(Plugin):
    @handler.command("title", filters=filters.ChatType.SUPERGROUP, block=False)
    async def start(self, update: Update, context: CallbackContext) -> None:
        user = update.effective_user
        message = update.effective_message
        args = self.get_args(context)
        title = args[0].strip() if args else ""
        logger.info("用户 %s[%s] 发出 title 命令", user.full_name, user.id)
        can_edit = False
        with contextlib.suppress(Exception):
            member = await context.bot.get_chat_member(message.chat.id, user.id)
            if isinstance(member, ChatMemberAdministrator):
                can_edit = member.can_be_edited
        if not can_edit:
            reply = await message.reply_text("你没有权限使用此命令。")
            self.add_delete_message_job(message)
            self.add_delete_message_job(reply)
            return
        if not title:
            reply = await message.reply_text("参数不能为空。")
            self.add_delete_message_job(message)
            self.add_delete_message_job(reply)
            return
        try:
            await context.bot.set_chat_administrator_custom_title(message.chat.id, user.id, title)
        except Exception:
            reply = await message.reply_text("设置失败，可能是参数不合法。")
            self.add_delete_message_job(message)
            self.add_delete_message_job(reply)
            return
        reply = await message.reply_text("设置成功。")
        self.add_delete_message_job(message)
        self.add_delete_message_job(reply)
