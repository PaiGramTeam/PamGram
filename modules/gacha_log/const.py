from simnet.models.starrail.wish import StarRailBannerType

UIGF_VERSION = "v4.0"


GACHA_TYPE_LIST = {
    StarRailBannerType.NOVICE: "新手跃迁",
    StarRailBannerType.PERMANENT: "常驻跃迁",
    StarRailBannerType.CHARACTER: "角色跃迁",
    StarRailBannerType.WEAPON: "光锥跃迁",
    StarRailBannerType.COLLABORATION_CHARACTER: "角色联动跃迁",
    StarRailBannerType.COLLABORATION_WEAPON: "光锥联动跃迁",
}
GACHA_TYPE_LIST_REVERSE = {v: k for k, v in GACHA_TYPE_LIST.items()}
