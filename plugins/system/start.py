from telegram import Update, ReplyKeyboardRemove
from telegram.ext import CallbackContext, CommandHandler
from telegram.helpers import escape_markdown

from core.base.redisdb import RedisDB
from core.cookies import CookiesService
from core.plugin import handler, Plugin
from core.user import UserService
from plugins.genshin.sign import SignSystem
from plugins.genshin.verification import VerificationSystem
from utils.decorators.error import error_callable
from utils.decorators.restricts import restricts
from utils.log import logger


class StartPlugin(Plugin):
    def __init__(self, user_service: UserService = None, cookies_service: CookiesService = None, redis: RedisDB = None):
        self.cookies_service = cookies_service
        self.user_service = user_service
        self.sign_system = SignSystem(redis)
        self.verification_system = VerificationSystem(redis)

    @handler.command("start", block=False)
    @error_callable
    @restricts()
    async def start(self, update: Update, context: CallbackContext) -> None:
        user = update.effective_user
        message = update.effective_message
        args = context.args
        if args is not None and len(args) >= 1:
            await message.reply_html(f"你好 {user.mention_html()} ！\n请点击 /{args[0]} 命令进入对应流程")
            return
        logger.info("用户 %s[%s] 发出start命令", user.full_name, user.id)
        await message.reply_markdown_v2(f"你好 {user.mention_markdown_v2()} {escape_markdown('！')}")

    @staticmethod
    @restricts()
    async def unknown_command(update: Update, _: CallbackContext) -> None:
        await update.effective_message.reply_text("前面的区域，以后再来探索吧！")

    @handler(CommandHandler, command="ping", block=False)
    @restricts()
    async def ping(self, update: Update, _: CallbackContext) -> None:
        await update.effective_message.reply_text("online! ヾ(✿ﾟ▽ﾟ)ノ")

    @handler(CommandHandler, command="reply_keyboard_remove", block=False)
    @restricts()
    async def reply_keyboard_remove(self, update: Update, _: CallbackContext) -> None:
        await update.message.reply_text("移除远程键盘成功", reply_markup=ReplyKeyboardRemove())
