import datetime
from enum import Enum
from typing import Any, Dict, List, Union

from pydantic import BaseModel, validator

from metadata.shortname import not_real_roles, roleToId, lightConeToId
from modules.gacha_log.const import SRGF_VERSION


class ImportType(Enum):
    PaiGram = "PaiGram"
    SRGF = "SRGF"
    UNKNOWN = "UNKNOWN"


class FiveStarItem(BaseModel):
    name: str
    icon: str
    count: int
    type: str
    isUp: bool
    isBig: bool
    time: datetime.datetime


class FourStarItem(BaseModel):
    name: str
    icon: str
    count: int
    type: str
    time: datetime.datetime


class GachaItem(BaseModel):
    id: str
    name: str
    gacha_id: str = ""
    gacha_type: str
    item_id: str = ""
    item_type: str
    rank_type: str
    time: datetime.datetime

    @validator("name")
    def name_validator(cls, v):
        if item_id := (roleToId(v) or lightConeToId(v)):
            if item_id not in not_real_roles:
                return v
        raise ValueError("Invalid name")

    @validator("gacha_type")
    def check_gacha_type(cls, v):
        if v not in {"1", "2", "11", "12"}:
            raise ValueError("gacha_type must be 1, 2, 11 or 12")
        return v

    @validator("item_type")
    def check_item_type(cls, item):
        if item not in {"角色", "光锥"}:
            raise ValueError("error item type")
        return item

    @validator("rank_type")
    def check_rank_type(cls, rank):
        if rank not in {"5", "4", "3"}:
            raise ValueError("error rank type")
        return rank


class GachaLogInfo(BaseModel):
    user_id: str
    uid: str
    update_time: datetime.datetime
    import_type: str = ""
    item_list: Dict[str, List[GachaItem]] = {
        "角色跃迁": [],
        "光锥跃迁": [],
        "常驻跃迁": [],
        "新手跃迁": [],
    }

    @property
    def get_import_type(self) -> ImportType:
        try:
            return ImportType(self.import_type)
        except ValueError:
            return ImportType.UNKNOWN


class Pool:
    def __init__(self, five: List[str], four: List[str], name: str, to: str, **kwargs):
        self.five = five
        self.real_name = name
        self.name = "、".join(self.five)
        self.four = four
        self.from_ = kwargs.get("from")
        self.to = to
        self.from_time = datetime.datetime.strptime(self.from_, "%Y-%m-%d %H:%M:%S")
        self.to_time = datetime.datetime.strptime(self.to, "%Y-%m-%d %H:%M:%S")
        self.start = self.from_time
        self.start_init = False
        self.end = self.to_time
        self.dict = {}
        self.count = 0

    def parse(self, item: Union[FiveStarItem, FourStarItem]):
        if self.from_time <= item.time <= self.to_time:
            if self.dict.get(item.name):
                self.dict[item.name]["count"] += 1
            else:
                self.dict[item.name] = {
                    "name": item.name,
                    "icon": item.icon,
                    "count": 1,
                    "rank_type": 5 if isinstance(item, FiveStarItem) else 4,
                }

    def count_item(self, item: List[GachaItem]):
        for i in item:
            if self.from_time <= i.time <= self.to_time:
                self.count += 1
                if not self.start_init:
                    self.start = i.time
                    self.start_init = True
                self.end = i.time

    def to_list(self):
        return list(self.dict.values())


class ItemType(Enum):
    CHARACTER = "角色"
    LIGHTCONE = "光锥"


class SRGFGachaType(Enum):
    BEGINNER = "2"
    STANDARD = "1"
    CHARACTER = "11"
    LIGHTCONE = "12"


class SRGFItem(BaseModel):
    id: str
    name: str
    count: str = "1"
    gacha_id: str = ""
    gacha_type: SRGFGachaType
    item_id: str = ""
    item_type: ItemType
    rank_type: str
    time: str


class SRGFInfo(BaseModel):
    uid: str = "0"
    lang: str = "zh-cn"
    region_time_zone: int = 8
    export_time: str = ""
    export_timestamp: int = 0
    export_app: str = ""
    export_app_version: str = ""
    srgf_version: str = SRGF_VERSION

    def __init__(self, **data: Any):
        super().__init__(**data)
        if not self.export_time:
            self.export_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.export_timestamp = int(datetime.datetime.now().timestamp())


class SRGFModel(BaseModel):
    info: SRGFInfo
    list: List[SRGFItem]
