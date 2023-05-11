from typing import List, Dict, Optional

from modules.wiki.base import WikiModel
from modules.wiki.models.light_cone import LightCone as LightConeModel


class LightCone(WikiModel):
    light_cone_url = WikiModel.BASE_URL + "light_cones.json"
    light_cone_path = WikiModel.BASE_PATH / "light_cones.json"

    def __init__(self):
        super().__init__()
        self.all_light_cones: List[LightConeModel] = []
        self.all_light_cones_map: Dict[int, LightConeModel] = {}
        self.all_light_cones_name: Dict[str, LightConeModel] = {}

    def clear_class_data(self) -> None:
        self.all_light_cones.clear()
        self.all_light_cones_map.clear()
        self.all_light_cones_name.clear()

    async def refresh(self):
        datas = await self.remote_get(self.light_cone_url)
        await self.dump(datas.json(), self.light_cone_path)
        await self.read()

    async def read(self):
        if not self.light_cone_path.exists():
            await self.refresh()
            return
        datas = await WikiModel.read(self.light_cone_path)
        self.clear_class_data()
        for data in datas:
            m = LightConeModel(**data)
            self.all_light_cones.append(m)
            self.all_light_cones_map[m.id] = m
            self.all_light_cones_name[m.name] = m

    def get_by_id(self, cid: int) -> Optional[LightConeModel]:
        return self.all_light_cones_map.get(cid)

    def get_by_name(self, name: str) -> Optional[LightConeModel]:
        return self.all_light_cones_name.get(name)

    def get_name_list(self) -> List[str]:
        return list(self.all_light_cones_name.keys())
