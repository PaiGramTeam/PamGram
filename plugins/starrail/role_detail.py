import math
from typing import TYPE_CHECKING, Dict, Any, List, Tuple, Optional, Union
from urllib.parse import quote

from pydantic import BaseModel, ValidationError
from simnet.errors import InternalDatabaseError
from simnet.models.starrail.chronicle.characters import StarRailDetailCharacters
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
    ReplyKeyboardRemove,
)
from telegram.constants import ChatAction
from telegram.ext import filters, ConversationHandler
from telegram.helpers import create_deep_linked_url

from core.plugin import Plugin, handler
from core.services.template.services import TemplateService
from core.config import config
from core.dependence.redisdb import RedisDB
from core.plugin import conversation
from metadata.shortname import roleToName, idToRole
from plugins.app.webapp import WebApp
from plugins.tools.genshin import GenshinHelper
from utils.log import logger
from utils.uid import mask_number

if TYPE_CHECKING:
    from simnet import StarRailClient
    from simnet.models.starrail.chronicle.characters import (
        PropertyInfo,
        StarRailDetailCharacter,
        RecommendProperty,
    )
    from telegram import Update
    from telegram.ext import ContextTypes
    from core.services.template.models import RenderResult

__all__ = ("RoleDetailPlugin",)


class NeedClient(Exception):
    """无缓存，需要 StarRailClient"""


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


class WebAppData(BaseModel):
    """小程序返回的数据"""

    cid: int
    custom: List[int]


SET_BY_WEB = 10100


