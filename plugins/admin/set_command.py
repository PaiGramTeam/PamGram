from typing import TYPE_CHECKING

from telegram import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat

from core.plugin import Plugin, handler
from core.config import config
from utils.log import logger

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes


class SetCommandPlugin(Plugin):
    @handler.command(command="set_command", block=False, admin=True)
    @handler.command("set_commands", block=False, admin=True)
    async def set_command(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] 发出 set_command 命令", user.full_name, user.id)
        user_command = [
            BotCommand("cancel", "取消操作（解决一切玄学问题）"),
            BotCommand("warp_log_import", "导入跃迁记录"),
            BotCommand("warp_log_export", "导出跃迁记录"),
            BotCommand("warp_log_delete", "删除跃迁记录"),
            BotCommand("action_log_import", "导入登录记录"),
            BotCommand("setuid", "添加/重设UID"),
            BotCommand("setcookie", "添加/重设Cookie"),
            BotCommand("player", "管理用户绑定玩家"),
            BotCommand("verify", "手动验证"),
            BotCommand("daily_note_tasks", "自动便笺提醒"),
            BotCommand("cookies_import", "从其他 BOT 导入账号信息"),
            BotCommand("cookies_export", "导出账号信息给其他 BOT"),
            BotCommand("privacy", "隐私政策"),
        ]
        group_command = [
            BotCommand("help", "帮助"),
            BotCommand("warp_log", "查看跃迁记录"),
            BotCommand("warp_log_online_view", "抽卡记录在线浏览"),
            BotCommand("action_log", "查询登录记录"),
            BotCommand("dailynote", "查询实时便笺"),
            BotCommand("redeem", "（国际服）兑换 Key"),
            BotCommand("ledger", "查询当月开拓月历"),
            BotCommand("ledger_history", "查询开拓月历历史记录"),
            BotCommand("avatars", "查询角色练度"),
            BotCommand("player_card", "角色卡片"),
            BotCommand("role_detail", "角色详细信息"),
            BotCommand("sign", "米游社星穹铁道每日签到"),
            BotCommand("light_cone", "光锥图鉴查询"),
            BotCommand("relics", "遗器套装查询"),
            BotCommand("strategy", "角色攻略查询"),
            BotCommand("material", "角色培养素材查询"),
            BotCommand("challenge", "混沌回忆信息查询"),
            BotCommand("challenge_history", "混沌回忆历史信息查询"),
            BotCommand("challenge_story", "虚构叙事信息查询"),
            BotCommand("challenge_story_history", "虚构叙事历史信息查询"),
            BotCommand("challenge_boss", "末日幻想信息查询"),
            BotCommand("challenge_boss_history", "末日幻想历史信息查询"),
            BotCommand("rogue", "模拟宇宙信息查询"),
            BotCommand("rogue_locust", "寰宇蝗灾信息查询"),
            BotCommand("rogue_tourn", "差分宇宙信息查询"),
            BotCommand("activity_export", "活动数据导出"),
        ]
        admin_command = [
            BotCommand("add_admin", "添加管理员"),
            BotCommand("del_admin", "删除管理员"),
            BotCommand("refresh_wiki", "刷新Wiki缓存"),
            BotCommand("save_entry", "保存条目数据"),
            BotCommand("remove_all_entry", "删除全部条目数据"),
            BotCommand("sign_all", "全部账号重新签到"),
            BotCommand("refresh_all_history", "全部账号刷新历史记录"),
            BotCommand("action_log_import_all", "全部账号导入登录记录"),
            BotCommand("send_log", "发送日志"),
            BotCommand("update", "更新"),
            BotCommand("set_command", "重设命令"),
            BotCommand("status", "当前Bot运行状态"),
            BotCommand("leave_chat", "退出群组"),
            BotCommand("get_chat", "获取会话信息"),
            BotCommand("add_block", "添加黑名单"),
            BotCommand("del_block", "移除黑名单"),
        ]
        await context.bot.delete_my_commands()
        await context.bot.set_my_commands(commands=group_command)
        await context.bot.set_my_commands(commands=group_command + user_command, scope=BotCommandScopeAllPrivateChats())
        if config.error.notification_chat_id:
            await context.bot.set_my_commands(
                commands=group_command + user_command + admin_command,
                scope=BotCommandScopeChat(config.error.notification_chat_id),
            )
        await message.reply_text("设置命令成功")
