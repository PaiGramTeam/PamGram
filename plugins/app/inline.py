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
from telegram.ext import CallbackContext, InlineQueryHandler

from core.plugin import Plugin, handler
from core.services.search.services import SearchServices
from core.services.wiki.services import WikiService
from utils.log import logger


class Inline(Plugin):
    """Inline模块"""

    def __init__(
        self,
        wiki_service: WikiService,
        search_service: SearchServices,
    ):
        self.wiki_service = wiki_service
        self.weapons_list: List[Dict[str, str]] = []
        self.characters_list: List[Dict[str, str]] = []
        self.refresh_task: List[Awaitable] = []
        self.search_service = search_service

    async def initialize(self):
        async def task_characters():
            logger.info("Inline 模块正在获取角色列表")
            datas: Dict[str, str] = {}
            for character in self.wiki_service.character.all_avatars:
                if not character.icon:
                    logger.warning(f"角色 {character.name} 无图标")
                    continue
                datas[character.name] = character.icon
            for character in self.wiki_service.raider.get_name_list():
                if character in datas:
                    self.characters_list.append(
                        {"name": character, "icon": datas[character]}
                    )
                else:
                    for key, value in datas.items():
                        if character.startswith(key):
                            self.characters_list.append(
                                {"name": character, "icon": value}
                            )
                            break
            logger.success("Inline 模块获取角色列表成功")

        self.refresh_task.append(asyncio.create_task(task_characters()))

    @handler(InlineQueryHandler, block=False)
    async def inline_query(self, update: Update, _: CallbackContext) -> None:
        user = update.effective_user
        ilq = cast(InlineQuery, update.inline_query)
        query = ilq.query
        logger.info(
            "用户 %s[%s] inline_query 查询\nquery[%s]", user.full_name, user.id, query
        )
        switch_pm_text = "需要帮助嘛？"
        results_list = []
        args = query.split(" ")
        if args[0] == "":
            results_list.append(
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="角色攻略查询",
                    description="输入角色名即可查询角色攻略",
                    input_message_content=InputTextMessageContent("角色攻略查询"),
                )
            )
        else:
            if args[0] == "查看角色攻略列表并查询":
                for character in self.characters_list:
                    name = character["name"]
                    icon = character["icon"]
                    results_list.append(
                        InlineQueryResultArticle(
                            id=str(uuid4()),
                            title=name,
                            description=f"查看角色攻略列表并查询 {name}",
                            thumb_url=icon,
                            input_message_content=InputTextMessageContent(
                                f"角色攻略查询{name}", parse_mode=ParseMode.MARKDOWN_V2
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
