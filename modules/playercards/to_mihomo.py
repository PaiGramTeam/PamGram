from abc import abstractmethod
from typing import TYPE_CHECKING, Dict, List, Optional, Any

from modules.playercards.fight_prop import nameToFightProp
from utils.log import logger

if TYPE_CHECKING:
    from modules.wiki.models.enums import RelicAffix
    from modules.wiki.models.relic_affix import SingleRelicAffix
    from modules.wiki.mihomo_map import MihomoMap

    from simnet.models.starrail.chronicle.characters import (
        StarRailDetailCharacters,
        StarRailDetailCharacter,
        PropertyInfo,
    )


class SimnetApiDataParser:
    @abstractmethod
    def get_mihomo_map(self) -> "MihomoMap":
        """Get the index of the data."""

    def get_skill_tree_list(self, data: "StarRailDetailCharacter") -> List[Dict[str, Any]]:
        skill_tree_levels: List[Dict[str, Any]] = []
        skill_tree_levels_map: Dict[str, Dict[str, Any]] = {}
        for behavior in data.skills:
            skill_tree_level = {
                "pointId": behavior.point_id,
                "level": behavior.level,
            }
            skill_tree_levels.append(skill_tree_level)
            skill_tree_levels_map[str(behavior.point_id)] = skill_tree_level
        rank_affected = self.get_mihomo_map().index.get_character_skill_upgrade_from_rank(str(data.id), data.rank)
        for rank in rank_affected:
            skill_id = rank.id[:4] + "0" + rank.id[4:]
            if skill_tree_level := skill_tree_levels_map.get(skill_id):
                skill_tree_level["level"] -= rank.level
        return skill_tree_levels

    @staticmethod
    def get_equip_list_single_weapon(data: "StarRailDetailCharacter") -> Optional[Dict[str, Any]]:
        weapon = data.equip
        if not weapon:
            return None
        return {
            "tid": weapon.id,
            "level": weapon.level,
            "promotion": 6,
            "rank": weapon.rank,
        }

    @staticmethod
    def get_properties_map(data: "StarRailDetailCharacters") -> Dict[int, "PropertyInfo"]:
        properties_map: Dict[int, "PropertyInfo"] = {}
        for i in data.property_info:
            properties_map[i.property_type] = i
        return properties_map

    @staticmethod
    def get_property_filter_enum(properties_map: Dict[int, "PropertyInfo"], property_type: int) -> "RelicAffix":
        property_name = properties_map[property_type].property_name_filter
        return nameToFightProp(property_name)

    @staticmethod
    def choose_affix(affix_map: Dict[str, "SingleRelicAffix"], property_type: "RelicAffix") -> "SingleRelicAffix":
        for value in affix_map.values():
            if value.property is property_type:
                return value

    @staticmethod
    def get_sub_affix_step(sub_affix: "SingleRelicAffix", cnt: int, value: str) -> int:
        if "%" in value:
            real_value = float(value.replace("%", "")) / 100.0
        else:
            real_value = float(value)
        real_value -= sub_affix.base_value * cnt
        cnt = round(real_value / sub_affix.step_value)
        return cnt if cnt >= 0 else 0

    def get_relic_list(
        self, properties_map: Dict[int, "PropertyInfo"], data: "StarRailDetailCharacter"
    ) -> Optional[List[Dict[str, Any]]]:
        relic_list = []
        for relic in data.relics + data.ornaments:
            tid = relic.id

            # 主属性
            mihomo_map = self.get_mihomo_map().get_affix_by_id(tid)
            if not mihomo_map:
                logger.warning("解析遗器基础数据失败 tid[%s]", tid)
                continue
            main_affix_name = self.get_property_filter_enum(properties_map, relic.main_property.property_type)
            main_affix = self.choose_affix(mihomo_map.main_affix, main_affix_name)
            if not main_affix:
                logger.warning("解析遗器主属性失败 tid[%s]", tid)
                continue
            main_affix_id = main_affix.id
            # 副属性
            sub_affix_list = []
            for affix in relic.properties:
                cnt = affix.times
                sub_affix_name = self.get_property_filter_enum(properties_map, affix.property_type)
                sub_affix = self.choose_affix(mihomo_map.sub_affix, sub_affix_name)
                if not sub_affix:
                    logger.warning("解析遗器副属性失败 tid[%s] property_type[%s]", tid, affix.property_type)
                    continue
                sub_affix_id = sub_affix.id
                sub_affix_step = self.get_sub_affix_step(sub_affix, cnt, affix.value)
                sub_affix_list.append(
                    {
                        "affixId": sub_affix_id,
                        "cnt": cnt,
                        "step": sub_affix_step,
                    }
                )

            relic_data = {
                "tid": relic.id,
                "level": relic.level,
                "mainAffixId": main_affix_id,
                "subAffixList": sub_affix_list,
                "type": relic.pos,
            }
            relic_list.append(relic_data)
        return relic_list

    def from_simnet_to_enka_single(self, index: int, data: "StarRailDetailCharacters") -> Dict:
        character = data.avatar_list[index]
        avatar_id = character.id
        avatar_level = character.level
        avatar_rank = character.rank
        skill_tree_list = self.get_skill_tree_list(character)
        equipment = self.get_equip_list_single_weapon(character)
        properties_map = self.get_properties_map(data)
        relic_list = self.get_relic_list(properties_map, character)
        return {
            "avatarId": avatar_id,
            "skillTreeList": skill_tree_list,
            "equipment": equipment,
            "level": avatar_level,
            "promotion": 6,
            "rank": avatar_rank,
            "relicList": relic_list,
            "source": "mihoyo",
        }

    def from_simnet_to_enka_loop(self, data: "StarRailDetailCharacters") -> List[Dict]:
        d = []
        for index, ch in enumerate(data.avatar_list):
            try:
                if parsed_data := self.from_simnet_to_enka_single(index, data):
                    d.append(parsed_data)
            except Exception as e:
                cid = ch.id
                logger.error("从 simnet 模型转换为 enka 模型时出现错误 cid[%s]", cid, exc_info=e)
        logger.success("成功转换 %s 个角色", len(d))
        return d

    def from_simnet_to_enka(self, data: "StarRailDetailCharacters") -> Dict:
        return {
            "avatarDetailList": self.from_simnet_to_enka_loop(data),
        }
