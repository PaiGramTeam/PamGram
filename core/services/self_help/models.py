from influxdb_client import Point
from influxdb_client.client.flux_table import FluxRecord
from simnet.models.starrail.self_help import StarRailSelfHelpActionLog


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
            .time(data.time)
        )

    @staticmethod
    def de(data: "FluxRecord") -> "StarRailSelfHelpActionLog":
        return StarRailSelfHelpActionLog(
            id=data["id"], uid=data["uid"], time=data.get_time(), reason=data["reason"], client_ip=data["client_ip"]
        )
