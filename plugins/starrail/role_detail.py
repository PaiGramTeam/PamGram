import os
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, Any, List, Optional

from pydantic import BaseModel
from simnet.errors import BadRequest as SimnetBadRequest, DataNotPublic
from simnet.models.starrail.chronicle.characters import StarRailDetailCharacters, PropertyInfo, RecommendProperty
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


class RelicScoreData(BaseModel, frozen=False):
    """遗物评分数据"""

    id: int
    count: int
    name: str
    icon: str
    property_name_relic: str


class RelicScore(BaseModel, frozen=False):
    """遗物评分"""

    ids: List[int]
    count: int = 0
    data: List[RelicScoreData]
    is_custom: bool = False

    @property
    def names(self) -> List[str]:
        return [i.property_name_relic for i in self.data]

    def add(self, id_: int, times: int) -> None:
        self.count += times
        for i in self.data:
            if i.id == id_:
                i.count += times
                break


class RoleDetailPlugin(Plugin):
    """角色详细信息查询"""

    BASE_TYPE_EN = {
        1: "Destruction",  # 毁灭
        2: "Hunt",  # 巡猎
        3: "Erudition",  # 智识
        4: "Harmony",  # 同协
        5: "Nihility",  # 虚无
        6: "Preservation",  # 存护
        7: "Abundance",  # 丰饶
    }

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
    def process_property(data: "StarRailDetailCharacters", index: int, score: RelicScore) -> List[List[Dict[str, Any]]]:
        """处理角色属性"""
        char = data.avatar_list[index].properties
        properties_map = RoleDetailPlugin.get_properties_map(data)
        data = []
        for i in char:
            info = properties_map[i.property_type]
            new_data = i.dict()
            new_data["show_add"] = i.show_add
            new_data["highlight"] = info.property_name_relic in score.names
            new_data["name"] = info.property_name_relic
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
    def process_relics(data: "StarRailDetailCharacters", index: int, score: RelicScore) -> List[Dict[str, Any]]:
        """处理角色遗物"""
        properties_map = RoleDetailPlugin.get_properties_map(data)

        def process_relic_prop(_data: Dict[str, Any]) -> None:
            info = properties_map[_data["property_type"]]
            _data["highlight"] = info.property_type in score.ids
            _data["name"] = info.property_name_relic
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
            # 计算遗物评分
            for j in i.properties:
                if j.property_type in score.ids:
                    score.add(j.property_type, j.times)
        for i in range(1, 7):
            if i not in data_map:
                data_map[i] = {"has_data": False}
        data_map1 = sorted(data_map.items(), key=lambda x: x[0])
        return [i[1] for i in data_map1]

    @staticmethod
    def process_char(data: "StarRailDetailCharacters", index: int) -> Dict[str, Any]:
        char = data.avatar_list[index]
        data = char.dict()
        data["path"] = RoleDetailPlugin.BASE_TYPE_EN[char.base_type]
        data["skills_map"] = [[j.dict() for j in i] for i in char.skills_map]
        data["skills_main"] = [i.dict() for i in char.skills_main]
        data["skills_single"] = [i.dict() for i in char.skills_single]
        return data

    @staticmethod
    def process_score(data: "StarRailDetailCharacters", char_id: int) -> RelicScore:
        properties_map = RoleDetailPlugin.get_properties_map(data)
        info = data.get_recommend_property_by_cid(char_id)
        if info.is_custom_property_valid:
            ids = info.custom_relic_properties
        else:
            ids = info.recommend_relic_properties
        return RelicScore(
            ids=ids,
            count=0,
            data=[
                RelicScoreData(
                    id=i,
                    count=0,
                    name=properties_map[i].property_name_filter,
                    icon=properties_map[i].icon,
                    property_name_relic=properties_map[i].property_name_relic,
                ) for i in ids
            ],
            is_custom=info.is_custom_property_valid,
        )

    @handler.command(command="role_detail", block=False)
    async def command_start(self, update: Update, context: CallbackContext) -> None:
        user = update.effective_user
        message = update.effective_message

        logger.info("用户 %s[%s] 查询角色详细信息", user.full_name, user.id)
        await message.reply_chat_action(ChatAction.TYPING)
        async with self.helper.genshin(user.id) as client:
            client: "StarRailClient"
            data = await client.get_starrail_characters()
            index = 3
            char = self.process_char(data, index)
            score = self.process_score(data, char["id"])
            properties = self.process_property(data, index, score)
            relics = self.process_relics(data, index, score)
            final = {"char": char, "properties": properties, "relics": relics, "score": score.dict()}
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        render_result = await self.template_service.render(
            "starrail/role_detail/main.jinja2",
            final,
            {"width": 1920, "height": 1080},
            full_page=True,
            query_selector=".pc-role-detail-num",
        )
        await render_result.reply_photo(message, filename=f"{client.player_id}.png", allow_sending_without_reply=True)
