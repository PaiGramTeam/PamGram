from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import CallbackContext, filters

from core.plugin import Plugin, handler
from core.services.game.services import GameCacheService
from core.services.search.models import StrategyEntry
from core.services.search.services import SearchServices
from core.services.wiki.services import WikiService
from metadata.shortname import roleToName, roleToTag
from utils.log import logger


class MaterialPlugin(Plugin):
    """角色培养素材查询"""

    KEYBOARD = [[InlineKeyboardButton(text="查看角色培养素材列表并查询", switch_inline_query_current_chat="查看角色培养素材列表并查询")]]

    def __init__(
        self,
        cache_service: GameCacheService = None,
        wiki_service: WikiService = None,
        search_service: SearchServices = None,
    ):
        self.cache_service = cache_service
        self.wiki_service = wiki_service
        self.search_service = search_service

    @handler.command(command="material", block=False)
    @handler.message(filters=filters.Regex("^角色培养素材查询(.*)"), block=False)
    async def command_start(self, update: Update, context: CallbackContext) -> None:
        message = update.effective_message
        user = update.effective_user
        args = self.get_args(context)
        if len(args) >= 1:
            character_name = args[0]
        else:
            reply_message = await message.reply_text(
                "请回复你要查询的角色培养素材图鉴的角色名",
                reply_markup=InlineKeyboardMarkup(self.KEYBOARD)
            )
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        character_name = roleToName(character_name)
        file_path = self.wiki_service.raider.raider_role_material_path / f"{character_name}.png"
        if not file_path.exists():
            reply_message = await message.reply_text(
                f"没有找到 {character_name} 的角色培养素材图鉴", reply_markup=InlineKeyboardMarkup(self.KEYBOARD)
            )
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        logger.info("用户 %s[%s] 查询角色培养素材命令请求 || 参数 %s", user.full_name, user.id, character_name)
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        caption = "From 米游社@听语惊花"
        if file_id := await self.cache_service.get_material_cache(character_name):
            await message.reply_photo(
                photo=file_id,
                caption=caption,
                filename=f"{character_name}.png",
                allow_sending_without_reply=True,
                parse_mode=ParseMode.HTML,
            )
        else:
            reply_photo = await message.reply_photo(
                photo=open(file_path, "rb"),
                caption=caption,
                filename=f"{character_name}.png",
                allow_sending_without_reply=True,
                parse_mode=ParseMode.HTML,
            )
            if reply_photo.photo:
                tags = roleToTag(character_name)
                photo_file_id = reply_photo.photo[0].file_id
                await self.cache_service.set_material_cache(character_name, photo_file_id)
                entry = StrategyEntry(
                    key=f"plugin:strategy:{character_name}",
                    title=character_name,
                    description=f"{character_name} 角色攻略",
                    tags=tags,
                    caption=caption,
                    parse_mode="HTML",
                    photo_file_id=photo_file_id,
                )
                await self.search_service.add_entry(entry)
