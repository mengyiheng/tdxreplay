"""tdxreplay — 通达信本地分钟线模拟实时回放。

目的：检验回测系统的真实性。把历史 LC1/LC5 分钟数据按真实时间轴
逐根重放成"模拟实时行情"，让你的策略/回测代码在盘中不可得的条件下
接受与实盘同构的数据流。

    from tdxreplay import ReplaySession

    for ev in ReplaySession(r"D:\\new_tdx64\\vipdoc", ["600519"],
                            "2026-10-19", speed=60):
        handle_bar(ev.code, ev.bar)   # 与实盘相同的处理函数
"""

from .engine import ReplayEvent, ReplaySession, list_dates

__version__ = "0.1.0"
__all__ = ["ReplaySession", "ReplayEvent", "list_dates", "__version__"]
