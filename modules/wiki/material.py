from typing import List, Dict, Optional

from modules.wiki.base import WikiModel
from modules.wiki.models.material import Material as MaterialModel


class Material(WikiModel):
    material_url = WikiModel.BASE_URL + "materials.json"
    material_path = WikiModel.BASE_PATH / "materials.json"

    def __init__(self):
        super().__init__()
        self.all_materials: List[MaterialModel] = []
        self.all_materials_map: Dict[int, MaterialModel] = {}
        self.all_materials_name: Dict[str, MaterialModel] = {}

    def clear_class_data(self) -> None:
        self.all_materials.clear()
        self.all_materials_map.clear()
        self.all_materials_name.clear()

    async def refresh(self):
        datas = await self.remote_get(self.material_url)
        await self.dump(datas.json(), self.material_path)
        await self.read()

    async def read(self):
        if not self.material_path.exists():
            await self.refresh()
            return
        datas = await WikiModel.read(self.material_path)
        self.clear_class_data()
        for data in datas:
            m = MaterialModel(**data)
            self.all_materials.append(m)
            self.all_materials_map[m.id] = m
            self.all_materials_name[m.name] = m

    def get_by_id(self, cid: int) -> Optional[MaterialModel]:
        return self.all_materials_map.get(cid)

    def get_by_name(self, name: str) -> Optional[MaterialModel]:
        return self.all_materials_name.get(name)

    def get_name_list(self) -> List[str]:
        return list(self.all_materials_name.keys())
