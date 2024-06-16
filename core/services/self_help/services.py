from typing import List, TYPE_CHECKING

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

    async def test_query(self) -> List["StarRailSelfHelpActionLog"]:
        data = []
        for record in (await self.repository.test_query()).records:
            data.append(ActionLogModel.de(record))
        return data
