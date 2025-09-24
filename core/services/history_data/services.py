import datetime
from typing import List

from simnet.models.starrail.chronicle.challenge import StarRailChallenge
from simnet.models.starrail.chronicle.challenge_boss import StarRailChallengeBoss, StarRailChallengeBossGroup
from simnet.models.starrail.chronicle.challenge_peak import (
    StarRailChallengePeak,
    StarRailChallengePeakGroup,
    StarRailChallengePeakRecord,
)
from simnet.models.starrail.chronicle.challenge_story import StarRailChallengeStory, StarRailChallengeStoryGroup
from simnet.models.starrail.diary import StarRailDiary

from core.services.history_data.models import (
    HistoryData,
    HistoryDataTypeEnum,
    HistoryDataAbyss,
    HistoryDataChallengeStory,
    HistoryDataLedger,
    HistoryDataChallengeBoss,
    HistoryDataChallengePeak,
)
from gram_core.base_service import BaseService
from gram_core.services.history_data.services import HistoryDataBaseServices

try:
    import ujson as jsonlib
except ImportError:
    import json as jsonlib


__all__ = (
    "HistoryDataBaseServices",
    "HistoryDataAbyssServices",
    "HistoryDataChallengeStoryServices",
    "HistoryDataChallengeBossServices",
    "HistoryDataLedgerServices",
    "HistoryDataChallengePeakServices",
)


class HistoryDataAbyssServices(BaseService, HistoryDataBaseServices):
    DATA_TYPE = HistoryDataTypeEnum.ABYSS.value

    @staticmethod
    def exists_data(data: HistoryData, old_data: List[HistoryData]) -> bool:
        floors = data.data.get("abyss_data", {}).get("all_floor_detail")
        return any(d.data.get("abyss_data", {}).get("all_floor_detail") == floors for d in old_data)

    @staticmethod
    def create(user_id: int, abyss_data: StarRailChallenge):
        data = HistoryDataAbyss(abyss_data=abyss_data)
        json_data = data.model_dump_json(by_alias=True)
        return HistoryData(
            user_id=user_id,
            data_id=abyss_data.season,
            time_created=datetime.datetime.now(),
            type=HistoryDataAbyssServices.DATA_TYPE,
            data=jsonlib.loads(json_data),
        )


class HistoryDataChallengeStoryServices(BaseService, HistoryDataBaseServices):
    DATA_TYPE = HistoryDataTypeEnum.CHALLENGE_STORY.value

    @staticmethod
    def exists_data(data: HistoryData, old_data: List[HistoryData]) -> bool:
        floors = data.data.get("story_data", {}).get("all_floor_detail")
        return any(d.data.get("story_data", {}).get("all_floor_detail") == floors for d in old_data)

    @staticmethod
    def create(user_id: int, story_data: StarRailChallengeStory, group: StarRailChallengeStoryGroup):
        data = HistoryDataChallengeStory(story_data=story_data, group=group)
        json_data = data.model_dump_json(by_alias=True)
        dict_data = jsonlib.loads(json_data)
        dict_data["story_data"]["groups"] = []
        return HistoryData(
            user_id=user_id,
            data_id=group.season,
            time_created=datetime.datetime.now(),
            type=HistoryDataChallengeStoryServices.DATA_TYPE,
            data=dict_data,
        )


class HistoryDataChallengeBossServices(BaseService, HistoryDataBaseServices):
    DATA_TYPE = HistoryDataTypeEnum.CHALLENGE_BOSS.value

    @staticmethod
    def exists_data(data: HistoryData, old_data: List[HistoryData]) -> bool:

        def _get_data(_data: HistoryData):
            detail = _data.data.get("boss_data", {}).get("all_floor_detail")
            _avatars = []
            for floor in detail:
                for avatar in floor.get("avatars", []):
                    _avatars.append(avatar["id"])
            return _avatars

        avatars = _get_data(data)
        return any(_get_data(d) == avatars for d in old_data)

    @staticmethod
    def create(user_id: int, boss_data: StarRailChallengeBoss, group: StarRailChallengeBossGroup):
        data = HistoryDataChallengeBoss(boss_data=boss_data, group=group)
        json_data = data.model_dump_json(by_alias=True)
        dict_data = jsonlib.loads(json_data)
        dict_data["boss_data"]["groups"] = []
        return HistoryData(
            user_id=user_id,
            data_id=group.season,
            time_created=datetime.datetime.now(),
            type=HistoryDataChallengeBossServices.DATA_TYPE,
            data=dict_data,
        )


class HistoryDataLedgerServices(BaseService, HistoryDataBaseServices):
    DATA_TYPE = HistoryDataTypeEnum.LEDGER.value

    @staticmethod
    def create(user_id: int, diary_data: StarRailDiary):
        data = HistoryDataLedger(diary_data=diary_data)
        json_data = data.model_dump_json(by_alias=True)
        return HistoryData(
            user_id=user_id,
            data_id=diary_data.data_id,
            time_created=datetime.datetime.now(),
            type=HistoryDataLedgerServices.DATA_TYPE,
            data=jsonlib.loads(json_data),
        )


class HistoryDataChallengePeakServices(BaseService, HistoryDataBaseServices):
    DATA_TYPE = HistoryDataTypeEnum.CHALLENGE_PEAK.value

    @staticmethod
    def exists_data(data: HistoryData, old_data: List[HistoryData]) -> bool:

        def _get_data(_data: HistoryData):
            group = _data.data.get("record", {})
            detail = group.get("mob_records", []).copy()
            if boss_record := group.get("boss_record"):
                detail.append(boss_record)
            _avatars = []
            for floor in detail:
                for avatar in floor.get("avatars", []):
                    _avatars.append(avatar["id"])
            return _avatars

        avatars = _get_data(data)
        return any(_get_data(d) == avatars for d in old_data)

    @staticmethod
    def create(user_id: int, peak_data: StarRailChallengePeak, record: StarRailChallengePeakRecord):
        data = HistoryDataChallengePeak(peak_data=peak_data, record=record)
        data_id = record.group.season
        json_data = data.model_dump_json(by_alias=True)
        dict_data = jsonlib.loads(json_data)
        dict_data["peak_data"]["challenge_peak_records"] = []
        return HistoryData(
            user_id=user_id,
            data_id=data_id,
            time_created=datetime.datetime.now(),
            type=HistoryDataChallengePeakServices.DATA_TYPE,
            data=dict_data,
        )
