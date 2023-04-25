from typing import List
from modules.wiki.base import WikiModel


class Raider(WikiModel):
    raider_url = WikiModel.BASE_URL + "raiders/"
    raider_path = WikiModel.BASE_PATH / "raiders"
    raider_info_path = WikiModel.BASE_PATH / "raiders" / "info.json"
    raider_path.mkdir(parents=True, exist_ok=True)

    def __init__(self):
        super().__init__()
        self.all_raiders = []

    def clear_class_data(self) -> None:
        self.all_raiders.clear()

    async def refresh(self):
        datas = await self.remote_get(self.raider_url + "info.json")
        data = datas.json()
        for name in data:
            photo = await self.remote_get(f"{self.raider_url}{name}.png")
            await self.save_file(photo.content, self.raider_path / f"{name}.png")
            self.all_raiders.append(name)
        await self.dump(data, self.raider_info_path)

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
