import math
from typing import List, Tuple, Union, Optional, TYPE_CHECKING, Dict

from pydantic import BaseModel
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import filters
from telegram.helpers import create_deep_linked_url

from core.basemodel import RegionEnum
from core.config import config
from core.dependence.assets import AssetsService, AssetsCouldNotFound
from core.dependence.redisdb import RedisDB
from core.plugin import Plugin, handler
from core.services.players import PlayersService
from core.services.template.services import TemplateService
from core.services.wiki.services import WikiService
from metadata.shortname import roleToName, idToRole
from modules.apihelper.client.components.player_cards import PlayerCards as PlayerCardsClient, PlayerInfo, Avatar, Relic
from modules.playercards.fight_prop import EquipmentsStats
from modules.playercards.helpers import ArtifactStatsTheory
from utils.log import logger

if TYPE_CHECKING:
    from telegram.ext import ContextTypes
    from telegram import Update

try:
    import ujson as jsonlib
except ImportError:
    import json as jsonlib


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

    async def initialize(self):
        await self.client.async_init()

    async def _load_history(self, uid) -> Optional[PlayerInfo]:
        data = await self.client.player_cards_file.load_history_info(uid)
        if data is None:
            return None
        return PlayerInfo.parse_obj(data)

    @handler.command(command="player_card", block=False)
    @handler.message(filters=filters.Regex("^角色卡片查询(.*)"), block=False)
    async def player_cards(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        user = update.effective_user
        message = update.effective_message
        args = self.get_args(context)
        await message.reply_chat_action(ChatAction.TYPING)
        player_info = await self.player_service.get_player(user.id)
        if player_info is None:
            buttons = [
                [
                    InlineKeyboardButton(
                        "点我绑定账号",
                        url=create_deep_linked_url(context.bot.username, "set_uid"),
                    )
                ]
            ]
            if filters.ChatType.GROUPS.filter(message):
                reply_message = await message.reply_text(
                    "未查询到您所绑定的账号信息，请先私聊派蒙绑定账号",
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
                self.add_delete_message_job(reply_message, delay=30)

                self.add_delete_message_job(message, delay=30)
            else:
                await message.reply_text("未查询到您所绑定的账号信息，请先绑定账号", reply_markup=InlineKeyboardMarkup(buttons))
            return
        # 暂时只支持国服
        if player_info.region != RegionEnum.HYPERION:
            await message.reply_text("此功能暂时只支持国服")
            return
        data = await self._load_history(player_info.player_id)
        if data is None or len(data.AvatarList) == 0:
            if isinstance(self.kitsune, str):
                photo = self.kitsune
            else:
                photo = open("resources/img/aaa.jpg", "rb")
            buttons = [
                [
                    InlineKeyboardButton(
                        "更新面板",
                        callback_data=f"update_player_card|{user.id}|{player_info.player_id}",
                    )
                ]
            ]
            reply_message = await message.reply_photo(
                photo=photo,
                caption="角色列表未找到，请尝试点击下方按钮更新角色列表",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            if reply_message.photo:
                self.kitsune = reply_message.photo[-1].file_id
            return
        if len(args) == 1:
            character_name = roleToName(args[0])
            logger.info(
                "用户 %s[%s] 角色卡片查询命令请求 || character_name[%s] uid[%s]",
                user.full_name,
                user.id,
                character_name,
                player_info.player_id,
            )
        else:
            logger.info("用户 %s[%s] 角色卡片查询命令请求", user.full_name, user.id)
            ttl = await self.cache.ttl(player_info.player_id)

            buttons = self.gen_button(data, user.id, player_info.player_id, update_button=ttl < 0)
            if isinstance(self.kitsune, str):
                photo = self.kitsune
            else:
                photo = open("resources/img/aaa.jpg", "rb")
            reply_message = await message.reply_photo(
                photo=photo,
                caption="请选择你要查询的角色",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            if reply_message.photo:
                self.kitsune = reply_message.photo[-1].file_id
            return
        for characters in data.AvatarList:
            if idToRole(characters.AvatarID) == character_name:
                break
        else:
            await message.reply_text(f"角色展柜中未找到 {character_name} ，请检查角色是否存在于角色展柜中，或者等待角色数据更新后重试")
            return
        if characters.AvatarID in {8001, 8002, 8003, 8004}:
            await message.reply_text(f"暂不支持查询 {character_name} 的角色卡片")
            return
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        render_result = await RenderTemplate(
            player_info.player_id,
            characters,
            self.template_service,
            self.assets_service,
            self.wiki_service,
            self.client,
        ).render()  # pylint: disable=W0631
        await render_result.reply_photo(
            message,
            filename=f"player_card_{player_info.player_id}_{character_name}.png",
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
        if data.AvatarList is None:
            await message.delete()
            await callback_query.answer("请先将角色加入到角色展柜并允许查看角色详情后再使用此功能，如果已经添加了角色，请等待角色数据更新后重试", show_alert=True)
            return
        buttons = self.gen_button(data, user.id, uid, update_button=False)
        render_data = await self.parse_holder_data(data)
        holder = await self.template_service.render(
            "genshin/player_card/holder.html",
            render_data,
            viewport={"width": 750, "height": 380},
            ttl=60 * 10,
            caption="更新角色列表成功，请选择你要查询的角色",
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
        if data.AvatarList is None:
            await message.delete()
            await callback_query.answer("请先将角色加入到角色展柜并允许查看角色详情后再使用此功能，如果已经添加了角色，请等待角色数据更新后重试", show_alert=True)
            return
        if page:
            buttons = self.gen_button(data, user.id, uid, page, await self.cache.ttl(uid) <= 0)
            await message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
            await callback_query.answer(f"已切换到第 {page} 页", show_alert=False)
            return
        for characters in data.AvatarList:
            if idToRole(characters.AvatarID) == result:
                break
        else:
            await message.delete()
            await callback_query.answer(f"角色展柜中未找到 {result} ，请检查角色是否存在于角色展柜中，或者等待角色数据更新后重试", show_alert=True)
            return
        if characters.AvatarID in {8001, 8002, 8003, 8004}:
            await callback_query.answer(f"暂不支持查询 {result} 的角色卡片")
            return
        await callback_query.answer(text="正在渲染图片中 请稍等 请不要重复点击按钮", show_alert=False)
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        render_result = await RenderTemplate(
            uid, characters, self.template_service, self.assets_service, self.wiki_service, self.client
        ).render()  # pylint: disable=W0631
        render_result.filename = f"player_card_{uid}_{result}.png"
        await render_result.edit_media(message)

    def gen_button(
        self,
        data: PlayerInfo,
        user_id: Union[str, int],
        uid: int,
        page: int = 1,
        update_button: bool = True,
    ) -> List[List[InlineKeyboardButton]]:
        """生成按钮"""
        buttons = []

        if data.AvatarList:
            buttons = [
                InlineKeyboardButton(
                    idToRole(value.AvatarID),
                    callback_data=f"get_player_card|{user_id}|{uid}|{idToRole(value.AvatarID)}",
                )
                for value in data.AvatarList
                if value.AvatarID
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
        for idx, character in enumerate(data.AvatarList):
            cid = 8004 if character.AvatarID in {8001, 8002, 8003, 8004} else character.AvatarID
            try:
                characters_data.append(
                    {
                        "level": character.Level,
                        "constellation": character.Rank,
                        "icon": self.assets_service.avatar.square(cid).as_uri(),
                    }
                )
            except AssetsCouldNotFound:
                logger.warning("角色 %s 的头像资源获取失败", cid)
            if idx > 6:
                break
        return {
            "uid": data.UID,
            "level": data.Level or 0,
            "signature": data.Signature or "",
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
    ):
        self.uid = uid
        self.template_service = template_service
        self.character = character
        self.assets_service = assets_service
        self.wiki_service = wiki_service
        self.client = client

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
        if self.character.EquipmentID and self.character.EquipmentID.ID:
            weapon = self.character.EquipmentID
            weapon_detail = self.wiki_service.light_cone.get_by_id(self.character.EquipmentID.ID)
        skills = [0, 0, 0, 0, 0]
        for index in range(5):
            skills[index] = self.character.BehaviorList[index].Level
        data = {
            "uid": self.uid,
            "character": self.character,
            "character_detail": self.wiki_service.character.get_by_id(self.character.AvatarID),
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
        }

        return await self.template_service.render(
            "starrail/player_card/player_card.html",
            data,
            {"width": 1100, "height": 1250},
            full_page=True,
            query_selector=".text-neutral-200",
            ttl=7 * 24 * 60 * 60,
        )

    async def cache_images(self):
        c = self.character
        cid = c.AvatarID
        data = {
            "banner_url": self.assets_service.avatar.gacha(cid).as_uri(),
            "skills": [i.as_uri() for i in self.assets_service.avatar.skills(cid)],
            "constellations": [i.as_uri() for i in self.assets_service.avatar.eidolons(cid)],
            "equipment": "",
        }
        if c.EquipmentID and c.EquipmentID.ID:
            data["equipment"] = self.assets_service.light_cone.icon(c.EquipmentID.ID).as_uri()
        return data

    def find_artifacts(self) -> List[Artifact]:
        """在 equipments 数组中找到圣遗物，并转换成带有分数的 model。equipments 数组包含圣遗物和武器"""

        stats = ArtifactStatsTheory(idToRole(self.character.AvatarID))

        def substat_score(s: EquipmentsStats) -> float:
            return stats.theory(s)

        def fix_equipment(e: Relic) -> Dict:
            rid = e.ID
            affix = self.client.get_affix_by_id(rid)
            relic_set = self.wiki_service.relic.get_by_id(affix.set_id)
            return {
                "id": rid,
                "name": relic_set.name,
                "icon": relic_set.icon,
                "level": e.Level,
                "rank": affix.rarity,
                "main_sub": self.client.get_affix(e, True, False)[0],
                "sub": self.client.get_affix(e, False, True),
            }
        relic_list = self.character.RelicList or []
        return [
            Artifact(
                equipment=fix_equipment(e),
                # 圣遗物单行属性评分
                substat_scores=[substat_score(s) for s in self.client.get_affix(e)],
            )
            for e in relic_list
        ]
