import math
from typing import List, Tuple, Union, Optional, TYPE_CHECKING, Dict

from pydantic import BaseModel
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.constants import ChatAction
from telegram.ext import filters

from core.config import config
from core.dependence.assets import AssetsService, AssetsCouldNotFound
from core.dependence.redisdb import RedisDB
from core.plugin import Plugin, handler
from core.services.players import PlayersService
from core.services.template.services import TemplateService
from core.services.wiki.services import WikiService
from metadata.shortname import roleToName, idToRole
from modules.apihelper.client.components.player_cards import PlayerCards as PlayerCardsClient, PlayerInfo, Avatar, Relic
from modules.apihelper.client.components.remote import Remote
from modules.playercards.fight_prop import EquipmentsStats
from modules.playercards.helpers import ArtifactStatsTheory
from plugins.tools.genshin import PlayerNotFoundError
from utils.log import logger
from utils.uid import mask_number

try:
    from starrail_damage_cal.mihomo.models import Avatar as DamageAvatar
    from starrail_damage_cal.to_data import get_data as get_damage_data
    from starrail_damage_cal.cal_damage import cal_info as cal_damage_info
    from msgspec import convert as msgspec_convert

    STARRAIL_ARTIFACT_FUNCTION_AVAILABLE = True
except ImportError:
    DamageAvatar = None
    get_damage_data = None
    cal_damage_info = None
    msgspec_convert = None

    STARRAIL_ARTIFACT_FUNCTION_AVAILABLE = False

if TYPE_CHECKING:
    from telegram.ext import ContextTypes
    from telegram import Update

try:
    import ujson as jsonlib
except ImportError:
    import json as jsonlib


DEP_MSG = "自 2.0 版本开始，不再推荐使用此功能，推荐使用 /role_detail 查询角色信息。"


