from asyncio import sleep

from typing import TYPE_CHECKING

from simnet.errors import (
    TimedOut as SimnetTimedOut,
    BadRequest as SimnetBadRequest,
    InvalidCookies,
)

from core.services.self_help.services import ActionLogService
from gram_core.basemodel import RegionEnum
from gram_core.plugin import Plugin
from gram_core.services.cookies import CookiesService
from gram_core.services.cookies.models import CookiesStatusEnum
from plugins.tools.genshin import GenshinHelper, PlayerNotFoundError, CookiesNotFoundError
from utils.log import logger

if TYPE_CHECKING:
    from telegram.ext import ContextTypes

    from simnet import StarRailClient


class ActionLogSystem(Plugin):
    """登录记录系统"""

    def __init__(
        self,
        cookies: CookiesService,
        helper: GenshinHelper,
        action_log_service: ActionLogService,
    ):
        self.cookies = cookies
        self.helper = helper
        self.action_log_service = action_log_service

    async def import_action_log(self, client: "StarRailClient", authkey: str) -> bool:
        data = await client.get_starrail_action_log(authkey=authkey)
        # 确保第一个数据为登出、最后一条数据为登入
        if data[0].status == 1:
            data.pop(0)
        if data[-1].status == 0:
            data.pop(-1)
        return await self.action_log_service.add(data)

    async def daily_import_login(self, _: "ContextTypes.DEFAULT_TYPE"):
        logger.info("正在执行每日刷新登录记录任务")
        for cookie_model in await self.cookies.get_all(
            region=RegionEnum.HYPERION, status=CookiesStatusEnum.STATUS_SUCCESS
        ):
            user_id = cookie_model.user_id
            cookies = cookie_model.data
            if cookies.get("stoken") is None:
                continue
            try:
                async with self.helper.genshin(user_id, region=RegionEnum.HYPERION) as client:
                    client: "StarRailClient"
                    try:
                        authkey = await client.get_authkey_by_stoken("csc")
                    except ValueError:
                        logger.warning("用户 user_id[%s] 请求登录记录失败 无 stoken", user_id)
                        continue
                    await self.import_action_log(client, authkey)
            except (InvalidCookies, PlayerNotFoundError, CookiesNotFoundError):
                continue
            except SimnetBadRequest as exc:
                logger.warning(
                    "用户 user_id[%s] 请求登录记录失败 [%s]%s", user_id, exc.ret_code, exc.original or exc.message
                )
                continue
            except SimnetTimedOut:
                logger.info("用户 user_id[%s] 请求登录记录超时", user_id)
                continue
            except Exception as exc:
                logger.error("执行自动刷新登录记录时发生错误 user_id[%s]", user_id, exc_info=exc)
                continue
            await sleep(1)
