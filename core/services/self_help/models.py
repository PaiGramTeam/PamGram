from datetime import timedelta

from influxdb_client import Point
from influxdb_client.client.flux_table import FluxRecord
from simnet.models.starrail.self_help import StarRailSelfHelpActionLog

from modules.action_log.date import TZ

FIX = timedelta(minutes=6)


class ActionLogModel:
    @staticmethod
    def en(data: "StarRailSelfHelpActionLog") -> Point:
        return (
            Point.measurement("action_log")
            .tag("uid", data.uid)
            .field("id", data.id)
            .field("status", data.status)
            .field("reason", data.reason.value)
            .field("client_ip", data.client_ip)
            .time(data.time.replace(tzinfo=TZ) + FIX)
        )

    @staticmethod
    def de(data: "FluxRecord") -> "StarRailSelfHelpActionLog":
        utc_time = data.get_time()
        time = utc_time.astimezone(TZ)
        return StarRailSelfHelpActionLog(
            id=data["id"], uid=data["uid"], time=time, reason=data["reason"], client_ip=data["client_ip"]
        )
