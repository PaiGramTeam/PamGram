"""末日幻影数据查询"""

import math
from functools import lru_cache, partial
from typing import List, Optional, Tuple, TYPE_CHECKING

from telegram import Message, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction, ParseMode
from telegram.ext import CallbackContext, filters, ContextTypes

from core.dependence.assets import AssetsService
from core.plugin import Plugin, handler
from core.services.cookies.error import TooManyRequestPublicCookies
from core.services.history_data.models import HistoryDataChallengeBoss
from core.services.history_data.services import HistoryDataChallengeBossServices
from core.services.template.models import RenderResult
from core.services.template.services import TemplateService
from gram_core.config import config
from gram_core.dependence.redisdb import RedisDB
from gram_core.plugin.methods.inline_use_data import IInlineUseData
from plugins.tools.genshin import GenshinHelper
from utils.enkanetwork import RedisCache
from utils.log import logger
from utils.uid import mask_number

try:
    import ujson as jsonlib

except ImportError:
    import json as jsonlib

if TYPE_CHECKING:
    from simnet import StarRailClient
    from simnet.models.starrail.chronicle.challenge_boss import StarRailChallengeBoss, StarRailChallengeBossGroup

cmd_pattern = r"(?i)^/challenge_boss(?:@[\w]+)?\s*((?:\d+)|(?:all))?\s*(pre)?"
msg_pattern = r"^末日幻影数据((?:查询)|(?:总览))(上期)?\D?(\d*)?.*?$"
MAX_FLOOR = 4


@lru_cache
def get_args(text: str) -> bool:
    prev = "pre" in text or "上期" in text
    return prev


class AbyssUnlocked(Exception):
    """根本没动"""


class AbyssFastPassed(Exception):
    """快速通过，无数据"""


