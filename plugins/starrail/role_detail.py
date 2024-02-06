import os
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, Any, List

from simnet.errors import BadRequest as SimnetBadRequest, DataNotPublic
from simnet.models.starrail.chronicle.characters import StarRailDetailCharacters, PropertyInfo
from simnet.models.starrail.diary import StarRailDiary
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import filters, CallbackContext

from core.plugin import Plugin, handler
from core.services.cookies import CookiesService
from core.services.template.models import RenderResult
from core.services.template.services import TemplateService
from plugins.tools.genshin import GenshinHelper
from utils.log import logger
from utils.uid import mask_number

if TYPE_CHECKING:
    from simnet import StarRailClient


__all__ = ("RoleDetailPlugin",)


class RoleDetailPlugin(Plugin):
    """角色详细信息查询"""

    def __init__(
        self,
        helper: GenshinHelper,
        cookies_service: CookiesService,
        template_service: TemplateService,
    ):
        self.template_service = template_service
        self.cookies_service = cookies_service
        self.current_dir = os.getcwd()
        self.helper = helper

    @staticmethod
    def get_properties_map(data: "StarRailDetailCharacters") -> Dict[int, "PropertyInfo"]:
        properties_map: Dict[int, "PropertyInfo"] = {}
        for i in data.property_info:
            properties_map[i.property_type] = i
        return properties_map

    @staticmethod
    def process_property(data: "StarRailDetailCharacters", index: int) -> List[List[Dict[str, Any]]]:
        """处理角色属性"""
        char = data.avatar_list[index].properties
        properties_map = RoleDetailPlugin.get_properties_map(data)
        data = []
        for i in char:
            info = properties_map[i.property_type]
            new_data = i.dict()
            new_data["show_add"] = i.show_add
            new_data["name"] = info.name
            new_data["icon"] = info.icon
            data.append(new_data)
        data2 = [[], []]
        for idx, i in enumerate(data):
            if idx < 6:
                data2[0].append(i)
            else:
                data2[1].append(i)
        return data2

    @staticmethod
    def process_relics(data: "StarRailDetailCharacters", index: int) -> List[Dict[str, Any]]:
        """处理角色遗物"""
        properties_map = RoleDetailPlugin.get_properties_map(data)

        def process_relic_prop(_data: Dict[str, Any]) -> None:
            info = properties_map[_data["property_type"]]
            _data["name"] = info.name
            _data["icon"] = info.icon

        relics = data.avatar_list[index].relics
        ornaments = data.avatar_list[index].ornaments
        properties_map = RoleDetailPlugin.get_properties_map(data)
        data_map: Dict[int, Dict[str, Any]] = {}
        for i in (relics + ornaments):
            new_data = i.dict()
            new_data["has_data"] = True
            new_data["properties"].insert(0, new_data["main_property"])
            for j in new_data["properties"]:
                process_relic_prop(j)
            data_map[i.pos] = new_data
        for i in range(1, 7):
            if i not in data_map:
                data_map[i] = {"has_data": False}
        data_map1 = sorted(data_map.items(), key=lambda x: x[0])
        return [i[1] for i in data_map1]

    @handler.command(command="role_detail", block=False)
    async def command_start(self, update: Update, context: CallbackContext) -> None:
        user = update.effective_user
        message = update.effective_message

        logger.info("用户 %s[%s] 查询角色详细信息", user.full_name, user.id)
        await message.reply_chat_action(ChatAction.TYPING)
        async with self.helper.genshin(user.id) as client:
            client: "StarRailClient"
            data = await client.get_starrail_characters()
            char = data.avatar_list[3].dict()
            char["skills_map"] = [[j.dict() for j in i] for i in data.avatar_list[3].skills_map]
            char["skills_main"] = [i.dict() for i in data.avatar_list[3].skills_main]
            char["skills_single"] = [i.dict() for i in data.avatar_list[3].skills_single]
            properties = self.process_property(data, 3)
            relics = self.process_relics(data, 3)
            final = {"char": char, "properties": properties, "relics": relics}
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        render_result = await self.template_service.render(
            "starrail/role_detail/main.jinja2",
            final,
            {"width": 1000, "height": 1200},
            full_page=True,
            query_selector=".pc-role-detail-num",
        )
        await render_result.reply_photo(message, filename=f"{client.player_id}.png", allow_sending_without_reply=True)
