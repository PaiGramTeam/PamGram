"""混沌回忆数据查询"""
import asyncio
import re
from functools import lru_cache
from typing import Any, List, Optional, Tuple, Union, TYPE_CHECKING

from arkowrapper import ArkoWrapper
from pytz import timezone
from telegram import Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import CallbackContext, filters

from core.dependence.assets import AssetsService
from core.plugin import Plugin, handler
from core.services.cookies.error import TooManyRequestPublicCookies
from core.services.template.models import RenderGroupResult, RenderResult
from core.services.template.services import TemplateService
from plugins.tools.genshin import GenshinHelper
from utils.log import logger
from utils.uid import mask_number

try:
    import ujson as jsonlib

except ImportError:
    import json as jsonlib

if TYPE_CHECKING:
    from simnet import StarRailClient


TZ = timezone("Asia/Shanghai")
cmd_pattern = r"(?i)^/challenge(?:@[\w]+)?\s*((?:\d+)|(?:all))?\s*(pre)?"
msg_pattern = r"^混沌回忆数据((?:查询)|(?:总览))(上期)?\D?(\d*)?.*?$"


@lru_cache
def get_args(text: str) -> Tuple[int, bool, bool]:
    if text.startswith("/"):
        result = re.match(cmd_pattern, text).groups()
        try:
            floor = int(result[0] or 0)
        except ValueError:
            floor = 0
        return floor, result[0] == "all", bool(result[1])
    result = re.match(msg_pattern, text).groups()
    return int(result[2] or 0), result[0] == "总览", result[1] == "上期"


class AbyssUnlocked(Exception):
    """根本没动"""


