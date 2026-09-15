"""Step 2.3 — notice when a relationship has died, before the money does.

This is the component most often missing from a statistical arbitrage system,
and the one that prevents the classic failure: a bot that keeps averaging into a
spread which stopped mean-reverting months ago.

Each cycle it refits the relationship on recent history only and asks four
questions — is it still cointegrated, does the spread still revert at a usable
speed, has the hedge ratio moved beyond its own historical variation, and has the
spread gone so far that the relationship should be presumed broken. The answers
produce one of three states:

* **healthy** — trade normally
* **degraded** — no new entries; positions already open may run
* **broken** — force the exit now, at a loss, without waiting for reversion

`--replay` walks the whole history and prints what the monitor would have said at
each point. That is the only honest way to choose the thresholds: set them so the
monitor would have flagged the failures you already know about. On stored data
`AUDUSD~NZDUSD` reads broken in every window it has, and `GBPUSD~USDNOK` turns
broken in 2022, years before a full-sample fit noticed.

    python health.py -s USDNOK,USDZAR --replay
    python health.py -s AUDUSD,NZDUSD --replay --lookback 500 --recheck-every 20
    python health.py -s BTC-USDT,ETH-USDT -a crypto --max-pvalue 0.10

Exit codes: 0 healthy, 3 degraded or broken, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

import paths

paths.ensure_code_importable()
paths.ensure_marketdata_importable()

import pair_report as pr                                          # noqa: E402

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from statsmodels.tsa.stattools import coint                   # noqa: E402

UserError = pr.UserError

HEALTHY, DEGRADED, BROKEN = "healthy", "degraded", "broken"


@dataclass
class Check:
    """One cycle of the monitor."""

    bar: int
    when: str
    beta: float
    pvalue: float
    half_life: float
    z: float
    beta_drift: float
    state: str
    trigger: str
    trigger_code: str = ""        # which check fired, for counting without parsing prose


def assess(window: pd.DataFrame, *, history_betas: list[float], max_pvalue: float,
           degraded_pvalue: float, min_half_life: float, max_half_life: float,
           break_z: float, max_beta_drift: float,
           coint_maxlag: int = 1) -> Check:
    """Judge the relationship from `window` alone, which ends at the current bar."""
    a, b = window.columns
    y = window[a].to_numpy(float)
    x = window[b].to_numpy(float)
    beta, alpha = (float(v) for v in np.polyfit(x, y, 1))
    spread = y - beta * x - alpha

    ar = float(np.polyfit(spread[:-1], spread[1:], 1)[0])
    half_life = math.log(2) / -math.log(ar) if 0.0 < ar < 1.0 else float("nan")
    sd = float(np.std(spread, ddof=1)) or 1e-12
    z = float(spread[-1] / sd)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # A fixed lag keeps every cycle comparable and keeps the replay quick.
        # Measured on 2000 independent random-walk pairs it rejects 4.7% of the
        # time at the nominal 5% level, so the thresholds below mean what they
        # say. Windows here are shorter than that test used, which costs power
        # rather than size: the monitor misses weak relationships sooner than it
        # invents strong ones.
        pvalue = float(coint(y, x, trend="c", autolag=None, maxlag=coint_maxlag)[1])

    # Drift is measured against the ratio's own past variation, so a naturally
    # wandering pair is not punished for wandering the amount it always has.
    if len(history_betas) >= 10:
        past = np.array(history_betas[-60:])
        centre = float(np.mean(past))
        # A ratio that has been perfectly steady has zero dispersion, and dividing
        # by that would declare the smallest movement infinitely abnormal. The
        # scale is floored at a tenth of the ratio, so with the default limit of
        # three the ratio must move about 30% before it counts as drifting.
        # Measured hedge ratios wander far more than a few percent — EURUSD
        # against GBPUSD ranged from 0.05 to 1.43 on stored data — so a tighter
        # floor would fire constantly on pairs that are behaving normally.
        scale = max(float(np.std(past, ddof=1)), abs(centre) * 0.10, 1e-6)
        beta_drift = abs(beta - centre) / scale
    else:
        beta_drift = 0.0

    state, trigger, code = HEALTHY, "", ""
    if abs(z) >= break_z:
        state, code = BROKEN, "break-level"
        trigger = f"spread at {z:+.1f} sigma, past the break level"
    elif pvalue > degraded_pvalue:
        state, code = BROKEN, "cointegration"
        trigger = f"cointegration p {pvalue:.3f} above {degraded_pvalue:g}"
    elif not math.isfinite(half_life):
        state, code = BROKEN, "not-reverting"
        trigger = "spread is not mean reverting at all"
    elif beta_drift > max_beta_drift:
        state, code = BROKEN, "hedge-drift"
        trigger = (f"hedge ratio {beta_drift:.1f} standard deviations from its own "
                   "recent mean")
    elif pvalue > max_pvalue:
        state, code = DEGRADED, "cointegration"
        trigger = f"cointegration p {pvalue:.3f} above {max_pvalue:g}"
    elif not (min_half_life <= half_life <= max_half_life):
        state, code = DEGRADED, "half-life"
        trigger = f"half-life {half_life:.1f} outside {min_half_life:g} to {max_half_life:g}"
    return Check(bar=len(window) - 1, when=f"{window.index[-1]:%Y-%m-%d}", beta=beta,
                 pvalue=pvalue, half_life=half_life, z=z, beta_drift=beta_drift,
                 state=state, trigger=trigger, trigger_code=code)


def replay(prices: pd.DataFrame, *, lookback: int, every: int, **thresholds) -> list[Check]:
    """Walk the history, judging only on bars available at each point."""
    lp = np.log(prices)
    checks: list[Check] = []
    betas: list[float] = []
    for end in range(lookback, len(lp) + 1, every):
        window = lp.iloc[end - lookback:end]
        check = assess(window, history_betas=betas, **thresholds)
        # The index carried by `assess` is window-relative; restate it against
        # the full series so a caller can line it up with a price chart.
        check.bar = end - 1
        betas.append(check.beta)
        checks.append(check)
    return checks


def summarise(checks: list[Check]) -> dict:
    if not checks:
        return {"checks": 0}
    states = [c.state for c in checks]
    triggers: dict[str, int] = {}
    for c in checks:
        if c.trigger_code:
            triggers[c.trigger_code] = triggers.get(c.trigger_code, 0) + 1
    return {"checks": len(checks),
            "healthy": states.count(HEALTHY) / len(states),
            "degraded": states.count(DEGRADED) / len(states),
            "broken": states.count(BROKEN) / len(states),
            "transitions": sum(1 for i in range(1, len(states))
                               if states[i] != states[i - 1]),
            "triggers": triggers,
            "final": states[-1]}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="health", description=__doc__.splitlines()[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sel = p.add_argument_group("selection")
    sel.add_argument("-s", "--symbols", required=True)
    sel.add_argument("-a", "--asset-class", default="forex")
    sel.add_argument("-t", "--timeframe", default="1d")
    sel.add_argument("--source", default=None)
    sel.add_argument("--start", default=None)
    sel.add_argument("--end", default=None)

    search = p.add_argument_group("searched - set these with --replay, not by taste")
    search.add_argument("--lookback", type=int, default=500,
                        help="bars the monitor may look back on each cycle")
    search.add_argument("--recheck-every", type=int, default=10, help="bars between cycles")
    search.add_argument("--max-pvalue", type=float, default=0.05,
                        help="above this the relationship is degraded")
    search.add_argument("--degraded-pvalue", type=float, default=0.20,
                        help="above this it is broken, not merely degraded")
    search.add_argument("--min-half-life", type=float, default=2.0)
    search.add_argument("--max-half-life", type=float, default=60.0)
    search.add_argument("--break-z", type=float, default=4.0,
                        help="spread distance at which the relationship is presumed broken")
    search.add_argument("--max-beta-drift", type=float, default=3.0,
                        help="hedge ratio moves, in standard deviations of its own past")

    out = p.add_argument_group("output")
    out.add_argument("--replay", action="store_true",
                    help="walk the whole history instead of judging only the last bar")
    out.add_argument("--show", type=int, default=25, help="rows to print when replaying")
    out.add_argument("--store", default=str(paths.STORE))
    out.add_argument("--json", action="store_true")
    out.add_argument("-q", "--quiet", action="store_true")
    out.add_argument("-v", "--verbose", action="store_true")
    out.add_argument("--price", default="log", help=argparse.SUPPRESS)
    out.add_argument("--split", type=float, default=0.70, help=argparse.SUPPRESS)
    out.add_argument("--hedge", default="ols", help=argparse.SUPPRESS)
    out.add_argument("--entry-z", type=float, default=2.0, help=argparse.SUPPRESS)
    out.add_argument("--exit-z", type=float, default=0.5, help=argparse.SUPPRESS)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))
    if args.lookback < 120:
        raise UserError("--lookback must be at least 120 bars for the test to mean anything")
    if args.recheck_every < 1:
        raise UserError("--recheck-every must be at least 1")
    if args.max_pvalue >= args.degraded_pvalue:
        raise UserError("--max-pvalue must be below --degraded-pvalue")

    prices = pr.load_prices(args)
    a, b = prices.columns
    if len(prices) <= args.lookback:
        raise UserError(f"only {len(prices)} bars, fewer than --lookback {args.lookback}")

    thresholds = dict(max_pvalue=args.max_pvalue, degraded_pvalue=args.degraded_pvalue,
                      min_half_life=args.min_half_life, max_half_life=args.max_half_life,
                      break_z=args.break_z, max_beta_drift=args.max_beta_drift)

    log(f"{a} ~ {b}   {args.timeframe}   {prices.index[0]:%Y-%m-%d} to "
        f"{prices.index[-1]:%Y-%m-%d}   {len(prices):,} bars")

    if not args.replay:
        window = np.log(prices).iloc[-args.lookback:]
        check = assess(window, history_betas=[], **thresholds)
        log(f"  {check.state.upper()}"
            + (f" — {check.trigger}" if check.trigger else " — every check passed"))
        log(f"  beta {check.beta:+.4f}   cointegration p {check.pvalue:.3f}   "
            f"half-life "
            + (f"{check.half_life:.1f}" if math.isfinite(check.half_life) else "none")
            + f"   z {check.z:+.2f}")
        if args.json:
            print(json.dumps(asdict(check), indent=2, default=str))
        return 0 if check.state == HEALTHY else 3

    checks = replay(prices, lookback=args.lookback, every=args.recheck_every, **thresholds)
    stats = summarise(checks)
    step = max(1, len(checks) // max(args.show, 1))
    log("")
    log(f"  {'date':>12s} {'beta':>8s} {'p':>7s} {'half-life':>10s} {'z':>7s} "
        f"{'drift':>6s} {'state':>9s}  trigger")
    for c in checks[::step]:
        hl = f"{c.half_life:.1f}" if math.isfinite(c.half_life) else "none"
        log(f"  {c.when:>12s} {c.beta:+8.3f} {c.pvalue:7.3f} {hl:>10s} {c.z:+7.2f} "
            f"{c.beta_drift:6.1f} {c.state:>9s}  {c.trigger}")

    log("")
    log(f"  {stats['checks']} cycles: healthy {stats['healthy']:.0%}, "
        f"degraded {stats['degraded']:.0%}, broken {stats['broken']:.0%}, "
        f"{stats['transitions']} changes of state, ending {stats['final']}")
    if stats["triggers"]:
        log("  what fired: " + ", ".join(f"{k} x{v}" for k, v in
                                         sorted(stats["triggers"].items(),
                                                key=lambda kv: -kv[1])))
        if len(stats["triggers"]) == 1:
            log("  Only one check ever fires, so the others are not earning their place.")
    if stats["healthy"] < 0.5:
        log(f"  This relationship is tradable less than half the time. A backtest that "
            f"ignores the monitor is reporting profit from periods the monitor would "
            f"have sat out.")
    if args.json:
        print(json.dumps({"pair": f"{a}~{b}", **stats,
                          "checks": [asdict(c) for c in checks]}, indent=2, default=str))
    return 0 if stats["final"] == HEALTHY else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:                                       # noqa: BLE001
        if "-v" in sys.argv or "--verbose" in sys.argv:
            raise
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