class PlayerCards(Plugin):
    def __init__(
        self,
        player_service: PlayersService,
        template_service: TemplateService,
        assets_service: AssetsService,
        wiki_service: WikiService,
        redis: RedisDB,
    ):
        self.player_service = player_service
        self.client = PlayerCardsClient(redis)
        self.cache = self.client.cache
        self.assets_service = assets_service
        self.template_service = template_service
        self.wiki_service = wiki_service
        self.kitsune: Optional[str] = None
        self.fight_prop_rule: Dict[str, Dict[str, float]] = {}

    async def initialize(self):
        await self.client.async_init()
        await self._refresh()

    async def _refresh(self):
        self.fight_prop_rule = await Remote.get_fight_prop_rule_data()

    async def _load_history(self, uid) -> Optional[PlayerInfo]:
        data = await self.client.player_cards_file.load_history_info(uid)
        if data is None:
            return None
        return PlayerInfo.parse_obj(data)

    async def get_uid_and_ch(
        self, user_id: int, args: List[str], reply: Optional[Message]
    ) -> Tuple[Optional[int], Optional[str]]:
        """通过消息获取 uid，优先级：args > reply > self"""
        uid, ch_name, user_id_ = None, None, user_id
        if args:
            for i in args:
                if i is not None:
                    if i.isdigit() and len(i) == 9:
                        uid = int(i)
                    else:
                        ch_name = roleToName(i)
        if reply:
            try:
                user_id_ = reply.from_user.id
            except AttributeError:
                pass
        if not uid:
            player_info = await self.player_service.get_player(user_id_)
            if player_info is not None:
                uid = player_info.player_id
            if (not uid) and (user_id_ != user_id):
                player_info = await self.player_service.get_player(user_id)
                if player_info is not None:
                    uid = player_info.player_id
        return uid, ch_name

    @staticmethod
    def get_caption_stats(character: "Avatar") -> List[str]:
        tags = []

        def num(_s) -> int:
            return int(round(float(_s.replace("%", "")), 0))

        for stat in character.property:
            tags.append(f"{stat.name}{num(stat.total)}")

        return tags

    def get_caption(self, character: "Avatar") -> str:
        tags = [idToRole(character.avatarId), f"等级{character.level}", f"命座{character.rank}"]
        if equip := character.equipment:
            weapon_detail = self.wiki_service.light_cone.get_by_id(equip.tid)
            tags.append(weapon_detail.name)
            tags.append(f"武器等级{equip.level}")
            tags.append(f"精{equip.rank}")
        tags.extend(PlayerCards.get_caption_stats(character))
        return "#" + " #".join(tags)

    @handler.command(command="player_card", player=True, block=False)
    @handler.message(filters=filters.Regex("^角色卡片查询(.*)"), player=True, block=False)
    async def player_cards(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        user_id = await self.get_real_user_id(update)
        message = update.effective_message
        args = self.get_args(context)
        await message.reply_chat_action(ChatAction.TYPING)
        uid, ch_name = await self.get_uid_and_ch(user_id, args, message.reply_to_message)
        if uid is None:
            raise PlayerNotFoundError(user_id)
        data = await self._load_history(uid)
        if data is None or len(data.avatarList) == 0:
            if isinstance(self.kitsune, str):
                photo = self.kitsune
            else:
                photo = open("resources/img/aaa.jpg", "rb")
            buttons = [
                [
                    InlineKeyboardButton(
                        "更新面板",
                        callback_data=f"update_player_card|{user_id}|{uid}",
                    )
                ]
            ]
            reply_message = await message.reply_photo(
                photo=photo,
                caption=f"角色列表未找到，请尝试点击下方按钮更新角色列表 - UID {uid}\n\n{DEP_MSG}",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            if reply_message.photo:
                self.kitsune = reply_message.photo[-1].file_id
            return
        if ch_name is not None:
            self.log_user(
                update,
                logger.info,
                "角色卡片查询命令请求 || character_name[%s] uid[%s]",
                ch_name,
                uid,
            )
        else:
            self.log_user(update, logger.info, "角色卡片查询命令请求")
            ttl = await self.cache.ttl(uid)

            buttons = self.gen_button(data, user_id, uid, update_button=ttl < 0)
            if isinstance(self.kitsune, str):
                photo = self.kitsune
            else:
                photo = open("resources/img/aaa.jpg", "rb")
            reply_message = await message.reply_photo(
                photo=photo,
                caption=f"请选择你要查询的角色 - UID {uid}\n\n{DEP_MSG}",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            if reply_message.photo:
                self.kitsune = reply_message.photo[-1].file_id
            return
        for characters in data.avatarList:
            if idToRole(characters.avatarId) == ch_name:
                break
        else:
            await message.reply_text(
                f"角色展柜中未找到 {ch_name} ，请检查角色是否存在于角色展柜中，或者等待角色数据更新后重试\n\n{DEP_MSG}"
            )
            return
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        render_result = await RenderTemplate(
            uid,
            characters,
            self.template_service,
            self.assets_service,
            self.wiki_service,
            self.client,
            self.fight_prop_rule,
        ).render()  # pylint: disable=W0631
        await render_result.reply_photo(
            message,
            filename=f"player_card_{uid}_{ch_name}.png",
            caption=self.get_caption(characters),
        )

    @handler.callback_query(pattern=r"^update_player_card\|", block=False)
    async def update_player_card(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE") -> None:
        user = update.effective_user
        message = update.effective_message
        callback_query = update.callback_query

        async def get_player_card_callback(callback_query_data: str) -> Tuple[int, int]:
            _data = callback_query_data.split("|")
            _user_id = int(_data[1])
            _uid = int(_data[2])
            logger.debug("callback_query_data函数返回 user_id[%s] uid[%s]", _user_id, _uid)
            return _user_id, _uid

        user_id, uid = await get_player_card_callback(callback_query.data)
        if user.id != user_id:
            await callback_query.answer(text="这不是你的按钮！\n" + config.notice.user_mismatch, show_alert=True)
            return

        ttl = await self.cache.ttl(uid)

        if ttl > 0:
            await callback_query.answer(text=f"请等待 {ttl} 秒后再更新", show_alert=True)
            return

        await message.reply_chat_action(ChatAction.TYPING)
        await callback_query.answer(text="正在获取角色列表 请不要重复点击按钮")
        data = await self.client.update_data(str(uid))
        if isinstance(data, str):
            await callback_query.answer(text=data, show_alert=True)
            return
        if data.avatarList is None:
            await message.delete()
            await callback_query.answer(
                "请先将角色加入到角色展柜并允许查看角色详情后再使用此功能，如果已经添加了角色，请等待角色数据更新后重试",
                show_alert=True,
            )
            return
        buttons = self.gen_button(data, user.id, uid, update_button=False)
        render_data = await self.parse_holder_data(data)
        holder = await self.template_service.render(
            "starrail/player_card/holder.html",
            render_data,
            viewport={"width": 750, "height": 380},
            ttl=60 * 10,
            caption=f"更新角色列表成功，请选择你要查询的角色 - UID {uid}\n\n{DEP_MSG}",
        )
        await holder.edit_media(message, reply_markup=InlineKeyboardMarkup(buttons))

    @handler.callback_query(pattern=r"^get_player_card\|", block=False)
    async def get_player_cards(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE") -> None:
        callback_query = update.callback_query
        user = callback_query.from_user
        message = callback_query.message

        async def get_player_card_callback(
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

        result, user_id, uid = await get_player_card_callback(callback_query.data)
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
                "用户 %s[%s] 角色卡片查询命令请求 || page[%s] uid[%s]",
                user.full_name,
                user.id,
                page,
                uid,
            )
        else:
            logger.info(
                "用户 %s[%s] 角色卡片查询命令请求 || character_name[%s] uid[%s]",
                user.full_name,
                user.id,
                result,
                uid,
            )
        data = await self._load_history(uid)
        if isinstance(data, str):
            await message.reply_text(data)
            return
        if data.avatarList is None:
            await message.delete()
            await callback_query.answer(
                "请先将角色加入到角色展柜并允许查看角色详情后再使用此功能，如果已经添加了角色，请等待角色数据更新后重试",
                show_alert=True,
            )
            return
        if page:
            buttons = self.gen_button(data, user.id, uid, page, await self.cache.ttl(uid) <= 0)
            await message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
            await callback_query.answer(f"已切换到第 {page} 页", show_alert=False)
            return
        for characters in data.avatarList:
            if idToRole(characters.avatarId) == result:
                break
        else:
            await message.delete()
            await callback_query.answer(
                f"角色展柜中未找到 {result} ，请检查角色是否存在于角色展柜中，或者等待角色数据更新后重试",
                show_alert=True,
            )
            return
        await callback_query.answer(text="正在渲染图片中 请稍等 请不要重复点击按钮", show_alert=False)
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        render_result = await RenderTemplate(
            uid,
            characters,
            self.template_service,
            self.assets_service,
            self.wiki_service,
            self.client,
            self.fight_prop_rule,
        ).render()  # pylint: disable=W0631
        render_result.filename = f"player_card_{uid}_{result}.png"
        render_result.caption = self.get_caption(characters)
        await render_result.edit_media(message)

    @staticmethod
    def gen_button(
        data: PlayerInfo,
        user_id: Union[str, int],
        uid: int,
        page: int = 1,
        update_button: bool = True,
    ) -> List[List[InlineKeyboardButton]]:
        """生成按钮"""
        buttons = []

        if data.avatarList:
            buttons = [
                InlineKeyboardButton(
                    idToRole(value.avatarId),
                    callback_data=f"get_player_card|{user_id}|{uid}|{idToRole(value.avatarId)}",
                )
                for value in data.avatarList
                if value.avatarId
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
                    callback_data=f"get_player_card|{user_id}|{uid}|{last_page}",
                )
            )
        if last_page or next_page:
            last_button.append(
                InlineKeyboardButton(
                    f"{page}/{all_page}",
                    callback_data=f"get_player_card|{user_id}|{uid}|empty_data",
                )
            )
        if update_button:
            last_button.append(
                InlineKeyboardButton(
                    "更新面板",
                    callback_data=f"update_player_card|{user_id}|{uid}",
                )
            )
        if next_page:
            last_button.append(
                InlineKeyboardButton(
                    "下一页 >>",
                    callback_data=f"get_player_card|{user_id}|{uid}|{next_page}",
                )
            )
        if last_button:
            send_buttons.append(last_button)
        return send_buttons

    async def parse_holder_data(self, data: PlayerInfo) -> dict:
        """
        生成渲染所需数据
        """
        characters_data = []
        for idx, character in enumerate(data.avatarList):
            cid = character.avatarId
            try:
                characters_data.append(
                    {
                        "level": character.level,
                        "constellation": character.rank,
                        "icon": self.assets_service.avatar.square(cid).as_uri(),
                    }
                )
            except AssetsCouldNotFound:
                logger.warning("角色 %s 的头像资源获取失败", cid)
            if idx == 7:
                break
        return {
            "uid": mask_number(data.uid),
            "level": data.level or 0,
            "signature": data.signature or "",
            "characters": characters_data,
        }


class Artifact(BaseModel):
    equipment: Dict = {}
    # 圣遗物评分
    score: float = 0
    # 圣遗物评级
    score_label: str = "E"
    # 圣遗物评级颜色
    score_class: str = ""
    # 圣遗物单行属性评分
    substat_scores: List[float]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for substat_scores in self.substat_scores:
            self.score += substat_scores
        self.score = round(self.score, 1)

        for r in (
            ("D", 10.0),
            ("C", 16.5),
            ("B", 23.1),
            ("A", 29.7),
            ("S", 36.3),
            ("SS", 42.9),
            ("SSS", 49.5),
            ("ACE", 56.1),
            ("ACE²", 66.0),
        ):
            if self.score >= r[1]:
                self.score_label = r[0]
                self.score_class = self.get_score_class(r[0])

    @staticmethod
    def get_score_class(label: str) -> str:
        mapping = {
            "D": "text-neutral-400",
            "C": "text-neutral-200",
            "B": "text-violet-400",
            "A": "text-violet-400",
            "S": "text-yellow-400",
            "SS": "text-yellow-400",
            "SSS": "text-yellow-400",
            "ACE": "text-red-500",
            "ACE²": "text-red-500",
        }
        return mapping.get(label, "text-neutral-400")


class RenderTemplate:
    def __init__(
        self,
        uid: Union[int, str],
        character: Avatar,
        template_service: TemplateService,
        assets_service: AssetsService,
        wiki_service: WikiService,
        client: PlayerCardsClient,
        fight_prop_rule: Dict[str, Dict[str, float]],
    ):
        self.uid = uid
        self.template_service = template_service
        self.character = character
        self.assets_service = assets_service
        self.wiki_service = wiki_service
        self.client = client
        self.fight_prop_rule = fight_prop_rule

    async def render(self):
        images = await self.cache_images()

        artifacts = self.find_artifacts()
        artifact_total_score: float = sum(artifact.score for artifact in artifacts)
        artifact_total_score = round(artifact_total_score, 1)

        artifact_total_score_label: str = "E"
        for r in (
            ("D", 10.0),
            ("C", 16.5),
            ("B", 23.1),
            ("A", 29.7),
            ("S", 36.3),
            ("SS", 42.9),
            ("SSS", 49.5),
            ("ACE", 56.1),
            ("ACE²", 66.0),
        ):
            if artifact_total_score / 5 >= r[1]:
                artifact_total_score_label = r[0]

        weapon = None
        weapon_detail = None
        if self.character.equipment and self.character.equipment.tid:
            weapon = self.character.equipment
            weapon_detail = self.wiki_service.light_cone.get_by_id(self.character.equipment.tid)
        skills = [0, 0, 0, 0, 0]
        for index in range(5):
            skills[index] = self.character.skillTreeList[index].level
        data = {
            "uid": mask_number(self.uid),
            "character": self.character,
            "character_detail": self.wiki_service.character.get_by_id(self.character.avatarId),
            "weapon": weapon,
            "weapon_detail": weapon_detail,
            # 圣遗物评分
            "artifact_total_score": artifact_total_score,
            # 圣遗物评级
            "artifact_total_score_label": artifact_total_score_label,
            # 圣遗物评级颜色
            "artifact_total_score_class": Artifact.get_score_class(artifact_total_score_label),
            "artifacts": artifacts,
            "skills": skills,
            "images": images,
            **(await self.cal_avatar_damage()),
        }

        return await self.template_service.render(
            "starrail/player_card/player_card.html",
            data,
            {"width": 1000, "height": 1200},
            full_page=True,
            query_selector=".text-neutral-200",
            ttl=7 * 24 * 60 * 60,
        )

    async def cache_images(self):
        c = self.character
        cid = c.avatarId
        data = {
            "banner_url": self.assets_service.avatar.gacha(cid).as_uri(),
            "skills": [i.as_uri() for i in self.assets_service.avatar.skills(cid)][:-1],
            "constellations": [i.as_uri() for i in self.assets_service.avatar.eidolons(cid)],
            "equipment": "",
        }
        if c.equipment and c.equipment.tid:
            data["equipment"] = self.assets_service.light_cone.icon(c.equipment.tid).as_uri()
        return data

    def find_artifacts(self) -> List[Artifact]:
        """在 equipments 数组中找到圣遗物，并转换成带有分数的 model。equipments 数组包含圣遗物和武器"""

        stats = ArtifactStatsTheory(idToRole(self.character.avatarId), self.fight_prop_rule)

        def substat_score(s: EquipmentsStats) -> float:
            return stats.theory(s)

        def fix_equipment(e: Relic) -> Dict:
            rid = e.tid
            affix = self.client.get_affix_by_id(rid)
            relic_set = self.wiki_service.relic.get_by_id(affix.set_id)
            try:
                icon = relic_set.image_list[affix.type.num]
            except IndexError:
                icon = relic_set.icon
            return {
                "id": rid,
                "name": relic_set.name,
                "icon": icon,
                "level": e.level,
                "rank": affix.rarity,
                "main_sub": self.client.get_affix(e, True, False)[0],
                "sub": self.client.get_affix(e, False, True),
            }

        relic_list = self.character.relicList or []
        return [
            Artifact(
                equipment=fix_equipment(e),
                # 圣遗物单行属性评分
                substat_scores=[substat_score(s) for s in self.client.get_affix(e, False)],
            )
            for e in relic_list
            if self.client.get_affix_by_id(e.tid) is not None
        ]

    async def cal_avatar_damage(self) -> Dict:
        if not STARRAIL_ARTIFACT_FUNCTION_AVAILABLE:
            return {
                "damage_function_available": False,
            }
        try:
            data = self.character.dict()
            if "property" in data:
                del data["property"]
            avatar = msgspec_convert(data, type=DamageAvatar)
            damage_data = await get_damage_data(avatar, "", str(self.uid))
            damage_info = await cal_damage_info(damage_data[0])
            return {
                "damage_function_available": True,
                "damage_info": damage_info,
            }
        except Exception:
            logger.warning("计算角色伤害时出现错误 uid[%s] avatar[%s]", self.uid, self.character.avatarId)
            return {
                "damage_function_available": False,
            }
