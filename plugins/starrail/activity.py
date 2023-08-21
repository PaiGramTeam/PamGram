import asyncio
from typing import Optional, List, Dict, TYPE_CHECKING, Any, Coroutine

from simnet.models.starrail.chronicle.activity import (
    StarRailStarFight,
    StarRailFantasticStory,
    StarRailTreasureDungeonRecord,
)
from telegram import Update, Message
from telegram.constants import ChatAction
from telegram.ext import CallbackContext, filters

from core.dependence.assets import AssetsService
from core.plugin import Plugin, handler
from core.services.template.services import TemplateService
from gram_core.services.template.models import RenderResult, RenderGroupResult
from plugins.tools.genshin import GenshinHelper
from utils.log import logger

if TYPE_CHECKING:
    from simnet import StarRailClient


__all__ = ("PlayerActivityPlugins",)


class NotSupport(Exception):
    """不支持的服务器"""


class NotHaveData(Exception):
    """没有数据"""


class PlayerActivityPlugins(Plugin):
    """玩家活动信息查询"""

    def __init__(
        self,
        template: TemplateService,
        assets: AssetsService,
        helper: GenshinHelper,
    ):
        self.template_service = template
        self.assets = assets
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

    @handler.command("star_fight", block=False)
    @handler.message(filters.Regex("^星芒战幕信息查询(.*)"), block=False)
    async def star_fight_command_start(self, update: Update, context: CallbackContext) -> Optional[int]:
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] 查询星芒战幕信息命令请求", user.full_name, user.id)
        try:
            uid = await self.get_uid(user.id, context.args, message.reply_to_message)
            async with self.helper.genshin(user.id) as client:
                render_result = await self.star_fight_render(client, uid)
        except AttributeError as exc:
            logger.error("活动数据有误")
            logger.exception(exc)
            await message.reply_text("活动数据有误 估计是彦卿晕了")
            return
        except NotHaveData:
            reply_message = await message.reply_text("没有查找到此活动数据")
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        await render_result.reply_photo(message, filename=f"{user.id}.png", allow_sending_without_reply=True)

    async def get_star_fight_rander_data(self, uid: int, data: StarRailStarFight) -> Dict:
        if not data.exists_data:
            raise NotHaveData
        avatar_icons = {}
        for record in data.records:
            for avatar in record.lineup:
                avatar_icons[avatar.id] = self.assets.avatar.square(avatar.id).as_uri()
        return {
            "uid": uid,
            "records": data.records,
            "avatar_icons": avatar_icons,
        }

    async def star_fight_render(self, client: "StarRailClient", uid: Optional[int] = None) -> RenderResult:
        if uid is None:
            uid = client.player_id

        act_data = await client.get_starrail_activity(uid)
        try:
            star_fight_data = act_data.star_fight
        except ValueError:
            raise NotHaveData
        data = await self.get_star_fight_rander_data(uid, star_fight_data)

        return await self.template_service.render(
            "starrail/activity/star_fight.html",
            data,
            {"width": 500, "height": 1200},
            full_page=True,
            query_selector="#container",
        )

    @handler.command("fantastic_story", block=False)
    @handler.message(filters.Regex("^评书奇谭信息查询(.*)"), block=False)
    async def fantastic_story_command_start(self, update: Update, context: CallbackContext) -> Optional[int]:
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] 查询评书奇谭信息命令请求", user.full_name, user.id)
        try:
            uid = await self.get_uid(user.id, context.args, message.reply_to_message)
            async with self.helper.genshin(user.id) as client:
                render_result = await self.fantastic_story_render(client, uid)
        except AttributeError as exc:
            logger.error("活动数据有误")
            logger.exception(exc)
            await message.reply_text("活动数据有误 估计是彦卿晕了")
            return
        except NotHaveData:
            reply_message = await message.reply_text("没有查找到此活动数据")
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        await render_result.reply_photo(message, filename=f"{user.id}.png", allow_sending_without_reply=True)

    async def get_fantastic_story_rander_data(self, uid: int, data: StarRailFantasticStory) -> Dict:
        if not data.exists_data:
            raise NotHaveData
        avatar_icons = {}
        for record in data.records:
            for avatar in record.avatars:
                avatar_icons[avatar.id] = self.assets.avatar.square(avatar.id).as_uri()
        return {
            "uid": uid,
            "records": data.records,
            "avatar_icons": avatar_icons,
        }

    async def fantastic_story_render(self, client: "StarRailClient", uid: Optional[int] = None) -> RenderResult:
        if uid is None:
            uid = client.player_id

        act_data = await client.get_starrail_activity(uid)
        try:
            fantastic_story_data = act_data.fantastic_story
        except ValueError:
            raise NotHaveData
        data = await self.get_fantastic_story_rander_data(uid, fantastic_story_data)

        return await self.template_service.render(
            "starrail/activity/fantastic_story.html",
            data,
            {"width": 500, "height": 1200},
            full_page=True,
            query_selector="#container",
        )

    @handler.command("treasure_dungeon", block=False)
    @handler.message(filters.Regex("^地城探宝信息查询(.*)"), block=False)
    async def treasure_dungeon_command_start(self, update: Update, context: CallbackContext) -> Optional[int]:
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] 查询地城探宝信息命令请求", user.full_name, user.id)
        try:
            uid = await self.get_uid(user.id, context.args, message.reply_to_message)
            async with self.helper.genshin(user.id) as client:
                render_result = await self.treasure_dungeon_render(client, uid)
                if render_result is None:
                    raise NotHaveData
        except AttributeError as exc:
            logger.error("活动数据有误")
            logger.exception(exc)
            await message.reply_text("活动数据有误 估计是彦卿晕了")
            return
        except NotHaveData:
            reply_message = await message.reply_text("没有查找到此活动数据")
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        await RenderGroupResult(results=render_result).reply_media_group(
            message, allow_sending_without_reply=True, write_timeout=60
        )
        logger.info("用户 %s[%s] [bold]地城探宝信息数据[/bold]: 成功发送图片", user.full_name, user.id, extra={"markup": True})

    async def treasure_dungeon_render(self, client: "StarRailClient", uid: Optional[int] = None) -> List[RenderResult]:
        if uid is None:
            uid = client.player_id

        act_data = await client.get_starrail_activity(uid)
        try:
            data = act_data.treasure_dungeon
            if not data.exists_data:
                raise NotHaveData
            if all(record.finish_time is None for record in data.records):
                raise NotHaveData
        except ValueError:
            raise NotHaveData

        avatar_icons = {}
        for record in data.records:
            for avatar in record.avatars:
                avatar_icons[avatar.id] = self.assets.avatar.icon(avatar.id).as_uri()

        def render(record: StarRailTreasureDungeonRecord) -> Coroutine[Any, Any, RenderResult]:
            render_data = {
                "uid": uid,
                "record": record,
                "avatar_icons": avatar_icons,
            }
            return self.template_service.render(
                "starrail/activity/treasure_dungeon.html",
                render_data,
                {"width": 500, "height": 762},
                full_page=True,
                query_selector="#container",
            )

        tasks = [render(record) for record in data.records if record.finish_time is not None]
        if len(tasks) == 1:
            return [await tasks[0]]
        return await asyncio.gather(*tasks)
