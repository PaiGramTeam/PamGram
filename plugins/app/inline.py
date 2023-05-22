import asyncio
from typing import Awaitable, Dict, List, cast
from uuid import uuid4

from telegram import (
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InlineQueryResultCachedDocument,
    InputTextMessageContent,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import CallbackContext

from core.plugin import Plugin, handler
from core.dependence.assets import AssetsService
from core.services.search.services import SearchServices
from core.services.wiki.services import WikiService
from utils.log import logger


class Inline(Plugin):
    """Inline模块"""

    def __init__(
        self,
        asset_service: AssetsService,
        search_service: SearchServices,
        wiki_service: WikiService,
    ):
        self.asset_service = asset_service
        self.wiki_service = wiki_service
        self.weapons_list: List[Dict[str, str]] = []
        self.characters_list: List[Dict[str, str]] = []
        self.characters_material_list: List[Dict[str, str]] = []
        self.light_cone_list: List[Dict[str, str]] = []
        self.relics_list: List[Dict[str, str]] = []
        self.refresh_task: List[Awaitable] = []
        self.search_service = search_service

    async def initialize(self):
        async def task_light_cone():
            logger.info("Inline 模块正在获取光锥列表")
            light_cone_datas: Dict[str, str] = {}
            for light_cone in self.asset_service.light_cone.data:
                light_cone_datas[light_cone.name] = light_cone.icon_
            # 光锥列表
            for light_cone in self.wiki_service.raider.all_light_cone_raiders:
                if light_cone in light_cone_datas:
                    self.light_cone_list.append({"name": light_cone, "icon": light_cone_datas[light_cone]})
                else:
                    logger.warning(f"未找到光锥 {light_cone} 的图标，inline 不显示此光锥")
            logger.success("Inline 模块获取光锥列表完成")

        async def task_relics():
            logger.info("Inline 模块正在获取遗器列表")
            relics_datas: Dict[str, str] = {}
            for relics in self.wiki_service.relic.all_relics:
                relics_datas[relics.name] = relics.icon
            for relics in self.wiki_service.raider.all_relic_raiders:
                if relics in relics_datas:
                    self.relics_list.append({"name": relics, "icon": relics_datas[relics]})
                else:
                    logger.warning(f"未找到遗器 {relics} 的图标，inline 不显示此遗器")
            logger.success("Inline 模块获取遗器列表完成")

        async def task_characters():
            logger.info("Inline 模块正在获取角色列表")
            datas: Dict[str, str] = {}
            for character in self.asset_service.avatar.data:
                datas[character.name] = character.square or character.normal
            # 角色攻略
            for character in self.wiki_service.raider.all_role_raiders:
                if character in datas:
                    self.characters_list.append({"name": character, "icon": datas[character]})
                else:
                    for key, value in datas.items():
                        if character.startswith(key) or character.endswith(key):
                            self.characters_list.append({"name": character, "icon": value})
                            break
            # 角色培养素材
            for character in self.wiki_service.raider.all_role_material_raiders:
                if character in datas:
                    self.characters_material_list.append({"name": character, "icon": datas[character]})
                else:
                    for key, value in datas.items():
                        if character.startswith(key) or character.endswith(key):
                            self.characters_material_list.append({"name": character, "icon": value})
                            break
            logger.success("Inline 模块获取角色列表成功")

        self.refresh_task.append(asyncio.create_task(task_characters()))
        self.refresh_task.append(asyncio.create_task(task_light_cone()))
        self.refresh_task.append(asyncio.create_task(task_relics()))

    @handler.inline_query(block=False)
    async def inline_query(self, update: Update, _: CallbackContext) -> None:
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
        else:
            if args[0] in ["查看角色攻略列表并查询", "查看角色培养素材列表并查询", "查看光锥列表并查询", "查看遗器套装列表并查询"]:
                temp_data = {
                    "查看角色攻略列表并查询": (self.characters_list, "角色攻略查询"),
                    "查看角色培养素材列表并查询": (self.characters_material_list, "角色培养素材查询"),
                    "查看光锥列表并查询": (self.light_cone_list, "光锥查询"),
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
                            thumb_url=icon,
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
                            thumb_url="https://www.miyoushe.com/_nuxt/img/game-sr.4f80911.jpg",
                            input_message_content=InputTextMessageContent(f"当前查询内容为 {args[0]}\n如果无查看图片描述 这是正常的 客户端问题"),
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
                switch_pm_text=switch_pm_text,
                switch_pm_parameter="inline_message",
                cache_time=0,
                auto_pagination=True,
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
                switch_pm_text="糟糕，发生错误了。",
                switch_pm_parameter="inline_message",
            )
