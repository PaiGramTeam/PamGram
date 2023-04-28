import asyncio
from pathlib import Path
from ssl import SSLZeroReturnError
from typing import Optional, List, Dict

from aiofiles import open as async_open
from httpx import AsyncClient, HTTPError

from core.base_service import BaseService
from modules.wiki.base import WikiModel
from modules.wiki.models.avatar_config import AvatarIcon
from modules.wiki.models.light_cone_config import LightConeIcon
from utils.const import PROJECT_ROOT
from utils.log import logger
from utils.typedefs import StrOrURL, StrOrInt

ASSETS_PATH = PROJECT_ROOT.joinpath("resources/assets")
ASSETS_PATH.mkdir(exist_ok=True, parents=True)
DATA_MAP = {
    "avatar": WikiModel.BASE_URL + "avatar_icons.json",
    "light_cone": WikiModel.BASE_URL + "light_cone_icons.json",
}


class AssetsServiceError(Exception):
    pass


class AssetsCouldNotFound(AssetsServiceError):
    def __init__(self, message: str, target: str):
        self.message = message
        self.target = target
        super().__init__(f"{message}: target={message}")


class _AssetsService:
    client: Optional[AsyncClient] = None

    def __init__(self, client: Optional[AsyncClient] = None) -> None:
        self.client = client

    async def _download(self, url: StrOrURL, path: Path, retry: int = 5) -> Optional[Path]:
        """从 url 下载图标至 path"""
        logger.debug("正在从 %s 下载图标至 %s", url, path)
        headers = None
        for time in range(retry):
            try:
                response = await self.client.get(url, follow_redirects=False, headers=headers)
            except Exception as error:  # pylint: disable=W0703
                if not isinstance(error, (HTTPError, SSLZeroReturnError)):
                    logger.error(error)  # 打印未知错误
                if time != retry - 1:  # 未达到重试次数
                    await asyncio.sleep(1)
                else:
                    raise error
                continue
            if response.status_code != 200:  # 判定页面是否正常
                return None
            async with async_open(path, "wb") as file:
                await file.write(response.content)  # 保存图标
            return path.resolve()


class _AvatarAssets(_AssetsService):
    path: Path
    data: List[AvatarIcon]
    name_map: Dict[str, AvatarIcon]
    id_map: Dict[int, AvatarIcon]

    def __init__(self, client: Optional[AsyncClient] = None) -> None:
        super().__init__(client)
        self.path = ASSETS_PATH.joinpath("avatar")
        self.path.mkdir(exist_ok=True, parents=True)

    async def initialize(self):
        logger.info("正在初始化角色素材图标")
        html = await self.client.get(DATA_MAP["avatar"])
        self.data = [AvatarIcon(**data) for data in html.json()]
        self.name_map = {icon.name: icon for icon in self.data}
        self.id_map = {icon.id: icon for icon in self.data}
        tasks = []
        for icon in self.data:
            base_path = self.path / f"{icon.id}"
            base_path.mkdir(exist_ok=True, parents=True)
            gacha_path = base_path / "gacha.webp"
            icon_path = base_path / "icon.webp"
            normal_path = base_path / "normal.webp"
            square_path = base_path / "square.png"
            if not gacha_path.exists():
                tasks.append(self._download(icon.gacha, gacha_path))
            if not icon_path.exists():
                tasks.append(self._download(icon.icon_, icon_path))
            if not normal_path.exists():
                tasks.append(self._download(icon.normal, normal_path))
            if not square_path.exists() and icon.square:
                tasks.append(self._download(icon.square, square_path))
            if len(tasks) >= 100:
                await asyncio.gather(*tasks)
                tasks = []
        if tasks:
            await asyncio.gather(*tasks)
        logger.info("角色素材图标初始化完成")

    def get_path(self, icon: AvatarIcon, name: str, ext: str = "webp") -> Path:
        path = self.path / f"{icon.id}"
        path.mkdir(exist_ok=True, parents=True)
        return path / f"{name}.{ext}"

    def get_by_id(self, id_: int) -> Optional[AvatarIcon]:
        return self.id_map.get(id_, None)

    def get_by_name(self, name: str) -> Optional[AvatarIcon]:
        return self.name_map.get(name, None)

    def get_target(self, target: StrOrInt) -> AvatarIcon:
        data = None
        if isinstance(target, int):
            data = self.get_by_id(target)
        elif isinstance(target, str):
            data = self.get_by_name(target)
        if data is None:
            raise AssetsCouldNotFound("角色素材图标不存在", target)
        return data

    def gacha(self, target: StrOrInt) -> Path:
        icon = self.get_target(target)
        return self.get_path(icon, "gacha")

    def icon(self, target: StrOrInt) -> Path:
        icon = self.get_target(target)
        return self.get_path(icon, "icon")

    def normal(self, target: StrOrInt) -> Path:
        icon = self.get_target(target)
        return self.get_path(icon, "normal")

    def square(self, target: StrOrInt, allow_icon: bool = True) -> Path:
        icon = self.get_target(target)
        path = self.get_path(icon, "square", "png")
        if not path.exists():
            if allow_icon:
                return self.get_path(icon, "icon")
            raise AssetsCouldNotFound("角色素材图标不存在", target)
        return path


