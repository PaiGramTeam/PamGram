from __future__ import annotations

import functools
from typing import List

__all__ = [
    "roles",
    "light_cones",
    "roleToId",
    "roleToName",
    "idToRole",
    "lightConeToName",
    "lightConeToId",
    "not_real_roles",
    "roleToTag",
]

# noinspection SpellCheckingInspection
roles = {
    8001: ["开拓者"],
    8002: ["开拓者"],
    8003: ["开拓者"],
    8004: ["开拓者"],
    1001: ["三月七"],
    1002: ["丹恒"],
    1003: ["姬子"],
    1004: ["瓦尔特"],
    1005: ["卡芙卡"],
    1006: ["银狼"],
    1008: ["阿兰"],
    1009: ["艾丝妲"],
    1013: ["黑塔"],
    1101: ["布洛妮娅"],
    1102: ["希儿"],
    1103: ["希露瓦"],
    1104: ["杰帕德"],
    1105: ["娜塔莎"],
    1106: ["佩拉"],
    1107: ["克拉拉"],
    1108: ["桑博"],
    1109: ["虎克"],
    1201: ["青雀"],
    1202: ["停云"],
    1203: ["罗刹"],
    1204: ["景元"],
    1206: ["素裳"],
    1209: ["彦卿"],
    1211: ["白露"],
}
not_real_roles = []
light_cones = {
    20000: ["锋镝"],
    20001: ["物穰"],
    20002: ["天倾"],
    20003: ["琥珀"],
    20004: ["幽邃"],
    20005: ["齐颂"],
    20006: ["智库"],
    20007: ["离弦"],
    20008: ["嘉果"],
    20009: ["乐圮"],
    20010: ["戍御"],
    20011: ["渊环"],
    20012: ["轮契"],
    20013: ["灵钥"],
    20014: ["相抗"],
    20015: ["蕃息"],
    20016: ["俱殁"],
    20017: ["开疆"],
    20018: ["匿影"],
    20019: ["调和"],
    20020: ["睿见"],
    21000: ["一场术后对话"],
    21001: ["晚安与睡颜"],
    21002: ["余生的第一天"],
    21003: ["唯有沉默"],
    21004: ["记忆中的模样"],
    21005: ["鼹鼠党欢迎你"],
    21006: ["「我」的诞生"],
    21007: ["同一种心情"],
    21008: ["猎物的视线"],
    21009: ["朗道的选择"],
    21010: ["论剑"],
    21011: ["与行星相会"],
    21012: ["秘密誓心"],
    21013: ["别让世界静下来"],
    21014: ["此时恰好"],
    21015: ["决心如汗珠般闪耀"],
    21016: ["宇宙市场趋势"],
    21017: ["点个关注吧！"],
    21018: ["舞！舞！舞！"],
    21019: ["在蓝天下"],
    21020: ["天才们的休憩"],
    21021: ["等价交换"],
    21022: ["延长记号"],
    21023: ["我们是地火"],
    21024: ["春水初生"],
    21025: ["过往未来"],
    21026: ["汪！散步时间！"],
    21027: ["早餐的仪式感"],
    21028: ["暖夜不会漫长"],
    21029: ["后会有期"],
    21030: ["这就是我啦！"],
    21031: ["重返幽冥"],
    21032: ["镂月裁云之意"],
    21033: ["无处可逃"],
    21034: ["今日亦是和平的一日"],
    23000: ["银河铁道之夜"],
    23001: ["于夜色中"],
    23002: ["无可取代的东西"],
    23003: ["但战斗还未结束"],
    23004: ["以世界之名"],
    23005: ["制胜的瞬间"],
    23010: ["拂晓之前"],
    23012: ["如泥酣眠"],
    23013: ["时节不居"],
    24000: ["记一位星神的陨落"],
    24001: ["星海巡航"],
    24002: ["记忆的质料"],
}


# noinspection PyPep8Naming
@functools.lru_cache()
def roleToName(shortname: str) -> str:
    """将角色昵称转为正式名"""
    shortname = str.casefold(shortname)  # 忽略大小写
    return next((value[0] for value in roles.values() for name in value if name == shortname), shortname)


# noinspection PyPep8Naming
@functools.lru_cache()
def roleToId(name: str) -> int | None:
    """获取角色ID"""
    name = str.casefold(name)
    return next((key for key, value in roles.items() for n in value if n == name), None)


# noinspection PyPep8Naming
@functools.lru_cache()
def idToRole(aid: int) -> str | None:
    """获取角色名"""
    return roles.get(aid, [None])[0]


# noinspection PyPep8Naming
@functools.lru_cache()
def lightConeToName(shortname: str) -> str:
    """将光锥昵称转为正式名"""
    shortname = str.casefold(shortname)  # 忽略大小写
    return next((value[0] for value in light_cones.values() for name in value if name == shortname), shortname)


# noinspection PyPep8Naming
@functools.lru_cache()
def lightConeToId(name: str) -> int | None:
    """获取光锥ID"""
    name = str.casefold(name)
    return next((key for key, value in light_cones.items() for n in value if n == name), None)


# noinspection PyPep8Naming
@functools.lru_cache()
def roleToTag(role_name: str) -> List[str]:
    """通过角色名获取TAG"""
    role_name = str.casefold(role_name)
    return next((value for value in roles.values() if value[0] == role_name), [role_name])


@functools.lru_cache()
def lightConeToTag(name: str) -> List[str]:
    """通过光锥名获取TAG"""
    name = str.casefold(name)
    return next((value for value in light_cones.values() if value[0] == name), [name])
