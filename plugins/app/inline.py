import asyncio
from typing import Awaitable, Dict, List, cast, Tuple
from uuid import uuid4

from telegram import (
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InlineQueryResultCachedDocument,
    InputTextMessageContent,
    Update,
    InlineQueryResultsButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InlineQueryResultPhoto,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import CallbackContext, ContextTypes

from core.dependence.assets import AssetsService
from core.plugin import Plugin, handler
from core.services.search.services import SearchServices
from core.services.wiki.services import WikiService
from gram_core.config import config
from gram_core.plugin.methods.inline_use_data import IInlineUseData
from gram_core.services.cookies import CookiesService
from gram_core.services.players import PlayersService
from utils.log import logger


class Inline(Plugin):
    """Inline模块"""

    def __init__(
        self,
        asset_service: AssetsService,
        search_service: SearchServices,
        wiki_service: WikiService,
        cookies_service: CookiesService,
        players_service: PlayersService,
    ):
        self.asset_service = asset_service
        self.wiki_service = wiki_service
        self.weapons_list: List[Dict[str, str]] = []
        self.characters_list: List[Dict[str, str]] = []
        self.characters_material_list: List[Dict[str, str]] = []
        self.characters_guide_list: List[Dict[str, str]] = []
        self.light_cone_list: List[Dict[str, str]] = []
        self.relics_list: List[Dict[str, str]] = []
        self.refresh_task: List[Awaitable] = []
        self.search_service = search_service
        self.cookies_service = cookies_service
        self.players_service = players_service
        self.inline_use_data: List[IInlineUseData] = []
        self.inline_use_data_map: Dict[str, IInlineUseData] = {}
        self.img_url = "https://i.dawnlab.me/b1bdf9cc3061d254f038e557557694bc.jpg"

    async def initialize(self):
        async def task_light_cone():
            logger.info("Inline 模块正在获取光锥列表")
            light_cone_datas: Dict[str, str] = {}
            light_cone_datas_name: Dict[str, str] = {}
            for light_cone in self.asset_service.light_cone.data:
                light_cone_datas[light_cone.name] = light_cone.icon_
                light_cone_datas_name[str(light_cone.id)] = light_cone.name
            # 光锥列表
            for lid in self.wiki_service.raider.all_light_cone_raiders:
                if lid not in light_cone_datas_name:
                    continue
                light_cone = light_cone_datas_name[lid]
                if light_cone in light_cone_datas:
                    self.light_cone_list.append({"name": light_cone, "icon": light_cone_datas[light_cone]})
                else:
                    logger.warning(f"未找到光锥 {light_cone} 的图标，inline 不显示此光锥")
            logger.success("Inline 模块获取光锥列表完成")

        async def task_relics():
            logger.info("Inline 模块正在获取遗器列表")
            relics_datas: Dict[str, str] = {}
            relics_datas_name: Dict[str, str] = {}
            for relics in self.wiki_service.relic.all_relics:
                relics_datas[relics.name] = relics.icon
                relics_datas_name[str(relics.id)] = relics.name
            for rid in self.wiki_service.raider.all_relic_raiders:
                if rid not in relics_datas_name:
                    continue
                relics = relics_datas_name[rid]
                if relics in relics_datas:
                    self.relics_list.append({"name": relics, "icon": relics_datas[relics]})
                else:
                    logger.warning(f"未找到遗器 {relics} 的图标，inline 不显示此遗器")
            logger.success("Inline 模块获取遗器列表完成")

        async def task_characters():
            logger.info("Inline 模块正在获取角色列表")
            datas: Dict[str, str] = {}
            datas_name: Dict[str, str] = {}
            for character in self.asset_service.avatar.data:
                datas[character.name] = character.square or character.normal
                datas_name[str(character.id)] = character.name

            def get_character(_cid: str) -> str:
                if _cid in datas_name:
                    return datas_name[_cid]

            # 角色攻略
            for cid in self.wiki_service.raider.all_role_raiders:
                character = get_character(cid)
                if not character:
                    continue
                if character in datas:
                    self.characters_list.append({"name": character, "icon": datas[character]})
                else:
                    for key, value in datas.items():
                        if character.startswith(key) or character.endswith(key):
                            self.characters_list.append({"name": character, "icon": value})
                            break
            # 角色攻略
            for cid in self.wiki_service.raider.all_guide_for_role_raiders:
                character = get_character(cid)
                if not character:
                    continue
                if character in datas:
                    self.characters_guide_list.append({"name": character, "icon": datas[character]})
                else:
                    for key, value in datas.items():
                        if character.startswith(key) or character.endswith(key):
                            self.characters_guide_list.append({"name": character, "icon": value})
                            break
            logger.success("Inline 模块获取角色列表成功")

        self.refresh_task.append(asyncio.create_task(task_characters()))
        self.refresh_task.append(asyncio.create_task(task_light_cone()))
        self.refresh_task.append(asyncio.create_task(task_relics()))

    async def init_inline_use_data(self):
        if self.inline_use_data:
            return
        for _, instance in self.application.managers.plugins_map.items():
            if _data := await instance.get_inline_use_data():
                self.inline_use_data.extend(_data)
        for data in self.inline_use_data:
            self.inline_use_data_map[data.hash] = data

    async def user_base_data(self, user_id: int, player_id: int, offset: int) -> Tuple[int, bool, bool]:
        uid, has_cookie, has_player = 0, False, False
        player = await self.players_service.get_player(user_id, None, player_id, offset)
        if player is not None:
            uid = player.player_id
            has_player = True
            if player.account_id is not None:
                cookie_model = await self.cookies_service.get(player.user_id, player.account_id, player.region)
                if cookie_model is not None:
                    has_cookie = True
        return uid, has_cookie, has_player

    def get_inline_use_button_data(self, user_id: int, uid: int, cookie: bool, player: bool) -> InlineKeyboardMarkup:
        button_data = []
        start = f"use_inline_func|{user_id}|{uid}"
        for data in self.inline_use_data:
            if data.is_show(cookie, player):
                button_data.append(
                    InlineKeyboardButton(text=data.text, callback_data=data.get_button_callback_data(start))
                )
        # 每三个一行
        button_data = [button_data[i : i + 3] for i in range(0, len(button_data), 3)]
        return InlineKeyboardMarkup(button_data)

    @handler.callback_query(pattern=r"^use_inline_func\|", block=False)
    async def use_by_inline_query_callback(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        user = update.effective_user
        callback_query = update.callback_query

        async def get_inline_query_callback(callback_query_data: str) -> Tuple[int, int, str]:
            _data = callback_query_data.split("|")
            _user_id = int(_data[1])
            _uid = int(_data[2])
            _hash = _data[3]
            logger.debug("callback_query_data函数返回 user_id[%s] uid[%s] hash[%s]", _user_id, _uid, _hash)
            return _user_id, _uid, _hash

        user_id, uid, hash_str = await get_inline_query_callback(callback_query.data)
        if user.id != user_id:
            await callback_query.answer(text="这不是你的按钮！\n" + config.notice.user_mismatch, show_alert=True)
            return
        callback = self.inline_use_data_map.get(hash_str)
        if callback is None:
            await callback_query.answer(text="数据不存在，请重新生成按钮", show_alert=True)
            return
        IInlineUseData.set_uid_to_context(context, uid)
        await callback.callback(update, context)

    @handler.inline_query(pattern="^功能", block=False)
    async def use_by_inline_query(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE") -> None:
        if not config.channels_helper:
            logger.warning("未设置 helper 频道")
            return
        await self.init_inline_use_data()
        user = update.effective_user
        ilq = cast(InlineQuery, update.inline_query)
        query = ilq.query
        switch_pm_text = "需要帮助嘛？"
        logger.info("用户 %s[%s] inline_query 功能查询\nquery[%s]", user.full_name, user.id, query)
        user_id = user.id
        uid, offset = self.get_real_uid_or_offset(update)
        real_uid, has_cookie, has_player = await self.user_base_data(user_id, uid, offset)
        button_data = self.get_inline_use_button_data(user_id, real_uid, has_cookie, has_player)
        try:
            await ilq.answer(
                results=[
                    InlineQueryResultPhoto(
                        id=str(uuid4()),
                        photo_url=self.img_url,
                        thumbnail_url=self.img_url,
                        caption="请从下方按钮选择功能",
                        reply_markup=button_data,
                    )
                ],
                cache_time=0,
                auto_pagination=True,
                button=InlineQueryResultsButton(
                    text=switch_pm_text,
                    start_parameter="inline_message",
                ),
            )
        except BadRequest as exc:
            if "Query is too old" in exc.message:  # 过时请求全部忽略
                logger.warning("用户 %s[%s] inline_query 请求过时", user.full_name, user.id)
                return
            if "can't parse entities" not in exc.message:
                raise exc
            logger.warning("inline_query发生BadRequest错误", exc_info=exc)
            await ilq.answer(
                results=[],
                button=InlineQueryResultsButton(
                    text="糟糕，发生错误了。",
                    start_parameter="inline_message",
                ),
            )

    @handler.inline_query(block=False)
    async def z_inline_query(self, update: Update, _: CallbackContext) -> None:
        user = update.effective_user
        ilq = cast(InlineQuery, update.inline_query)
        query = ilq.query
        logger.info("用户 %s[%s] inline_query 查询\nquery[%s]", user.full_name, user.id, query)
        switch_pm_text = "需要帮助嘛？"
        results_list = []
        args = query.split(" ")
        if args[0] == "":
            temp_data = [
                ("光锥图鉴查询", "输入光锥名称即可查询光锥图鉴"),
                ("角色攻略查询", "输入角色名即可查询角色攻略图鉴"),
                ("角色图鉴查询", "输入角色名即可查询角色图鉴"),
                ("角色培养素材查询", "输入角色名即可查询角色培养素材图鉴"),
                ("遗器套装查询", "输入遗器套装名称即可查询遗器套装图鉴"),
            ]
            for i in temp_data:
                results_list.append(
                    InlineQueryResultArticle(
                        id=str(uuid4()),
                        title=i[0],
                        description=i[1],
                        input_message_content=InputTextMessageContent(i[0]),
                    )
                )
            results_list.append(
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="使用功能",
                    description="输入 功能 即可直接使用 BOT 功能",
                    input_message_content=InputTextMessageContent("Inline 模式下输入 功能 即可直接使用 BOT 功能"),
                )
            )
        elif args[0] == "cookies_export":
            return
        elif args[0] == "功能":
            return
        else:
            if args[0] in [
                "查看角色攻略列表并查询",
                "查看角色图鉴列表并查询",
                "查看光锥列表并查询",
                "查看遗器套装列表并查询",
                "查看角色培养素材列表并查询",
            ]:
                temp_data = {
                    "查看角色攻略列表并查询": (self.characters_list, "角色攻略查询"),
                    "查看角色图鉴列表并查询": (self.characters_guide_list, "角色图鉴查询"),
                    "查看角色培养素材列表并查询": (self.characters_material_list, "角色培养素材查询"),
                    "查看光锥列表并查询": (self.light_cone_list, "光锥图鉴查询"),
                    "查看遗器套装列表并查询": (self.relics_list, "遗器套装查询"),
                }[args[0]]
                for character in temp_data[0]:
                    name = character["name"]
                    icon = character["icon"]
                    results_list.append(
                        InlineQueryResultArticle(
                            id=str(uuid4()),
                            title=name,
                            description=f"{args[0]} {name}",
                            thumbnail_url=icon,
                            input_message_content=InputTextMessageContent(
                                f"{temp_data[1]}{name}", parse_mode=ParseMode.MARKDOWN_V2
                            ),
                        )
                    )
            else:
                simple_search_results = await self.search_service.search(args[0])
                if simple_search_results:
                    results_list.append(
                        InlineQueryResultArticle(
                            id=str(uuid4()),
                            title=f"当前查询内容为 {args[0]}",
                            description="如果无查看图片描述 这是正常的 客户端问题",
                            thumbnail_url="https://www.miyoushe.com/_nuxt/img/game-sr.4f80911.jpg",
                            input_message_content=InputTextMessageContent(
                                f"当前查询内容为 {args[0]}\n如果无查看图片描述 这是正常的 客户端问题"
                            ),
                        )
                    )
                    for simple_search_result in simple_search_results:
                        description = simple_search_result.description
                        if len(description) >= 10:
                            description = description[:10]
                        item = None
                        if simple_search_result.photo_file_id:
                            item = InlineQueryResultCachedPhoto(
                                id=str(uuid4()),
                                title=simple_search_result.title,
                                photo_file_id=simple_search_result.photo_file_id,
                                description=description,
                                caption=simple_search_result.caption,
                                parse_mode=simple_search_result.parse_mode,
                            )
                        elif simple_search_result.document_file_id:
                            item = InlineQueryResultCachedDocument(
                                id=str(uuid4()),
                                title=simple_search_result.title,
                                document_file_id=simple_search_result.document_file_id,
                                description=description,
                                caption=simple_search_result.caption,
                                parse_mode=simple_search_result.parse_mode,
                            )
                        if item:
                            results_list.append(item)
        if not results_list:
            results_list.append(
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="好像找不到问题呢",
                    description="这个问题我也不知道。",
                    input_message_content=InputTextMessageContent("这个问题我也不知道。"),
                )
            )
        try:
            await ilq.answer(
                results=results_list,
                cache_time=0,
                auto_pagination=True,
                button=InlineQueryResultsButton(
                    text=switch_pm_text,
                    start_parameter="inline_message",
                ),
            )
        except BadRequest as exc:
            if "Query is too old" in exc.message:  # 过时请求全部忽略
                logger.warning("用户 %s[%s] inline_query 请求过时", user.full_name, user.id)
                return
            if "can't parse entities" not in exc.message:
                raise exc
            logger.warning("inline_query发生BadRequest错误", exc_info=exc)
            await ilq.answer(
                results=[],
                button=InlineQueryResultsButton(
                    text="糟糕，发生错误了。",
                    start_parameter="inline_message",
                ),
            )
