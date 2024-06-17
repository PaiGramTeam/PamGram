from typing import List, Dict, Union

from simnet.models.starrail.self_help import StarRailSelfHelpActionLog

from modules.action_log.date import DateUtils
from modules.action_log.models import ActionLogPair


class ActionLogAnalyse(DateUtils):
    def __init__(self, data: List[StarRailSelfHelpActionLog], data2: Dict[int, int]):
        super().__init__()
        self.data = data
        self.data2 = data2
        self.pairs = self.init_pair(data)
        self.this_week_data: List[ActionLogPair] = []
        self.last_week_data: List[ActionLogPair] = []
        self.this_month_data: List[ActionLogPair] = []
        self.last_month_data: List[ActionLogPair] = []
        self.init_pair_data()

    def init_pair_data(self):
        """通过时间点判断数据属于哪个时间段"""
        for d in self.pairs:
            if self.week_start <= d.start_time < self.week_end:
                self.this_week_data.append(d)
            elif self.week_last_start <= d.start_time < self.week_last_end:
                self.last_week_data.append(d)
            if self.month_start <= d.start_time < self.month_end:
                self.this_month_data.append(d)
            elif self.month_last_start <= d.start_time < self.month_last_end:
                self.last_month_data.append(d)

    @staticmethod
    def init_pair(data: List[StarRailSelfHelpActionLog]) -> List[ActionLogPair]:
        # 确保第一个数据为登入，最后一条数据为登出
        if data[0].status == 0:
            data.pop(0)
        if data[-1].status == 1:
            data.pop(-1)
        pairs = []
        for i in range(0, len(data), 2):
            pairs.append(ActionLogPair(start=data[i], end=data[i + 1]))
        return pairs

    def get_this_week_duration(self) -> int:
        """本周时长"""
        return sum(d.duration.seconds for d in self.this_week_data)

    def get_last_week_duration(self) -> int:
        """上周时长"""
        return sum(d.duration.seconds for d in self.last_week_data)

    def get_this_month_duration(self) -> int:
        """本月时长"""
        return sum(d.duration.seconds for d in self.this_month_data)

    def get_last_month_duration(self) -> int:
        """上月时长"""
        return sum(d.duration.seconds for d in self.last_month_data)

    def get_this_month_avg_duration(self) -> float:
        """本月平均时长"""
        return self.get_this_month_duration() / len(self.this_month_data)

    def get_last_month_avg_duration(self) -> float:
        """上月平均时长"""
        return self.get_last_month_duration() / len(self.last_month_data)

    def get_this_week_long_duration(self) -> int:
        """周最长会话"""
        return max(d.duration.seconds for d in self.this_week_data)

    def get_this_week_short_duration(self) -> int:
        """周最短会话"""
        return min(d.duration.seconds for d in self.this_week_data)

    def get_this_month_long_duration(self) -> int:
        """月最长会话"""
        return max(d.duration.seconds for d in self.this_month_data)

    def get_this_month_short_duration(self) -> int:
        """月最短会话"""
        return min(d.duration.seconds for d in self.this_month_data)

    @staticmethod
    def format_sec(sec: Union[int, float]) -> str:
        hour = sec // 3600
        minute = (sec % 3600) // 60
        second = sec % 60
        if hour:
            return f"{int(hour)}时{int(minute)}分"
        if minute:
            return f"{int(minute)}分{int(second)}秒"
        return f"{int(second)}秒"

    def get_data(self) -> List[Dict[str, str]]:
        data = {
            "本周时长": self.get_this_week_duration(),
            "上周时长": self.get_last_week_duration(),
            "本月时长": self.get_this_month_duration(),
            "上月时长": self.get_last_month_duration(),
            "本月平均": self.get_this_month_avg_duration(),
            "上月平均": self.get_last_month_avg_duration(),
            "周最长会话": self.get_this_week_long_duration(),
            "月最长会话": self.get_this_month_long_duration(),
            "周最短会话": self.get_this_week_short_duration(),
            "月最短会话": self.get_this_month_short_duration(),
        }
        datas = []
        for k, v in data.items():
            datas.append(
                {
                    "name": k,
                    "value": self.format_sec(v),
                }
            )

        max_hour = max(self.data2, key=self.data2.get)
        min_hour = min(self.data2, key=self.data2.get)
        datas.append({"name": "最常上线", "value": f"{max_hour}点"})
        datas.append({"name": "最少上线", "value": f"{min_hour}点"})

        return datas

    def get_line_data(self) -> List[Dict[str, str]]:
        data = []
        for k, v in self.data2.items():
            data.append(
                {
                    "month": f"{k}点",
                    "value": v,
                }
            )
        return data

    def get_record_data(self) -> List[Dict[str, str]]:
        data = []
        limit = 4
        data_len = len(self.data) - 1
        for i in range(data_len, data_len - limit, -1):
            record = self.data[i]
            data.append(
                {
                    "time": record.time.strftime("%Y年%m月%d日 %H:%M:%S"),
                    "reason": record.reason.value,
                }
            )
        return data
