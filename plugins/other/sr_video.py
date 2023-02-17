from typing import Optional, List, Tuple

from bs4 import BeautifulSoup
from httpx import AsyncClient
from pydantic import BaseModel
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InputMediaPhoto,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from telegram.constants import ParseMode, MessageLimit
from telegram.error import BadRequest
from telegram.ext import CallbackContext, ConversationHandler, filters
from telegram.helpers import escape_markdown

from core.baseplugin import BasePlugin
from core.bot import bot
from core.config import config
from core.plugin import Plugin, conversation, handler
from modules.apihelper.models.genshin.hyperion import ArtworkImage
from utils.decorators.admins import bot_admins_rights_check
from utils.decorators.error import error_callable
from utils.decorators.restricts import restricts
from utils.log import logger


class SRVideoHandlerData:
    def __init__(self):
        self.post_id: int = 0
        self.post_text: str = ""
        self.post_images: Optional[List[ArtworkImage]] = None
        self.post_video: str = ""
        self.delete_photo: Optional[List[int]] = []
        self.channel_id: int = -1
        self.tags: Optional[List[str]] = []


class OffContent(BaseModel):
    sTitle: str
    sContent: str
    sCategoryName: str
    iInfoId: int


CHECK_POST, SEND_POST, CHECK_COMMAND, GTE_DELETE_PHOTO = range(10900, 10904)
GET_POST_CHANNEL, GET_TAGS, GET_TEXT, CHECK_VIDEO = range(10904, 10908)