class _LightConeAssets(_AssetsService):
    path: Path
    data: List[LightConeIcon]
    name_map: Dict[str, LightConeIcon]
    id_map: Dict[int, LightConeIcon]

    def __init__(self, client: Optional[AsyncClient] = None) -> None:
        super().__init__(client)
        self.path = ASSETS_PATH.joinpath("light_cone")
        self.path.mkdir(exist_ok=True, parents=True)

    async def initialize(self):
        logger.info("正在初始化光锥素材图标")
        html = await self.client.get(DATA_MAP["light_cone"])
        self.data = [LightConeIcon(**data) for data in html.json()]
        self.name_map = {icon.name: icon for icon in self.data}
        self.id_map = {icon.id: icon for icon in self.data}
        tasks = []
        for icon in self.data:
            base_path = self.path / f"{icon.id}"
            base_path.mkdir(exist_ok=True, parents=True)
            gacha_path = base_path / "gacha.webp"
            icon_path = base_path / "icon.webp"
            if not gacha_path.exists():
                tasks.append(self._download(icon.gacha, gacha_path))
            if not icon_path.exists():
                tasks.append(self._download(icon.icon_, icon_path))
            if len(tasks) >= 100:
                await asyncio.gather(*tasks)
                tasks = []
        if tasks:
            await asyncio.gather(*tasks)
        logger.info("光锥素材图标初始化完成")

    def get_path(self, icon: LightConeIcon, name: str) -> Path:
        path = self.path / f"{icon.id}"
        path.mkdir(exist_ok=True, parents=True)
        return path / f"{name}.webp"

    def get_by_id(self, id_: int) -> Optional[LightConeIcon]:
        return self.id_map.get(id_, None)

    def get_by_name(self, name: str) -> Optional[LightConeIcon]:
        return self.name_map.get(name, None)

    def get_target(self, target: StrOrInt) -> Optional[LightConeIcon]:
        if isinstance(target, int):
            return self.get_by_id(target)
        elif isinstance(target, str):
            return self.get_by_name(target)
        return None

    def gacha(self, target: StrOrInt) -> Path:
        icon = self.get_target(target)
        if icon is None:
            raise AssetsCouldNotFound("光锥素材图标不存在", target)
        return self.get_path(icon, "gacha")

    def icon(self, target: StrOrInt) -> Path:
        icon = self.get_target(target)
        if icon is None:
            raise AssetsCouldNotFound("光锥素材图标不存在", target)
        return self.get_path(icon, "icon")


class AssetsService(BaseService.Dependence):
    """asset服务

    用于储存和管理 asset :
        当对应的 asset (如某角色图标)不存在时，该服务会先查找本地。
        若本地不存在，则从网络上下载；若存在，则返回其路径
    """

    client: Optional[AsyncClient] = None

    avatar: _AvatarAssets
    """角色"""

    light_cone: _LightConeAssets
    """光锥"""

    def __init__(self):
        self.client = AsyncClient(timeout=60.0)
        self.avatar = _AvatarAssets(self.client)
        self.light_cone = _LightConeAssets(self.client)

    async def initialize(self):  # pylint: disable=W0221
        await self.avatar.initialize()
        await self.light_cone.initialize()
