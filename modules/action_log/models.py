from datetime import datetime, timedelta

from pydantic import BaseModel
from simnet.models.starrail.self_help import StarRailSelfHelpActionLog


class ActionLogPair(BaseModel):
    start: StarRailSelfHelpActionLog
    end: StarRailSelfHelpActionLog

    @property
    def start_time(self) -> datetime:
        return self.start.time

    @property
    def end_time(self) -> datetime:
        return self.end.time

    @property
    def duration(self) -> timedelta:
        return self.end.time - self.start.time
