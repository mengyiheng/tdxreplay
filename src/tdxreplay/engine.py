"""tdxreplay.engine — 把本地通达信分钟线按真实时间轴重放为"模拟实时"行情流。

设计目标：检验回测系统的真实性。用与实盘完全相同的消费接口
（逐根 K 线流），在盘中不可得的历史时段复现"当时你只能看到什么"。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Tuple

from tdxdata import MinuteBar, read_minute
from tdxdata.vipdoc import find_bar_file


@dataclass(frozen=True)
class ReplayEvent:
    """一根重放出来的 K 线。

    ``pace_seconds`` 是按真实时间轴本根与上根之间的理论间隔（秒），
    供消费方判断是否跨了午休/开盘跳空。
    """

    code: str
    market: str
    bar: MinuteBar
    index: int                # 全局序号（从 0 开始）
    pace_seconds: int         # 与上一根的理论间隔；首根为 0


def _parse_dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


def _in_trading(dt: datetime) -> bool:
    t = dt.hour * 60 + dt.minute
    return 9 * 60 + 30 <= t <= 11 * 60 + 30 or 13 * 60 <= t <= 15 * 60


class ReplaySession:
    """模拟实时回放会话。

    参数：
        vipdoc:   通达信数据目录（含 sh/sz/bj 子目录）
        codes:    证券代码列表，如 ["600519", "000001"]
        trade_date: 交易日 "YYYY-MM-DD"，None = 用数据里最新的完整一天
        speed:    重放速度倍率；1 = 真实速度，60 = 1 分钟 K 线每秒走 1 根，
                  0 或 None = 不做时间节流（全速，适合批量验证）
        max_gap_seconds: 相邻两根的理论间隔超过该秒数时（午休/开盘跳空）
                  按该上限节流，避免回放长时间停滞

    用法（生成器模式，与实盘行情循环同构）::

        for ev in ReplaySession(vipdoc, ["600519"], "2026-10-19", speed=60):
            print(ev.code, ev.bar.datetime, ev.bar.close)   # 你的实盘处理逻辑

    用法（回调模式）::

        session.run(on_bar=lambda ev: ..., on_end=lambda: ...)
    """

    def __init__(self, vipdoc: str | Path, codes: List[str],
                 trade_date: Optional[str] = None,
                 speed: Optional[float] = 1.0,
                 max_gap_seconds: int = 60,
                 kinds: str = "lc1"):
        self.vipdoc = Path(vipdoc)
        self.codes = list(codes)
        self.speed = speed
        self.max_gap_seconds = max_gap_seconds
        self.kinds = kinds
        self.timeline: List[Tuple[datetime, str, str, MinuteBar]] = []
        self._load(trade_date)

    # ---------- 数据装载 ----------

    def _load(self, trade_date: Optional[str]) -> None:
        per_code: dict[str, List[Tuple[datetime, MinuteBar]]] = {}
        for code in self.codes:
            path = find_bar_file(self.vipdoc, code, self.kinds)
            bars = [b for b in read_minute(path)
                    if trade_date is None or b.datetime.startswith(trade_date)]
            if trade_date is None and bars:
                latest = max(b.datetime[:10] for b in bars)
                bars = [b for b in bars if b.datetime.startswith(latest)]
            if not bars:
                continue
            per_code[code] = [(_parse_dt(b.datetime), b) for b in bars]

        if not per_code:
            raise FileNotFoundError(
                f"在 {self.vipdoc} 中找不到 {self.codes} 的分钟数据"
                + (f"（{trade_date}）" if trade_date else ""))

        merged: List[Tuple[datetime, str, str, MinuteBar]] = []
        for code, items in per_code.items():
            market = "sh" if code.startswith(("6", "5", "9")) else (
                "bj" if code.startswith(("4", "8")) else "sz")
            for dt, bar in items:
                merged.append((dt, code, market, bar))
        merged.sort(key=lambda x: x[0])
        self.timeline = merged

    # ---------- 重放 ----------

    def _iter_events(self) -> Iterator[ReplayEvent]:
        prev_dt: Optional[datetime] = None
        for i, (dt, code, market, bar) in enumerate(self.timeline):
            if prev_dt is None:
                pace = 0
            else:
                pace = min(int((dt - prev_dt).total_seconds()), self.max_gap_seconds * 60)
                pace = max(pace, 0)
            yield ReplayEvent(code, market, bar, i, pace)
            prev_dt = dt

    def __iter__(self) -> Iterator[ReplayEvent]:
        """按 speed 节流地逐根产出。speed 为 0/None 时全速。"""
        wall_start = time.monotonic()
        virt_start = self.timeline[0][0].timestamp() if self.timeline else 0.0
        for ev in self._iter_events():
            if self.speed:
                virt_now = ev.bar.datetime and _parse_dt(ev.bar.datetime).timestamp()
                target = wall_start + (virt_now - virt_start) / self.speed
                delay = target - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
            yield ev

    def run(self, on_bar: Callable[[ReplayEvent], None],
            on_end: Optional[Callable[[], None]] = None) -> int:
        """回调模式：每根 K 线调用 on_bar，结束调用 on_end。返回总根数。"""
        n = 0
        for ev in self:
            on_bar(ev)
            n += 1
        if on_end:
            on_end()
        return n


def list_dates(vipdoc: str | Path, code: str, kinds: str = "lc1") -> List[str]:
    """列出某代码本地分钟数据覆盖的交易日（升序）。"""
    path = find_bar_file(vipdoc, code, kinds)
    return sorted({b.datetime[:10] for b in read_minute(path)})
