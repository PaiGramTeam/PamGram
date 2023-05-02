import asyncio
from typing import List, Dict
from modules.wiki.base import WikiModel


class Raider(WikiModel):
    raider_url = "https://raw.githubusercontent.com/PaiGramTeam/star-rail-atlas/master"
    raider_path = WikiModel.BASE_PATH / "raiders"
    raider_role_path = WikiModel.BASE_PATH / "raiders" / "role"
    raider_light_cone_path = WikiModel.BASE_PATH / "raiders" / "light_cone"
    raider_role_material_path = WikiModel.BASE_PATH / "raiders" / "role_material"
    raider_info_path = WikiModel.BASE_PATH / "raiders" / "path.json"
    raider_role_path.mkdir(parents=True, exist_ok=True)
    raider_light_cone_path.mkdir(parents=True, exist_ok=True)
    raider_role_material_path.mkdir(parents=True, exist_ok=True)
    name_map = {"role": "role", "lightcone": "light_cone", "material for role": "role_material"}

    def __init__(self):
        super().__init__()
        self.all_role_raiders: List[str] = []
        self.all_light_cone_raiders: List[str] = []
        self.all_role_material_raiders: List[str] = []

    def clear_class_data(self) -> None:
        self.all_role_raiders.clear()
        self.all_light_cone_raiders.clear()
        self.all_role_material_raiders.clear()

    async def refresh_task(self, name: str, path: str = "", start: str = ""):
        photo = await self.remote_get(f"{self.raider_url}{path}")
        await self.save_file(photo.content, self.raider_path / start / f"{name}.png")

    async def refresh(self):
        datas = await self.remote_get(self.raider_url + "/path.json")
        data = datas.json()
        new_data = {}
        for key, start in self.name_map.items():
            new_data[start] = list(data[key].keys())
            tasks = []
            for name, path in data[key].items():
                tasks.append(self.refresh_task(name, path, start))
            await asyncio.gather(*tasks)
        await self.dump(new_data, self.raider_info_path)
        await self.read()

    async def read(self):
        if not self.raider_info_path.exists():
            await self.refresh()
            return
        datas: Dict[str, List] = await WikiModel.read(self.raider_info_path)
        self.clear_class_data()
        self.all_role_raiders.extend(datas["role"])
        self.all_light_cone_raiders.extend(datas["light_cone"])
        self.all_role_material_raiders.extend(datas["role_material"])
