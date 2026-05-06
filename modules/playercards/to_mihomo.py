from abc import abstractmethod
from typing import TYPE_CHECKING, Dict, List, Optional, Any

from starrailres.models.info import LevelInfo

from modules.playercards.fight_prop import nameToFightProp
from utils.log import logger

if TYPE_CHECKING:
    from modules.wiki.models.enums import RelicAffix
    from modules.wiki.models.relic_affix import SingleRelicAffix
    from modules.wiki.mihomo_map import MihomoMap

    from starrailres.index import Index

    from simnet.models.starrail.chronicle.characters import (
        StarRailDetailCharacters,
        StarRailDetailCharacter,
        PropertyInfo,
    )


class SimnetApiDataParser:
    @abstractmethod
    def get_mihomo_map(self) -> "MihomoMap":
        """Get the index of the data."""

    @staticmethod
    def get_character_skill_upgrade_from_skill_tree(
        index: "Index", cid: str, skill_tree_levels: List[LevelInfo]
    ) -> tuple[List[LevelInfo], Dict[str, Dict[str, Any]]]:
        """
        Get character skill upgrade from skill tree.
        """
        skill_map = {}
        if cid not in index.characters:
            return [], skill_map
        skill_trees = index.characters[cid].skill_trees
        skill_upgrades = []
        for skill_tree in skill_tree_levels:
            if skill_tree.id in skill_trees and skill_tree.id in index.character_skill_trees:
                skill_up_list = index.character_skill_trees[skill_tree.id].level_up_skills
                for skill_up in skill_up_list:
                    if skill_tree.id not in skill_map:
                        skill_map[skill_tree.id] = {"id": skill_up.id, "num": skill_up.num}

                    skill_upgrades.append(LevelInfo(skill_up.id, skill_up.num * skill_tree.level))
        return skill_upgrades, skill_map

    @staticmethod
    def update_list1_with_reduction(
        old_list1: List[LevelInfo], map1: Dict[str, Dict[str, Any]], reduce_list: List[LevelInfo]
    ) -> List[LevelInfo]:
        """
        根据映射关系和减少 level 列表，更新老的 list1。

        参数:
            old_list1: 老的 list1，包含 LevelInfo 对象
            map1: 映射字典，键是原始 id，值是映射列表 [{"id": new_id, "num": num}, ...]
            reduce_list: 需要减少的 level 列表，id 是映射后的 id

        返回:
            new_list1: 更新后的 list1
        """
        # 1. 建立反向映射：映射后 id -> [(原始 id, num), ...]
        reverse_map = {}
        for orig_id, m in map1.items():
            new_id = m["id"]
            num = m["num"]
            if new_id not in reverse_map:
                reverse_map[new_id] = []
            reverse_map[new_id].append((orig_id, num))

        # 2. 将 reduce_list 转换为字典（相同 id 时累加 level）
        reduce_dict: Dict[str, int] = {}
        for item in reduce_list:
            reduce_dict[item.id] = reduce_dict.get(item.id, 0) + item.level

        # 3. 创建 old_dict 用于查找
        old_dict = {item.id: item.level for item in old_list1}

        # 4. 初始化 new_dict 为 old_dict 的副本
        new_dict = old_dict.copy()

        # 5. 对于每个要减少的映射后 id
        for mapped_id, reduce_level in reduce_dict.items():
            if mapped_id in reverse_map:
                orig_items = reverse_map[mapped_id]  # [(orig_id, num), ...]

                # 计算所有原始 id 的 num 总和
                total_num = sum(num for _, num in orig_items)

                # 每个原始 id 的 level 减少量 = reduce_level / total_num
                reduce_per_orig = reduce_level / total_num

                # 更新每个原始 id 的 level
                for orig_id, num in orig_items:
                    if orig_id in new_dict:
                        # 原始 id 的 level 减少量 = reduce_per_orig（与 num 无关）
                        new_dict[orig_id] = max(0, int(new_dict[orig_id] - reduce_per_orig))

        # 6. 根据 new_dict 重建 new_list1，保持原始顺序
        new_list1 = [LevelInfo(id=item.id, level=new_dict[item.id]) for item in old_list1]

        return new_list1

    def get_skill_tree_list(self, data: "StarRailDetailCharacter") -> List[Dict[str, Any]]:
        cid = str(data.id)
        skill_tree_levels = []
        for i in data.skills:
            if i.point_type != 2:
                if not i.is_activated:
                    continue
            skill_tree_levels.append(LevelInfo(id=str(i.point_id), level=i.level))
        final_skills, skill_map = self.get_character_skill_upgrade_from_skill_tree(
            self.get_mihomo_map().index, cid, skill_tree_levels
        )
        rank_affected = self.get_mihomo_map().index.get_character_skill_upgrade_from_rank(cid, data.rank)
        new_list = self.update_list1_with_reduction(skill_tree_levels, skill_map, rank_affected)
        return [{"pointId": i.id, "level": i.level} for i in new_list]

    @staticmethod
    def get_equip_list_single_weapon(data: "StarRailDetailCharacter") -> Optional[Dict[str, Any]]:
        weapon = data.equip
        if not weapon:
            return None
        promotion = 0
        if 20 < weapon.level <= 30:
            promotion = 1
        elif 30 < weapon.level <= 40:
            promotion = 2
        elif 40 < weapon.level <= 50:
            promotion = 3
        elif 50 < weapon.level <= 60:
            promotion = 4
        elif 60 < weapon.level <= 70:
            promotion = 5
        elif weapon.level > 70:
            promotion = 6
        return {
            "tid": weapon.id,
            "level": weapon.level,
            "promotion": promotion,
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
