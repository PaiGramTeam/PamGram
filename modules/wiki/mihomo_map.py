import asyncio
from typing import Optional, Dict

from starrailres import Index

from modules.wiki.base import WikiModel
from modules.wiki.models.relic_affix import RelicAffixAll


class MihomoMap(WikiModel):
    mihomo_map_base_url = WikiModel.BASE_URL + "mihomo_map/"
    mihomo_map_base_path = WikiModel.BASE_PATH / "mihomo_map"
    file_set = {
        "characters.json",
        "character_ranks.json",
        "character_skills.json",
        "character_skill_trees.json",
        "character_promotions.json",
        "light_cones.json",
        "light_cone_ranks.json",
        "light_cone_promotions.json",
        "relics.json",
        "relic_sets.json",
        "relic_main_affixes.json",
        "relic_sub_affixes.json",
        "paths.json",
        "elements.json",
        "properties.json",
        "avatars.json",
        "relic_config.json",
    }

    def __init__(self):
        super().__init__()
        self.mihomo_map_base_path.mkdir(parents=True, exist_ok=True)
        self.index: Optional[Index] = None
        self.relic_datas_map: Dict[int, RelicAffixAll] = {}

    async def refresh_one(self, filename: str):
        datas = await self.remote_get(self.mihomo_map_base_url + filename)
        await self.dump(datas.json(), self.mihomo_map_base_path / filename)

    async def refresh(self):
        tasks = [self.refresh_one(f) for f in self.file_set]
        await asyncio.gather(*tasks)
        await self.read()

    async def read(self):
        if not len(list(self.mihomo_map_base_path.glob("*.json"))):
            await self.refresh()
            return
        self.index = Index(self.mihomo_map_base_path)
        data = await WikiModel.read(self.mihomo_map_base_path / "relic_config.json")
        for i in data:
            self.relic_datas_map[i["id"]] = RelicAffixAll(**i)

    def get_affix_by_id(self, cid: int) -> RelicAffixAll:
        return self.relic_datas_map.get(cid)
