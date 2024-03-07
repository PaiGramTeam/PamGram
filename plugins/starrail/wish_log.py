from io import BytesIO
from typing import Optional, TYPE_CHECKING, List

from simnet.models.starrail.wish import StarRailBannerType
from telegram import Document, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update, User
from telegram.constants import ChatAction
from telegram.ext import CallbackContext, ConversationHandler, filters
from telegram.helpers import create_deep_linked_url

from core.dependence.assets import AssetsService
from core.plugin import Plugin, conversation, handler
from core.services.cookies import CookiesService
from core.services.players import PlayersService
from core.services.template.models import FileType
from core.services.template.services import TemplateService
from modules.gacha_log.error import (
    GachaLogAccountNotFound,
    GachaLogAuthkeyTimeout,
    GachaLogFileError,
    GachaLogInvalidAuthkey,
    GachaLogMixedProvider,
    GachaLogNotFound,
)
from modules.gacha_log.helpers import from_url_get_authkey
from modules.gacha_log.log import GachaLog
from modules.gacha_log.migrate import GachaLogMigrate
from plugins.tools.genshin import PlayerNotFoundError
from utils.log import logger

try:
    import ujson as jsonlib

except ImportError:
    import json as jsonlib


if TYPE_CHECKING:
    from telegram import Update, Message, User, Document
    from telegram.ext import ContextTypes
    from gram_core.services.players.models import Player

INPUT_URL, INPUT_FILE, CONFIRM_DELETE = range(10100, 10103)


