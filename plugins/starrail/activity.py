import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiofiles
import ujson
from simnet.models.starrail.chronicle.activity import StarRailActivity
from telegram.ext import filters

from gram_core.plugin import Plugin, handler
from plugins.tools.genshin import GenshinHelper
from utils.log import logger
from pydantic import BaseModel

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

    from simnet import StarRailClient

data_path = Path("data") / "apihelper" / "activity"
data_path.mkdir(parents=True, exist_ok=True)


class ActivityUserModel(BaseModel):
    uid: str = "0"
    lang: str = "zh-cn"
    region_time_zone: int = 8
    export_time: str = ""
    export_timestamp: int = 0
    export_app: str = "PamGram"
    export_app_version: str = "4.0"

    def __init__(self, **data: Any):
        super().__init__(**data)
        if not self.export_time:
            self.export_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.export_timestamp = int(datetime.datetime.now().timestamp())


class ActivityModel(StarRailActivity):

    info: ActivityUserModel


class NotHaveData(Exception):
    """没有数据"""

    MSG = "没有查找到活动数据"


class PlayerActivityPlugins(Plugin):
    """玩家活动信息查询"""

    def __init__(
        self,
        helper: GenshinHelper,
    ):
        self.helper = helper

    @handler.command("activity_export", block=False)
    @handler.message(filters.Regex("^活动数据导出(.*)"), block=False)
    async def activity_export(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE"):
        user_id = await self.get_real_user_id(update)
        message = update.effective_message
        uid, offset = self.get_real_uid_or_offset(update)
        self.log_user(update, logger.info, "导出活动数据命令请求")
        try:
            async with self.helper.genshin_or_public(user_id, uid=uid, offset=offset) as client:
                client: "StarRailClient"
                uid = client.player_id
                data = await client.get_starrail_activity()
                if not data.activities:
                    raise NotHaveData()
                export_data = ActivityModel(info=ActivityUserModel(uid=str(uid)), **data.dict())
        except NotHaveData as e:
            reply_message = await message.reply_text(e.MSG)
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        filename = data_path / f"{uid}.json"
        async with aiofiles.open(filename, "w", encoding="utf-8") as f:
            await f.write(ujson.dumps(export_data.dict(), indent=4, ensure_ascii=False))

        await message.reply_document(
            document=filename,
            filename=f"{uid}.json",
            caption="活动数据导出成功",
        )
