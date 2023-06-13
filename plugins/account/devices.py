from typing import Dict

import ujson
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, TelegramObject, Update
from telegram.ext import CallbackContext, ConversationHandler, filters
from telegram.helpers import escape_markdown

from core.basemodel import RegionEnum
from core.plugin import Plugin, conversation, handler
from core.services.cookies.services import CookiesService
from core.services.devices import DevicesService
from core.services.devices.models import DevicesDataBase as Devices
from core.services.players.services import PlayersService
from utils.log import logger

from modules.apihelper.utility.devices import devices_methods

__all__ = ("AccountDevicesPlugin",)


class AccountDevicesPluginData(TelegramObject):
    devices: dict = {}
    account_id: int = 0

    def reset(self):
        self.devices = {}
        self.account_id = 0


CHECK_SERVER, INPUT_DEVICES, COMMAND_RESULT = range(10100, 10103)


class AccountDevicesPlugin(Plugin.Conversation):
    """设备绑定"""

    def __init__(
        self,
        players_service: PlayersService = None,
        cookies_service: CookiesService = None,
        devices_service: DevicesService = None,
    ):
        self.cookies_service = cookies_service
        self.players_service = players_service
        self.devices_service = devices_service
        devices_methods.service = devices_service

    @staticmethod
    def parse_cookie(cookie: Dict[str, str]) -> Dict[str, str]:
        if not isinstance(cookie, dict):
            raise ValueError
        cookies = {}
        must_keys = ["x-rpc-device_id", "x-rpc-device_fp"]
        optional_keys = ["x-rpc-device_name"]
        for k in must_keys:
            if k not in cookie:
                return {}.copy()

        for k in must_keys + optional_keys:
            cookies[k] = cookie.get(k)

        return {k: v for k, v in cookies.items() if v is not None}

    @conversation.entry_point
    @handler.command(command="setdevice", filters=filters.ChatType.PRIVATE, block=False)
    @handler.command(command="setdevices", filters=filters.ChatType.PRIVATE, block=False)
    async def command_start(self, update: Update, context: CallbackContext) -> int:
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] 绑定设备命令请求", user.full_name, user.id)
        account_devices_plugin_data: AccountDevicesPluginData = context.chat_data.get("account_devices_plugin_data")
        if account_devices_plugin_data is None:
            account_devices_plugin_data = AccountDevicesPluginData()
            context.chat_data["account_devices_plugin_data"] = account_devices_plugin_data
        else:
            account_devices_plugin_data.reset()

        text = f'你好 {user.mention_markdown_v2()} {escape_markdown("！请选择要绑定的服务器！或回复退出取消操作")}'
        reply_keyboard = [["米游社", "HoYoLab"], ["退出"]]
        await message.reply_markdown_v2(text, reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
        return CHECK_SERVER

    @conversation.state(state=CHECK_SERVER)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=False)
    async def check_server(self, update: Update, context: CallbackContext) -> int:
        user = update.effective_user
        message = update.effective_message
        account_devices_plugin_data: AccountDevicesPluginData = context.chat_data.get("account_devices_plugin_data")
        if message.text == "退出":
            await message.reply_text("退出任务", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        if message.text == "米游社":
            region = RegionEnum.HYPERION
            bbs_name = "米游社"
        elif message.text == "HoYoLab":
            region = RegionEnum.HOYOLAB
            bbs_name = "HoYoLab"
        else:
            await message.reply_text("选择错误，请重新选择")
            return CHECK_SERVER
        player_info = await self.players_service.get(user.id, region=region)
        if player_info:
            cookies_database = await self.cookies_service.get(user.id, player_info.account_id, region)
            if not cookies_database:
                await message.reply_text(f"你还没有绑定 {bbs_name} 的Cookies，请先绑定Cookies")
                return ConversationHandler.END
            account_devices_plugin_data.account_id = player_info.account_id
        else:
            await message.reply_text(f"你还没有绑定 {bbs_name} 的Cookies，请先绑定Cookies")
            return ConversationHandler.END
        await message.reply_text(f"请输入{bbs_name}的 JSON 格式的设备 ID 以及对应 FP ！或回复退出取消操作", reply_markup=ReplyKeyboardRemove())
        return INPUT_DEVICES

    @conversation.state(state=INPUT_DEVICES)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=False)
    async def input_cookies(self, update: Update, context: CallbackContext) -> int:
        message = update.effective_message
        user = update.effective_user
        account_devices_plugin_data: AccountDevicesPluginData = context.chat_data.get("account_devices_plugin_data")
        if message.text == "退出":
            await message.reply_text("退出任务", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        try:
            devices = self.parse_cookie(ujson.loads(message.text))
        except (AttributeError, ValueError, IndexError, ujson.JSONDecodeError) as exc:
            logger.info("用户 %s[%s] Devices解析出现错误\ntext:%s", user.full_name, user.id, message.text)
            logger.debug("解析Devices出现错误", exc_info=exc)
            await message.reply_text("解析Devices出现错误，请检查是否正确", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        if not devices:
            logger.info("用户 %s[%s] Devices格式有误", user.full_name, user.id)
            await message.reply_text("Devices格式有误，请检查", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        account_devices_plugin_data.devices = devices
        reply_keyboard = [["确认", "退出"]]
        await message.reply_markdown_v2("请确认修改！", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
        return COMMAND_RESULT

    @conversation.state(state=COMMAND_RESULT)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=False)
    async def command_result(self, update: Update, context: CallbackContext) -> int:
        user = update.effective_user
        message = update.effective_message
        account_devices_plugin_data: AccountDevicesPluginData = context.chat_data.get("account_devices_plugin_data")
        if message.text == "退出":
            await message.reply_text("退出任务", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        if message.text == "确认":
            device = await self.devices_service.get(account_devices_plugin_data.account_id)
            if device:
                device.data = account_devices_plugin_data.devices
                await self.devices_service.update(device)
                logger.success("用户 %s[%s] 更新Devices", user.full_name, user.id)
            else:
                device = Devices(
                    account_id=account_devices_plugin_data.account_id,
                    data=account_devices_plugin_data.devices,
                )
                await self.devices_service.add(device)
                logger.info("用户 %s[%s] 绑定Devices成功", user.full_name, user.id)
            await message.reply_text("保存成功", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        await message.reply_text("回复错误，请重新输入")
        return COMMAND_RESULT