class WishLogPlugin(Plugin.Conversation):
    """跃迁记录导入/导出/分析"""

    def __init__(
        self,
        template_service: TemplateService,
        players_service: PlayersService,
        assets: AssetsService,
        cookie_service: CookiesService,
    ):
        self.template_service = template_service
        self.players_service = players_service
        self.assets_service = assets
        self.cookie_service = cookie_service
        self.gacha_log = GachaLog()

    async def get_player_id(self, uid: int) -> Optional[int]:
        """获取绑定的游戏ID"""
        logger.debug("尝试获取已绑定的星穹铁道账号")
        player = await self.players_service.get_player(uid)
        if player is None:
            raise PlayerNotFoundError(uid)
        return player.player_id

    async def _refresh_user_data(
        self, user: User, data: dict = None, authkey: str = None, verify_uid: bool = True
    ) -> str:
        """刷新用户数据
        :param user: 用户
        :param data: 数据
        :param authkey: 认证密钥
        :return: 返回信息
        """
        try:
            logger.debug("尝试获取已绑定的星穹铁道账号")
            player_id = await self.get_player_id(user.id)
            if authkey:
                new_num = await self.gacha_log.get_gacha_log_data(user.id, player_id, authkey)
                return "更新完成，本次没有新增数据" if new_num == 0 else f"更新完成，本次共新增{new_num}条跃迁记录"
            if data:
                new_num = await self.gacha_log.import_gacha_log_data(user.id, player_id, data, verify_uid)
                return "更新完成，本次没有新增数据" if new_num == 0 else f"更新完成，本次共新增{new_num}条跃迁记录"
        except GachaLogNotFound:
            return "彦卿没有找到你的跃迁记录，快来私聊彦卿导入吧~"
        except GachaLogAccountNotFound:
            return "导入失败，可能文件包含的跃迁记录所属 uid 与你当前绑定的 uid 不同"
        except GachaLogFileError:
            return "导入失败，数据格式错误"
        except GachaLogInvalidAuthkey:
            return "更新数据失败，authkey 无效"
        except GachaLogAuthkeyTimeout:
            return "更新数据失败，authkey 已经过期"
        except GachaLogMixedProvider:
            return "导入失败，你已经通过其他方式导入过跃迁记录了，本次无法导入"
        except PlayerNotFoundError:
            logger.info("未查询到用户 %s[%s] 所绑定的账号信息", user.full_name, user.id)
            return "彦卿没有找到您所绑定的账号信息，请先私聊彦卿绑定账号"

    async def import_from_file(self, user: User, message: Message, document: Document = None) -> None:
        if not document:
            document = message.document
        # TODO: 使用 mimetype 判断文件类型
        if document.file_name.endswith(".json"):
            file_type = "json"
        else:
            await message.reply_text("文件格式错误，请发送符合 SRGF 标准的跃迁记录文件")
            return
        if document.file_size > 5 * 1024 * 1024:
            await message.reply_text("文件过大，请发送小于 5 MB 的文件")
            return
        try:
            out = BytesIO()
            await (await document.get_file()).download_to_memory(out=out)
            if file_type == "json":
                # bytesio to json
                data = jsonlib.loads(out.getvalue().decode("utf-8"))
            else:
                await message.reply_text("文件解析失败，请检查文件")
                return
        except GachaLogFileError:
            await message.reply_text("文件解析失败，请检查文件是否符合 SRGF 标准")
            return
        except (KeyError, IndexError, ValueError):
            await message.reply_text("文件解析失败，请检查文件编码是否正确或符合 SRGF 标准")
            return
        except Exception as exc:
            logger.error("文件解析失败 %s", repr(exc))
            await message.reply_text("文件解析失败，请检查文件是否符合 SRGF 标准")
            return
        await message.reply_chat_action(ChatAction.TYPING)
        reply = await message.reply_text("文件解析成功，正在导入数据")
        await message.reply_chat_action(ChatAction.TYPING)
        try:
            text = await self._refresh_user_data(user, data=data, verify_uid=file_type == "json")
        except Exception as exc:  # pylint: disable=W0703
            logger.error("文件解析失败 %s", repr(exc))
            text = "文件解析失败，请检查文件是否符合 SRGF 标准"
        await reply.edit_text(text)

    @conversation.entry_point
    @handler.command(command="warp_log_import", filters=filters.ChatType.PRIVATE, block=False)
    @handler.message(filters=filters.Regex("^导入跃迁记录(.*)") & filters.ChatType.PRIVATE, block=False)
    @handler.command(command="start", filters=filters.Regex("warp_log_import$"), block=False)
    async def command_start(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> int:
        message = update.effective_message
        user = update.effective_user
        args = self.get_args(context)
        logger.info("用户 %s[%s] 导入跃迁记录命令请求", user.full_name, user.id)
        authkey = from_url_get_authkey(args[0] if args else "")
        if authkey == "warp_log_import":
            authkey = ""
        if not authkey:
            await message.reply_text(
                "<b>开始导入跃迁历史记录：请通过 https://starrailstation.com/cn/warp#import 获取跃迁记录链接后发送给我"
                "（非 starrailstation.com 导出的文件数据）</b>\n\n"
                "> 你还可以向彦卿发送从其他工具导出的 SRGF 标准的记录文件\n"
                # "> 在绑定 Cookie 时添加 stoken 可能有特殊效果哦（仅限国服）\n"
                "<b>注意：导入的数据将会与旧数据进行合并。</b>",
                parse_mode="html",
            )
            return INPUT_URL
        text = "小彦卿正在从服务器获取数据，请稍后"
        if not args:
            text += "\n\n> 由于你绑定的 Cookie 中存在 stoken ，本次通过 stoken 自动刷新数据"
        reply = await message.reply_text(text)
        await message.reply_chat_action(ChatAction.TYPING)
        data = await self._refresh_user_data(user, authkey=authkey)
        await reply.edit_text(data)
        return ConversationHandler.END

    @conversation.state(state=INPUT_URL)
    @handler.message(filters=~filters.COMMAND, block=False)
    async def import_data_from_message(self, update: Update, _: CallbackContext) -> int:
        message = update.effective_message
        user = update.effective_user
        if message.document:
            await self.import_from_file(user, message)
            return ConversationHandler.END
        if not message.text:
            await message.reply_text("请发送文件或链接")
            return INPUT_URL
        authkey = from_url_get_authkey(message.text)
        reply = await message.reply_text("小彦卿正在从服务器获取数据，请稍后")
        await message.reply_chat_action(ChatAction.TYPING)
        text = await self._refresh_user_data(user, authkey=authkey)
        await reply.edit_text(text)
        return ConversationHandler.END

    @conversation.entry_point
    @handler.command(command="warp_log_delete", filters=filters.ChatType.PRIVATE, block=False)
    @handler.message(filters=filters.Regex("^删除跃迁记录(.*)") & filters.ChatType.PRIVATE, block=False)
    async def command_start_delete(self, update: Update, context: CallbackContext) -> int:
        message = update.effective_message
        user = update.effective_user
        logger.info("用户 %s[%s] 删除跃迁记录命令请求", user.full_name, user.id)
        try:
            player_id = await self.get_player_id(user.id)
            context.chat_data["uid"] = player_id
        except PlayerNotFoundError:
            logger.info("未查询到用户 %s[%s] 所绑定的账号信息", user.full_name, user.id)
            await message.reply_text("未查询到您所绑定的账号信息，请先绑定账号")
            return ConversationHandler.END
        _, status = await self.gacha_log.load_history_info(str(user.id), str(player_id), only_status=True)
        if not status:
            await message.reply_text("你还没有导入跃迁记录哦~")
            return ConversationHandler.END
        await message.reply_text("你确定要删除跃迁记录吗？（此项操作无法恢复），如果确定请发送 ”确定“，发送其他内容取消")
        return CONFIRM_DELETE

    @conversation.state(state=CONFIRM_DELETE)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=False)
    async def command_confirm_delete(self, update: Update, context: CallbackContext) -> int:
        message = update.effective_message
        user = update.effective_user
        if message.text == "确定":
            status = await self.gacha_log.remove_history_info(str(user.id), str(context.chat_data["uid"]))
            await message.reply_text("跃迁记录已删除" if status else "跃迁记录删除失败")
            return ConversationHandler.END
        await message.reply_text("已取消")
        return ConversationHandler.END

    @handler.command(command="warp_log_force_delete", block=False, admin=True)
    async def command_warp_log_force_delete(self, update: Update, context: CallbackContext):
        message = update.effective_message
        args = self.get_args(context)
        if not args:
            await message.reply_text("请指定用户ID")
            return
        try:
            cid = int(args[0])
            if cid < 0:
                raise ValueError("Invalid cid")
            player_id = await self.get_player_id(cid)
            _, status = await self.gacha_log.load_history_info(str(cid), str(player_id), only_status=True)
            if not status:
                await message.reply_text("该用户还没有导入跃迁记录")
                return
            status = await self.gacha_log.remove_history_info(str(cid), str(player_id))
            await message.reply_text("跃迁记录已强制删除" if status else "跃迁记录删除失败")
        except GachaLogNotFound:
            await message.reply_text("该用户还没有导入跃迁记录")
        except PlayerNotFoundError:
            await message.reply_text("该用户暂未绑定账号")
        except (ValueError, IndexError):
            await message.reply_text("用户ID 不合法")

    @handler.command(command="warp_log_export", filters=filters.ChatType.PRIVATE, block=False)
    @handler.message(filters=filters.Regex("^导出跃迁记录(.*)") & filters.ChatType.PRIVATE, block=False)
    async def command_start_export(self, update: Update, context: CallbackContext) -> None:
        message = update.effective_message
        user = update.effective_user
        logger.info("用户 %s[%s] 导出跃迁记录命令请求", user.full_name, user.id)
        try:
            await message.reply_chat_action(ChatAction.TYPING)
            player_id = await self.get_player_id(user.id)
            path = await self.gacha_log.gacha_log_to_srgf(str(user.id), str(player_id))
            await message.reply_chat_action(ChatAction.UPLOAD_DOCUMENT)
            await message.reply_document(document=open(path, "rb+"), caption="跃迁记录导出文件 - SRGF V1.0")
        except GachaLogNotFound:
            logger.info("未找到用户 %s[%s] 的跃迁记录", user.full_name, user.id)
            buttons = [
                [InlineKeyboardButton("点我导入", url=create_deep_linked_url(context.bot.username, "warp_log_import"))]
            ]
            await message.reply_text("彦卿没有找到你的跃迁记录，快来私聊彦卿导入吧~", reply_markup=InlineKeyboardMarkup(buttons))
        except GachaLogAccountNotFound:
            await message.reply_text("导入失败，可能文件包含的跃迁记录所属 uid 与你当前绑定的 uid 不同")
        except GachaLogFileError:
            await message.reply_text("导入失败，数据格式错误")
        except PlayerNotFoundError:
            logger.info("未查询到用户 %s[%s] 所绑定的账号信息", user.full_name, user.id)
            await message.reply_text("未查询到您所绑定的账号信息，请先绑定账号")

    @handler.command(command="warp_log", block=False)
    @handler.message(filters=filters.Regex("^跃迁记录?(光锥|角色|常驻|新手)$"), block=False)
    async def command_start_analysis(self, update: Update, context: CallbackContext) -> None:
        message = update.effective_message
        user = update.effective_user
        pool_type = StarRailBannerType.CHARACTER
        if args := self.get_args(context):
            if "光锥" in args:
                pool_type = StarRailBannerType.WEAPON
            elif "常驻" in args:
                pool_type = StarRailBannerType.STANDARD
            elif "新手" in args:
                pool_type = StarRailBannerType.NOVICE
        logger.info("用户 %s[%s] 跃迁记录命令请求 || 参数 %s", user.full_name, user.id, pool_type.name)
        try:
            await message.reply_chat_action(ChatAction.TYPING)
            player_id = await self.get_player_id(user.id)
            data = await self.gacha_log.get_analysis(user.id, player_id, pool_type, self.assets_service)
            if isinstance(data, str):
                reply_message = await message.reply_text(data)
                if filters.ChatType.GROUPS.filter(message):
                    self.add_delete_message_job(reply_message, delay=300)
                    self.add_delete_message_job(message, delay=300)
            else:
                await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
                png_data = await self.template_service.render(
                    "starrail/gacha_log/gacha_log.html",
                    data,
                    full_page=True,
                    file_type=FileType.DOCUMENT if len(data.get("fiveLog")) > 300 else FileType.PHOTO,
                    query_selector=".body_box",
                )
                if png_data.file_type == FileType.DOCUMENT:
                    await png_data.reply_document(message, filename="跃迁记录.png")
                else:
                    await png_data.reply_photo(message)
        except GachaLogNotFound:
            logger.info("未找到用户 %s[%s] 的跃迁记录", user.full_name, user.id)
            buttons = [
                [InlineKeyboardButton("点我导入", url=create_deep_linked_url(context.bot.username, "warp_log_import"))]
            ]
            await message.reply_text("彦卿没有找到你此卡池的跃迁记录，快来点击按钮私聊彦卿导入吧~", reply_markup=InlineKeyboardMarkup(buttons))

    @handler.command(command="warp_count", block=False)
    @handler.message(filters=filters.Regex("^跃迁统计?(光锥|角色|常驻|新手)$"), block=False)
    async def command_start_count(self, update: Update, context: CallbackContext) -> None:
        message = update.effective_message
        user = update.effective_user
        pool_type = StarRailBannerType.CHARACTER
        all_five = False
        if args := self.get_args(context):
            if "光锥" in args:
                pool_type = StarRailBannerType.WEAPON
            elif "常驻" in args:
                pool_type = StarRailBannerType.STANDARD
            elif "新手" in args:
                pool_type = StarRailBannerType.NOVICE
            if "仅五星" in args:
                all_five = True
        logger.info("用户 %s[%s] 跃迁统计命令请求 || 参数 %s || 仅五星 %s", user.full_name, user.id, pool_type.name, all_five)
        try:
            group = filters.ChatType.GROUPS.filter(message)
            await message.reply_chat_action(ChatAction.TYPING)
            player_id = await self.get_player_id(user.id)
            if all_five:
                data = await self.gacha_log.get_all_five_analysis(user.id, player_id, self.assets_service)
            else:
                data = await self.gacha_log.get_pool_analysis(user.id, player_id, pool_type, self.assets_service, group)
            if isinstance(data, str):
                reply_message = await message.reply_text(data)
                if filters.ChatType.GROUPS.filter(message):
                    self.add_delete_message_job(reply_message)
                    self.add_delete_message_job(message)
            else:
                document = False
                if data["hasMore"] and not group:
                    document = True
                    data["hasMore"] = False
                await message.reply_chat_action(ChatAction.UPLOAD_DOCUMENT if document else ChatAction.UPLOAD_PHOTO)
                png_data = await self.template_service.render(
                    "starrail/gacha_count/gacha_count.html",
                    data,
                    full_page=True,
                    query_selector=".body_box",
                    file_type=FileType.DOCUMENT if document else FileType.PHOTO,
                )
                if document:
                    await png_data.reply_document(message, filename="跃迁统计.png")
                else:
                    await png_data.reply_photo(message)
        except GachaLogNotFound:
            logger.info("未找到用户 %s[%s] 的跃迁记录", user.full_name, user.id)
            buttons = [
                [InlineKeyboardButton("点我导入", url=create_deep_linked_url(context.bot.username, "warp_log_import"))]
            ]
            await message.reply_text("彦卿没有找到你此卡池的跃迁记录，快来私聊彦卿导入吧~", reply_markup=InlineKeyboardMarkup(buttons))

    @staticmethod
    async def get_migrate_data(
        old_user_id: int, new_user_id: int, old_players: List["Player"]
    ) -> Optional[GachaLogMigrate]:
        return await GachaLogMigrate.create(old_user_id, new_user_id, old_players)
