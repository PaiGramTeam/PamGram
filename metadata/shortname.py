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
    "lightConeToTag",
]

# noinspection SpellCheckingInspection
roles = {
    8001: ["开拓者·毁灭"],
    8002: ["开拓者·毁灭"],
    8003: ["开拓者·存护"],
    8004: ["开拓者·存护"],
    1001: ["三月七", "mar7th", "三月", "小三月", "阿七", "冷面小粉龙", "纠缠之缘", "小仓唯", "xcw", "37"],
    1002: ["丹恒", "danheng", "冷面小青龙", "闷葫芦"],
    1003: ["姬子", "himeko", "姬子阿姐", "寄子"],
    1004: ["瓦尔特", "welt", "瓦尔特杨", "杨叔", "牧月忍冬", "约阿希姆诺基安维塔宁", "老杨"],
    1005: ["卡芙卡", "kafka", "妈", "妈妈"],
    1006: ["银狼", "silverwolf", "小板鸭", "酷鸭", "超级骇客", "淫狼"],
    1008: ["阿兰", "arlan"],
    1009: ["艾丝妲", "asta", "富婆", "代理站长", "知名不具"],
    1013: ["黑塔", "herta", "天才俱乐部#83", "天才俱乐部第83席", "天才俱乐部第八十三席", "黑塔女士", "转圈圈", "人偶"],
    1101: ["布洛妮娅", "bronya", "布洛妮娅兰德", "兰德鸭", "大板鸭", "三涡轮增鸭", "渡鸭"],
    1102: ["希儿", "seele", "蝴蝶", "希尔"],
    1103: ["希露瓦", "serval", "希露瓦朗道", "朗道家长女", "贝洛伯格机械师"],
    1104: ["杰帕德", "gepard", "杰帕德朗道", "杰哥", "小杰杰"],
    1105: ["娜塔莎", "natasha", "娜塔", "娜塔莎姐姐", "老巫婆"],
    1106: ["佩拉", "pela", "佩拉格娅谢尔盖耶夫娜", "佩拉格娅", "谢尔盖耶夫娜", "冰砂糖"],
    1107: ["克拉拉", "clara", "猩红兔子", "天才侦探少女", "史瓦罗", "史瓦罗发射器"],
    1108: ["桑博", "sampo", "桑博科斯基", "深蓝帅哥", "布鲁海尔波桑"],
    1109: ["虎克", "hook", "胡克"],
    1110: ["玲可", "lynx"],
    1111: ["卢卡", "luka"],
    1112: ["托帕&账账", "topaz"],
    1201: ["青雀", "qingque", "克莱茵"],
    1202: ["停云", "tingyun", "屑狐狸", "骚狐狸", "停运"],
    1203: ["罗刹", "luocha", "主教"],
    1204: ["景元", "jingyuan", "云骑将军", "闭目将军"],
    1205: ["刃", "blade"],
    1206: ["素裳", "sushang", "李素裳", "李大枕头"],
    1207: ["驭空", "yukong"],
    1208: ["符玄", "fuxuan", "typec"],
    1209: ["彦卿", "yanqing", "马彦卿", "老马", "燕青"],
    1210: ["桂乃芬", "guinaifen"],
    1211: ["白露", "bailu", "衔药龙女", "小龙女", "龙女"],
    1212: ["镜流", "jingliu"],
    1213: ["丹恒•饮月", "danhengil", "饮月君", "饮月"],
    1214: ["雪衣", "xueyi"],
    1215: ["寒鸦", "hanya"],
    1217: ["藿藿", "huohuo"],
    1302: ["银枝", "argenti"],
    1303: ["阮•梅", "ruanmei"],
    1305: ["真理医生", "drratio"],
    1306: ["花火", "sparkle"],
    1307: ["黑天鹅", "blackswan"],
    1312: ["米沙", "misha"],
}
not_real_roles = [1306]
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
    21035: ["何物为真"],
    21036: ["美梦小镇大冒险"],
    21037: ["最后的赢家"],
    21038: ["在火的远处"],
    21039: ["织造命运之线"],
    21040: ["银河沦陷日"],
    21041: ["好戏开演"],
    21042: ["铭记于心的约定"],
    22000: ["新手任务开始前"],
    22001: ["嘿，我在这儿"],
    23000: ["银河铁道之夜"],
    23001: ["于夜色中"],
    23002: ["无可取代的东西"],
    23003: ["但战斗还未结束"],
    23004: ["以世界之名"],
    23005: ["制胜的瞬间"],
    23006: ["只需等待"],
    23007: ["雨一直下"],
    23008: ["棺的回响"],
    23009: ["到不了的彼岸"],
    23010: ["拂晓之前"],
    23011: ["她已闭上双眼"],
    23012: ["如泥酣眠"],
    23013: ["时节不居"],
    23014: ["此身为剑"],
    23015: ["比阳光更明亮的"],
    23016: ["烦恼着，幸福着"],
    23017: ["惊魂夜"],
    23018: ["片刻，留在眼底"],
    23019: ["镜中故我"],
    23020: ["纯粹思维的洗礼"],
    23021: ["游戏尘寰"],
    23022: ["重塑时光之忆"],
    24000: ["记一位星神的陨落"],
    24001: ["星海巡航"],
    24002: ["记忆的质料"],
    24003: ["孤独的疗愈"],
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