class SRVideo(Plugin.Conversation, BasePlugin.Conversation):
    """星穹铁道官网文章推送"""

    MENU_KEYBOARD = ReplyKeyboardMarkup([["推送频道", "添加TAG"], ["编辑文字", "删除图片"], ["退出"]], True, True)
    OFF_URL = "https://api-takumi-static.mihoyo.com/content_v2_user/app/1963de8dc19e461c/getContentList"
    OFF_C_URL = "https://api-takumi-static.mihoyo.com/content_v2_user/app/1963de8dc19e461c/getContent"
    OFF_PARAMS = {
        "iPage": "1",
        "iPageSize": "5",
        "sLangKey": "zh-cn",
        "isPreview": "0",
        "iChanId": "255",
    }

    def __init__(self):
        self.last_post_id_list: List[int] = []
        self.client = AsyncClient()
        if config.channels and len(config.channels) > 0:
            logger.success("官网文章定时推送处理已经开启")
            bot.app.job_queue.run_once(self.task, 20)
            bot.app.job_queue.run_custom(self.task, {"trigger": "cron", "minute": 1, "second": 0})

    async def get_official_news(self) -> List[OffContent]:
        try:
            response = await self.client.get(self.OFF_URL, params=self.OFF_PARAMS)
            res = response.json()
            return [OffContent(**i) for i in res["data"]["list"]]
        except Exception as exc:
            logger.error("获取官网文章失败 %s", str(exc))
            return []

    async def get_official_new(self, post_id: int) -> Optional[OffContent]:
        try:
            params = self.OFF_PARAMS.copy()
            params["iInfoId"] = str(post_id)
            response = await self.client.get(self.OFF_C_URL, params=params)
            res = response.json()
            return OffContent(**res["data"])
        except Exception as exc:
            logger.error("获取官网文章失败 %s", str(exc))
            return None

    async def task(self, context: CallbackContext):
        temp_post_id_list: List[int] = []

        # 请求
        official_posts: List[OffContent] = await self.get_official_news()
        temp_post_id_list.extend([post.iInfoId for post in official_posts])
        # 首次运行
        if not self.last_post_id_list:
            for temp_list in temp_post_id_list:
                self.last_post_id_list.append(temp_list)
            return

        # 筛选出新推送的文章
        new_post_id_list = set(temp_post_id_list).difference(set(self.last_post_id_list))
        if not new_post_id_list:
            return
        self.last_post_id_list = temp_post_id_list

        # 推送管理员
        for post in official_posts:
            buttons = [
                [
                    InlineKeyboardButton("确认", callback_data=f"video_admin|confirm|{post.iInfoId}"),
                    InlineKeyboardButton("取消", callback_data=f"video_admin|cancel|{post.iInfoId}"),
                ]
            ]
            url = f"https://sr.mihoyo.com/news/{post.iInfoId}"
            text = f"发现官网文章 <a href='{url}'>{post.sTitle}</a>\n是否开始处理"
            for user in config.admins:
                try:
                    await context.bot.send_message(
                        user.user_id, text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons)
                    )
                except BadRequest as exc:
                    logger.error("发送消息失败 %s", exc.message)

    @conversation.entry_point
    @handler.callback_query(pattern=r"^video_admin\|", block=False)
    @bot_admins_rights_check
    @error_callable
    async def callback_query_start(self, update: Update, context: CallbackContext) -> int:
        video_post_handler_data = context.chat_data.get("video_post_handler_data")
        if video_post_handler_data is None:
            video_post_handler_data = SRVideoHandlerData()
            context.chat_data["video_post_handler_data"] = video_post_handler_data
        callback_query = update.callback_query
        user = callback_query.from_user
        message = callback_query.message
        logger.info("用户 %s[%s] VIDEO POST命令请求", user.full_name, user.id)

        async def get_post_admin_callback(callback_query_data: str) -> Tuple[str, int]:
            _data = callback_query_data.split("|")
            _result = _data[1]
            _post_id = int(_data[2])
            logger.debug("callback_query_data函数返回 result[%s] post_id[%s]", _result, _post_id)
            return _result, _post_id

        result, post_id = await get_post_admin_callback(callback_query.data)

        if result == "cancel":
            await message.reply_text("操作已经取消")
            await message.delete()
        elif result == "confirm":
            reply_text = await message.reply_text("正在处理")
            video_post_handler_data.post_id = post_id
            status = await self.send_post_info(video_post_handler_data, message)
            await reply_text.delete()
            return status

        await message.reply_text("非法参数")
        return ConversationHandler.END

    @handler.command(command="video_post_refresh", filters=filters.ChatType.PRIVATE, block=True)
    @restricts()
    @bot_admins_rights_check
    @error_callable
    async def video_post_refresh(self, update: Update, context: CallbackContext) -> None:
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] VIDEO POST刷新命令请求", user.full_name, user.id)
        await self.task(context)
        await message.reply_text("手动刷新完成")

    @conversation.entry_point
    @handler.command(command="video_post", filters=filters.ChatType.PRIVATE, block=True)
    @restricts()
    @bot_admins_rights_check
    @error_callable
    async def command_start(self, update: Update, context: CallbackContext) -> int:
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] OFF POST 命令请求", user.full_name, user.id)
        video_post_handler_data = context.chat_data.get("video_post_handler_data")
        if video_post_handler_data is None:
            video_post_handler_data = SRVideoHandlerData()
            context.chat_data["video_post_handler_data"] = video_post_handler_data
        text = f"✿✿ヽ（°▽°）ノ✿ 你好！ {user.username} ，\n只需复制官网URL回复即可 \n退出投稿只需回复退出"
        reply_keyboard = [["退出"]]
        await message.reply_text(text, reply_markup=ReplyKeyboardMarkup(reply_keyboard, True, True))
        return CHECK_POST

    @staticmethod
    def extract_post_id(text: str) -> int:
        """ https://sr.mihoyo.com/news/101964 """
        if not text.startswith("https://sr.mihoyo.com/news/"):
            return -1
        try:
            return int(text.split("/")[-1])
        except (ValueError, IndexError):
            return -1

    @conversation.state(state=CHECK_POST)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=True)
    @error_callable
    async def check_post(self, update: Update, context: CallbackContext) -> int:
        video_post_handler_data: SRVideoHandlerData = context.chat_data.get("video_post_handler_data")
        message = update.effective_message
        if message.text == "退出":
            await message.reply_text("退出投稿", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END

        post_id = self.extract_post_id(update.message.text)
        if post_id == -1:
            await message.reply_text("获取作品ID错误，请检查连接是否合法", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        video_post_handler_data.post_id = post_id
        return await self.send_post_info(video_post_handler_data, message)

    @staticmethod
    def parse_post_text(soup: BeautifulSoup, post_info: OffContent) -> str:
        post_p = soup.find_all("p")
        post_text = f"*{escape_markdown(post_info.sTitle, version=2)}*\n\n"
        start = True
        for p in post_p:
            t = p.get_text()
            if not t and start:
                continue
            start = False
            post_text += f"{escape_markdown(p.get_text(), version=2)}\n"
        return post_text

    @staticmethod
    def parse_post_video(soup: BeautifulSoup) -> str:
        post_video = soup.find("video")
        if post_video is not None:
            post_video_src = post_video.get("src")
            if post_video_src is not None:
                return post_video_src
        return ""

    async def parse_post_image(self, soup: BeautifulSoup) -> List[ArtworkImage]:
        post_images = soup.find_all("img")
        images = []
        for image in post_images:
            image_src = image.get("src")
            if image_src is not None:
                image_content = await self.client.get(image_src)
                images.append(ArtworkImage(art_id=0, page=0, data=image_content.content))
        return images

    async def send_post_info(self, video_post_handler_data: SRVideoHandlerData, message: Message) -> int:
        post_info = await self.get_official_new(video_post_handler_data.post_id)
        if post_info is None:
            await message.reply_text(f"错误！获取文章 https://sr.mihoyo.com/news/{video_post_handler_data.post_id} 信息失败")
            return ConversationHandler.END
        post_soup = BeautifulSoup(post_info.sContent, features="html.parser")
        # content
        post_text = self.parse_post_text(post_soup, post_info)
        post_text += f"\n[source](https://sr.mihoyo.com/news/{video_post_handler_data.post_id})"
        if len(post_text) >= MessageLimit.CAPTION_LENGTH:
            post_text = post_text[: MessageLimit.CAPTION_LENGTH]
            await message.reply_text(f"警告！图片字符描述已经超过 {MessageLimit.CAPTION_LENGTH} 个字，已经切割")
        # video
        if not video_post_handler_data.post_video:
            if post_video := self.parse_post_video(post_soup):
                await message.reply_text(f"检测到视频，请转发下载好的视频给我，视频链接：{post_video}")
                return CHECK_VIDEO
        else:
            await message.reply_video(video_post_handler_data.post_video, caption=post_text, parse_mode=ParseMode.MARKDOWN_V2)
        # image
        post_images = []
        if not video_post_handler_data.post_video:
            post_images = await self.parse_post_image(post_soup)
            try:
                if len(post_images) > 1:
                    media = [InputMediaPhoto(img_info.data) for img_info in post_images]
                    media[0] = InputMediaPhoto(post_images[0].data, caption=post_text, parse_mode=ParseMode.MARKDOWN_V2)
                    if len(media) > 10:
                        media = media[:10]
                        await message.reply_text("获取到的图片已经超过10张，为了保证发送成功，已经删除一部分图片")
                    await message.reply_media_group(media)
                elif len(post_images) == 1:
                    image = post_images[0]
                    await message.reply_photo(image.data, caption=post_text, parse_mode=ParseMode.MARKDOWN_V2)
                else:
                    await message.reply_text(post_text, reply_markup=ReplyKeyboardRemove())
                    return ConversationHandler.END
            except (BadRequest, TypeError) as exc:
                await message.reply_text("发送图片时发生错误，错误信息已经写到日记", reply_markup=ReplyKeyboardRemove())
                logger.error("SR_Post模块发送图片时发生错误")
                logger.exception(exc)
                return ConversationHandler.END
        video_post_handler_data.post_text = post_text
        video_post_handler_data.post_images = post_images
        video_post_handler_data.delete_photo = []
        video_post_handler_data.tags = []
        video_post_handler_data.channel_id = -1
        await message.reply_text("请选择你的操作", reply_markup=self.MENU_KEYBOARD)
        return CHECK_COMMAND

    @conversation.state(state=CHECK_VIDEO)
    @handler.message(filters=filters.VIDEO & ~filters.COMMAND, block=True)
    @error_callable
    async def check_video(self, update: Update, context: CallbackContext) -> int:
        message = update.effective_message
        video_post_handler_data: SRVideoHandlerData = context.chat_data.get("video_post_handler_data")
        video_post_handler_data.post_video = message.video.file_id
        await message.reply_text("视频已经保存，继续进行下一步操作")
        return await self.send_post_info(video_post_handler_data, message)

    @conversation.state(state=CHECK_COMMAND)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=True)
    @error_callable
    async def check_command(self, update: Update, context: CallbackContext) -> int:
        message = update.effective_message
        if message.text == "退出":
            await message.reply_text("退出任务", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        elif message.text == "推送频道":
            return await self.get_channel(update, context)
        elif message.text == "添加TAG":
            return await self.add_tags(update, context)
        elif message.text == "编辑文字":
            return await self.edit_text(update, context)
        elif message.text == "删除图片":
            return await self.delete_photo(update, context)
        return ConversationHandler.END

    @staticmethod
    async def delete_photo(update: Update, context: CallbackContext) -> int:
        video_post_handler_data: SRVideoHandlerData = context.chat_data.get("video_post_handler_data")
        photo_len = len(video_post_handler_data.post_images)
        message = update.effective_message
        await message.reply_text(f"请回复你要删除的图片的序列，从1开始，如果删除多张图片回复的序列请以空格作为分隔符，当前一共有 {photo_len} 张图片")
        return GTE_DELETE_PHOTO

    @conversation.state(state=GTE_DELETE_PHOTO)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=True)
    @error_callable
    async def get_delete_photo(self, update: Update, context: CallbackContext) -> int:
        video_post_handler_data: SRVideoHandlerData = context.chat_data.get("video_post_handler_data")
        photo_len = len(video_post_handler_data.post_images)
        message = update.effective_message
        args = message.text.split(" ")
        index: List[int] = []
        try:
            for temp in args:
                if int(temp) > photo_len:
                    raise ValueError
                index.append(int(temp))
        except ValueError:
            await message.reply_text("数据不合法，请重新操作")
            return GTE_DELETE_PHOTO
        video_post_handler_data.delete_photo = index
        await message.reply_text("删除成功")
        await message.reply_text("请选择你的操作", reply_markup=self.MENU_KEYBOARD)
        return CHECK_COMMAND

    @staticmethod
    async def get_channel(update: Update, _: CallbackContext) -> int:
        message = update.effective_message
        reply_keyboard = []
        try:
            for channel_info in bot.config.channels:
                name = channel_info.name
                reply_keyboard.append([f"{name}"])
        except KeyError as error:
            logger.error("从配置文件获取频道信息发生错误，退出任务", exc_info=error)
            await message.reply_text("从配置文件获取频道信息发生错误，退出任务", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        await message.reply_text("请选择你要推送的频道", reply_markup=ReplyKeyboardMarkup(reply_keyboard, True, True))
        return GET_POST_CHANNEL

    @conversation.state(state=GET_POST_CHANNEL)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=True)
    @error_callable
    async def get_post_channel(self, update: Update, context: CallbackContext) -> int:
        video_post_handler_data: SRVideoHandlerData = context.chat_data.get("video_post_handler_data")
        message = update.effective_message
        channel_id = -1
        try:
            for channel_info in bot.config.channels:
                if message.text == channel_info.name:
                    channel_id = channel_info.chat_id
        except KeyError as exc:
            logger.error("从配置文件获取频道信息发生错误，退出任务", exc_info=exc)
            logger.exception(exc)
            await message.reply_text("从配置文件获取频道信息发生错误，退出任务", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        if channel_id == -1:
            await message.reply_text("获取频道信息失败，请检查你输入的内容是否正确", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        video_post_handler_data.channel_id = channel_id
        reply_keyboard = [["确认", "退出"]]
        await message.reply_text("请核对你修改的信息", reply_markup=ReplyKeyboardMarkup(reply_keyboard, True, True))
        return SEND_POST

    @staticmethod
    async def add_tags(update: Update, _: CallbackContext) -> int:
        message = update.effective_message
        await message.reply_text("请回复添加的tag名称，如果要添加多个tag请以空格作为分隔符，不用添加 # 作为开头，推送时程序会自动添加")
        return GET_TAGS

    @conversation.state(state=GET_TAGS)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=True)
    @error_callable
    async def get_tags(self, update: Update, context: CallbackContext) -> int:
        video_post_handler_data: SRVideoHandlerData = context.chat_data.get("video_post_handler_data")
        message = update.effective_message
        args = message.text.split(" ")
        video_post_handler_data.tags = args
        await message.reply_text("添加成功")
        await message.reply_text("请选择你的操作", reply_markup=self.MENU_KEYBOARD)
        return CHECK_COMMAND

    @staticmethod
    async def edit_text(update: Update, _: CallbackContext) -> int:
        message = update.effective_message
        await message.reply_text("请回复替换的文本")
        return GET_TEXT

    @conversation.state(state=GET_TEXT)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=True)
    @error_callable
    async def get_edit_text(self, update: Update, context: CallbackContext) -> int:
        video_post_handler_data: SRVideoHandlerData = context.chat_data.get("video_post_handler_data")
        message = update.effective_message
        video_post_handler_data.post_text = message.text_markdown_v2
        await message.reply_text("替换成功")
        await message.reply_text("请选择你的操作", reply_markup=self.MENU_KEYBOARD)
        return CHECK_COMMAND

    @conversation.state(state=SEND_POST)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=True)
    @error_callable
    async def send_post(self, update: Update, context: CallbackContext) -> int:
        video_post_handler_data: SRVideoHandlerData = context.chat_data.get("video_post_handler_data")
        message = update.effective_message
        if message.text == "退出":
            await message.reply_text(text="退出任务", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        await message.reply_text("正在推送", reply_markup=ReplyKeyboardRemove())
        channel_id = video_post_handler_data.channel_id
        channel_name = None
        try:
            for channel_info in bot.config.channels:
                if video_post_handler_data.channel_id == channel_info.chat_id:
                    channel_name = channel_info.name
        except KeyError as exc:
            logger.error("从配置文件获取频道信息发生错误，退出任务")
            logger.exception(exc)
            await message.reply_text("从配置文件获取频道信息发生错误，退出任务", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        post_text = video_post_handler_data.post_text
        post_images = []
        for index, _ in enumerate(video_post_handler_data.post_images):
            if index + 1 not in video_post_handler_data.delete_photo:
                post_images.append(video_post_handler_data.post_images[index])
        post_text += f" @{escape_markdown(channel_name)}"
        for tag in video_post_handler_data.tags:
            post_text += f" \\#{tag}"
        try:
            if len(post_images) > 1:
                media = [InputMediaPhoto(img_info.data) for img_info in post_images]
                media[0] = InputMediaPhoto(post_images[0].data, caption=post_text, parse_mode=ParseMode.MARKDOWN_V2)
                await context.bot.send_media_group(channel_id, media=media)
            elif len(post_images) == 1:
                image = post_images[0]
                await context.bot.send_photo(
                    channel_id, photo=image.data, caption=post_text, parse_mode=ParseMode.MARKDOWN_V2
                )
            elif video_post_handler_data.post_video:
                await context.bot.send_video(
                    channel_id, video=video_post_handler_data.post_video, caption=post_text, parse_mode=ParseMode.MARKDOWN_V2
                )
            elif not post_images:
                await context.bot.send_message(channel_id, post_text, parse_mode=ParseMode.MARKDOWN_V2)
            else:
                await message.reply_text("图片获取错误", reply_markup=ReplyKeyboardRemove())  # excuse?
                return ConversationHandler.END
        except (BadRequest, TypeError) as exc:
            await message.reply_text("发送图片/视频时发生错误，错误信息已经写到日记", reply_markup=ReplyKeyboardRemove())
            logger.error("SR_Post 模块发送图片/视频时发生错误")
            logger.exception(exc)
            return ConversationHandler.END
        await message.reply_text("推送成功", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
