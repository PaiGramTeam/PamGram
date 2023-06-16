import datetime
from typing import List, Literal

from pydantic import BaseModel


class StarRailExpedition(BaseModel):
    avatars: List[str]
    status: Literal["Ongoing", "Finished"]
    remaining_time: datetime.timedelta
    name: str

    @property
    def finished(self) -> bool:
        """Whether the expedition has finished."""
        return self.remaining_time <= datetime.timedelta(0)

    @property
    def completion_time(self) -> datetime.datetime:
        return datetime.datetime.now().astimezone() + self.remaining_time


class StarRailWidget(BaseModel):
    current_stamina: int
    max_stamina: int
    stamina_recover_time: datetime.timedelta
    accepted_expedition_num: int
    total_expedition_num: int
    expeditions: List[StarRailExpedition]
    current_train_score: int
    max_train_score: int
    current_rogue_score: int
    max_rogue_score: int
    has_signed: bool
    sign_url: str
    home_url: str
    note_url: str


class GenshinExpedition(BaseModel):
    avatar_side_icon: str
    status: Literal["Ongoing", "Finished"]


class GenshinWidget(BaseModel):
    current_resin: int
    max_resin: int
    resin_recovery_time: datetime.timedelta
    finished_task_num: int
    total_task_num: int
    is_extra_task_reward_received: bool
    current_expedition_num: int
    max_expedition_num: int
    expeditions: List[GenshinExpedition]
    current_home_coin: int
    max_home_coin: int
    has_signed: bool
    sign_url: str
    home_url: str
    note_url: str