class ChallengePlugin(Plugin):
    """混沌回忆数据查询"""

    def __init__(
        self,
        template: TemplateService,
        helper: GenshinHelper,
        assets_service: AssetsService,
    ):
        self.template_service = template
        self.helper = helper
        self.assets_service = assets_service

    async def get_uid(self, user_id: int, args: List[str], reply: Optional[Message]) -> int:
        """通过消息获取 uid，优先级：args > reply > self"""
        uid, user_id_ = None, user_id
        if args:
            for i in args:
                if i is not None:
                    if i.isdigit() and len(i) == 9:
                        uid = int(i)
        if reply:
            try:
                user_id_ = reply.from_user.id
            except AttributeError:
                pass
        if not uid:
            player_info = await self.helper.players_service.get_player(user_id_)
            if player_info is not None:
                uid = player_info.player_id
            if (not uid) and (user_id_ != user_id):
                player_info = await self.helper.players_service.get_player(user_id)
                if player_info is not None:
                    uid = player_info.player_id
        return uid

    @handler.command("challenge", block=False)
    @handler.message(filters.Regex(msg_pattern), block=False)
    async def command_start(self, update: Update, context: CallbackContext) -> None:
        user = update.effective_user
        message = update.effective_message
        uid: int = await self.get_uid(user.id, context.args, message.reply_to_message)

        # 若查询帮助
        if (message.text.startswith("/") and "help" in message.text) or "帮助" in message.text:
            await message.reply_text(
                "<b>混沌回忆数据</b>功能使用帮助（中括号表示可选参数）\n\n"
                "指令格式：\n<code>/challenge + [层数/all] + [pre]</code>\n（<code>pre</code>表示上期）\n\n"
                "文本格式：\n<code>混沌回忆数据 + 查询/总览 + [上期] + [层数]</code> \n\n"
                "例如以下指令都正确：\n"
                "<code>/challenge</code>\n<code>/challenge 1 pre</code>\n<code>/challenge all pre</code>\n"
                "<code>混沌回忆数据查询</code>\n<code>混沌回忆数据查询上期第1层</code>\n<code>混沌回忆数据总览上期</code>",
                parse_mode=ParseMode.HTML,
            )
            logger.info("用户 %s[%s] 查询[bold]混沌回忆数据[/bold]帮助", user.full_name, user.id, extra={"markup": True})
            return

        # 解析参数
        floor, total, previous = get_args(message.text)

        if floor > 10 or floor < 0:
            reply_msg = await message.reply_text("混沌回忆层数输入错误，请重新输入。支持的参数为： 1-10 或 all")
            if filters.ChatType.GROUPS.filter(message):
                self.add_delete_message_job(reply_msg)
                self.add_delete_message_job(message)
            return

        logger.info(
            "用户 %s[%s] [bold]混沌回忆挑战数据[/bold]请求: floor=%s total=%s previous=%s",
            user.full_name,
            user.id,
            floor,
            total,
            previous,
            extra={"markup": True},
        )

        async def reply_message_func(content: str) -> None:
            _reply_msg = await message.reply_text(f"开拓者 (<code>{uid}</code>) {content}", parse_mode=ParseMode.HTML)

        reply_text: Optional[Message] = None

        try:
            async with self.helper.genshin_or_public(user.id, uid=uid) as client:
                if total:
                    reply_text = await message.reply_text("彦卿需要时间整理混沌回忆数据，还请耐心等待哦~")
                await message.reply_chat_action(ChatAction.TYPING)
                images = await self.get_rendered_pic(client, uid, floor, total, previous)
        except TooManyRequestPublicCookies:
            reply_message = await message.reply_text("查询次数太多，请您稍后重试")
            if filters.ChatType.GROUPS.filter(message):
                self.add_delete_message_job(reply_message)
                self.add_delete_message_job(message)
            return
        except AbyssUnlocked:  # 若混沌回忆未解锁
            await reply_message_func("还未解锁混沌回忆哦~")
            return
        except IndexError:  # 若混沌回忆为挑战此层
            await reply_message_func("还没有挑战本层呢，咕咕咕~")
            return
        if images is None:
            await reply_message_func(f"还没有第 {floor} 层的挑战数据")
            return

        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)

        for group in ArkoWrapper(images).group(10):  # 每 10 张图片分一个组
            await RenderGroupResult(results=group).reply_media_group(
                message, allow_sending_without_reply=True, write_timeout=60
            )

        if reply_text is not None:
            await reply_text.delete()

        logger.info("用户 %s[%s] [bold]混沌回忆挑战数据[/bold]: 成功发送图片", user.full_name, user.id, extra={"markup": True})

    @staticmethod
    def get_floor_data(abyss_data, floor: int):
        try:
            floor_data = abyss_data.floors[-floor]
        except IndexError:
            floor_data = None
        if not floor_data:
            raise AbyssUnlocked()
        render_data = {
            "floor": floor_data,
            "floor_time": floor_data.node_1.challenge_time.datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "floor_nodes": [floor_data.node_1, floor_data.node_2],
            "floor_num": floor,
        }
        return render_data

    @staticmethod
    def get_avatar_data(avatars, floor_nodes):
        avatar_data = {i.id: sum([j.is_unlocked for j in i.ranks]) for i in avatars.avatar_list}
        for node in floor_nodes:
            for c in node.avatars:
                if c.id not in avatar_data:
                    avatar_data[c.id] = 0
        return avatar_data

    async def get_rendered_pic(
        self, client: "StarRailClient", uid: int, floor: int, total: bool, previous: bool
    ) -> Union[
        Tuple[
            Union[BaseException, Any],
            Union[BaseException, Any],
            Union[BaseException, Any],
            Union[BaseException, Any],
            Union[BaseException, Any],
        ],
        List[RenderResult],
        None,
    ]:
        """
        获取渲染后的图片

        Args:
            client (Client): 获取 genshin 数据的 client
            uid (int): 需要查询的 uid
            floor (int): 层数
            total (bool): 是否为总览
            previous (bool): 是否为上期

        Returns:
            bytes格式的图片
        """

        abyss_data = await client.get_starrail_challenge(uid, previous=previous, lang="zh-cn")
        if not abyss_data.has_data:
            raise AbyssUnlocked()
        start_time = abyss_data.begin_time.datetime.astimezone(TZ)
        time = start_time.strftime("%Y年%m月") + ("上" if start_time.day <= 15 else "下")
        total_stars = f"{abyss_data.total_stars}"

        render_data = {
            "time": time,
            "stars": total_stars,
            "uid": mask_number(uid),
            "max_floor": abyss_data.max_floor,
            "total_battles": abyss_data.total_battles,
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
            },
        }
        if total:

            def floor_task(floor_index: int):
                _abyss_data = self.get_floor_data(abyss_data, floor_index)
                _abyss_data["avatar_data"] = self.get_avatar_data(avatars, _abyss_data["floor_nodes"])
                return (
                    floor_index,
                    self.template_service.render(
                        "starrail/abyss/floor.html",
                        {
                            **render_data,
                            **_abyss_data,
                        },
                        viewport={"width": 690, "height": 500},
                        full_page=True,
                        ttl=15 * 24 * 60 * 60,
                    ),
                )

            render_inputs = []
            avatars = await client.get_starrail_characters(uid, lang="zh-cn")
            floors = abyss_data.floors[::-1]
            for i, f in enumerate(floors):
                render_inputs.append(floor_task(i + 1))

            render_group_inputs = list(map(lambda x: x[1], sorted(render_inputs, key=lambda x: x[0])))

            return await asyncio.gather(*render_group_inputs)

        if floor < 1:
            return [
                await self.template_service.render(
                    "starrail/abyss/overview.html", render_data, viewport={"width": 750, "height": 250}
                )
            ]
        try:
            floor_data = abyss_data.floors[-floor]
        except IndexError:
            floor_data = None
        if not floor_data:
            raise AbyssUnlocked()
        avatars = await client.get_starrail_characters(uid, lang="zh-cn")
        render_data.update(self.get_floor_data(abyss_data, floor))
        render_data["avatar_data"] = self.get_avatar_data(avatars, render_data["floor_nodes"])
        return [
            await self.template_service.render(
                "starrail/abyss/floor.html", render_data, viewport={"width": 690, "height": 500}
            )
        ]
