from typing import List, TYPE_CHECKING, Dict

from core.services.self_help.models import ActionLogModel
from core.services.self_help.repositories import ActionLogRepository
from gram_core.base_service import BaseService

if TYPE_CHECKING:
    from simnet.models.starrail.self_help import StarRailSelfHelpActionLog


class ActionLogService(BaseService):
    def __init__(self, repository: ActionLogRepository):
        self.repository = repository

    async def add(self, p: List["StarRailSelfHelpActionLog"]) -> bool:
        return await self.repository.add([ActionLogModel.en(data) for data in p])

    async def count_uptime_period(self, uid: int) -> Dict[int, int]:
        """计算最近一个月不同时间点的登录次数"""
        data = {k: 0 for k in range(24)}
        r = await self.repository.count_uptime_period(uid)
        if not r:
            return data
        for record in r.records:
            if record.get_value():
                data[record["hour"]] += 1
        return data

    async def get_data(self, uid: int, day: int = 30) -> List["StarRailSelfHelpActionLog"]:
        """获取指定天数内的某用户的登录记录"""
        data = []
        r = await self.repository.get_data(uid, day)
        if not r:
            return data
        for record in r.records:
            data.append(ActionLogModel.de(record))
        return data
