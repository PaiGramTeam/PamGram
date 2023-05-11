from typing import List, Dict, Optional

from modules.wiki.base import WikiModel
from modules.wiki.models.monster import Monster as MonsterModel


class Monster(WikiModel):
    monster_url = WikiModel.BASE_URL + "monsters.json"
    monster_path = WikiModel.BASE_PATH / "monsters.json"

    def __init__(self):
        super().__init__()
        self.all_monsters: List[MonsterModel] = []
        self.all_monsters_map: Dict[int, MonsterModel] = {}
        self.all_monsters_name: Dict[str, MonsterModel] = {}

    def clear_class_data(self) -> None:
        self.all_monsters.clear()
        self.all_monsters_map.clear()
        self.all_monsters_name.clear()

    async def refresh(self):
        datas = await self.remote_get(self.monster_url)
        await self.dump(datas.json(), self.monster_path)
        await self.read()

    async def read(self):
        if not self.monster_path.exists():
            await self.refresh()
            return
        datas = await WikiModel.read(self.monster_path)
        self.clear_class_data()
        for data in datas:
            m = MonsterModel(**data)
            self.all_monsters.append(m)
            self.all_monsters_map[m.id] = m
            self.all_monsters_name[m.name] = m

    def get_by_id(self, cid: int) -> Optional[MonsterModel]:
        return self.all_monsters_map.get(cid)

    def get_by_name(self, name: str) -> Optional[MonsterModel]:
        return self.all_monsters_name.get(name)

    def get_name_list(self) -> List[str]:
        return list(self.all_monsters_name.keys())
