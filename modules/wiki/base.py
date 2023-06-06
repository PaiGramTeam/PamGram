from pathlib import Path
from typing import List, Dict

import aiofiles
import ujson as jsonlib
from httpx import AsyncClient


class WikiModel:
    BASE_URL = "https://starrail-res.paimon.vip/data/"
    BASE_PATH = Path("data/wiki")
    BASE_PATH.mkdir(parents=True, exist_ok=True)

    def __init__(self):
        self.client = AsyncClient(timeout=120.0)

    async def remote_get(self, url: str):
        return await self.client.get(url)

    @staticmethod
    async def dump(datas, path: Path):
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(jsonlib.dumps(datas, indent=4, ensure_ascii=False))

    @staticmethod
    async def read(path: Path) -> List[Dict]:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            datas = jsonlib.loads(await f.read())
        return datas

    @staticmethod
    async def save_file(data, path: Path):
        async with aiofiles.open(path, "wb") as f:
            await f.write(data)

    @staticmethod
    async def read_file(path: Path):
        async with aiofiles.open(path, "rb") as f:
            return await f.read()
