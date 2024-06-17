from typing import TYPE_CHECKING, List

from gram_core.base_service import BaseService
from gram_core.dependence.influxdb import InfluxDatabase

if TYPE_CHECKING:
    from influxdb_client.client.flux_table import FluxTable
    from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
    from influxdb_client import Point


class ActionLogRepository(BaseService.Component):

    def __init__(self, influxdb: InfluxDatabase):
        self.influxdb = influxdb
        self.client = influxdb.client
        self.bucket = "hkrpg"

    async def add(self, p: List["Point"]) -> bool:
        async with self.client() as client:
            client: "InfluxDBClientAsync"
            return await client.write_api().write(self.bucket, record=p)

    async def count_uptime_period(self, uid: int) -> "FluxTable":
        async with self.client() as client:
            client: "InfluxDBClientAsync"
            query = (
                'import "date"'
                'from(bucket: "{}")'
                "|> range(start: -180d)"
                '|> filter(fn: (r) => r["_measurement"] == "action_log")'
                '|> filter(fn: (r) => r["_field"] == "status")'
                '|> filter(fn: (r) => r["_value"] == 1)'
                '|> filter(fn: (r) => r["uid"] == "{}")'
                "|> aggregateWindow(every: 1h, fn: count)"
            ).format(self.bucket, uid)
            query += '|> map(fn: (r) => ({r with hour: date.hour(t: r._time)}))|> yield(name: "hourly_count")'
            tables = await client.query_api().query(query)
            for table in tables:
                return table

    async def get_data(self, uid: int, day: int = 30) -> "FluxTable":
        async with self.client() as client:
            client: "InfluxDBClientAsync"
            query = (
                'from(bucket: "{}")'
                "|> range(start: -{}d)"
                '|> filter(fn: (r) => r["_measurement"] == "action_log")'
                '|> filter(fn: (r) => r["uid"] == "{}")'
                '|> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")'
            ).format(self.bucket, day, uid)
            tables = await client.query_api().query(query)
            for table in tables:
                return table
