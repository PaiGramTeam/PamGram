import asyncio
import math
from typing import Optional, List, Dict, TYPE_CHECKING, Any, Coroutine, Tuple

from simnet.models.starrail.chronicle.activity import (
    StarRailFantasticStory,
    StarRailTreasureDungeonRecord,
    StarRailFoxStoryTeam,
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
from utils.uid import mask_number

if TYPE_CHECKING:
    from simnet import StarRailClient


__all__ = ("PlayerActivityPlugins",)
ACTIVITY_DATA_ERROR = "活动数据有误"
ACTIVITY_ATTR_ERROR = "活动数据有误 估计是彦卿晕了"


class NotSupport(Exception):
    """不支持的服务器"""


class NotHaveData(Exception):
    """没有数据"""

    MSG = "没有查找到此活动数据"


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

    @handler.command("fantastic_story", block=False)
    @handler.message(filters.Regex("^评书奇谭信息查询(.*)"), block=False)
    async def fantastic_story_command_start(self, update: Update, context: CallbackContext) -> Optional[int]:
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] 查询评书奇谭信息命令请求", user.full_name, user.id)
        try:
            uid = await self.get_uid(user.id, context.args, message.reply_to_message)
            async with self.helper.genshin_or_public(user.id, uid=uid) as client:
                render_result = await self.fantastic_story_render(client, uid)
        except AttributeError as exc:
            logger.error(ACTIVITY_DATA_ERROR)
            logger.exception(exc)
            await message.reply_text(ACTIVITY_ATTR_ERROR)
            return
        except NotHaveData as e:
            reply_message = await message.reply_text(e.MSG)
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
            "uid": mask_number(uid),
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

    @handler.command("yitai_battle", block=False)
    @handler.message(filters.Regex("^以太战线信息查询(.*)"), block=False)
    async def yitai_battle_command_start(self, update: Update, context: CallbackContext) -> Optional[int]:
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] 查询以太战线信息命令请求", user.full_name, user.id)
        try:
            uid = await self.get_uid(user.id, context.args, message.reply_to_message)
            async with self.helper.genshin_or_public(user.id, uid=uid) as client:
                render_result = await self.yitai_battle_render(client, uid)
        except AttributeError as exc:
            logger.error(ACTIVITY_DATA_ERROR)
            logger.exception(exc)
            await message.reply_text(ACTIVITY_ATTR_ERROR)
            return
        except NotHaveData as e:
            reply_message = await message.reply_text(e.MSG)
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        await render_result.reply_photo(message, filename=f"{user.id}.png", allow_sending_without_reply=True)

    async def yitai_battle_render(self, client: "StarRailClient", uid: Optional[int] = None) -> RenderResult:
        if uid is None:
            uid = client.player_id

        act_data = await client.get_starrail_activity(uid)
        try:
            yitai_battle_data = act_data.yitai_battle
            if not (yitai_battle_data.exists_data and yitai_battle_data.info.exists_data):
                raise NotHaveData
        except ValueError:
            raise NotHaveData
        data = {
            "uid": mask_number(uid),
            "data": yitai_battle_data.info,
        }

        return await self.template_service.render(
            "starrail/activity/yitai.html",
            data,
            {"width": 960, "height": 1000},
            full_page=True,
            query_selector="#DIV_1",
        )

    @handler.command("endless_side", block=False)
    @handler.message(filters.Regex("^无尽位面信息查询(.*)"), block=False)
    async def endless_side_command_start(self, update: Update, context: CallbackContext) -> Optional[int]:
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] 查询无尽位面信息命令请求", user.full_name, user.id)
        try:
            uid = await self.get_uid(user.id, context.args, message.reply_to_message)
            async with self.helper.genshin_or_public(user.id, uid=uid) as client:
                render_result = await self.endless_side_render(client, uid)
        except AttributeError as exc:
            logger.error(ACTIVITY_DATA_ERROR)
            logger.exception(exc)
            await message.reply_text(ACTIVITY_ATTR_ERROR)
            return
        except NotHaveData as e:
            reply_message = await message.reply_text(e.MSG)
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        await render_result.reply_photo(message, filename=f"{user.id}.png", allow_sending_without_reply=True)

    async def endless_side_render(self, client: "StarRailClient", uid: Optional[int] = None) -> RenderResult:
        if uid is None:
            uid = client.player_id

        act_data = await client.get_starrail_activity(uid)
        try:
            endless_side_data = act_data.endless_side
            if not (
                endless_side_data.exists_data and endless_side_data.info.exists_data and endless_side_data.info.records
            ):
                raise NotHaveData
            if not endless_side_data.info.records[0].finished:
                raise NotHaveData
        except ValueError:
            raise NotHaveData
        data = {
            "uid": mask_number(uid),
            "info": endless_side_data.info,
        }

        return await self.template_service.render(
            "starrail/activity/endless_side.html",
            data,
            {"width": 960, "height": 1000},
            full_page=True,
            query_selector="#endless_side",
        )

    @handler.command("fox_story", block=False)
    @handler.message(filters.Regex("^狐斋志异信息查询(.*)"), block=False)
    async def fox_story_command_start(self, update: Update, context: CallbackContext) -> Optional[int]:
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] 查询狐斋志异信息命令请求", user.full_name, user.id)
        try:
            uid = await self.get_uid(user.id, context.args, message.reply_to_message)
            async with self.helper.genshin_or_public(user.id, uid=uid) as client:
                render_result = await self.fox_story_render(client, uid)
        except AttributeError as exc:
            logger.error(ACTIVITY_DATA_ERROR)
            logger.exception(exc)
            await message.reply_text(ACTIVITY_ATTR_ERROR)
            return
        except NotHaveData as e:
            reply_message = await message.reply_text(e.MSG)
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        await render_result.reply_photo(message, filename=f"{user.id}.png", allow_sending_without_reply=True)

    @staticmethod
    def line_percent(team: StarRailFoxStoryTeam) -> Tuple[float, float]:
        if team.index_arrived == 0:
            return 0, 0
        x, i = 0.0, team.index_arrived
        if i > 0:
            a = i - 1
            n = team.fans_range[i - 1]
            r = (team.fans - n) / (team.fans_range[i] - n)
            l = a + 0.5
            x = max(0.0, min(1.0, (r + l) * (2 / (2 * len(team.fans_range) - 1))))
        d = [
            2.5,
            3,
            4,
            4.5,
            5,
            5.5,
            6,
            7,
            7,
            8,
            8.5,
            9,
            9.5,
            10,
            11,
            11.5,
            12,
            13,
            13,
            14,
            14.5,
            15,
            16,
            16.5,
            17,
            18,
            19,
            20,
            20.5,
            21,
            21.5,
            22,
            22.5,
            22.5,
            22.5,
            23.5,
            24.5,
            25,
            26.5,
            27.5,
            28.5,
            29,
            30,
            31,
            31.5,
            32,
            32.5,
            32.5,
            32.5,
            33.5,
            33.5,
            33.5,
            33.5,
            33.5,
            33.5,
            33.5,
            34,
            35,
            35.5,
            36,
            37,
            37.5,
            38,
            38.5,
            38.5,
            38.5,
            38.5,
            37.5,
            37.5,
            37.5,
            36.5,
            37,
            37,
            38,
            39,
            39,
            40,
            40.5,
            41,
            42,
            42.5,
            43,
            43.5,
            43.5,
            44.5,
            44.5,
            44.5,
            45,
            45.5,
            45.5,
            46,
            47,
            47,
            48,
            48.5,
            49,
            50,
            50.5,
            51,
            52,
            52.5,
            53,
            53.5,
            53.5,
            53.5,
            53.5,
            54,
            54.5,
            55.5,
            56.5,
            58,
            59.5,
            60.5,
            61.5,
            62,
            63,
            63.5,
            64,
            65,
            65.5,
            66,
            66.5,
            66.5,
            66.5,
            66.5,
            66.5,
            66.5,
            67,
            67,
            68,
            69,
            70,
            70,
            70.5,
            71.5,
            71.5,
            71.5,
            71.5,
            71.5,
            71.5,
            71.5,
            72.5,
            72.5,
            72.5,
            73,
            73.5,
            73.5,
            74,
            74.5,
            75,
            76,
            77,
            77.5,
            78.5,
            79,
            80,
            80.5,
            81,
            81.5,
            81.5,
            81.5,
            81.5,
            81.5,
            81.5,
            81.5,
            81.5,
            81.5,
            81.5,
            81,
            80.5,
            80.5,
            81,
            81.5,
            82,
            83,
            83.5,
            84,
            84.5,
            85,
            86,
            86.5,
            87.5,
            88.5,
            89.5,
            90.5,
            92,
            93,
            94.5,
            95.5,
            96.5,
            97.5,
            98.5,
            99.5,
            100.5,
            101.5,
            102.5,
            103.5,
            104.5,
            105.5,
            106.5,
            108,
            109,
            110.5,
            111.5,
            112.5,
            113.5,
            114.5,
            115.5,
            116.5,
            117,
            118,
            118.5,
            118.5,
            119,
            119.5,
            120,
            120.5,
            121.5,
            122.5,
            123.5,
            124.5,
            126,
            127,
            128,
            129.5,
            130.5,
            131.5,
            132.5,
            133.5,
            134.5,
            135.5,
            136,
            137,
            138,
            138,
            139,
            139.5,
            139.5,
            140.5,
            140.5,
            141,
            141.5,
            142,
            143,
            143.5,
            143.5,
            144.5,
            144.5,
            145,
            145.5,
            145.5,
            146,
            146.5,
            147,
            147.5,
            148,
            148.5,
            149,
            149.5,
            150,
            150.5,
            151,
            152,
            153,
            153.5,
            154.5,
            155.5,
            156.5,
            158,
            158.5,
        ]

        def v(t):
            e = max(0, int(t))
            if e == len(d):
                return 0
            i = min(int(math.ceil(t)), len(d) - 1)
            s = d[e]
            return (s + (d[i] - s) * (t - e)) / 162

        return x * 100, v(x * len(d)) * 100

    async def fox_story_render(self, client: "StarRailClient", uid: Optional[int] = None) -> RenderResult:
        if uid is None:
            uid = client.player_id

        act_data = await client.get_starrail_activity(uid)
        try:
            fox_story_data = act_data.fox_story
            if not fox_story_data.exists_data:
                raise NotHaveData
            fox_story_data = fox_story_data.info
            if not fox_story_data.exists_data:
                raise NotHaveData
        except ValueError:
            raise NotHaveData
        data = {
            "uid": mask_number(uid),
            "data": fox_story_data,
            "line": self.line_percent(fox_story_data.team),
        }

        return await self.template_service.render(
            "starrail/activity/fox_story.html",
            data,
            {"width": 1920, "height": 1000},
            full_page=True,
            query_selector="#fox_story",
        )

    @handler.command("boxing_show", block=False)
    @handler.message(filters.Regex("^斗技表演赛信息查询(.*)"), block=False)
    async def boxing_show_command_start(self, update: Update, context: CallbackContext) -> None:
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] 查询斗技表演赛信息命令请求", user.full_name, user.id)
        try:
            uid = await self.get_uid(user.id, context.args, message.reply_to_message)
            async with self.helper.genshin_or_public(user.id, uid=uid) as client:
                render_result = await self.boxing_show_render(client, uid)
        except AttributeError as exc:
            logger.error(ACTIVITY_DATA_ERROR)
            logger.exception(exc)
            await message.reply_text(ACTIVITY_ATTR_ERROR)
            return
        except NotHaveData as e:
            reply_message = await message.reply_text(e.MSG)
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        await render_result.reply_photo(message, filename=f"{user.id}.png", allow_sending_without_reply=True)

    async def boxing_show_render(self, client: "StarRailClient", uid: Optional[int] = None) -> RenderResult:
        if uid is None:
            uid = client.player_id

        act_data = await client.get_starrail_activity(uid)
        try:
            boxing_show_data = act_data.boxing_show
            if not (boxing_show_data.exists_data and boxing_show_data.info.exists_data and boxing_show_data.info.list):
                raise NotHaveData
            if not boxing_show_data.info.list[0].has_challenge:
                raise NotHaveData
            box_data = boxing_show_data.info.list
        except ValueError:
            raise NotHaveData
        avatar_icons = {}
        for info in box_data:
            for avatar in info.avatars_used_activity:
                avatar_icons[avatar.id] = self.assets.avatar.icon(avatar.id).as_uri()
        data = {
            "uid": mask_number(uid),
            "data": boxing_show_data.info.list,
            "avatar_icons": avatar_icons,
        }

        return await self.template_service.render(
            "starrail/activity/boxing_show.html",
            data,
            {"width": 960, "height": 1000},
            full_page=True,
            query_selector="#boxing_show",
        )

    @handler.command("treasure_dungeon", block=False)
    @handler.message(filters.Regex("^地城探宝信息查询(.*)"), block=False)
    async def treasure_dungeon_command_start(self, update: Update, context: CallbackContext) -> Optional[int]:
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] 查询地城探宝信息命令请求", user.full_name, user.id)
        try:
            uid = await self.get_uid(user.id, context.args, message.reply_to_message)
            async with self.helper.genshin_or_public(user.id, uid=uid) as client:
                render_result = await self.treasure_dungeon_render(client, uid)
                if render_result is None:
                    raise NotHaveData
        except AttributeError as exc:
            logger.error(ACTIVITY_DATA_ERROR)
            logger.exception(exc)
            await message.reply_text(ACTIVITY_ATTR_ERROR)
            return
        except NotHaveData as e:
            reply_message = await message.reply_text(e.MSG)
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
                "uid": mask_number(uid),
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
        return await asyncio.gather(*tasks)  # noqa

    @handler.command("copper_man", block=False)
    @handler.message(filters.Regex("^金人巷信息查询(.*)"), block=False)
    async def copper_man_command_start(self, update: Update, context: CallbackContext) -> Optional[int]:
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] 查询金人巷信息命令请求", user.full_name, user.id)
        try:
            uid = await self.get_uid(user.id, context.args, message.reply_to_message)
            async with self.helper.genshin_or_public(user.id, uid=uid) as client:
                render_result = await self.copper_man_render(client, uid)
        except AttributeError as exc:
            logger.error(ACTIVITY_DATA_ERROR)
            logger.exception(exc)
            await message.reply_text(ACTIVITY_ATTR_ERROR)
            return
        except NotHaveData as e:
            reply_message = await message.reply_text(e.MSG)
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        await render_result.reply_photo(message, filename=f"{user.id}.png", allow_sending_without_reply=True)

    async def copper_man_render(self, client: "StarRailClient", uid: Optional[int] = None) -> RenderResult:
        if uid is None:
            uid = client.player_id

        act_data = await client.get_starrail_resident(uid)
        try:
            copper_man_data = act_data.copper_man
            if not copper_man_data.base.exists_data:
                raise ValueError
            if not copper_man_data.info.exists_data:
                raise ValueError
        except ValueError:
            raise NotHaveData
        data = {
            "uid": mask_number(uid),
            "basic": copper_man_data.info.basic,
            "shops": copper_man_data.info.shops[:-1],
            "last_shop": copper_man_data.info.shops[-1],
        }

        return await self.template_service.render(
            "starrail/activity/copper_man.html",
            data,
            {"width": 500, "height": 1200},
            full_page=True,
            query_selector="#container",
        )