class RoleDetailPlugin(Plugin.Conversation):
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
        self.kitsune: Optional[str] = None

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

    async def del_characters_for_redis(
        self,
        uid: int,
    ) -> None:
        nickname_k, data_k = f"{self.qname}:{uid}:nickname", f"{self.qname}:{uid}:data"
        await self.redis.delete(nickname_k, data_k)

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

    async def get_characters(
        self, uid: int, client: "StarRailClient" = None
    ) -> Tuple[Optional[str], Optional["StarRailDetailCharacters"]]:
        nickname, data = await self.get_characters_for_redis(uid)
        if nickname is None or data is None:
            if not client:
                raise NeedClient
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
    def process_property(
        properties_map: Dict[int, "PropertyInfo"], char: "StarRailDetailCharacter", score: RelicScore
    ) -> List[List[Dict[str, Any]]]:
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
    def process_relics(
        properties_map: Dict[int, "PropertyInfo"], char: "StarRailDetailCharacter", score: RelicScore
    ) -> List[Dict[str, Any]]:
        """处理角色遗物"""

        def process_relic_prop(_data: Dict[str, Any]) -> None:
            info = properties_map[_data["property_type"]]
            _data["highlight"] = info.property_type in score.ids
            _data["name"] = info.property_name_relic
            _data["icon"] = info.icon

        relics = char.relics
        ornaments = char.ornaments
        data_map: Dict[int, Dict[str, Any]] = {}
        for i in relics + ornaments:
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
    def process_char(data: "StarRailDetailCharacters", ch_id: int) -> Tuple["StarRailDetailCharacter", Dict[str, Any]]:
        for char in data.avatar_list:
            if char.id != ch_id:
                continue
            data = char.dict()
            data["path"] = RoleDetailPlugin.BASE_TYPE_EN[char.base_type]
            data["skills_map"] = [[j.dict() for j in i] for i in char.skills_map]
            data["skills_main"] = [i.dict() for i in char.skills_main]
            data["skills_single"] = [i.dict() for i in char.skills_single]
            return char, data
        raise FileNotFoundError("未找到角色")

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
                )
                for i in ids
            ],
            is_custom=recommend_property.is_custom_property_valid,
        )

    def parse_render_data(self, data: "StarRailDetailCharacters", nickname: str, ch_id: int, uid: int):
        properties_map = RoleDetailPlugin.get_properties_map(data)
        char, char_data = self.process_char(data, ch_id)
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

    @staticmethod
    def gen_button(
        data: "StarRailDetailCharacters",
        user_id: Union[str, int],
        uid: int,
        page: int = 1,
    ) -> List[List[InlineKeyboardButton]]:
        """生成按钮"""
        buttons = []

        if data.avatar_list:
            buttons = [
                InlineKeyboardButton(
                    idToRole(value.id),
                    callback_data=f"get_role_detail|{user_id}|{uid}|{idToRole(value.id)}",
                )
                for value in data.avatar_list
                if value.id
            ]
        all_buttons = [buttons[i : i + 4] for i in range(0, len(buttons), 4)]
        send_buttons = all_buttons[(page - 1) * 3 : page * 3]
        last_page = page - 1 if page > 1 else 0
        all_page = math.ceil(len(all_buttons) / 3)
        next_page = page + 1 if page < all_page and all_page > 1 else 0
        last_button = []
        if last_page:
            last_button.append(
                InlineKeyboardButton(
                    "<< 上一页",
                    callback_data=f"get_role_detail|{user_id}|{uid}|{last_page}",
                )
            )
        if last_page or next_page:
            last_button.append(
                InlineKeyboardButton(
                    f"{page}/{all_page}",
                    callback_data=f"get_role_detail|{user_id}|{uid}|empty_data",
                )
            )
        if next_page:
            last_button.append(
                InlineKeyboardButton(
                    "下一页 >>",
                    callback_data=f"get_role_detail|{user_id}|{uid}|{next_page}",
                )
            )
        if last_button:
            send_buttons.append(last_button)
        return send_buttons

    async def get_render_result(
        self, data: "StarRailDetailCharacters", nickname: str, ch_id: int, uid: int
    ) -> "RenderResult":
        final = self.parse_render_data(data, nickname, ch_id, uid)
        return await self.template_service.render(
            "starrail/role_detail/main.jinja2",
            final,
            {"width": 1920, "height": 1080},
            full_page=True,
            query_selector=".pc-role-detail-num",
        )

    @staticmethod
    def get_caption_stats(data: "StarRailDetailCharacters", character_id: int) -> List[str]:
        maps = RoleDetailPlugin.get_properties_map(data)
        tags = []

        def num(_s) -> int:
            return int(round(float(_s.replace("%", "")), 0))

        for character in data.avatar_list:
            if character.id == character_id:
                for stat in character.properties:
                    info = maps.get(stat.property_type)
                    tags.append(f"{info.name}{num(stat.final)}")

        return tags

    @staticmethod
    def get_caption(data: "StarRailDetailCharacters", character_id: int) -> str:
        tags = []
        for character in data.avatar_list:
            if character.id == character_id:
                tags.append(character.name)
                tags.append(f"等级{character.level}")
                tags.append(f"命座{character.rank}")
                if equip := character.equip:
                    tags.append(equip.name)
                    tags.append(f"武器等级{equip.level}")
                    tags.append(f"精{equip.rank}")
                tags.extend(RoleDetailPlugin.get_caption_stats(data, character_id))
                break
        return "#" + " #".join(tags)

    @handler.command(command="role_detail", block=False)
    @handler.message(filters=filters.Regex("^角色详细信息查询(.*)"), block=False)
    async def command_start(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        user_id = await self.get_real_user_id(update)
        message = update.effective_message
        args = self.get_args(context)
        ch_name = None
        for i in args:
            ch_name = roleToName(i)
            if ch_name:
                break
        self.log_user(
            update,
            logger.info,
            "角色详细信息查询命令请求 || character_name[%s]",
            ch_name,
        )
        await message.reply_chat_action(ChatAction.TYPING)
        async with self.helper.genshin(user_id) as client:
            nickname, data = await self.get_characters(client.player_id, client)
        uid = client.player_id
        if ch_name is None:
            buttons = self.gen_button(data, user_id, uid)
            if isinstance(self.kitsune, str):
                photo = self.kitsune
            else:
                photo = open("resources/img/aaa.png", "rb")
            await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
            reply_message = await message.reply_photo(
                photo=photo,
                caption=f"请选择你要查询的角色 - UID {uid}",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            if reply_message.photo:
                self.kitsune = reply_message.photo[-1].file_id
            return
        for characters in data.avatar_list:
            if idToRole(characters.id) == ch_name:
                break
        else:
            await message.reply_text(f"未在游戏中找到 {ch_name} ，请检查角色是否存在，或者等待角色数据更新后重试")
            return
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        render_result = await self.get_render_result(data, nickname, characters.id, client.player_id)
        await render_result.reply_photo(
            message,
            filename=f"{client.player_id}.png",
            allow_sending_without_reply=True,
            reply_markup=self.get_custom_button(user_id, uid, characters.id),
            caption=self.get_caption(data, characters.id),
        )

    @handler.callback_query(pattern=r"^get_role_detail\|", block=False)
    async def get_role_detail(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE") -> None:
        callback_query = update.callback_query
        user = callback_query.from_user
        message = callback_query.message

        async def get_role_detail_callback(
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

        result, user_id, uid = await get_role_detail_callback(callback_query.data)
        if user.id != user_id:
            await callback_query.answer(text="这不是你的按钮！\n" + config.notice.user_mismatch, show_alert=True)
            return
        if result == "empty_data":
            await callback_query.answer(text="此按钮不可用", show_alert=True)
            return
        page = 0
        if result.isdigit():
            page = int(result)
            logger.info(
                "用户 %s[%s] 角色详细信息查询命令请求 || page[%s] uid[%s]",
                user.full_name,
                user.id,
                page,
                uid,
            )
        else:
            logger.info(
                "用户 %s[%s] 角色详细信息查询命令请求 || character_name[%s] uid[%s]",
                user.full_name,
                user.id,
                result,
                uid,
            )
        try:
            nickname, data = await self.get_characters(uid)
        except NeedClient:
            async with self.helper.genshin(user.id) as client:
                nickname, data = await self.get_characters(client.player_id, client)
        if page:
            buttons = self.gen_button(data, user.id, uid, page)
            await message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
            await callback_query.answer(f"已切换到第 {page} 页", show_alert=False)
            return
        for characters in data.avatar_list:
            if idToRole(characters.id) == result:
                break
        else:
            await message.delete()
            await callback_query.answer(
                f"未在游戏中找到 {result} ，请检查角色是否存在，或者等待角色数据更新后重试",
                show_alert=True,
            )
            return
        await callback_query.answer(text="正在渲染图片中 请稍等 请不要重复点击按钮", show_alert=False)
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        render_result = await self.get_render_result(data, nickname, characters.id, uid)
        render_result.filename = f"role_detail_{uid}_{result}.png"
        render_result.caption = self.get_caption(data, characters.id)
        await render_result.edit_media(message, reply_markup=self.get_custom_button(user.id, uid, characters.id))

    @staticmethod
    def get_custom_button(user_id: int, uid: int, char_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton(">> 有效词条自定义 <<", callback_data=f"set_relic_prop|{user_id}|{uid}|{char_id}")]]
        )

    @handler.callback_query(pattern=r"^set_relic_prop\|", block=False)
    async def set_relic_prop_callback(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        callback_query = update.callback_query
        user = callback_query.from_user

        async def set_relic_prop_callback(
            callback_query_data: str,
        ) -> Tuple[int, int, int]:
            _data = callback_query_data.split("|")
            _user_id = int(_data[1])
            _uid = int(_data[2])
            _result = int(_data[3])
            logger.debug(
                "callback_query_data函数返回 result[%s] user_id[%s] uid[%s]",
                _result,
                _user_id,
                _uid,
            )
            return _result, _user_id, _uid

        char_id, user_id, uid = await set_relic_prop_callback(callback_query.data)
        if user.id != user_id:
            await callback_query.answer(text="这不是你的按钮！\n" + config.notice.user_mismatch, show_alert=True)
            return
        await callback_query.answer(url=create_deep_linked_url(context.bot.username, f"set_relic_prop_{uid}_{char_id}"))

    @conversation.entry_point
    @handler.command(command="start", filters=filters.Regex(r" set_relic_prop_(.*)"), block=False)
    async def start_set_relic_prop(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> int:
        user = update.effective_user
        message = update.effective_message
        args = self.get_args(context)
        uid = int(args[0].split("_")[3])
        char_id = int(args[0].split("_")[4])
        char_name = idToRole(char_id)
        logger.info(
            "用户 %s[%s] 通过start命令 进入设置遗器副属性自定义流程 uid[%s] char_id[%s]",
            user.full_name,
            user.id,
            uid,
            char_id,
        )
        try:
            nickname, data = await self.get_characters(uid)
        except NeedClient:
            async with self.helper.genshin(user.id) as client:
                nickname, data = await self.get_characters(client.player_id, client)
        rec = data.get_recommend_property_by_cid(char_id)
        if not rec:
            await message.reply_text(f"未在游戏中找到 {char_name} ，请检查角色是否存在，或者等待角色数据更新后重试")
            return ConversationHandler.END
        url = f"{config.pass_challenge_user_web}/relic_property?command=relic_property&cid={char_id}&"
        url += "recommend=" + ",".join([str(i) for i in rec.recommend_relic_properties]) + "&"
        url += "custom=" + ",".join([str(i) for i in rec.custom_relic_properties]) + "&"
        char_name_quote = quote(char_name, "utf-8")
        url += f"name={char_name_quote}"
        text = f"你好 {user.mention_markdown_v2()} {nickname} 请点击下方按钮，开始自定义 {char_name} 的遗器副属性"
        await message.reply_markdown_v2(
            text,
            reply_markup=ReplyKeyboardMarkup.from_button(
                KeyboardButton(
                    text="点我开始设置",
                    web_app=WebAppInfo(url=url),
                )
            ),
        )
        return SET_BY_WEB

    @conversation.state(state=SET_BY_WEB)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=False)
    async def set_by_web_text_role(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE") -> int:
        message = update.effective_message
        if message.text == "退出":
            await message.reply_text("退出任务", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        else:
            await message.reply_text("输入错误，请重新输入。或者回复 退出 退出任务。")
        return SET_BY_WEB

    @conversation.state(state=SET_BY_WEB)
    @handler.message(filters=filters.StatusUpdate.WEB_APP_DATA, block=False)
    async def set_by_web_role(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE") -> int:
        user = update.effective_user
        message = update.effective_message
        web_app_data = message.web_app_data
        if web_app_data:
            result = WebApp.de_web_app_data(web_app_data.data)
            if result.code == 0:
                if result.path == "relic_property":
                    try:
                        validate = WebAppData(**result.data)
                        async with self.helper.genshin(user.id) as client:
                            client: "StarRailClient"
                            await client.set_starrail_avatar_recommend_property(validate.cid, validate.custom)
                        await message.reply_text("修改自定义副属性成功。", reply_markup=ReplyKeyboardRemove())
                        await self.del_characters_for_redis(client.player_id)
                    except (ValidationError, InternalDatabaseError):
                        await message.reply_text(
                            "数据错误，请重试",
                            reply_markup=ReplyKeyboardRemove(),
                        )
            else:
                logger.warning(
                    "用户 %s[%s] WEB_APP_DATA 请求错误 [%s]%s", user.full_name, user.id, result.code, result.message
                )
                await message.reply_text(f"WebApp返回错误 {result.message}", reply_markup=ReplyKeyboardRemove())
        else:
            logger.warning("用户 %s[%s] WEB_APP_DATA 非法数据", user.full_name, user.id)
        return ConversationHandler.END
