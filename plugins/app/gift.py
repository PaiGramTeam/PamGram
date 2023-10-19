from datetime import datetime
from typing import List, Optional

from httpx import AsyncClient
from pydantic import BaseModel
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext, filters

from core.dependence.redisdb import RedisDB
from core.plugin import Plugin, handler


class Reward(BaseModel):
    name: str
    cnt: int

    @property
    def text(self) -> str:
        return f"{self.name} x{self.cnt}"


class Code(BaseModel):
    code: str
    reward: List[Reward]
    expire: int

    @property
    def text(self):
        reward_text = "，".join([reward.text for reward in self.reward])
        return f"<code>{self.code}</code> - {reward_text}"


class CodeList(BaseModel):
    main: List[Code]
    over: List[Code]


class GiftCodePlugin(Plugin):
    def __init__(self, redis: RedisDB):
        self.redis = redis.client
        self.redis_key = "gift:code"
        self.client = AsyncClient()
        self.api = "https://hsr-gift.paimon.vip/code.json"

    async def get_gift_code(self) -> Optional[CodeList]:
        try:
            req = await self.client.get(self.api)
            if req.status_code == 200:
                await self.redis.set(self.redis_key, req.text, ex=60 * 5)
                return CodeList.parse_raw(req.text)
            return None
        except Exception:
            return None

    async def get_gift_code_by_cache(self) -> Optional[CodeList]:
        data = await self.redis.get(self.redis_key)
        if data is None:
            return await self.get_gift_code()
        return CodeList.parse_raw(str(data, encoding="utf-8"))

    async def get_gift_code_message(self) -> str:
        data = await self.get_gift_code_by_cache()
        if data is None:
            return "请点击下方按钮查询目前可用的兑换码。"
        now = int(datetime.now().timestamp() * 1000)
        message = "目前可用的兑换码："
        main_effective_code = [code.text for code in data.main if code.expire > now]
        if main_effective_code:
            message += "\n\n国服：\n" + "\n".join(main_effective_code)
        over_effective_code = [code.text for code in data.over if code.expire > now]
        if over_effective_code:
            message += "\n\n国际服：\n" + "\n".join(over_effective_code)
        if not main_effective_code and not over_effective_code:
            return "目前没有可用的兑换码。"
        return message

    @handler.command("gift", block=False)
    @handler.message(filters=filters.Regex(r"^兑换码$"), block=False)
    async def start(self, update: Update, context: CallbackContext) -> None:
        message = update.effective_message
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(text="国际服兑换", url="https://hsr.hoyoverse.com/gift")],
                [InlineKeyboardButton(text="点我查看所有", url=f"https://t.me/{context.bot.username}/gift")],
            ],
        )
        reply = await message.reply_html(await self.get_gift_code_message(), reply_markup=keyboard)
        self.add_delete_message_job(message)
        self.add_delete_message_job(reply)
