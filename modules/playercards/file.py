import asyncio
from pathlib import Path
from typing import Optional, Dict, Union

import aiofiles

from utils.const import PROJECT_ROOT

try:
    import ujson as jsonlib
except ImportError:
    import json as jsonlib


PLAYER_CARDS_PATH = PROJECT_ROOT.joinpath("data", "apihelper", "player_cards")
PLAYER_CARDS_PATH.mkdir(parents=True, exist_ok=True)


class PlayerCardsFile:
    _lock = asyncio.Lock()

    def __init__(self, player_cards_path: Path = PLAYER_CARDS_PATH):
        self.player_cards_path = player_cards_path

    @staticmethod
    async def load_json(path):
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            return jsonlib.loads(await f.read())

    @staticmethod
    async def save_json(path, data: Dict):
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            return await f.write(jsonlib.dumps(data, ensure_ascii=False, indent=4))

    def get_file_path(self, uid: Union[str, int]):
        """获取文件路径
        :param uid: UID
        :return: 文件路径
        """
        return self.player_cards_path / f"{uid}.json"

    async def load_history_info(
        self,
        uid: Union[str, int],
    ) -> Optional[Dict]:
        """读取历史记录数据
        :param uid: uid
        :return: 角色历史记录数据
        """
        file_path = self.get_file_path(uid)
        if not file_path.exists():
            return None
        try:
            return await self.load_json(file_path)
        except jsonlib.JSONDecodeError:
            return None

    async def merge_info(
        self,
        uid: Union[str, int],
        data: Dict,
        props: Dict,
    ) -> Dict:
        assistAvatarDetail = "assistAvatarDetail"
        avatarId = "avatarId"
        avatarDetailList = "avatarDetailList"
        avatarList = "avatarList"
        async with self._lock:
            old_data = await self.load_history_info(uid)
            if old_data is None:
                old_data = {}
            avatars = []
            avatar_ids = []
            assist_avatar = data.get(assistAvatarDetail, None)
            if assist_avatar:
                avatars.append(assist_avatar)
                avatar_ids.append(assist_avatar.get(avatarId, 0))
            for avatar in data.get(avatarDetailList, []):
                if avatar.get(avatarId, 0) in avatar_ids:
                    continue
                avatars.append(avatar)
                avatar_ids.append(avatar.get(avatarId, 0))
            data[avatarList] = avatars
            if assistAvatarDetail in data:
                del data[assistAvatarDetail]
            if avatarDetailList in data:
                del data[avatarDetailList]
            for i in old_data.get(avatarList, []):
                if i.get(avatarId, 0) not in avatar_ids:
                    data[avatarList].append(i)
            for i in data[avatarList]:
                i["property"] = props.get(i.get(avatarId, 0), [])
            await self.save_json(self.get_file_path(uid), data)
            return data
