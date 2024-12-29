from abc import abstractmethod
from typing import Optional, TYPE_CHECKING, Dict, List, Any

from starrailres.models.info import (
    CharacterInfo,
    LightConeBasicInfo,
    SubAffixBasicInfo,
    RelicBasicInfo,
    LevelInfo,
    CharacterBasicInfo,
)

from modules.playercards.models import Avatar, PlayerInfoRaw, Property

if TYPE_CHECKING:
    from modules.wiki.mihomo_map import MihomoMap


class MihomoApiDataParser:
    @abstractmethod
    def get_mihomo_map(self) -> "MihomoMap":
        """Get the index of the data."""

    def character_parse(self, data: "Avatar") -> Optional["CharacterInfo"]:
        light_cone = None
        if data.equipment and data.equipment.tid:
            light_cone = LightConeBasicInfo(
                id=str(data.equipment.tid),
                rank=data.equipment.rank,
                level=data.equipment.level,
                promotion=data.equipment.promotion,
            )
        relics = []
        if data.relicList:
            for relic in data.relicList:
                sub_affix = []
                if relic.subAffixList:
                    for affix in relic.subAffixList:
                        sub_affix.append(
                            SubAffixBasicInfo(
                                id=str(affix.affixId),
                                cnt=affix.cnt,
                                step=affix.step,
                            )
                        )
                relic_data = RelicBasicInfo(
                    id=str(relic.tid),
                    level=relic.level,
                    main_affix_id=str(relic.mainAffixId),
                    sub_affix_info=sub_affix,
                )
                relics.append(relic_data)
        skill_tree_levels = []
        if data.skillTreeList:
            for behavior in data.skillTreeList:
                skill_tree_levels.append(
                    LevelInfo(
                        id=str(behavior.pointId),
                        level=behavior.level,
                    )
                )
        character_basic = CharacterBasicInfo(
            id=str(data.avatarId),
            rank=data.rank,
            level=data.level,
            promotion=data.promotion,
            skill_tree_levels=skill_tree_levels,
            light_cone=light_cone,
            relics=relics,
        )
        return self.get_mihomo_map().index.get_character_info(character_basic)

    @staticmethod
    def get_character_property(character: "CharacterInfo") -> List[Dict[str, Any]]:
        datas = []
        datas_map = {}
        for attr in character.attributes:
            prop = Property(
                name=attr.name,
                base=attr.value,
                percent=attr.percent,
            )
            datas.append(prop)
            datas_map[prop.name] = prop
        for attr in character.additions:
            prop = datas_map.get(attr.name)
            if prop:
                prop.addition = attr.value
            else:
                prop = Property(
                    name=attr.name,
                    addition=attr.value,
                    percent=attr.percent,
                )
                datas.append(prop)
                datas_map[prop.name] = prop
        return [i.model_dump() for i in datas]

    async def get_property_from_avatars(self, characters: List["Avatar"]) -> Dict[int, List[Dict]]:
        final_data: Dict[int, List[Dict]] = {}
        for character in characters:
            if character_info := self.character_parse(character):
                final_data[int(character_info.id)] = self.get_character_property(character_info)
        return final_data

    async def get_property(self, raw_api_data: Dict[str, Any]) -> Dict[int, List[Dict]]:
        api_data = PlayerInfoRaw.model_validate(raw_api_data)
        characters: List["Avatar"] = []
        if assist_avatar_list := api_data.assistAvatarList:
            characters.extend(assist_avatar_list)
        if avatar_detail_list := api_data.avatarDetailList:
            characters.extend(avatar_detail_list)
        return await self.get_property_from_avatars(characters)

    async def get_property_from_dict(self, raw_api_data: Dict[str, Any]) -> Dict[int, List[Dict]]:
        raw_characters: List = []
        if assist_avatar_list := raw_api_data.get("assistAvatarList"):
            raw_characters.extend(assist_avatar_list)
        if avatar_detail_list := raw_api_data.get("avatarDetailList"):
            raw_characters.extend(avatar_detail_list)
        characters: List["Avatar"] = [Avatar.model_validate(i) for i in raw_characters]
        return await self.get_property_from_avatars(characters)
