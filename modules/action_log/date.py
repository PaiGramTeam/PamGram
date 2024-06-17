from datetime import datetime, timedelta

from pytz import timezone

TZ = timezone("Asia/Shanghai")


class DateUtils:
    def __init__(self):
        self.now = datetime.now(tz=TZ)
        # 本周
        self.week_start = self.date_start(self.now - timedelta(days=self.now.weekday()))
        self.week_end = self.week_start + timedelta(days=7)
        # 上周
        self.week_last_start = self.week_start - timedelta(days=7)
        self.week_last_end = self.week_start
        # 本月
        self.month_start = self.date_start(self.now.replace(day=1))
        self.month_end = self.get_month_end(self.month_start)
        # 上月
        month_last = (self.month_start - timedelta(days=1)).replace(day=1)
        self.month_last_start = self.date_start(month_last)
        self.month_last_end = self.get_month_end(month_last)

    @staticmethod
    def date_start(date: datetime) -> datetime:
        return date.replace(hour=4, minute=0, second=0, microsecond=0)

    def get_week_start(self) -> datetime:
        day = self.now - timedelta(days=self.now.weekday())
        return self.date_start(day)

    def get_month_end(self, date: datetime) -> datetime:
        next_month = date.replace(day=28) + timedelta(days=5)
        next_month_start = next_month.replace(day=1)
        return self.date_start(next_month_start)
