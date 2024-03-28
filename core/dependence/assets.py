import asyncio
from pathlib import Path
from ssl import SSLZeroReturnError
from typing import Optional, List, Dict

from aiofiles import open as async_open
from httpx import AsyncClient, HTTPError

from core.base_service import BaseService
from modules.wiki.base import WikiModel
from modules.wiki.models.avatar_config import AvatarIcon
from modules.wiki.models.head_icon import HeadIcon
from modules.wiki.models.light_cone_config import LightConeIcon
from utils.const import PROJECT_ROOT
from utils.log import logger
from utils.typedefs import StrOrURL, StrOrInt

ASSETS_PATH = PROJECT_ROOT.joinpath("resources/assets")
ASSETS_PATH.mkdir(exist_ok=True, parents=True)
DATA_MAP = {
    "avatar": WikiModel.BASE_URL + "avatar_icons.json",
    "light_cone": WikiModel.BASE_URL + "light_cone_icons.json",
    "avatar_eidolon": WikiModel.BASE_URL + "avatar_eidolon_icons.json",
    "avatar_skill": WikiModel.BASE_URL + "skill/info.json",
    "head_icon": WikiModel.BASE_URL + "head_icons.json",
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
        eidolons = await self.client.get(DATA_MAP["avatar_eidolon"])
        eidolons_data = eidolons.json()
        skills = await self.client.get(DATA_MAP["avatar_skill"])
        skills_data = skills.json()
        self.data = [AvatarIcon(**data) for data in html.json()]
        self.name_map = {icon.name: icon for icon in self.data}
        self.id_map = {icon.id: icon for icon in self.data}
        tasks = []
        for icon in self.data:
            eidolons_s_data = eidolons_data.get(str(icon.id), [])
            skills_s_data = [f"{i}.png" for i in skills_data if i.startswith(str(icon.id) + "_")]
            base_path = self.path / f"{icon.id}"
            base_path.mkdir(exist_ok=True, parents=True)
            gacha_path = base_path / "gacha.webp"
            icon_path = base_path / "icon.webp"
            normal_path = base_path / "normal.webp"
            square_path = base_path / "square.png"
            eidolons_paths = [(base_path / f"eidolon_{eidolon_id}.webp") for eidolon_id in range(1, 7)]
            skills_paths = []
            for i in skills_s_data:
                temp_end = "_".join(i.split("_")[1:])
                skills_paths.append(base_path / f"skill_{temp_end}")
            if not gacha_path.exists():
                tasks.append(self._download(icon.gacha, gacha_path))
            if not icon_path.exists():
                tasks.append(self._download(icon.icon_, icon_path))
            if not normal_path.exists():
                tasks.append(self._download(icon.normal, normal_path))
            if not square_path.exists() and icon.square:
                tasks.append(self._download(icon.square, square_path))
            for index, eidolon in enumerate(eidolons_paths):
                if not eidolons_s_data:
                    break
                if not eidolon.exists():
                    tasks.append(self._download(eidolons_s_data[index], eidolon))
            for index, skill in enumerate(skills_paths):
                if not skill.exists():
                    tasks.append(self._download(WikiModel.BASE_URL + "skill/" + skills_s_data[index], skill))
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

    def get_target(self, target: StrOrInt, second_target: StrOrInt = None) -> AvatarIcon:
        data = None
        if isinstance(target, int):
            data = self.get_by_id(target)
        elif isinstance(target, str):
            data = self.get_by_name(target)
        if data is None:
            if second_target:
                return self.get_target(second_target)
            raise AssetsCouldNotFound("角色素材图标不存在", target)
        return data

    def gacha(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        icon = self.get_target(target, second_target)
        return self.get_path(icon, "gacha")

    def icon(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        icon = self.get_target(target, second_target)
        return self.get_path(icon, "icon")

    def normal(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        icon = self.get_target(target, second_target)
        return self.get_path(icon, "normal")

    def square(self, target: StrOrInt, second_target: StrOrInt = None, allow_icon: bool = True) -> Path:
        icon = self.get_target(target, second_target)
        path = self.get_path(icon, "square", "png")
        if not path.exists():
            if allow_icon:
                return self.get_path(icon, "icon")
            raise AssetsCouldNotFound("角色素材图标不存在", target)
        return path

    def eidolons(self, target: StrOrInt, second_target: StrOrInt = None) -> List[Path]:
        """星魂"""
        icon = self.get_target(target, second_target)
        return [self.get_path(icon, f"eidolon_{i}") for i in range(1, 7)]

    def skill_basic_atk(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        """普攻 001"""
        icon = self.get_target(target, second_target)
        return self.get_path(icon, "skill_basic_atk", "png")

    def skill_skill(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        """战技 002"""
        icon = self.get_target(target, second_target)
        return self.get_path(icon, "skill_skill", "png")

    def skill_ultimate(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        """终结技 003"""
        icon = self.get_target(target, second_target)
        return self.get_path(icon, "skill_ultimate", "png")

    def skill_talent(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        """天赋 004"""
        icon = self.get_target(target, second_target)
        return self.get_path(icon, "skill_talent", "png")

    def skill_technique(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        """秘技 007"""
        icon = self.get_target(target, second_target)
        return self.get_path(icon, "skill_technique", "png")

    def skills(self, target: StrOrInt, second_target: StrOrInt = None) -> List[Path]:
        icon = self.get_target(target, second_target)
        return [
            self.get_path(icon, "skill_basic_atk", "png"),
            self.get_path(icon, "skill_skill", "png"),
            self.get_path(icon, "skill_ultimate", "png"),
            self.get_path(icon, "skill_talent", "png"),
            self.get_path(icon, "skill_technique", "png"),
        ]


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

    def get_target(self, target: StrOrInt, second_target: StrOrInt = None) -> Optional[LightConeIcon]:
        if isinstance(target, int):
            return self.get_by_id(target)
        elif isinstance(target, str):
            return self.get_by_name(target)
        if second_target:
            return self.get_target(second_target)
        raise AssetsCouldNotFound("光锥素材图标不存在", target)

    def gacha(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        icon = self.get_target(target, second_target)
        return self.get_path(icon, "gacha")

    def icon(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        icon = self.get_target(target, second_target)
        return self.get_path(icon, "icon")


class _HeadIconAssets(_AssetsService):
    path: Path
    data: List[HeadIcon]
    id_map: Dict[int, HeadIcon]
    avatar_id_map: Dict[int, HeadIcon]

    def __init__(self, client: Optional[AsyncClient] = None) -> None:
        super().__init__(client)
        self.path = ASSETS_PATH.joinpath("head_icon")
        self.path.mkdir(exist_ok=True, parents=True)

    async def initialize(self):
        logger.info("正在初始化头像素材图标")
        html = await self.client.get(DATA_MAP["head_icon"])
        self.data = [HeadIcon(**data) for data in html.json()]
        self.id_map = {icon.id: icon for icon in self.data}
        self.avatar_id_map = {icon.avatar_id: icon for icon in self.data if icon.avatar_id}
        tasks = []
        for icon in self.data:
            webp_path = self.path / f"{icon.id}.webp"
            png_path = self.path / f"{icon.id}.png"
            if not webp_path.exists() and icon.webp:
                tasks.append(self._download(icon.webp, webp_path))
            if not png_path.exists():
                tasks.append(self._download(icon.png, png_path))
            if len(tasks) >= 100:
                await asyncio.gather(*tasks)
                tasks = []
        if tasks:
            await asyncio.gather(*tasks)
        logger.info("头像素材图标初始化完成")

    def get_path(self, icon: HeadIcon, ext: str) -> Path:
        path = self.path / f"{icon.id}.{ext}"
        return path

    def get_by_id(self, id_: int) -> Optional[HeadIcon]:
        return self.id_map.get(id_, None)

    def get_by_avatar_id(self, avatar_id: int) -> Optional[HeadIcon]:
        return self.avatar_id_map.get(avatar_id, None)

    def get_target(self, target: StrOrInt, second_target: StrOrInt = None) -> Optional[HeadIcon]:
        if 1000 < target <= 9000:
            data = self.get_by_avatar_id(target)
            if data:
                return data
        data = self.get_by_id(target)
        if data:
            return data
        if second_target:
            return self.get_target(second_target)
        raise AssetsCouldNotFound("头像素材图标不存在", target)

    def webp(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        icon = self.get_target(target, second_target)
        return self.get_path(icon, "webp")

    def png(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        icon = self.get_target(target, second_target)
        return self.get_path(icon, "png")

    def icon(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        icon = self.get_target(target, second_target)
        webp_path = self.get_path(icon, "webp")
        png_path = self.get_path(icon, "png")
        if webp_path.exists():
            return webp_path
        if png_path.exists():
            return png_path
        raise AssetsCouldNotFound("头像素材图标不存在", target)


class AssetsService(BaseService.Dependence):
    """asset服务

    用于储存和管理 asset :
        当对应的 asset (如某角色图标)不存在时，该服务会先查找本地。
        若本地不存在，则从网络上下载；若存在，则返回其路径
    """

    client: Optional[AsyncClient] = None

    avatar: _AvatarAssets
    """角色"""

    head_icon: _HeadIconAssets
    """头像"""

    light_cone: _LightConeAssets
    """光锥"""

    def __init__(self):
        self.client = AsyncClient(timeout=60.0)
        self.avatar = _AvatarAssets(self.client)
        self.head_icon = _HeadIconAssets(self.client)
        self.light_cone = _LightConeAssets(self.client)

    async def initialize(self):  # pylint: disable=W0221
        await self.avatar.initialize()
        await self.head_icon.initialize()
        await self.light_cone.initialize()
