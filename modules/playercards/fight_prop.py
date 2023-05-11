import functools

from pydantic import BaseModel

from modules.wiki.models.enums import RelicAffix

relic_affix_map = {
    RelicAffix.AttackAddedRatio: "攻击力百分比",
    RelicAffix.AttackDelta: "攻击力",
    RelicAffix.BreakDamageAddedRatioBase: "击破特攻",
    RelicAffix.CriticalChanceBase: "暴击率百分比",
    RelicAffix.CriticalDamageBase: "暴击伤害百分比",
    RelicAffix.DefenceAddedRatio: "防御力百分比",
    RelicAffix.DefenceDelta: "防御力",
    RelicAffix.FireAddedRatio: "火属性伤害提高百分比",
    RelicAffix.HPAddedRatio: "生命值百分比",
    RelicAffix.HPDelta: "生命值",
    RelicAffix.HealRatioBase: "治疗量加成百分比",
    RelicAffix.IceAddedRatio: "冰属性伤害提高百分比",
    RelicAffix.ImaginaryAddedRatio: "虚数属性伤害提高百分比",
    RelicAffix.PhysicalAddedRatio: "物理属性伤害提高百分比",
    RelicAffix.QuantumAddedRatio: "量子属性伤害提高百分比",
    RelicAffix.SpeedDelta: "速度",
    RelicAffix.SPRatioBase: "能量恢复效率百分比",
    RelicAffix.StatusProbabilityBase: "效果命中百分比",
    RelicAffix.StatusResistanceBase: "效果抵抗百分比",
    RelicAffix.ThunderAddedRatio: "雷属性伤害提高百分比",
    RelicAffix.WindAddedRatio: "风属性伤害提高百分比",
}
relic_affix_name_map = {v: k for k, v in relic_affix_map.items()}
relic_affix_score_map = {
    RelicAffix.AttackAddedRatio: 1.0,
    RelicAffix.AttackDelta: 0.5,
    RelicAffix.BreakDamageAddedRatioBase: 1.0,
    RelicAffix.CriticalChanceBase: 2.0,
    RelicAffix.CriticalDamageBase: 2.0,
    RelicAffix.DefenceAddedRatio: 1.0,
    RelicAffix.DefenceDelta: 0.5,
    RelicAffix.FireAddedRatio: 1.0,
    RelicAffix.HPAddedRatio: 1.0,
    RelicAffix.HPDelta: 0.5,
    RelicAffix.HealRatioBase: 1.0,
    RelicAffix.IceAddedRatio: 1.0,
    RelicAffix.ImaginaryAddedRatio: 1.0,
    RelicAffix.PhysicalAddedRatio: 1.0,
    RelicAffix.QuantumAddedRatio: 1.0,
    RelicAffix.SpeedDelta: 1.0,
    RelicAffix.SPRatioBase: 1.0,
    RelicAffix.StatusProbabilityBase: 1.0,
    RelicAffix.StatusResistanceBase: 1.0,
    RelicAffix.ThunderAddedRatio: 1.0,
    RelicAffix.WindAddedRatio: 1.0,
}


# noinspection PyPep8Naming
@functools.lru_cache()
def FightProp(prop: RelicAffix, percent: bool = True) -> str:
    name = relic_affix_map.get(prop)
    return name if percent else name.replace("百分比", "")


# noinspection PyPep8Naming
@functools.lru_cache()
def nameToFightProp(name: str) -> RelicAffix:
    return relic_affix_name_map.get(name)


# noinspection PyPep8Naming
@functools.lru_cache()
def FightPropScore(prop) -> float:
    return relic_affix_score_map.get(prop)


class EquipmentsStats(BaseModel):
    prop_id: RelicAffix
    prop_value: float

    @property
    def name(self) -> str:
        return FightProp(self.prop_id, False)

    @property
    def value(self) -> str:
        return (
            str(round(self.prop_value, 1)) if self.prop_value > 1 else str(str(round(self.prop_value * 100.0, 1)) + "%")
        )
