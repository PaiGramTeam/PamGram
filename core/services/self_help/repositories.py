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

    async def test_query(self) -> "FluxTable":
        async with self.client() as client:
            client: "InfluxDBClientAsync"
            query = (
                'from(bucket: "{}") '
                "|> range(start: -7d) "
                '|> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")'
            ).format(self.bucket)
            tables = await client.query_api().query(query)
            for table in tables:
                return table
