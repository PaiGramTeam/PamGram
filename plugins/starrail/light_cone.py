from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import CallbackContext, filters

from core.plugin import Plugin, handler
from core.services.game.services import GameCacheService
from core.services.search.models import StrategyEntry
from core.services.search.services import SearchServices
from core.services.wiki.services import WikiService
from metadata.shortname import lightConeToTag, lightConeToName
from utils.log import logger


class LightConePlugin(Plugin):
    """光锥图鉴查询"""

    KEYBOARD = [[InlineKeyboardButton(text="查看光锥列表并查询", switch_inline_query_current_chat="查看光锥列表并查询")]]

    def __init__(
        self,
        cache_service: GameCacheService = None,
        wiki_service: WikiService = None,
        search_service: SearchServices = None,
    ):
        self.cache_service = cache_service
        self.wiki_service = wiki_service
        self.search_service = search_service

    @handler.command(command="light_cone", block=False)
    @handler.message(filters=filters.Regex("^光锥查询(.*)"), block=False)
    async def command_start(self, update: Update, context: CallbackContext) -> None:
        message = update.effective_message
        user = update.effective_user
        args = self.get_args(context)
        if len(args) >= 1:
            light_cone_name = args[0]
        else:
            reply_message = await message.reply_text("请回复你要查询的光锥名称", reply_markup=InlineKeyboardMarkup(self.KEYBOARD))
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        light_cone_name = lightConeToName(light_cone_name)
        file_path = self.wiki_service.raider.raider_light_cone_path / f"{light_cone_name}.png"
        if not file_path.exists():
            reply_message = await message.reply_text(
                f"没有找到 {light_cone_name} 的光锥图鉴", reply_markup=InlineKeyboardMarkup(self.KEYBOARD)
            )
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        logger.info("用户 %s[%s] 查询光锥图鉴命令请求 || 参数 %s", user.full_name, user.id, light_cone_name)
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        caption = "From 米游社@听语惊花"
        if file_id := await self.cache_service.get_light_cone_cache(light_cone_name):
            await message.reply_photo(
                photo=file_id,
                caption=caption,
                filename=f"{light_cone_name}.png",
                allow_sending_without_reply=True,
                parse_mode=ParseMode.HTML,
            )
        else:
            reply_photo = await message.reply_photo(
                photo=open(file_path, "rb"),
                caption=caption,
                filename=f"{light_cone_name}.png",
                allow_sending_without_reply=True,
                parse_mode=ParseMode.HTML,
            )
            if reply_photo.photo:
                tags = lightConeToTag(light_cone_name)
                photo_file_id = reply_photo.photo[0].file_id
                await self.cache_service.set_light_cone_cache(light_cone_name, photo_file_id)
                entry = StrategyEntry(
                    key=f"plugin:strategy:{light_cone_name}",
                    title=light_cone_name,
                    description=f"{light_cone_name} 光锥图鉴",
                    tags=tags,
                    caption=caption,
                    parse_mode="HTML",
                    photo_file_id=photo_file_id,
                )
                await self.search_service.add_entry(entry)
