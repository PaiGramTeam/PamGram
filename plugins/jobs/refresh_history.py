import datetime
from asyncio import sleep
from typing import TYPE_CHECKING, Dict

from simnet.errors import (
    TimedOut as SimnetTimedOut,
    BadRequest as SimnetBadRequest,
    InvalidCookies,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden

from core.plugin import Plugin, job
from core.services.history_data.services import (
    HistoryDataAbyssServices,
    HistoryDataLedgerServices,
    HistoryDataChallengeStoryServices,
    HistoryDataChallengeBossServices,
    HistoryDataChallengePeakServices,
)
from gram_core.basemodel import RegionEnum
from gram_core.plugin import handler
from gram_core.services.cookies import CookiesService
from gram_core.services.cookies.models import CookiesStatusEnum
from modules.errorpush import SentryClient
from plugins.starrail.challenge import ChallengePlugin
from plugins.starrail.challenge_boss import ChallengeBossPlugin
from plugins.starrail.challenge_peak import ChallengePeakPlugin
from plugins.starrail.challenge_story import ChallengeStoryPlugin
from plugins.starrail.ledger import LedgerPlugin
from plugins.tools.genshin import GenshinHelper, PlayerNotFoundError, CookiesNotFoundError
from utils.log import logger

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

    from simnet import StarRailClient

REGION = [RegionEnum.HYPERION, RegionEnum.HOYOLAB]
NOTICE_TEXT = """#### %s更新 ####
时间：%s (UTC+8)
UID: %s
结果: 新的%s已保存，可通过命令回顾"""


class RefreshHistoryJob(Plugin):
    """历史记录定时刷新"""

    def __init__(
        self,
        cookies: CookiesService,
        genshin_helper: GenshinHelper,
        history_abyss: HistoryDataAbyssServices,
        history_data_abyss_story: HistoryDataChallengeStoryServices,
        history_ledger: HistoryDataLedgerServices,
        history_data_abyss_boss: HistoryDataChallengeBossServices,
        history_data_abyss_peak: HistoryDataChallengePeakServices,
    ):
        self.cookies = cookies
        self.genshin_helper = genshin_helper
        self.history_data_abyss = history_abyss
        self.history_data_abyss_story = history_data_abyss_story
        self.history_data_ledger = history_ledger
        self.history_data_abyss_boss = history_data_abyss_boss
        self.history_data_abyss_peak = history_data_abyss_peak

    @staticmethod
    async def send_notice(context: "ContextTypes.DEFAULT_TYPE", user_id: int, notice_text: str):
        try:
            await context.bot.send_message(user_id, notice_text, parse_mode=ParseMode.HTML)
        except (BadRequest, Forbidden) as exc:
            logger.error("执行自动刷新历史记录时发生错误 user_id[%s] Message[%s]", user_id, exc.message)
        except Exception as exc:
            logger.error("执行自动刷新历史记录时发生错误 user_id[%s]", user_id, exc_info=exc)

    async def save_abyss_data(self, client: "StarRailClient") -> bool:
        uid = client.player_id
        abyss_data = await client.get_starrail_challenge(uid, previous=False, lang="zh-cn")
        if abyss_data.has_data:
            return await ChallengePlugin.save_abyss_data(self.history_data_abyss, uid, abyss_data)
        return False

    async def send_abyss_notice(self, context: "ContextTypes.DEFAULT_TYPE", user_id: int, uid: int):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        notice_text = NOTICE_TEXT % ("混沌回忆历史记录", now, uid, "挑战记录")
        await self.send_notice(context, user_id, notice_text)

    async def save_abyss_story_data(self, client: "StarRailClient") -> bool:
        uid = client.player_id
        abyss_data = await client.get_starrail_challenge_story(uid, previous=False, lang="zh-cn")
        if abyss_data.has_data and abyss_data.groups:
            group = abyss_data.groups[0]
            return await ChallengeStoryPlugin.save_abyss_data(self.history_data_abyss_story, uid, abyss_data, group)
        return False

    async def send_abyss_story_notice(self, context: "ContextTypes.DEFAULT_TYPE", user_id: int, uid: int):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        notice_text = NOTICE_TEXT % ("虚构叙事历史记录", now, uid, "挑战记录")
        await self.send_notice(context, user_id, notice_text)

    async def _save_ledger_data(self, client: "StarRailClient", year: int, month: int) -> bool:
        req_month = f"{year}0{month}" if month < 10 else f"{year}{month}"
        diary_info = await client.get_starrail_diary(client.player_id, month=req_month)
        return await LedgerPlugin.save_ledger_data(self.history_data_ledger, client.player_id, diary_info)

    @staticmethod
    def get_ledger_months() -> Dict[int, int]:
        now = datetime.datetime.now()
        now_time = (now - datetime.timedelta(days=1)) if now.day == 1 and now.hour <= 4 else now
        months = {}
        last_month = now_time.replace(day=1) - datetime.timedelta(days=1)
        months[last_month.month] = last_month.year

        last_month = last_month.replace(day=1) - datetime.timedelta(days=1)
        months[last_month.month] = last_month.year
        return months

    async def save_ledger_data(self, client: "StarRailClient") -> bool:
        months = self.get_ledger_months()
        ok = False
        for month, year in months.items():
            if await self._save_ledger_data(client, year, month):
                ok = True
        return ok

    async def send_ledger_notice(self, context: "ContextTypes.DEFAULT_TYPE", user_id: int, uid: int):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        notice_text = NOTICE_TEXT % ("旅行札记历史记录", now, uid, "旅行札记历史记录")
        await self.send_notice(context, user_id, notice_text)

    async def save_abyss_boss_data(self, client: "StarRailClient") -> bool:
        uid = client.player_id
        abyss_data = await client.get_starrail_challenge_boss(uid, previous=False, lang="zh-cn")
        if abyss_data.has_data and abyss_data.groups:
            group = abyss_data.groups[0]
            return await ChallengeBossPlugin.save_abyss_data(self.history_data_abyss_boss, uid, abyss_data, group)
        return False

    async def send_abyss_boss_notice(self, context: "ContextTypes.DEFAULT_TYPE", user_id: int, uid: int):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        notice_text = NOTICE_TEXT % ("末日幻影历史记录", now, uid, "挑战记录")
        await self.send_notice(context, user_id, notice_text)

    async def save_abyss_peak_data(self, client: "StarRailClient") -> bool:
        uid = client.player_id
        abyss_data = await client.get_starrail_challenge_peak(uid, previous=False, lang="zh-cn")
        if abyss_data.challenge_peak_best_record_brief.total_battle_num and abyss_data.challenge_peak_records:
            group = abyss_data.challenge_peak_records[0]
            return await ChallengePeakPlugin.save_abyss_data(self.history_data_abyss_peak, uid, abyss_data, group)
        return False

    async def send_abyss_peak_notice(self, context: "ContextTypes.DEFAULT_TYPE", user_id: int, uid: int):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        notice_text = NOTICE_TEXT % ("异相仲裁历史记录", now, uid, "挑战记录")
        await self.send_notice(context, user_id, notice_text)

    @handler.command(command="remove_same_history", block=False, admin=True)
    async def remove_same_history(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE"):
        user = update.effective_user
        logger.info("用户 %s[%s] remove_same_history 命令请求", user.full_name, user.id)
        message = update.effective_message
        reply = await message.reply_text("正在执行移除相同数据历史记录任务，请稍后...")
        text = "移除相同数据历史记录任务完成\n"
        num1 = await self.history_data_abyss.remove_same_data()
        text += f"混沌回忆数据移除数量：{num1}\n"
        num3 = await self.history_data_abyss_story.remove_same_data()
        text += f"虚构叙事数据移除数量：{num3}\n"
        num2 = await self.history_data_ledger.remove_same_data()
        text += f"开拓月历数据移除数量：{num2}\n"
        num4 = await self.history_data_abyss_boss.remove_same_data()
        text += f"末日幻影数据移除数量：{num4}\n"
        num5 = await self.history_data_abyss_peak.remove_same_data()
        text += f"异相仲裁数据移除数量：{num5}\n"
        await reply.edit_text(text)

    @handler.command(command="refresh_all_history", block=False, admin=True)
    async def refresh_all_history(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        user = update.effective_user
        logger.info("用户 %s[%s] refresh_all_history 命令请求", user.full_name, user.id)
        message = update.effective_message
        reply = await message.reply_text("正在执行刷新历史记录任务，请稍后...")
        await self.daily_refresh_history(context)
        await reply.edit_text("全部账号刷新历史记录任务完成")

    @job.run_daily(time=datetime.time(hour=6, minute=1, second=0), name="RefreshHistoryJob")
    @SentryClient.monitor(monitor_slug="RefreshHistoryJob")
    async def daily_refresh_history(self, context: "ContextTypes.DEFAULT_TYPE"):
        logger.info("正在执行每日刷新历史记录任务")
        for database_region in REGION:
            for cookie_model in await self.cookies.get_all(
                region=database_region, status=CookiesStatusEnum.STATUS_SUCCESS
            ):
                user_id = cookie_model.user_id
                try:
                    async with self.genshin_helper.genshin(user_id) as client:
                        if await self.save_abyss_data(client):
                            await self.send_abyss_notice(context, user_id, client.player_id)
                        if await self.save_abyss_story_data(client):
                            await self.send_abyss_story_notice(context, user_id, client.player_id)
                        if await self.save_ledger_data(client):
                            await self.send_ledger_notice(context, user_id, client.player_id)
                        if await self.save_abyss_boss_data(client):
                            await self.send_abyss_boss_notice(context, user_id, client.player_id)
                        if await self.save_abyss_peak_data(client):
                            await self.send_abyss_peak_notice(context, user_id, client.player_id)
                except (InvalidCookies, PlayerNotFoundError, CookiesNotFoundError):
                    continue
                except SimnetBadRequest as exc:
                    logger.warning(
                        "用户 user_id[%s] 请求历史记录失败 [%s]%s", user_id, exc.ret_code, exc.original or exc.message
                    )
                    continue
                except SimnetTimedOut:
                    logger.info("用户 user_id[%s] 请求历史记录超时", user_id)
                    continue
                except Exception as exc:
                    logger.error("执行自动刷新历史记录时发生错误 user_id[%s]", user_id, exc_info=exc)
                    continue
                await sleep(1)

        logger.success("执行每日刷新历史记录任务完成")
