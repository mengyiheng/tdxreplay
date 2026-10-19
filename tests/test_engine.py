from datetime import date

import pytest

from tdxdata import MinuteBar, write_minute
from tdxreplay import ReplayEvent, ReplaySession, list_dates


def _make_vipdoc(tmp_path, codes_minutes):
    """codes_minutes: {code: [(HH,MM,close), ...]} -> 临时 vipdoc 目录。"""
    for code, points in codes_minutes.items():
        market = "sh" if code.startswith("6") else "sz"
        d = tmp_path / market / "minline"
        d.mkdir(parents=True, exist_ok=True)
        bars = [MinuteBar(f"2026-10-19 {h:02d}:{m:02d}", 10.0, 10.5, 9.9, c, 1e5, 100)
                for h, m, c in points]
        write_minute(d / f"{market}{code}.lc1", bars)


def test_multi_code_timeline_merged_and_sorted(tmp_path):
    _make_vipdoc(tmp_path, {
        "600519": [(9, 31, 10.1), (9, 32, 10.2), (9, 33, 10.3)],
        "000001": [(9, 32, 5.1), (9, 34, 5.2)],
    })
    evs = list(ReplaySession(tmp_path, ["600519", "000001"], "2026-10-19", speed=0))
    # 同一时刻的多股 K 线按代码加入顺序稳定排列
    assert [(ev.code, ev.bar.datetime) for ev in evs] == [
        ("600519", "2026-10-19 09:31"),
        ("600519", "2026-10-19 09:32"),
        ("000001", "2026-10-19 09:32"),
        ("600519", "2026-10-19 09:33"),
        ("000001", "2026-10-19 09:34"),
    ]


def test_date_filter(tmp_path):
    _make_vipdoc(tmp_path, {"600519": [(9, 31, 10.1)]})
    # 数据只有 10-19，请求别的日期应报错
    with pytest.raises(FileNotFoundError):
        ReplaySession(tmp_path, ["600519"], "2026-10-20", speed=0)


def test_latest_day_default(tmp_path):
    for day, closes in (("2026-10-16", [(9, 31, 1.0)]), ("2026-10-19", [(9, 31, 2.0)])):
        d = tmp_path / "sh" / "minline"
        d.mkdir(parents=True, exist_ok=True)
        write_minute(d / "sh600519.lc1",
                     [MinuteBar(f"{day} {h:02d}:{m:02d}", 1, 1, 1, c, 0, 1)
                      for h, m, c in closes],
                     append=True)
    s = ReplaySession(tmp_path, ["600519"], speed=0)
    assert s.timeline[0][3].datetime.startswith("2026-10-19")


def test_pace_seconds_and_lunch_gap(tmp_path):
    # 11:30 最后一根上午 K 与 13:01 第一根下午 K 之间应有 pace 但被 clamp
    _make_vipdoc(tmp_path, {"600519": [(11, 30, 1.0), (13, 1, 2.0)]})
    evs = list(ReplaySession(tmp_path, ["600519"], "2026-10-19", speed=0,
                             max_gap_seconds=60))
    assert evs[0].pace_seconds == 0
    assert evs[1].pace_seconds == 60 * 60      # 91 分钟被压到 60 分钟上限
    assert all(isinstance(ev, ReplayEvent) for ev in evs)


def test_full_speed_runs_without_sleep(tmp_path):
    _make_vipdoc(tmp_path, {"600519": [(h, m, 1.0) for h in (9, 10) for m in range(1, 30)]})
    s = ReplaySession(tmp_path, ["600519"], "2026-10-19", speed=0)
    n = s.run(on_bar=lambda ev: None)
    assert n == 58


def test_list_dates(tmp_path):
    _make_vipdoc(tmp_path, {"600519": [(9, 31, 1.0)]})
    assert list_dates(tmp_path, "600519") == ["2026-10-19"]
