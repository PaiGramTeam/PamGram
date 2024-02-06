from typing import TYPE_CHECKING, Dict, Any, List, Tuple, Optional

from pydantic import BaseModel
from simnet.models.starrail.chronicle.characters import StarRailDetailCharacters, PropertyInfo, StarRailDetailCharacter, \
    RecommendProperty
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import CallbackContext, filters

from core.plugin import Plugin, handler
from core.services.template.services import TemplateService
from gram_core.dependence.redisdb import RedisDB
from metadata.shortname import roleToName
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
        template_service: TemplateService,
        redis: RedisDB,
    ):
        self.template_service = template_service
        self.helper = helper
        self.qname = "plugins:role_detail"
        self.redis = redis.client
        self.expire = 15 * 60  # 15分钟

    async def set_characters_for_redis(
        self,
        uid: int,
        nickname: str,
        data: "StarRailDetailCharacters",
    ) -> None:
        nickname_k, data_k = f"{self.qname}:{uid}:nickname", f"{self.qname}:{uid}:data"
        json_data = data.json(by_alias=True)
        await self.redis.set(nickname_k, nickname, ex=self.expire)
        await self.redis.set(data_k, json_data, ex=self.expire)

    async def get_characters_for_redis(
        self,
        uid: int,
    ) -> Tuple[Optional[str], Optional["StarRailDetailCharacters"]]:
        nickname_k, data_k = f"{self.qname}:{uid}:nickname", f"{self.qname}:{uid}:data"
        nickname_v, data_v = await self.redis.get(nickname_k), await self.redis.get(data_k)
        if nickname_v is None or data_v is None:
            return None, None
        nickname = str(nickname_v, encoding="utf-8")
        json_data = str(data_v, encoding="utf-8")
        return nickname, StarRailDetailCharacters.parse_raw(json_data)

    async def get_characters(self, client: "StarRailClient") -> Tuple[Optional[str], Optional["StarRailDetailCharacters"]]:
        nickname, data = await self.get_characters_for_redis(client.player_id)
        if nickname is None or data is None:
            data = await client.get_starrail_characters()
            nickname = (await client.get_starrail_user()).info.nickname
            await self.set_characters_for_redis(client.player_id, nickname, data)
        return nickname, data

    @staticmethod
    def get_properties_map(data: "StarRailDetailCharacters") -> Dict[int, "PropertyInfo"]:
        properties_map: Dict[int, "PropertyInfo"] = {}
        for i in data.property_info:
            properties_map[i.property_type] = i
        return properties_map

    @staticmethod
    def process_property(properties_map: Dict[int, "PropertyInfo"], char: "StarRailDetailCharacter", score: RelicScore) -> List[List[Dict[str, Any]]]:
        """处理角色属性"""
        data = []
        for i in char.properties:
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
    def process_relics(properties_map: Dict[int, "PropertyInfo"], char: "StarRailDetailCharacter", score: RelicScore) -> List[Dict[str, Any]]:
        """处理角色遗物"""
        def process_relic_prop(_data: Dict[str, Any]) -> None:
            info = properties_map[_data["property_type"]]
            _data["highlight"] = info.property_type in score.ids
            _data["name"] = info.property_name_relic
            _data["icon"] = info.icon

        relics = char.relics
        ornaments = char.ornaments
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
    def process_char(data: "StarRailDetailCharacters", ch_name: str) -> Tuple["StarRailDetailCharacter", Dict[str, Any]]:
        for char in data.avatar_list:
            if char.name != ch_name:
                continue
            data = char.dict()
            data["path"] = RoleDetailPlugin.BASE_TYPE_EN[char.base_type]
            data["skills_map"] = [[j.dict() for j in i] for i in char.skills_map]
            data["skills_main"] = [i.dict() for i in char.skills_main]
            data["skills_single"] = [i.dict() for i in char.skills_single]
            return char, data
        raise ValueError("未找到角色")

    @staticmethod
    def process_score(properties_map: Dict[int, "PropertyInfo"], recommend_property: "RecommendProperty") -> RelicScore:
        if recommend_property.is_custom_property_valid:
            ids = recommend_property.custom_relic_properties
        else:
            ids = recommend_property.recommend_relic_properties
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
            is_custom=recommend_property.is_custom_property_valid,
        )

    def parse_render_data(self, data: "StarRailDetailCharacters", nickname: str, ch_name: str, uid: int):
        properties_map = RoleDetailPlugin.get_properties_map(data)
        char, char_data = self.process_char(data, ch_name)
        recommend_property = data.get_recommend_property_by_cid(char.id)
        score = self.process_score(properties_map, recommend_property)
        properties = self.process_property(properties_map, char, score)
        relics = self.process_relics(properties_map, char, score)
        return {
            "nickname": nickname,
            "uid": mask_number(uid),
            "char": char_data,
            "properties": properties,
            "relics": relics,
            "score": score.dict(),
        }

    @handler.command(command="role_detail", block=False)
    async def command_start(self, update: Update, context: CallbackContext) -> None:
        user = update.effective_user
        message = update.effective_message
        args = self.get_args(context)
        ch_name = None
        for i in args:
            ch_name = roleToName(i)
            if ch_name:
                break
        logger.info("用户 %s[%s] 查询角色详细信息 ch_name[%s]", user.full_name, user.id, ch_name)
        await message.reply_chat_action(ChatAction.TYPING)
        async with self.helper.genshin(user.id) as client:
            nickname, data = await self.get_characters(client)
        try:
            final = self.parse_render_data(data, nickname, ch_name, client.player_id)
        except ValueError:
            reply_message = await message.reply_text("未找到该角色")
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        render_result = await self.template_service.render(
            "starrail/role_detail/main.jinja2",
            final,
            {"width": 1920, "height": 1080},
            full_page=True,
            query_selector=".pc-role-detail-num",
        )
        await render_result.reply_photo(message, filename=f"{client.player_id}.png", allow_sending_without_reply=True)
