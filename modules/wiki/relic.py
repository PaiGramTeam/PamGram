from typing import List, Dict, Optional

from modules.wiki.base import WikiModel
from modules.wiki.models.relic import Relic as RelicModel


class Relic(WikiModel):
    relic_url = WikiModel.BASE_URL + "relics.json"
    relic_path = WikiModel.BASE_PATH / "relics.json"

    def __init__(self):
        super().__init__()
        self.all_relics: List[RelicModel] = []
        self.all_relics_map: Dict[int, RelicModel] = {}
        self.all_relics_name: Dict[str, RelicModel] = {}

    def clear_class_data(self) -> None:
        self.all_relics.clear()
        self.all_relics_map.clear()
        self.all_relics_name.clear()

    async def refresh(self):
        datas = await self.remote_get(self.relic_url)
        await self.dump(datas.json(), self.relic_path)
        await self.read()

    async def read(self):
        if not self.relic_path.exists():
            await self.refresh()
            return
        datas = await WikiModel.read(self.relic_path)
        self.clear_class_data()
        for data in datas:
            m = RelicModel(**data)
            self.all_relics.append(m)
            self.all_relics_map[m.id] = m
            self.all_relics_name[m.name] = m

    def get_by_id(self, cid: int) -> Optional[RelicModel]:
        return self.all_relics_map.get(cid)

    def get_by_name(self, name: str) -> Optional[RelicModel]:
        return self.all_relics_name.get(name)

    def get_name_list(self) -> List[str]:
        return list(self.all_relics_name.keys())
