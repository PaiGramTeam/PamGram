from functools import partial
from io import BytesIO
from typing import Optional, TYPE_CHECKING, List, Union, Tuple, Dict

from simnet.models.starrail.wish import StarRailBannerType
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import ConversationHandler, filters
from telegram.helpers import create_deep_linked_url

from core.dependence.assets import AssetsService
from core.plugin import Plugin, conversation, handler
from core.services.cookies import CookiesService
from core.services.players import PlayersService
from core.services.template.models import FileType
from core.services.template.services import TemplateService
from gram_core.config import config
from gram_core.plugin.methods.inline_use_data import IInlineUseData
from modules.gacha_log.const import SRGF_VERSION, GACHA_TYPE_LIST_REVERSE
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
from modules.gacha_log.models import GachaLogInfo
from plugins.tools.genshin import PlayerNotFoundError
from plugins.tools.head_icon import HeadIconService
from plugins.tools.phone_theme import PhoneThemeService
from utils.log import logger

try:
    import ujson as jsonlib

except ImportError:
    import json as jsonlib


if TYPE_CHECKING:
    from telegram import Update, Message, User, Document
    from telegram.ext import ContextTypes
    from gram_core.services.players.models import Player
    from gram_core.services.template.models import RenderResult

INPUT_URL, INPUT_FILE, CONFIRM_DELETE = range(10100, 10103)
WAITING = f"小{config.notice.bot_name}正在从服务器获取数据，请稍后"
WISHLOG_NOT_FOUND = f"{config.notice.bot_name}没有找到你的抽卡记录，快来私聊{config.notice.bot_name}导入吧~"


