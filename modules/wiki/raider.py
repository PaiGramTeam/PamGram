import asyncio
from typing import List
from modules.wiki.base import WikiModel


class Raider(WikiModel):
    raider_url = WikiModel.BASE_URL + "raiders/"
    raider_path = WikiModel.BASE_PATH / "raiders"
    raider_info_path = WikiModel.BASE_PATH / "raiders" / "info.json"
    raider_path.mkdir(parents=True, exist_ok=True)

    def __init__(self):
        super().__init__()
        self.all_raiders: List[str] = []

    def clear_class_data(self) -> None:
        self.all_raiders.clear()

    async def refresh_task(self, name: str):
        photo = await self.remote_get(f"{self.raider_url}{name}.png")
        await self.save_file(photo.content, self.raider_path / f"{name}.png")

    async def refresh(self):
        datas = await self.remote_get(self.raider_url + "info.json")
        data = datas.json()
        tasks = []
        for name in data:
            tasks.append(self.refresh_task(name))
        await asyncio.gather(*tasks)
        await self.dump(data, self.raider_info_path)
        await self.read()

    async def read(self):
        if not self.raider_info_path.exists():
            await self.refresh()
            return
        datas = await WikiModel.read(self.raider_info_path)
        self.clear_class_data()
        for data in datas:
            self.all_raiders.append(data)

    def get_name_list(self) -> List[str]:
        return self.all_raiders.copy()

    def get_item_id(self, name: str) -> int:
        return self.all_raiders.index(name)
