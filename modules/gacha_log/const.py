from simnet.models.starrail.wish import StarRailBannerType

SRGF_VERSION = "v1.0"


GACHA_TYPE_LIST = {
    StarRailBannerType.NOVICE: "新手跃迁",
    StarRailBannerType.PERMANENT: "常驻跃迁",
    StarRailBannerType.CHARACTER: "角色跃迁",
    StarRailBannerType.WEAPON: "光锥跃迁",
}
GACHA_TYPE_LIST_REVERSE = {v: k for k, v in GACHA_TYPE_LIST.items()}