class WishLogPlugin(Plugin.Conversation):
    """跃迁记录导入/导出/分析"""

    def __init__(
        self,
        template_service: TemplateService,
        players_service: PlayersService,
        assets: AssetsService,
        cookie_service: CookiesService,
        head_icon: HeadIconService,
        phone_theme: PhoneThemeService,
    ):
        self.template_service = template_service
        self.players_service = players_service
        self.assets_service = assets
        self.cookie_service = cookie_service
        self.head_icon = head_icon
        self.phone_theme = phone_theme
        self.gacha_log = GachaLog()
        self.wish_photo = None

    async def get_player_id(self, user_id: int, player_id: int, offset: int) -> int:
        """获取绑定的游戏ID"""
        logger.debug("尝试获取已绑定的星穹铁道账号")
        player = await self.players_service.get_player(user_id, player_id=player_id, offset=offset)
        if player is None:
            raise PlayerNotFoundError(user_id)
        return player.player_id

    async def _refresh_user_data(
        self, user: "User", player_id: int, data: dict = None, authkey: str = None, verify_uid: bool = True
    ) -> str:
        """刷新用户数据
        :param user: 用户
        :param data: 数据
        :param authkey: 认证密钥
        :return: 返回信息
        """
        try:
            logger.debug("尝试获取已绑定的星穹铁道账号")
            if authkey:
                new_num = await self.gacha_log.get_gacha_log_data(user.id, player_id, authkey)
                return "更新完成，本次没有新增数据" if new_num == 0 else f"更新完成，本次共新增{new_num}条跃迁记录"
            if data:
                new_num = await self.gacha_log.import_gacha_log_data(user.id, player_id, data, verify_uid)
                return "更新完成，本次没有新增数据" if new_num == 0 else f"更新完成，本次共新增{new_num}条跃迁记录"
        except GachaLogNotFound:
            return WISHLOG_NOT_FOUND
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
            return config.notice.user_not_found

    async def import_from_file(
        self, user: "User", player_id: int, message: "Message", document: "Document" = None
    ) -> None:
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
            text = await self._refresh_user_data(user, player_id, data=data, verify_uid=file_type == "json")
        except Exception as exc:  # pylint: disable=W0703
            logger.error("文件解析失败 %s", repr(exc))
            text = "文件解析失败，请检查文件是否符合 SRGF 标准"
        await reply.edit_text(text)

    @conversation.entry_point
    @handler.command(command="warp_log_import", filters=filters.ChatType.PRIVATE, block=False)
    @handler.message(filters=filters.Regex("^导入跃迁记录(.*)") & filters.ChatType.PRIVATE, block=False)
    @handler.command(command="start", filters=filters.Regex("warp_log_import$"), block=False)
    async def command_start(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> int:
        uid, offset = self.get_real_uid_or_offset(update)
        message = update.effective_message
        user = update.effective_user
        player_id = await self.get_player_id(user.id, uid, offset)
        context.chat_data["uid"] = player_id
        args = self.get_args(context)
        logger.info("用户 %s[%s] 导入跃迁记录命令请求", user.full_name, user.id)
        authkey = from_url_get_authkey(args[0] if args else "")
        if authkey == "warp_log_import":
            authkey = ""
        if not authkey:
            await message.reply_text(
                "<b>开始导入跃迁历史记录：请通过 https://starrailstation.com/cn/warp#import 获取跃迁记录链接后发送给我"
                "（非 starrailstation.com 导出的文件数据）</b>\n\n"
                f"> 你还可以向彦卿发送从其他工具导出的 SRGF {SRGF_VERSION} 标准的记录文件\n"
                # "> 在绑定 Cookie 时添加 stoken 可能有特殊效果哦（仅限国服）\n"
                "<b>注意：导入的数据将会与旧数据进行合并。</b>",
                parse_mode="html",
            )
            return INPUT_URL
        text = WAITING
        if not args:
            text += "\n\n> 由于你绑定的 Cookie 中存在 stoken ，本次通过 stoken 自动刷新数据"
        reply = await message.reply_text(text)
        await message.reply_chat_action(ChatAction.TYPING)
        data = await self._refresh_user_data(user, player_id, authkey=authkey)
        await reply.edit_text(data)
        return ConversationHandler.END

    @conversation.state(state=INPUT_URL)
    @handler.message(filters=~filters.COMMAND, block=False)
    async def import_data_from_message(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> int:
        message = update.effective_message
        user = update.effective_user
        player_id = context.chat_data["uid"]
        if message.document:
            await self.import_from_file(user, player_id, message)
            return ConversationHandler.END
        if not message.text:
            await message.reply_text("请发送文件或链接")
            return INPUT_URL
        authkey = from_url_get_authkey(message.text)
        reply = await message.reply_text(WAITING)
        await message.reply_chat_action(ChatAction.TYPING)
        text = await self._refresh_user_data(user, player_id, authkey=authkey)
        await reply.edit_text(text)
        return ConversationHandler.END

    @conversation.entry_point
    @handler.command(command="warp_log_delete", filters=filters.ChatType.PRIVATE, block=False)
    @handler.message(filters=filters.Regex("^删除跃迁记录(.*)") & filters.ChatType.PRIVATE, block=False)
    async def command_start_delete(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> int:
        uid, offset = self.get_real_uid_or_offset(update)
        message = update.effective_message
        user = update.effective_user
        logger.info("用户 %s[%s] 删除跃迁记录命令请求", user.full_name, user.id)
        try:
            player_id = await self.get_player_id(user.id, uid, offset)
            context.chat_data["uid"] = player_id
        except PlayerNotFoundError:
            logger.info("未查询到用户 %s[%s] 所绑定的账号信息", user.full_name, user.id)
            await message.reply_text(config.notice.user_not_found)
            return ConversationHandler.END
        _, status = await self.gacha_log.load_history_info(str(user.id), str(player_id), only_status=True)
        if not status:
            await message.reply_text("你还没有导入跃迁记录哦~")
            return ConversationHandler.END
        await message.reply_text(
            "你确定要删除跃迁记录吗？（此项操作无法恢复），如果确定请发送 ”确定“，发送其他内容取消"
        )
        return CONFIRM_DELETE

    @conversation.state(state=CONFIRM_DELETE)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=False)
    async def command_confirm_delete(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> int:
        message = update.effective_message
        user = update.effective_user
        if message.text == "确定":
            status = await self.gacha_log.remove_history_info(str(user.id), str(context.chat_data["uid"]))
            await message.reply_text("跃迁记录已删除" if status else "跃迁记录删除失败")
            return ConversationHandler.END
        await message.reply_text("已取消")
        return ConversationHandler.END

    @handler.command(command="warp_log_force_delete", block=False, admin=True)
    async def command_warp_log_force_delete(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        uid, offset = self.get_real_uid_or_offset(update)
        message = update.effective_message
        args = self.get_args(context)
        if not args:
            await message.reply_text("请指定用户ID")
            return
        try:
            cid = int(args[0])
            if cid < 0:
                raise ValueError("Invalid cid")
            player_id = await self.get_player_id(cid, uid, offset)
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
    async def command_start_export(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        uid, offset = self.get_real_uid_or_offset(update)
        message = update.effective_message
        user = update.effective_user
        logger.info("用户 %s[%s] 导出跃迁记录命令请求", user.full_name, user.id)
        try:
            await message.reply_chat_action(ChatAction.TYPING)
            player_id = await self.get_player_id(user.id, uid, offset)
            path = await self.gacha_log.gacha_log_to_srgf(str(user.id), str(player_id))
            await message.reply_chat_action(ChatAction.UPLOAD_DOCUMENT)
            await message.reply_document(document=open(path, "rb+"), caption=f"跃迁记录导出文件 - SRGF {SRGF_VERSION}")
        except GachaLogNotFound:
            logger.info("未找到用户 %s[%s] 的跃迁记录", user.full_name, user.id)
            buttons = [
                [InlineKeyboardButton("点我导入", url=create_deep_linked_url(context.bot.username, "warp_log_import"))]
            ]
            await message.reply_text(WISHLOG_NOT_FOUND, reply_markup=InlineKeyboardMarkup(buttons))
        except GachaLogAccountNotFound:
            await message.reply_text("导入失败，可能文件包含的跃迁记录所属 uid 与你当前绑定的 uid 不同")
        except GachaLogFileError:
            await message.reply_text("导入失败，数据格式错误")
        except PlayerNotFoundError:
            logger.info("未查询到用户 %s[%s] 所绑定的账号信息", user.full_name, user.id)
            await message.reply_text(config.notice.user_not_found)

    async def rander_wish_log_analysis(
        self, user_id: int, player_id: int, pool_type: StarRailBannerType
    ) -> Union[str, "RenderResult"]:
        data = await self.gacha_log.get_analysis(user_id, player_id, pool_type, self.assets_service)
        if isinstance(data, str):
            return data
        await self.add_theme_data(data, player_id)
        png_data = await self.template_service.render(
            "starrail/gacha_log/gacha_log.html",
            data,
            full_page=True,
            file_type=FileType.DOCUMENT if len(data.get("fiveLog")) > 300 else FileType.PHOTO,
            query_selector=".body_box",
        )
        return png_data

    @staticmethod
    def gen_button(user_id: int, uid: int, info: "GachaLogInfo") -> List[List[InlineKeyboardButton]]:
        buttons = []
        pools = []
        skip_pools = []
        for k, v in info.item_list.items():
            if k in skip_pools:
                continue
            if not v:
                continue
            pools.append(k)
        # 2 个一组
        for i in range(0, len(pools), 2):
            row = []
            for pool in pools[i : i + 2]:
                for k, v in {"log": "", "count": "（按卡池）"}.items():
                    row.append(
                        InlineKeyboardButton(
                            f"{pool.replace('祈愿', '')}{v}",
                            callback_data=f"get_wish_log|{user_id}|{uid}|{k}|{pool}",
                        )
                    )
            buttons.append(row)
        buttons.append([InlineKeyboardButton("五星抽卡统计", callback_data=f"get_wish_log|{user_id}|{uid}|count|five")])
        return buttons

    async def wish_log_pool_choose(self, user_id: int, player_id: int, message: "Message"):
        await message.reply_chat_action(ChatAction.TYPING)
        gacha_log, status = await self.gacha_log.load_history_info(str(user_id), str(player_id))
        if not status:
            raise GachaLogNotFound
        buttons = self.gen_button(user_id, player_id, gacha_log)
        if isinstance(self.wish_photo, str):
            photo = self.wish_photo
        else:
            photo = open("resources/img/wish.jpg", "rb")
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        reply_message = await message.reply_photo(
            photo=photo,
            caption="请选择你要查询的卡池",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        if reply_message.photo:
            self.wish_photo = reply_message.photo[-1].file_id

    async def wish_log_pool_send(self, user_id: int, uid: int, pool_type: "StarRailBannerType", message: "Message"):
        await message.reply_chat_action(ChatAction.TYPING)
        png_data = await self.rander_wish_log_analysis(user_id, uid, pool_type)
        if isinstance(png_data, str):
            reply = await message.reply_text(png_data)
            if filters.ChatType.GROUPS.filter(message):
                self.add_delete_message_job(reply)
                self.add_delete_message_job(message)
        else:
            await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
            if png_data.file_type == FileType.DOCUMENT:
                await png_data.reply_document(message, filename="抽卡统计.png")
            else:
                await png_data.reply_photo(message)

    @handler.command(command="warp_log", block=False)
    @handler.message(filters=filters.Regex("^跃迁记录?(光锥|角色|常驻|新手)$"), block=False)
    async def command_start_analysis(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        user_id = await self.get_real_user_id(update)
        uid, offset = self.get_real_uid_or_offset(update)
        message = update.effective_message
        pool_type = None
        if args := self.get_args(context):
            if "角色" in args:
                pool_type = StarRailBannerType.CHARACTER
            elif "光锥" in args:
                pool_type = StarRailBannerType.WEAPON
            elif "常驻" in args:
                pool_type = StarRailBannerType.STANDARD
            elif "新手" in args:
                pool_type = StarRailBannerType.NOVICE
        self.log_user(update, logger.info, "跃迁记录命令请求 || 参数 %s", pool_type.name if pool_type else None)
        try:
            player_id = await self.get_player_id(user_id, uid, offset)
            if pool_type is None:
                await self.wish_log_pool_choose(user_id, player_id, message)
            else:
                await self.wish_log_pool_send(user_id, player_id, pool_type, message)
        except GachaLogNotFound:
            self.log_user(update, logger.info, "未找到跃迁记录")
            buttons = [
                [InlineKeyboardButton("点我导入", url=create_deep_linked_url(context.bot.username, "warp_log_import"))]
            ]
            await message.reply_text(
                WISHLOG_NOT_FOUND,
                reply_markup=InlineKeyboardMarkup(buttons),
            )

    @handler.callback_query(pattern=r"^get_wish_log\|", block=False)
    async def get_wish_log(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE") -> None:
        callback_query = update.callback_query
        user = callback_query.from_user
        message = callback_query.message

        async def get_wish_log_callback(
            callback_query_data: str,
        ) -> Tuple[str, str, int, int]:
            _data = callback_query_data.split("|")
            _user_id = int(_data[1])
            _uid = int(_data[2])
            _t = _data[3]
            _result = _data[4]
            logger.debug(
                "callback_query_data函数返回 result[%s] user_id[%s] uid[%s] show_type[%s]",
                _result,
                _user_id,
                _uid,
                _t,
            )
            return _result, _t, _user_id, _uid

        try:
            pool, show_type, user_id, uid = await get_wish_log_callback(callback_query.data)
        except IndexError:
            await callback_query.answer("按钮数据已过期，请重新获取。", show_alert=True)
            self.add_delete_message_job(message, delay=1)
            return
        if user.id != user_id:
            await callback_query.answer(text="这不是你的按钮！\n" + config.notice.user_mismatch, show_alert=True)
            return
        if show_type == "count":
            await self.get_wish_log_count(update, user_id, uid, pool)
        else:
            await self.get_wish_log_log(update, user_id, uid, pool)

    async def get_wish_log_log(self, update: "Update", user_id: int, uid: int, pool: str):
        callback_query = update.callback_query
        message = callback_query.message

        pool_type = GACHA_TYPE_LIST_REVERSE.get(pool)
        await message.reply_chat_action(ChatAction.TYPING)
        try:
            png_data = await self.rander_wish_log_analysis(user_id, uid, pool_type)
        except GachaLogNotFound:
            png_data = "未找到抽卡记录"
        if isinstance(png_data, str):
            await callback_query.answer(png_data, show_alert=True)
            self.add_delete_message_job(message, delay=1)
        else:
            await callback_query.answer(text="正在渲染图片中 请稍等 请不要重复点击按钮", show_alert=False)
            await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
            if png_data.file_type == FileType.DOCUMENT:
                await png_data.reply_document(message, filename="抽卡统计.png")
                self.add_delete_message_job(message, delay=1)
            else:
                await png_data.edit_media(message)

    async def get_wish_log_count(self, update: "Update", user_id: int, uid: int, pool: str):
        callback_query = update.callback_query
        message = callback_query.message

        all_five = pool == "five"
        group = filters.ChatType.GROUPS.filter(message)
        pool_type = GACHA_TYPE_LIST_REVERSE.get(pool)
        await message.reply_chat_action(ChatAction.TYPING)
        try:
            if all_five:
                png_data = await self.gacha_log.get_all_five_analysis(user_id, uid, self.assets_service)
            else:
                png_data = await self.gacha_log.get_pool_analysis(user_id, uid, pool_type, self.assets_service, group)
        except GachaLogNotFound:
            png_data = "未找到抽卡记录"
        if isinstance(png_data, str):
            await callback_query.answer(png_data, show_alert=True)
            self.add_delete_message_job(message, delay=1)
        else:
            await self.add_theme_data(png_data, uid)
            await callback_query.answer(text="正在渲染图片中 请稍等 请不要重复点击按钮", show_alert=False)
            document = False
            if png_data["hasMore"] and not group:
                document = True
                png_data["hasMore"] = False
            await message.reply_chat_action(ChatAction.UPLOAD_DOCUMENT if document else ChatAction.UPLOAD_PHOTO)
            png = await self.template_service.render(
                "starrail/gacha_count/gacha_count.html",
                png_data,
                full_page=True,
                query_selector=".body_box",
                file_type=FileType.DOCUMENT if document else FileType.PHOTO,
            )
            await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
            if document:
                await png.reply_document(message, filename="抽卡统计.png")
                self.add_delete_message_job(message, delay=1)
            else:
                await png.edit_media(message)

    async def add_theme_data(self, data: Dict, player_id: int):
        data["avatar"] = (await self.head_icon.get_head_icon(player_id)).as_uri()
        data["background"] = (await self.phone_theme.get_phone_theme(player_id)).as_uri()
        return data

    @staticmethod
    async def get_migrate_data(
        old_user_id: int, new_user_id: int, old_players: List["Player"]
    ) -> Optional[GachaLogMigrate]:
        return await GachaLogMigrate.create(old_user_id, new_user_id, old_players)

    async def wish_log_use_by_inline(
        self, update: "Update", context: "ContextTypes.DEFAULT_TYPE", pool_type: "StarRailBannerType"
    ):
        callback_query = update.callback_query
        user = update.effective_user
        user_id = user.id
        uid = IInlineUseData.get_uid_from_context(context)

        self.log_user(update, logger.info, "跃迁记录命令请求 || 参数 %s", pool_type.name if pool_type else None)
        notice = None
        try:
            render_result = await self.rander_wish_log_analysis(user_id, uid, pool_type)
            if isinstance(render_result, str):
                notice = render_result
            else:
                await render_result.edit_inline_media(callback_query, filename="跃迁统计.png")
        except GachaLogNotFound:
            self.log_user(update, logger.info, "未找到跃迁记录")
            notice = "未找到跃迁记录"
        if notice:
            await callback_query.answer(notice, show_alert=True)

    async def get_inline_use_data(self) -> List[Optional[IInlineUseData]]:
        types = {
            "角色": StarRailBannerType.CHARACTER,
            "武器": StarRailBannerType.WEAPON,
            "常驻": StarRailBannerType.STANDARD,
            "新手": StarRailBannerType.NOVICE,
        }
        data = []
        for k, v in types.items():
            data.append(
                IInlineUseData(
                    text=f"{k}跃迁",
                    hash=f"wish_log_{v.value}",
                    callback=partial(self.wish_log_use_by_inline, pool_type=v),
                    player=True,
                )
            )
        return data
