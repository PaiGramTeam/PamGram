from pydantic import BaseModel

from modules.wiki.models.enums import RelicAffix


# noinspection PyPep8Naming
def FightProp(prop: RelicAffix) -> str:
    data = {
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
    return data.get(prop)


# noinspection PyPep8Naming
def FightPropScore(prop) -> float:
    data = {
        RelicAffix.AttackAddedRatio: 1.0,
        RelicAffix.AttackDelta: 1.0,
        RelicAffix.BreakDamageAddedRatioBase: 1.0,
        RelicAffix.CriticalChanceBase: 1.0,
        RelicAffix.CriticalDamageBase: 1.0,
        RelicAffix.DefenceAddedRatio: 1.0,
        RelicAffix.DefenceDelta: 1.0,
        RelicAffix.FireAddedRatio: 1.0,
        RelicAffix.HPAddedRatio: 1.0,
        RelicAffix.HPDelta: 1.0,
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
    return data.get(prop)


class EquipmentsStats(BaseModel):
    prop_id: RelicAffix
    prop_value: float

    @property
    def name(self) -> str:
        return FightProp(self.prop_id)

    @property
    def value(self) -> str:
        return str(round(self.prop_value, 1)) if self.prop_value > 1 else str(str(round(self.prop_value * 100.0, 1)) + "%")
