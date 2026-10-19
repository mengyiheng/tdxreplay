"""tdxreplay 命令行。

用法:
  tdxreplay run  --vipdoc D:\\new_tdx64\\vipdoc --codes 600519,000001 --date 2026-10-19 --speed 60
  tdxreplay serve --vipdoc ... --codes 600519 --date 2026-10-19 --port 8640
  tdxreplay dates --vipdoc ... --code 600519
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tdxreplay", description="通达信本地分钟线模拟实时回放")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--vipdoc", required=True, help="通达信 vipdoc 目录")
        sp.add_argument("--codes", required=True, help="逗号分隔的证券代码")
        sp.add_argument("--date", default=None, help="交易日 YYYY-MM-DD（默认取最新一天）")
        sp.add_argument("--kinds", default="lc1", choices=["lc1", "lc5"])
        sp.add_argument("--speed", type=float, default=1.0,
                        help="速度倍率；0 = 全速不节流")

    run = sub.add_parser("run", help="终端回放")
    common(run)

    serve = sub.add_parser("serve", help="以 HTTP SSE 提供行情流")
    common(serve)
    serve.add_argument("--port", type=int, default=8640)

    dates = sub.add_parser("dates", help="列出本地数据覆盖的交易日")
    dates.add_argument("--vipdoc", required=True)
    dates.add_argument("--code", required=True)
    dates.add_argument("--kinds", default="lc1")

    a = p.parse_args(argv)

    if a.cmd == "dates":
        from .engine import list_dates
        for d in list_dates(a.vipdoc, a.code, a.kinds):
            print(d)
        return 0

    codes = [c.strip() for c in a.codes.split(",") if c.strip()]
    from .engine import ReplaySession
    session = ReplaySession(a.vipdoc, codes, a.date, speed=a.speed, kinds=a.kinds)

    if a.cmd == "run":
        def on_bar(ev):
            b = ev.bar
            print(f"{b.datetime}  {ev.market}{ev.code}  "
                  f"O={b.open:.2f} H={b.high:.2f} L={b.low:.2f} C={b.close:.2f} "
                  f"V={b.vol:.0f}")
        n = session.run(on_bar)
        print(f"[tdxreplay] 回放完成，共 {n} 根")
        return 0

    from .serve import serve
    serve(session, port=a.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