class ChallengeBossPlugin(Plugin):
    """末日幻影数据查询"""

    def __init__(
        self,
        template: TemplateService,
        helper: GenshinHelper,
        assets_service: AssetsService,
        history_data_abyss: HistoryDataChallengeBossServices,
        redis: RedisDB,
    ):
        self.template_service = template
        self.helper = helper
        self.assets_service = assets_service
        self.history_data_abyss = history_data_abyss
        self.cache = RedisCache(redis.client, key="plugin:challenge_boss:history")

    async def get_uid(self, user_id: int, reply: Optional[Message], player_id: int, offset: int) -> int:
        """通过消息获取 uid，优先级：args > reply > self"""
        uid, user_id_ = player_id, user_id
        if reply:
            try:
                user_id_ = reply.from_user.id
            except AttributeError:
                pass
        if not uid:
            player_info = await self.helper.players_service.get_player(user_id_, offset=offset)
            if player_info is not None:
                uid = player_info.player_id
            if (not uid) and (user_id_ != user_id):
                player_info = await self.helper.players_service.get_player(user_id, offset=offset)
                if player_info is not None:
                    uid = player_info.player_id
        return uid

    @handler.command("challenge_boss", block=False)
    @handler.message(filters.Regex(msg_pattern), block=False)
    async def command_start(self, update: Update, context: CallbackContext) -> None:
        user_id = await self.get_real_user_id(update)
        uid, offset = self.get_real_uid_or_offset(update)
        args = self.get_args(context)
        message = update.effective_message
        uid: int = await self.get_uid(user_id, message.reply_to_message, uid, offset)

        # 若查询帮助
        if (message.text.startswith("/") and "help" in message.text) or "帮助" in message.text:
            await message.reply_text(
                "<b>末日幻影数据</b>功能使用帮助（中括号表示可选参数）\n\n"
                "指令格式：\n<code>/challenge_boss + [层数/all] + [pre]</code>\n（<code>pre</code>表示上期）\n\n"
                "文本格式：\n<code>末日幻影数据 + 查询/总览 + [上期] + [层数]</code> \n\n"
                "例如以下指令都正确：\n"
                "<code>/challenge_boss</code>\n<code>/challenge_boss 1 pre</code>\n<code>/challenge_boss all pre</code>\n"
                "<code>末日幻影数据查询</code>\n<code>末日幻影数据查询上期第1层</code>\n<code>末日幻影数据总览上期</code>",
                parse_mode=ParseMode.HTML,
            )
            self.log_user(update, logger.info, "查询[bold]末日幻影数据[/bold]帮助", extra={"markup": True})
            return

        # 解析参数
        previous = get_args(" ".join([i for i in args if not i.startswith("@")]))

        self.log_user(
            update,
            logger.info,
            "[bold]末日幻影挑战数据[/bold]请求: uid=%s previous=%s",
            uid,
            previous,
            extra={"markup": True},
        )

        async def reply_message_func(content: str) -> None:
            _reply_msg = await message.reply_text(f"开拓者 (<code>{uid}</code>) {content}", parse_mode=ParseMode.HTML)

        reply_text: Optional[Message] = None

        try:
            async with self.helper.genshin_or_public(user_id, uid=uid) as client:
                reply_text = await message.reply_text("彦卿需要时间整理末日幻影数据，还请耐心等待哦~")
                await message.reply_chat_action(ChatAction.TYPING)
                abyss_data, season = await self.get_rendered_pic_data(client, uid, previous)
                images = await self.get_rendered_pic(abyss_data, season, uid)
        except TooManyRequestPublicCookies:
            reply_message = await message.reply_text("查询次数太多，请您稍后重试")
            if filters.ChatType.GROUPS.filter(message):
                self.add_delete_message_job(reply_message)
                self.add_delete_message_job(message)
            return
        except AbyssUnlocked:  # 若末日幻影未解锁
            await reply_message_func("还未解锁末日幻影哦~")
            return
        except AbyssFastPassed:  # 若末日幻影已快速通过
            await reply_message_func("本层已被快速通过，无详细数据~")
            return
        except IndexError:  # 若末日幻影为挑战此层
            await reply_message_func("还没有挑战本层呢，咕咕咕~")
            return
        except ValueError as e:
            if uid:
                await reply_message_func("UID 输入错误，请重新输入")
                return
            raise e

        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        await images.reply_photo(message)

        if reply_text is not None:
            await reply_text.delete()

        self.log_user(update, logger.info, "[bold]末日幻影挑战数据[/bold]: 成功发送图片", extra={"markup": True})

    @staticmethod
    def get_floor_data(abyss_data: "StarRailChallengeBoss", floor: int):
        try:
            floor_data = abyss_data.floors[-floor]
        except IndexError:
            floor_data = None
        if not floor_data:
            raise AbyssUnlocked()
        if floor_data.is_fast:
            raise AbyssFastPassed()
        render_data = {
            "floor": floor_data,
            "floor_time": floor_data.last_update_time.datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "floor_nodes": [floor_data.node_1, floor_data.node_2],
            "floor_num": floor,
        }
        return render_data

    async def get_rendered_pic_data(
        self, client: "StarRailClient", uid: int, previous: bool
    ) -> Tuple["StarRailChallengeBoss", "StarRailChallengeBossGroup"]:
        abyss_data = await client.get_starrail_challenge_boss(uid, previous=previous, lang="zh-cn")
        group = None
        if abyss_data.has_data and abyss_data.groups:
            if previous:
                if len(abyss_data.groups) > 1:
                    group = abyss_data.groups[1]
            else:
                group = abyss_data.groups[0]
            await self.save_abyss_data(self.history_data_abyss, uid, abyss_data, group)
        return abyss_data, group

    async def get_rendered_pic(
        self,
        abyss_data: "StarRailChallengeBoss",
        season: "StarRailChallengeBossGroup",
        uid: int,
    ) -> RenderResult:
        """
        获取渲染后的图片

        Args:
            abyss_data (StarRailChallengeStory): 末日幻影数据
            season (StarRailChallengeStoryGroup): 末日幻影组数据
            uid (int): 需要查询的 uid

        Returns:
            bytes格式的图片
        """

        if not abyss_data.has_data:
            raise AbyssUnlocked()
        if not season:
            raise AbyssUnlocked()
        start_time = season.begin_time.datetime.strftime("%m月%d日 %H:%M")
        end_time = season.end_time.datetime.strftime("%m月%d日 %H:%M")
        total_stars = f"{abyss_data.total_stars}"

        render_data = {
            "title": "末日幻影",
            "start_time": start_time,
            "end_time": end_time,
            "stars": total_stars,
            "uid": mask_number(uid),
            "max_floor": abyss_data.max_floor,
            "total_battles": abyss_data.total_battles,
            "upper_boss": season.upper_boss,
            "lower_boss": season.lower_boss,
            "floor_colors": {
                1: "#374952",
                2: "#374952",
                3: "#55464B",
                4: "#55464B",
                5: "#55464B",
                6: "#1D2A5D",
                7: "#1D2A5D",
                8: "#1D2A5D",
                9: "#292B58",
                10: "#382024",
                11: "#252550",
                12: "#1D2A4A",
            },
        }

        floors_data = []
        floors = abyss_data.floors[::-1]
        for i in range(len(floors)):
            try:
                floors_data.append(self.get_floor_data(abyss_data, i + 1))
            except AbyssFastPassed:
                pass
        render_data["floors"] = floors_data
        return await self.template_service.render(
            "starrail/abyss/overview.html",
            render_data,
            viewport={"width": 2745, "height": 4000},
            query_selector=".container",
        )

    @staticmethod
    async def save_abyss_data(
        history_data_abyss: "HistoryDataChallengeBossServices",
        uid: int,
        abyss_data: "StarRailChallengeBoss",
        group: "StarRailChallengeBossGroup",
    ) -> bool:
        if not group:
            return False
        model = history_data_abyss.create(uid, abyss_data, group)
        old_data = await history_data_abyss.get_by_user_id_data_id(uid, model.data_id)
        exists = history_data_abyss.exists_data(model, old_data)
        if not exists:
            await history_data_abyss.add(model)
            return True
        return False

    async def get_abyss_data(self, uid: int):
        return await self.history_data_abyss.get_by_user_id(uid)

    @staticmethod
    def get_season_data_name(data: "HistoryDataChallengeBoss"):
        last_battles = data.boss_data.floors[0]
        start_time = last_battles.last_update_time.datetime
        time = start_time.strftime("%Y.%m.%d")
        name = ""
        if "其" in last_battles.name:
            name = last_battles.name.split("其")[0]
        honor = ""
        if data.boss_data.total_stars == 12:
            fast_count = len([i for i in data.boss_data.floors if i.is_fast])
            if data.boss_data.total_battles == (4 - fast_count):
                honor = "👑"
            num_of_characters = max(
                len(last_battles.node_1.avatars),
                len(last_battles.node_2.avatars),
            )
            if num_of_characters == 2:
                honor = "双通"
            elif num_of_characters == 1:
                honor = "单通"

        return f"{name} {time} {data.boss_data.total_stars} ★ {honor}".strip()

    async def get_session_button_data(self, user_id: int, uid: int, force: bool = False):
        redis = await self.cache.get(str(uid))
        if redis and not force:
            return redis["buttons"]
        data = await self.get_abyss_data(uid)
        data.sort(key=lambda x: x.id, reverse=True)
        abyss_data = [HistoryDataChallengeBoss.from_data(i) for i in data]
        buttons = [
            {
                "name": self.get_season_data_name(abyss_data[idx]),
                "value": f"get_challenge_boss_history|{user_id}|{uid}|{value.id}",
            }
            for idx, value in enumerate(data)
        ]
        await self.cache.set(str(uid), {"buttons": buttons})
        return buttons

    async def gen_season_button(
        self,
        user_id: int,
        uid: int,
        page: int = 1,
    ) -> List[List[InlineKeyboardButton]]:
        """生成按钮"""
        data = await self.get_session_button_data(user_id, uid)
        if not data:
            return []
        buttons = [
            InlineKeyboardButton(
                value["name"],
                callback_data=value["value"],
            )
            for value in data
        ]
        all_buttons = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        send_buttons = all_buttons[(page - 1) * 7 : page * 7]
        last_page = page - 1 if page > 1 else 0
        all_page = math.ceil(len(all_buttons) / 7)
        next_page = page + 1 if page < all_page and all_page > 1 else 0
        last_button = []
        if last_page:
            last_button.append(
                InlineKeyboardButton(
                    "<< 上一页",
                    callback_data=f"get_challenge_boss_history|{user_id}|{uid}|p_{last_page}",
                )
            )
        if last_page or next_page:
            last_button.append(
                InlineKeyboardButton(
                    f"{page}/{all_page}",
                    callback_data=f"get_challenge_boss_history|{user_id}|{uid}|empty_data",
                )
            )
        if next_page:
            last_button.append(
                InlineKeyboardButton(
                    "下一页 >>",
                    callback_data=f"get_challenge_boss_history|{user_id}|{uid}|p_{next_page}",
                )
            )
        if last_button:
            send_buttons.append(last_button)
        return send_buttons

    @handler.command("challenge_boss_history", block=False)
    @handler.message(filters.Regex(r"^末日幻影历史数据"), block=False)
    async def challenge_boss_history_command_start(self, update: Update, _: CallbackContext) -> None:
        user_id = await self.get_real_user_id(update)
        message = update.effective_message
        uid, offset = self.get_real_uid_or_offset(update)
        uid: int = await self.get_uid(user_id, message.reply_to_message, uid, offset)
        self.log_user(update, logger.info, "查询末日幻影历史数据 uid[%s]", uid)

        async with self.helper.genshin_or_public(user_id, uid=uid) as _:
            await self.get_session_button_data(user_id, uid, force=True)
            buttons = await self.gen_season_button(user_id, uid)
            if not buttons:
                await message.reply_text("还没有末日幻影历史数据哦~")
                return
        await message.reply_text("请选择要查询的末日幻影历史数据", reply_markup=InlineKeyboardMarkup(buttons))

    async def get_challenge_boss_history_page(self, update: "Update", user_id: int, uid: int, result: str):
        """翻页处理"""
        callback_query = update.callback_query

        self.log_user(update, logger.info, "切换末日幻影历史数据页 page[%s]", result)
        page = int(result.split("_")[1])
        async with self.helper.genshin_or_public(user_id) as _:
            buttons = await self.gen_season_button(user_id, uid, page)
            if not buttons:
                await callback_query.answer("还没有末日幻影历史数据哦~", show_alert=True)
                await callback_query.edit_message_text("还没有末日幻影历史数据哦~")
                return
        await callback_query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
        await callback_query.answer(f"已切换到第 {page} 页", show_alert=False)

    async def get_challenge_boss_history_floor(self, update: "Update", data_id: int):
        """渲染层数数据"""
        callback_query = update.callback_query
        message = callback_query.message
        reply = None
        if message.reply_to_message:
            reply = message.reply_to_message

        data = await self.history_data_abyss.get_by_id(data_id)
        if not data:
            await callback_query.answer("数据不存在，请尝试重新发送命令", show_alert=True)
            await callback_query.edit_message_text("数据不存在，请尝试重新发送命令~")
            return
        abyss_data = HistoryDataChallengeBoss.from_data(data)

        await callback_query.answer("正在渲染图片中 请稍等 请不要重复点击按钮", show_alert=False)

        images = await self.get_rendered_pic(abyss_data.boss_data, abyss_data.group, data.user_id)

        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)

        await images.reply_photo(reply or message)
        self.log_user(update, logger.info, "[bold]末日幻影挑战数据[/bold]: 成功发送图片", extra={"markup": True})
        self.add_delete_message_job(message, delay=1)

    @handler.callback_query(pattern=r"^get_challenge_boss_history\|", block=False)
    async def get_challenge_boss_history(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE") -> None:
        callback_query = update.callback_query
        user = callback_query.from_user

        async def get_challenge_boss_history_callback(
            callback_query_data: str,
        ) -> Tuple[str, int, int]:
            _data = callback_query_data.split("|")
            _user_id = int(_data[1])
            _uid = int(_data[2])
            _result = _data[3]
            logger.debug(
                "callback_query_data函数返回 result[%s] user_id[%s] uid[%s]",
                _result,
                _user_id,
                _uid,
            )
            return _result, _user_id, _uid

        result, user_id, uid = await get_challenge_boss_history_callback(callback_query.data)
        if user.id != user_id:
            await callback_query.answer(text="这不是你的按钮！\n" + config.notice.user_mismatch, show_alert=True)
            return
        if result == "empty_data":
            await callback_query.answer(text="此按钮不可用", show_alert=True)
            return
        if result.startswith("p_"):
            await self.get_challenge_boss_history_page(update, user_id, uid, result)
            return
        data_id = int(result)
        await self.get_challenge_boss_history_floor(update, data_id)

    async def challenge_boss_use_by_inline(
        self, update: "Update", context: "ContextTypes.DEFAULT_TYPE", previous: bool
    ):
        callback_query = update.callback_query
        user = update.effective_user
        user_id = user.id
        uid = IInlineUseData.get_uid_from_context(context)

        self.log_user(update, logger.info, "查询末日幻影挑战总览数据 previous[%s]", previous)
        notice = None
        try:
            async with self.helper.genshin_or_public(user_id, uid=uid) as client:
                if not client.public:
                    await client.get_record_cards()
                abyss_data, season = await self.get_rendered_pic_data(client, uid, previous)
                image = await self.get_rendered_pic(abyss_data, season, uid)
        except AbyssUnlocked:  # 若深渊未解锁
            notice = "还未解锁末日幻影哦~"
        except TooManyRequestPublicCookies:
            notice = "查询次数太多，请您稍后重试"

        if notice:
            await callback_query.answer(notice, show_alert=True)
            return

        await image.edit_inline_media(callback_query)

    async def get_inline_use_data(self) -> List[Optional[IInlineUseData]]:
        return [
            IInlineUseData(
                text="本期末日幻影总览",
                hash="challenge_boss_current",
                callback=partial(self.challenge_boss_use_by_inline, previous=False),
                player=True,
            ),
            IInlineUseData(
                text="上期末日幻影总览",
                hash="challenge_boss_previous",
                callback=partial(self.challenge_boss_use_by_inline, previous=True),
                player=True,
            ),
        ]
