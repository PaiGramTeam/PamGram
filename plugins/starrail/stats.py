from typing import Optional, List, TYPE_CHECKING

from simnet.errors import BadRequest as SimnetBadRequest
from telegram import Update, Message
from telegram.constants import ChatAction
from telegram.ext import CallbackContext, filters

from core.plugin import Plugin, handler
from core.services.cookies.error import TooManyRequestPublicCookies
from core.services.template.models import RenderResult
from core.services.template.services import TemplateService
from plugins.tools.genshin import GenshinHelper
from utils.log import logger
from utils.uid import mask_number

if TYPE_CHECKING:
    from simnet import StarRailClient


__all__ = ("PlayerStatsPlugins",)


class PlayerStatsPlugins(Plugin):
    """玩家统计查询"""

    def __init__(
        self,
        template: TemplateService,
        helper: GenshinHelper,
    ):
        self.template_service = template
        self.helper = helper

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

    @handler.command("stats", block=False)
    @handler.message(filters.Regex("^玩家统计查询(.*)"), block=False)
    async def command_start(self, update: Update, context: CallbackContext) -> Optional[int]:
        user_id = await self.get_real_user_id(update)
        message = update.effective_message
        self.log_user(update, logger.info, "查询游戏用户命令请求")
        try:
            uid: int = await self.get_uid(user_id, context.args, message.reply_to_message)
            async with self.helper.genshin_or_public(user_id, uid=uid) as client:
                render_result = await self.render(client, uid)
        except TooManyRequestPublicCookies:
            await message.reply_text("用户查询次数过多 请稍后重试")
            return
        except AttributeError as exc:
            logger.error("角色数据有误")
            logger.exception(exc)
            await message.reply_text("角色数据有误 估计是彦卿晕了")
            return
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        await render_result.reply_photo(message, filename=f"{user_id}.png", allow_sending_without_reply=True)

    async def render(self, client: "StarRailClient", uid: Optional[int] = None) -> RenderResult:
        if uid is None:
            uid = client.player_id

        user_info = await client.get_starrail_user(uid)
        try:
            rogue = await client.get_starrail_rogue(uid)
        except SimnetBadRequest:
            rogue = None
        logger.debug(user_info)

        # 因为需要替换线上图片地址为本地地址，先克隆数据，避免修改原数据
        user_info = user_info.copy(deep=True)

        data = {
            "uid": mask_number(uid),
            "info": user_info.info,
            "stats": user_info.stats,
            "stats_labels": [
                ("活跃天数", "active_days"),
                ("成就达成数", "achievement_num"),
                ("获取角色数", "avatar_num"),
                ("忘却之庭", "abyss_process"),
                ("战利品开启数", "chest_num"),
            ],
            "rogue": rogue.basic_info if rogue else None,
            "rogue_labels": [
                ("技能树已激活", "unlocked_skill_points"),
                ("已解锁奇物", "unlocked_miracle_num"),
                ("已解锁祝福", "unlocked_buff_num"),
            ],
            "style": "xianzhou",  # nosec
        }

        return await self.template_service.render(
            "starrail/stats/stats.html",
            data,
            {"width": 650, "height": 440},
            full_page=True,
        )
