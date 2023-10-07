import os
from typing import Dict

from modules.playercards.fight_prop import FightPropScore, EquipmentsStats, nameToFightProp, FightProp
from modules.wiki.models.enums import RelicAffix


class ArtifactStatsTheory:
    def __init__(self, character_name: str, fight_prop_rule_data: Dict[str, Dict[str, float]]):
        self.character_name = character_name
        self.fight_prop_rules = fight_prop_rule_data.get(self.character_name, {})
        fight_prop_rule_list = list(self.fight_prop_rules.keys())
        self.main_prop = [nameToFightProp(fight_prop_rule) for fight_prop_rule in fight_prop_rule_list]
        if not self.main_prop:
            self.main_prop = [
                RelicAffix.CriticalChanceBase,
                RelicAffix.CriticalDamageBase,
                RelicAffix.AttackAddedRatio,
            ]

    def theory(self, sub_stats: EquipmentsStats) -> float:
        """圣遗物词条评分
        Args:
            sub_stats: 圣遗物对象
        Returns:
            返回得分
        """
        score: float = 0
        if sub_stats.prop_id in self.main_prop:
            base_value = 100.0 if sub_stats.prop_value < 1 else 1.0
            weight = self.fight_prop_rules.get(FightProp(sub_stats.prop_id), 0.0)
            if weight == 0.0:
                weight = FightPropScore(sub_stats.prop_id)
            score = float(weight * sub_stats.prop_value * base_value)
        return round(score, 1)
