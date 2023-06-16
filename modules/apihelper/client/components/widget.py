from genshin import Client

from modules.apihelper.models.genshin.widget import StarRailWidget, GenshinWidget
from modules.apihelper.utility.helpers import get_ds, update_device_headers


class Widget:
    genshin_url = "https://api-takumi-record.mihoyo.com/game_record/genshin/aapi/widget/v2?game_id=2"
    starrail_url = "https://api-takumi-record.mihoyo.com/game_record/hkrpg/aapi/widget"
    HEADERS = {
        "User-Agent": "okhttp/4.8.0",
        "x-rpc-sys_version": "12",
        "x-rpc-channel": "mihoyo",
        "x-rpc-device_name": "",
        "x-rpc-device_model": "",
        "Referer": "https://app.mihoyo.com",
        "Host": "api-takumi-record.mihoyo.com",
    }

    @staticmethod
    async def get_headers(hoyolab_id: int):
        app_version, client_type, ds_sign = get_ds()
        headers = Widget.HEADERS.copy()
        headers["x-rpc-app_version"] = app_version
        headers["x-rpc-client_type"] = client_type
        headers["ds"] = ds_sign
        update_device_headers(hoyolab_id, headers)
        return headers

    @staticmethod
    async def get_starrail_widget(client: Client):
        headers = await Widget.get_headers(client.hoyolab_id)
        data = await client.cookie_manager.request(Widget.starrail_url, method="GET", headers=headers)
        return StarRailWidget(**data)

    @staticmethod
    async def get_genshin_widget(client: Client):
        headers = await Widget.get_headers(client.hoyolab_id)
        data = await client.cookie_manager.request(Widget.genshin_url, method="GET", headers=headers)
        return GenshinWidget(**data)
