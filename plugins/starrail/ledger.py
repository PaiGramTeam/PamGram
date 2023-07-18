import os
import re
from datetime import datetime, timedelta

from simnet.errors import BadRequest as SimnetBadRequest, DataNotPublic, InvalidCookies
from simnet.models.starrail.diary import StarRailDiary
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import filters, CallbackContext
from telegram.helpers import create_deep_linked_url

from core.plugin import Plugin, handler
from core.services.cookies import CookiesService
from core.services.template.models import RenderResult
from core.services.template.services import TemplateService
from plugins.tools.genshin import CookiesNotFoundError, GenshinHelper, PlayerNotFoundError
from utils.log import logger


__all__ = ("LedgerPlugin",)


class LedgerPlugin(Plugin):
    """开拓月历查询"""

    def __init__(
        self,
        helper: GenshinHelper,
        cookies_service: CookiesService,
        template_service: TemplateService,
    ):
        self.template_service = template_service
        self.cookies_service = cookies_service
        self.current_dir = os.getcwd()
        self.helper = helper

    async def _start_get_ledger(self, client, year, month) -> RenderResult:
        req_month = f"{year}0{month}" if month < 10 else f"{year}{month}"
        diary_info: StarRailDiary = await client.get_starrail_diary(client.uid, month=req_month)
        color = ["#73a9c6", "#d56565", "#70b2b4", "#bd9a5a", "#739970", "#7a6da7", "#597ea0"]
        categories = [
            {
                "id": i.id,
                "name": i.name,
                "color": color[idx % len(color)],
                "amount": i.amount,
                "percentage": i.percentage,
            }
            for idx, i in enumerate(diary_info.month_data.categories)
        ]
        color = [i["color"] for i in categories]

        def format_amount(amount: int) -> str:
            return f"{round(amount / 10000, 2)}w" if amount >= 10000 else amount

        ledger_data = {
            "uid": client.uid,
            "day": month,
            "current_hcoin": format_amount(diary_info.month_data.current_hcoin),
            "gacha": int(diary_info.month_data.current_hcoin / 160),
            "current_rails_pass": format_amount(diary_info.month_data.current_rails_pass),
            "last_hcoin": format_amount(diary_info.month_data.last_hcoin),
            "last_gacha": int(diary_info.month_data.last_hcoin / 160),
            "last_rails_pass": format_amount(diary_info.month_data.last_rails_pass),
            "categories": categories,
            "color": color,
        }
        render_result = await self.template_service.render(
            "starrail/ledger/ledger.html", ledger_data, {"width": 580, "height": 610}
        )
        return render_result

    @handler.command(command="ledger", block=False)
    @handler.message(filters=filters.Regex("^开拓月历查询(.*)"), block=False)
    async def command_start(self, update: Update, context: CallbackContext) -> None:
        user = update.effective_user
        message = update.effective_message

        now = datetime.now()
        now_time = (now - timedelta(days=1)) if now.day == 1 and now.hour <= 4 else now
        month = now_time.month
        try:
            args = self.get_args(context)
            if len(args) >= 1:
                month = args[0].replace("月", "")
            if re_data := re.findall(r"\d+", str(month)):
                month = int(re_data[0])
            else:
                num_dict = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
                month = sum(num_dict.get(i, 0) for i in str(month))
            # check right
            allow_month_year = {now_time.month: now_time.year}

            last_month = now_time.replace(day=1) - timedelta(days=1)
            allow_month_year[last_month.month] = last_month.year

            last_month = last_month.replace(day=1) - timedelta(days=1)
            allow_month_year[last_month.month] = last_month.year

            if (month not in allow_month_year) or (not isinstance(month, int)):
                raise IndexError
            year = allow_month_year[month]
        except IndexError:
            reply_message = await message.reply_text("仅可查询最新三月的数据，请重新输入")
            if filters.ChatType.GROUPS.filter(message):
                self.add_delete_message_job(reply_message, delay=30)
                self.add_delete_message_job(message, delay=30)
            return
        logger.info("用户 %s[%s] 查询开拓月历", user.full_name, user.id)
        await message.reply_chat_action(ChatAction.TYPING)
        try:
            async with self.helper.genshin(user.id) as client:
                try:
                    render_result = await self._start_get_ledger(client, year, month)
                except InvalidCookies as exc:  # 如果抛出InvalidCookies 判断是否真的玄学过期（或权限不足？）
                    await client.get_starrail_user(client.uid)
                    logger.warning(
                        "用户 %s[%s] 无法请求开拓月历数据 API返回信息为 [%s]%s", user.full_name, user.id, exc.retcode, exc.original
                    )
                    reply_message = await message.reply_text("出错了呜呜呜 ~ 当前访问令牌无法请求角色数数据，请尝试重新获取Cookie。")
                    if filters.ChatType.GROUPS.filter(message):
                        self.add_delete_message_job(reply_message, delay=30)
                        self.add_delete_message_job(message, delay=30)
                    return
        except (PlayerNotFoundError, CookiesNotFoundError):
            buttons = [
                [
                    InlineKeyboardButton(
                        "点我绑定账号", url=create_deep_linked_url(self.application.bot.username, "set_cookie")
                    )
                ]
            ]
            if filters.ChatType.GROUPS.filter(message):
                reply_message = await message.reply_text(
                    "未查询到您所绑定的账号信息，请先私聊彦卿绑定账号", reply_markup=InlineKeyboardMarkup(buttons)
                )
                self.add_delete_message_job(reply_message, delay=30)
                self.add_delete_message_job(message, delay=30)
            else:
                await message.reply_text("未查询到您所绑定的账号信息，请先绑定账号", reply_markup=InlineKeyboardMarkup(buttons))
            return
        except DataNotPublic:
            reply_message = await message.reply_text("查询失败惹，可能是开拓月历功能被禁用了？请先通过米游社或者 hoyolab 获取一次开拓月历后重试。")
            if filters.ChatType.GROUPS.filter(message):
                self.add_delete_message_job(reply_message, delay=30)
                self.add_delete_message_job(message, delay=30)
            return
        except SimnetBadRequest as exc:
            if exc.retcode == -120:
                await message.reply_text("当前角色开拓等级不足，暂时无法获取信息")
                return
            raise exc
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        await render_result.reply_photo(message, filename=f"{client.player_id}.png", allow_sending_without_reply=True)
