"""Step 1d — replay bars through the live signal code and charge real costs.

The engine walks bars forward, calls `signal.target_position` with history that
ends at the current bar, and fills the resulting change at the next bar. Costs
come from the Step 1a profile: spread and commission on every crossing, and
financing for every night a position is held.

    python backtest.py -s USDNOK,USDZAR --broker demo
    python backtest.py -s USDNOK,USDZAR --broker demo --entry-z 1.5 --stop-z 3 --open
    python backtest.py -s USDNOK,USDZAR --broker demo --signal random --seed 7 --dry-run

Exit codes: 0 net profitable, 3 net loss, 2 usage error, 1 runtime error.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import sys
import webbrowser
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import paths

paths.ensure_code_importable()

import costs as cost_model                                        # noqa: E402
import pair_report as pr                                          # noqa: E402
import strategy as sig                                            # noqa: E402

UserError = pr.UserError
DEFAULT_REPORTS = paths.BACKTEST_STUDIES
DEFAULT_TRIALS = paths.BACKTEST_LOG


@dataclass
class Trade:
    entry_bar: int
    exit_bar: int
    entry_time: str
    exit_time: str
    direction: str
    entry_z: float
    exit_z: float
    bars_held: int
    gross_bps: float
    transaction_bps: float
    carry_bps: float
    net_bps: float
    exit_reason: str


@dataclass
class Result:
    bars: int
    trades: list
    equity_gross: np.ndarray
    equity_net: np.ndarray
    position: np.ndarray
    z: np.ndarray
    gross_bps: float
    transaction_bps: float
    carry_bps: float
    net_bps: float
    exposure_bars: int


def health_states(prices: pd.DataFrame, *, lookback: int, every: int,
                  thresholds: dict) -> np.ndarray:
    """The monitor's verdict at every bar, judged only on bars available then.

    Cycles run every `every` bars and the verdict holds until the next one, so a
    bar is never scored with information it could not have had. Bars before the
    first full lookback have no verdict and are treated as unhealthy, which keeps
    the gate from trading a relationship it has not yet been able to assess.
    """
    import health as hm

    states = np.array([hm.BROKEN] * len(prices), dtype=object)
    for check in hm.replay(prices, lookback=lookback, every=every, **thresholds):
        states[check.bar:] = check.state
    return states


def run_backtest(prices: pd.DataFrame, profile: dict, params: sig.SignalParams, *,
                 warmup: int, bars_per_night: float, signal_mode: str = "strategy",
                 seed: int = 0, lag: int = 1, close_at_end: bool = True,
                 health: np.ndarray | None = None) -> Result:
    """Walk the bars once. Decide on a close, fill at the next one.

    `lag` is the number of bars between the decision and the fill. It exists so
    the verification suite can push it to two and confirm the result gets worse;
    a backtest whose profit survives a longer delay is usually reading the
    future somewhere.
    """
    a, b = prices.columns
    values = prices.to_numpy(float)
    simple = np.vstack([np.zeros(2), values[1:] / values[:-1] - 1.0])
    index = prices.index

    rng = np.random.default_rng(seed)
    state = sig.SignalState()
    n = len(prices)

    position = np.zeros(n)
    zs = np.full(n, np.nan)
    gross = np.zeros(n)
    transaction = np.zeros(n)
    carry = np.zeros(n)

    pending: list[tuple[int, int, float, float]] = []       # fill bar, position, beta, z
    current, current_beta, entry_bar, entry_z = 0, 0.0, -1, 0.0
    trades: list[Trade] = []
    open_gross = open_cost = open_carry = 0.0
    exit_reason = ""

    for t in range(n):
        # 1. Returns accrue on the position held coming into this bar.
        if current != 0 and t > 0:
            denom = 1.0 + abs(current_beta)
            pos_a, pos_b = sig.leg_weights(current, current_beta)
            bar_gross = (pos_a * simple[t, 0] + pos_b * simple[t, 1]) / denom * 1e4
            gross[t] = bar_gross
            open_gross += bar_gross
            # `_carry_bps` is signed the way brokers quote swap: negative is a
            # debit. The equity line adds carry, so the sign passes straight
            # through and a debit reduces the result.
            night = _carry_bps(profile, a, b, current, current_beta) * bars_per_night
            carry[t] = night
            open_carry += night

        # 2. Fills that were decided earlier land now. A change of position is
        #    always an exit followed by an entry, even when it is a straight
        #    flip from long to short: booking a flip as one continuous trade
        #    reports a direction and a holding period that never happened.
        while pending and pending[0][0] == t:
            _, wanted, beta_at_decision, z_at_decision = pending.pop(0)
            if wanted == current:
                continue
            if current != 0:
                exit_cost = _turn_cost(profile, a, b, current, 0,
                                       current_beta, current_beta)
                transaction[t] += exit_cost
                open_cost += exit_cost
                trades.append(_close(index, entry_bar, t, current, entry_z,
                                     z_at_decision, open_gross, open_cost,
                                     open_carry, exit_reason))
                open_gross = open_cost = open_carry = 0.0
            if wanted != 0:
                entry_cost = _turn_cost(profile, a, b, 0, wanted,
                                        beta_at_decision, beta_at_decision)
                transaction[t] += entry_cost
                open_cost += entry_cost
                entry_bar, entry_z = t, z_at_decision
            current, current_beta = wanted, beta_at_decision
        position[t] = current

        # 3. Decide, using history that ends here, for a fill `lag` bars later.
        if t >= warmup and t + lag < n:
            history = prices.iloc[: t + 1]
            target = sig.target_position(history, state, params)
            state = target.state
            wanted = target.position
            if signal_mode == "random":
                # A coin flip with the same trade frequency, for calibration.
                wanted = int(rng.choice([-1, 0, 1], p=[0.15, 0.70, 0.15]))
            if health is not None:
                # broken: leave now, at whatever the spread is worth. degraded:
                # keep what is open but start nothing new. The monitor can only
                # ever reduce exposure, never create it.
                if health[t] == "broken":
                    wanted = 0
                elif health[t] == "degraded" and current == 0:
                    wanted = 0
            if target.fit is not None:
                zs[t] = target.z
                # With a fill delay the strategy already believes it holds the
                # new position, so the same intent would be queued again on
                # every bar until the fill lands. Queue each change once.
                queued = pending[-1][1] if pending else current
                if wanted != current and wanted != queued:
                    exit_reason = target.reason
                    pending.append((t + lag, wanted, target.fit.beta, target.z))

    # A position still open at the last bar has earned returns that belong to no
    # trade. Close it at the final price so every basis point is attributed.
    if current != 0 and close_at_end:
        exit_cost = _turn_cost(profile, a, b, current, 0, current_beta, current_beta)
        transaction[n - 1] += exit_cost
        open_cost += exit_cost
        last_z = float(zs[n - 1]) if np.isfinite(zs[n - 1]) else float("nan")
        trades.append(_close(index, entry_bar, n - 1, current, entry_z, last_z,
                             open_gross, open_cost, open_carry,
                             "exit: end of the sample, closed at the last price"))

    net = gross - transaction + carry
    return Result(bars=n, trades=trades,
                  equity_gross=np.cumsum(gross), equity_net=np.cumsum(net),
                  position=position, z=zs,
                  gross_bps=float(gross.sum()),
                  transaction_bps=float(transaction.sum()),
                  carry_bps=float(carry.sum()),
                  net_bps=float(net.sum()),
                  exposure_bars=int((position != 0).sum()))


def _close(index, entry_bar: int, exit_bar: int, position: int, entry_z: float,
           exit_z: float, gross: float, cost: float, carry: float,
           reason: str) -> Trade:
    """Book one finished position."""
    return Trade(
        entry_bar=entry_bar, exit_bar=exit_bar,
        entry_time=str(index[entry_bar].date()), exit_time=str(index[exit_bar].date()),
        direction="long spread" if position > 0 else "short spread",
        entry_z=entry_z, exit_z=exit_z, bars_held=exit_bar - entry_bar,
        gross_bps=gross, transaction_bps=cost, carry_bps=carry,
        net_bps=gross - cost + carry, exit_reason=reason)


def carry_per_night_bps(profile: dict, a: str, b: str, position: int,
                        beta: float) -> float:
    """Financing for one night on a unit of spread exposure, signed.

    Public because anything that predicts what a trade will cost has to charge
    what the engine charges. Two definitions of financing would let a bound be
    computed against costs that are never actually paid.
    """
    return _carry_bps(profile, a, b, position, beta)


def cheaper_direction(profile: dict, a: str, b: str, beta: float) -> int:
    """Which way round the spread is cheaper to finance: +1 long, -1 short.

    Financing is signed the way brokers quote swap, so a debit is negative and
    the cheaper side is the *larger* of the two values. Taking the minimum picks
    the most expensive leg, and a threshold priced against it looks unaffordable
    when it is not. That bug shipped once, in two places, which is why the
    answer now lives in one.
    """
    return max((carry_per_night_bps(profile, a, b, p, beta), p)
               for p in (1, -1))[1]


def round_trip_bps(profile: dict, a: str, b: str, position: int,
                   beta: float) -> float:
    """Transaction cost of opening and closing one unit of spread exposure.

    Public for the same reason as `carry_per_night_bps`.
    """
    return (_turn_cost(profile, a, b, 0, position, beta, beta)
            + _turn_cost(profile, a, b, position, 0, beta, beta))


def _carry_bps(profile: dict, a: str, b: str, position: int, beta: float) -> float:
    """Signed financing for one night on a unit of spread exposure."""
    pos_a, pos_b = sig.leg_weights(position, beta)
    total = 0.0
    for symbol, units in ((a, pos_a), (b, pos_b)):
        cost = profile.get(symbol)
        if cost is None:
            raise UserError(f"no cost profile for {symbol}")
        total += abs(units) * cost.carry_bps("long" if units > 0 else "short")
    return total / (1.0 + abs(beta))


def _turn_cost(profile: dict, a: str, b: str, old: int, new: int,
               old_beta: float, new_beta: float) -> float:
    """Spread and commission for moving from one position to another."""
    old_a, old_b = sig.leg_weights(old, old_beta)
    new_a, new_b = sig.leg_weights(new, new_beta)
    denom = 1.0 + abs(new_beta if new != 0 else old_beta)
    total = 0.0
    for symbol, delta in ((a, abs(new_a - old_a)), (b, abs(new_b - old_b))):
        cost = profile.get(symbol)
        if cost is None:
            raise UserError(f"no cost profile for {symbol}")
        total += delta * (cost.spread_bps() + cost.commission_bps)
    return total / denom


# ---------------------------------------------------------------- report
def drawdown(equity: np.ndarray) -> np.ndarray:
    peak = np.maximum.accumulate(equity)
    return equity - peak


def sharpe_ratio(net: np.ndarray, bars_per_year: float) -> float:
    """Annualised mean over deviation of the per-bar net returns.

    One definition, used by both `summarise` and `risk_metrics`. It lived in two
    places for one commit, which is how this project has produced three separate
    "two copies of a formula disagreed" defects.
    """
    if len(net) <= 2:
        return 0.0
    vol = float(np.std(net, ddof=1))
    return (float(np.mean(net)) / vol * math.sqrt(bars_per_year)) if vol > 0 else 0.0


def underwater_bars(equity: np.ndarray) -> tuple[int, int]:
    """Longest stretch below a previous peak, and how much of it is unrecovered.

    Returns the longest underwater run in bars and the length of the run still
    open at the end of the record. The second number matters because a strategy
    whose worst drawdown is still unrecovered on the last bar has not shown that
    it recovers at all; the maximum drawdown alone cannot say that.
    """
    if len(equity) == 0:
        return 0, 0
    peak = np.maximum.accumulate(equity)
    under = equity < peak
    longest = run = 0
    for flag in under:
        run = run + 1 if flag else 0
        longest = max(longest, run)
    trailing = 0
    for flag in under[::-1]:
        if not flag:
            break
        trailing += 1
    return longest, trailing


def risk_metrics(result: Result, bars_per_year: float, net: np.ndarray,
                 dd: np.ndarray, years: float) -> dict:
    """Profit and risk detail beyond the headline net figure.

    Everything here is derived from trades and the net equity curve that
    `run_backtest` already produced, so these numbers cannot disagree with the
    headline ones: there is no second simulation and no second cost model.

    Two of them are included specifically because they are the ones that stop a
    backtest being read too kindly.

    `sharpe_stderr` is the standard error of the Sharpe ratio itself, about
    `sqrt((1 + SR^2 / 2) / n)` annualised. A Sharpe of 0.33 measured over thirty
    trades is not distinguishable from zero, and printing the ratio without its
    error invites treating it as though it were.

    `mean_stderr_bps` is the standard error of the per-trade mean, the same
    quantity `sizing.py` uses for its haircut. When the mean is fewer than two
    standard errors from zero, the growth-optimal size collapses, and the reader
    should see why before seeing the profit.
    """
    trades = result.trades
    net_per_trade = np.array([t.net_bps for t in trades], dtype=float)
    wins = net_per_trade[net_per_trade > 0]
    losses = net_per_trade[net_per_trade <= 0]

    gross_win = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(-losses.sum()) if len(losses) else 0.0
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

    # Longest run of consecutive losing trades, which is what a drawdown feels
    # like to whoever is watching it happen.
    worst_streak = streak = 0
    for value in net_per_trade:
        streak = streak + 1 if value <= 0 else 0
        worst_streak = max(worst_streak, streak)

    downside = net[net < 0]
    downside_dev = float(np.std(downside, ddof=1)) if len(downside) > 2 else 0.0
    sortino = (float(np.mean(net)) / downside_dev * math.sqrt(bars_per_year)
               if downside_dev > 0 else 0.0)

    vol = float(np.std(net, ddof=1)) if len(net) > 2 else 0.0
    sharpe = sharpe_ratio(net, bars_per_year)
    n_obs = max(len(net), 2)
    sharpe_stderr = math.sqrt((1.0 + 0.5 * sharpe ** 2) / n_obs) * math.sqrt(bars_per_year)

    max_dd = float(dd.min()) if len(dd) else 0.0
    annual = result.net_bps / years
    calmar = (annual / abs(max_dd)) if max_dd < 0 else float("inf")

    longest_uw, trailing_uw = underwater_bars(result.equity_net)

    mean_bps = float(net_per_trade.mean()) if len(net_per_trade) else 0.0
    mean_se = (float(net_per_trade.std(ddof=1) / math.sqrt(len(net_per_trade)))
               if len(net_per_trade) > 1 else float("nan"))

    # The worst five per cent of trades, and the average of them. A single
    # percentile says where the tail starts; the mean beyond it says how far it
    # goes, which is the number that sizes a stop.
    var95 = (float(np.percentile(net_per_trade, 5)) if len(net_per_trade) else 0.0)
    tail = net_per_trade[net_per_trade <= var95]
    shortfall = float(tail.mean()) if len(tail) else 0.0

    return {
        "net_pct": result.net_bps / 100.0,
        "gross_pct": result.gross_bps / 100.0,
        "net_pct_per_year": annual / 100.0,
        "max_drawdown_pct": max_dd / 100.0,
        "volatility_pct_per_year": vol * math.sqrt(bars_per_year) / 100.0,
        "profit_factor": profit_factor,
        "expectancy_bps": mean_bps,
        "mean_stderr_bps": mean_se,
        "mean_over_stderr": (mean_bps / mean_se) if mean_se and math.isfinite(mean_se)
        and mean_se > 0 else float("nan"),
        "avg_win_bps": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss_bps": float(losses.mean()) if len(losses) else 0.0,
        "payoff_ratio": (float(wins.mean() / -losses.mean())
                         if len(wins) and len(losses) and losses.mean() < 0
                         else float("inf")),
        "best_trade_bps": float(net_per_trade.max()) if len(net_per_trade) else 0.0,
        "worst_trade_bps": float(net_per_trade.min()) if len(net_per_trade) else 0.0,
        "trade_var95_bps": var95,
        "expected_shortfall_bps": shortfall,
        "worst_losing_streak": worst_streak,
        "sortino": sortino,
        "sharpe": sharpe,
        "sharpe_stderr": sharpe_stderr,
        "calmar": calmar,
        "longest_underwater_bars": longest_uw,
        "unrecovered_bars": trailing_uw,
        "trades_per_year": len(trades) / years if years > 0 else 0.0,
    }


def summarise(result: Result, split: int, bars_per_year: float) -> dict:
    net = np.diff(np.concatenate([[0.0], result.equity_net]))
    wins = [t for t in result.trades if t.net_bps > 0]
    dd = drawdown(result.equity_net)
    years = max(result.bars / bars_per_year, 1e-9)
    sharpe = sharpe_ratio(net, bars_per_year)
    return {
        "trades": len(result.trades),
        "win_rate": len(wins) / len(result.trades) if result.trades else 0.0,
        "gross_bps": result.gross_bps,
        "transaction_bps": result.transaction_bps,
        "carry_bps": result.carry_bps,
        "net_bps": result.net_bps,
        "net_bps_per_year": result.net_bps / years,
        "max_drawdown_bps": float(dd.min()) if len(dd) else 0.0,
        "sharpe": sharpe,
        "time_in_market": result.exposure_bars / max(result.bars, 1),
        "avg_bars_held": (float(np.mean([t.bars_held for t in result.trades]))
                          if result.trades else 0.0),
        "net_in_sample_bps": float(result.equity_net[split - 1]) if split > 0 else 0.0,
        "net_out_of_sample_bps": float(result.equity_net[-1] - result.equity_net[split - 1])
        if split > 0 else 0.0,
        **risk_metrics(result, bars_per_year, net, dd, years),
    }


def show_risk(stats: dict, log) -> None:
    """The profit and risk detail, in percent, under the headline bps line.

    Percent is what the reader converts to anyway, and basis points are what the
    engine computes in; both are printed so neither has to be trusted on faith.
    All of it is per unit of spread notional, which is stated because it is the
    assumption that turns these figures into an account return and it is not the
    same as leverage of one.
    """
    pf = stats["profit_factor"]
    payoff = stats["payoff_ratio"]
    calmar = stats["calmar"]
    ratio = stats["mean_over_stderr"]

    log("")
    log("  profit                              risk")
    log(f"    net             {stats['net_pct']:>9,.2f}%"
        f"         max drawdown      {stats['max_drawdown_pct']:>9,.2f}%")
    log(f"    per year        {stats['net_pct_per_year']:>9,.2f}%"
        f"         volatility/year   {stats['volatility_pct_per_year']:>9,.2f}%")
    log(f"    gross           {stats['gross_pct']:>9,.2f}%"
        f"         Calmar            {calmar:>10,.2f}")
    log(f"    profit factor   {pf:>10,.2f}"
        f"         Sortino           {stats['sortino']:>10,.2f}")
    log(f"    payoff ratio    {payoff:>10,.2f}"
        f"         longest underwater{stats['longest_underwater_bars']:>8,} bars")
    log(f"    trades/year     {stats['trades_per_year']:>10,.1f}"
        f"         worst losing run  {stats['worst_losing_streak']:>8,} trades")
    log("")
    log(f"    per trade: expectancy {stats['expectancy_bps']:+,.1f} bps, "
        f"average win {stats['avg_win_bps']:+,.1f}, "
        f"average loss {stats['avg_loss_bps']:+,.1f}")
    log(f"    tail:      worst {stats['worst_trade_bps']:+,.1f} bps, "
        f"worst 5% start {stats['trade_var95_bps']:+,.1f}, "
        f"average beyond it {stats['expected_shortfall_bps']:+,.1f}")

    # The two lines that decide whether any of the above should be believed.
    log("")
    log(f"    Sharpe {stats['sharpe']:.2f} +/- {stats['sharpe_stderr']:.2f} "
        f"(standard error; on this many observations)")
    if math.isfinite(ratio):
        verdict = ("the mean is indistinguishable from zero" if abs(ratio) < 2
                   else "the mean is at least two standard errors from zero")
        log(f"    mean/standard error {ratio:+.2f} - {verdict}")
    if stats["unrecovered_bars"] > 0:
        log(f"    still {stats['unrecovered_bars']:,} bars below the previous peak "
            f"on the last bar of the record")
    log("    all figures are per unit of spread notional, not account equity; "
        "sizing.py converts")


def waterfall_chart(stats: dict) -> str:
    """Gross, then each cost, then net — the four numbers that matter, to scale."""
    width, height, pad_l, pad_b = 900, 190, 54, 26
    steps = [("gross", stats["gross_bps"], "up" if stats["gross_bps"] >= 0 else "down"),
             ("transaction", -stats["transaction_bps"], "down"),
             ("carry", stats["carry_bps"], "up" if stats["carry_bps"] >= 0 else "down"),
             ("net", stats["net_bps"], "net")]
    running, marks = 0.0, []
    for name, value, kind in steps[:-1]:
        marks.append((name, running, running + value, kind))
        running += value
    marks.append(("net", 0.0, stats["net_bps"], "net"))
    lo = min([m[1] for m in marks] + [m[2] for m in marks] + [0.0])
    hi = max([m[1] for m in marks] + [m[2] for m in marks] + [0.0])
    span = (hi - lo) or 1.0
    lo, hi = lo - span * 0.15, hi + span * 0.15
    sy = lambda v: 10 + (hi - v) / (hi - lo) * (height - 10 - pad_b)      # noqa: E731
    slot = (width - pad_l - 20) / len(marks)
    body = [f"<line class='grid' x1='{pad_l}' y1='{sy(0):.1f}' "
            f"x2='{width-20}' y2='{sy(0):.1f}'/>"]
    for i, (name, start, end, kind) in enumerate(marks):
        x = pad_l + i * slot + slot * 0.22
        w = slot * 0.56
        top, bottom = sy(max(start, end)), sy(min(start, end))
        cls = {"up": "bar-up", "down": "bar-down", "net": "bar-net"}[kind]
        body.append(f"<rect class='{cls}' x='{x:.1f}' y='{top:.1f}' width='{w:.1f}' "
                    f"height='{max(bottom-top, 1.5):.1f}'/>")
        body.append(f"<text class='tick' x='{x+w/2:.1f}' y='{height-12}' "
                    f"text-anchor='middle'>{name}</text>")
        body.append(f"<text class='barlab' x='{x+w/2:.1f}' y='{top-5:.1f}' "
                    f"text-anchor='middle'>{end-start:+,.0f}</text>")
    return (f"<div class='chart'><svg viewBox='0 0 {width} {height}' "
            f"preserveAspectRatio='none'>{''.join(body)}</svg></div>")


EXTRA_CSS = """
rect.bar-up{fill:var(--ok);opacity:.75}rect.bar-down{fill:var(--no);opacity:.75}
rect.bar-net{fill:var(--a);opacity:.85}
text.barlab{fill:var(--fg);font-size:10px;font-family:ui-monospace,Menlo,monospace}
td.num{font-family:ui-monospace,Menlo,monospace;text-align:right;white-space:nowrap}
.big{display:flex;gap:18px;flex-wrap:wrap;margin-bottom:6px}
.big div{flex:1 1 150px;border:1px solid var(--line);border-radius:6px;padding:8px 12px;
background:var(--zebra)}
.big b{display:block;font-size:19px;font-family:ui-monospace,Menlo,monospace}
.big span{color:var(--muted);font-size:11px}
"""


def build_html(prices, result: Result, stats: dict, args, split: int,
               params: sig.SignalParams, estimated: bool) -> str:
    a, b = prices.columns
    index = prices.index
    profitable = stats["net_bps"] > 0

    tiles = "".join(
        f"<div><b>{v}</b><span>{k}</span></div>" for k, v in [
            ("net, bps", f"{stats['net_bps']:+,.0f}"),
            ("gross, bps", f"{stats['gross_bps']:+,.0f}"),
            ("costs paid, bps", f"{stats['transaction_bps'] - stats['carry_bps']:,.0f}"),
            ("trades", f"{stats['trades']}"),
            ("win rate", f"{stats['win_rate']:.0%}"),
            ("max drawdown, bps", f"{stats['max_drawdown_bps']:,.0f}"),
        ])

    charts = [
        ("Where the money went",
         waterfall_chart(stats),
         "Gross result, then what the broker took, then what is left. If the last bar is "
         "not clearly positive the strategy does not pay for itself."),
        ("Equity, gross against net",
         pr.line_chart(index, {"gross": result.equity_gross, "net": result.equity_net},
                       split=split, decimals=0, sign=True),
         "The gap between the two lines is the cost of trading. It only widens."),
        ("Drawdown",
         pr.line_chart(index, {"drawdown": drawdown(result.equity_net)},
                       split=split, decimals=0, sign=True),
         "Distance below the previous peak, in basis points. This is what a live account "
         "would have felt."),
        ("Z-score and position",
         pr.line_chart(index, {"z": np.nan_to_num(result.z, nan=0.0),
                               "position x entry": result.position * params.entry_z},
                       hlines=[(params.entry_z, "entry"), (-params.entry_z, "entry"),
                               (params.exit_z, "exit"), (-params.exit_z, "exit"),
                               (params.stop_z, "mean"), (-params.stop_z, "mean"),
                               (0.0, "mean")],
                       split=split, decimals=1, sign=True),
         "The second line is the position, scaled to the entry threshold, so entries and "
         "exits can be read against the signal that caused them."),
        ("Holding periods",
         pr.histogram(np.array([t.bars_held for t in result.trades], dtype=float)
                      if result.trades else np.array([0.0]),
                      marks=[(params.max_holding_bars, "entry")], bins=min(args.bins, 30)),
         "A pile at the maximum means the time stop is doing the exiting, not the spread."),
    ]

    rows = []
    for t in result.trades[: args.max_trade_rows]:
        cls = "ok" if t.net_bps > 0 else "no"
        rows.append(
            f"<tr><td class='k'>{t.entry_time}</td><td class='k'>{t.exit_time}</td>"
            f"<td>{html.escape(t.direction)}</td>"
            f"<td class='num'>{t.entry_z:+.2f}</td><td class='num'>{t.exit_z:+.2f}</td>"
            f"<td class='num'>{t.bars_held}</td>"
            f"<td class='num'>{t.gross_bps:+,.1f}</td>"
            f"<td class='num'>{-t.transaction_bps:,.1f}</td>"
            f"<td class='num'>{t.carry_bps:+,.1f}</td>"
            f"<td class='num'><span class='b {cls}'>{t.net_bps:+,.1f}</span></td>"
            f"<td class='n'>{html.escape(t.exit_reason.split(':')[-1].strip())}</td></tr>")
    trades_table = (
        "<table><thead><tr><th>in</th><th>out</th><th>side</th><th>z in</th>"
        "<th>z out</th><th>bars</th><th>gross</th><th>cost</th><th>carry</th>"
        "<th>net</th><th>why it closed</th></tr></thead><tbody>"
        + "".join(rows) + "</tbody></table>") if rows else "<p>No trades.</p>"

    params_rows = [
        ("pair", f"{a} ~ {b}"), ("timeframe", args.timeframe),
        ("window", f"{index[0]:%Y-%m-%d} to {index[-1]:%Y-%m-%d}  ({len(index):,} bars)"),
        ("in / out split", f"{args.split:.0%}  ({split} / {len(index)-split})"),
        ("entry / exit z", f"{params.entry_z:g} / {params.exit_z:g}"),
        ("stop z", f"{params.stop_z:g}"),
        ("max holding", f"{params.max_holding_bars} bars"),
        ("hedge", f"{params.hedge_source}, window {params.fit_window}, "
                  f"refit every {params.rehedge_every}"),
        ("fill", f"{args.lag} bar after the decision, at the close"),
        ("cost profile", f"{args.broker}" + ("  (ESTIMATED)" if estimated else "")),
        ("signal", args.signal),
    ]
    results_rows = [
        ("net", f"{stats['net_bps']:+,.1f} bps", stats["net_bps"] > 0,
         "after every cost"),
        ("net per year", f"{stats['net_bps_per_year']:+,.1f} bps", None, ""),
        ("in sample / out of sample", f"{stats['net_in_sample_bps']:+,.0f} / "
         f"{stats['net_out_of_sample_bps']:+,.0f} bps",
         stats["net_out_of_sample_bps"] > 0, "out of sample is the honest half"),
        ("gross", f"{stats['gross_bps']:+,.1f} bps", None, "before costs"),
        ("transaction cost", f"{stats['transaction_bps']:,.1f} bps", None,
         "spread and commission"),
        ("carry", f"{stats['carry_bps']:+,.1f} bps", None,
         "financing, negative is a debit"),
        ("Sharpe", f"{stats['sharpe']:.2f}", None, "annualised, on bar returns"),
        ("max drawdown", f"{stats['max_drawdown_bps']:,.1f} bps", None, ""),
        ("trades", f"{stats['trades']}", None,
         f"average {stats['avg_bars_held']:.1f} bars held"),
        ("win rate", f"{stats['win_rate']:.1%}", None, ""),
        ("time in market", f"{stats['time_in_market']:.1%}", None, ""),
    ]

    sections = [f"<div class='big'>{tiles}</div>",
                "<h2>Results</h2><table><tbody>"
                + "".join(pr._row(k, v, ok, note) for k, v, ok, note in results_rows)
                + "</tbody></table>"]
    for title, svg, caption in charts:
        sections.append(f"<h2>{html.escape(title)}</h2>{svg}"
                        f"<div class='cap'>{html.escape(caption)}</div>")
    sections.append(f"<h2>Trades</h2>{trades_table}")
    sections.append("<h2>Parameters used</h2><div class='cols'><div><table><tbody>"
                    + "".join(f"<tr><td class='k'>{html.escape(k)}</td>"
                              f"<td class='v'>{html.escape(str(v))}</td></tr>"
                              for k, v in params_rows[:6])
                    + "</tbody></table></div><div><table><tbody>"
                    + "".join(f"<tr><td class='k'>{html.escape(k)}</td>"
                              f"<td class='v'>{html.escape(str(v))}</td></tr>"
                              for k, v in params_rows[6:])
                    + "</tbody></table></div></div>")

    note = ("Costs come from an ESTIMATED profile, not a broker sheet, so every number "
            "below the gross line is provisional. " if estimated else "")
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{a} ~ {b} backtest</title><style>{pr.CSS}{EXTRA_CSS}</style>"
            f"</head><body><h1>{a} ~ {b} · backtest</h1>"
            f"<div class='meta'>{args.timeframe} · {index[0]:%Y-%m-%d} to "
            f"{index[-1]:%Y-%m-%d} · {len(index):,} bars · generated "
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC</div>"
            f"<div class='verdict {'pass' if profitable else ''}'>"
            f"<b>{'NET PROFITABLE' if profitable else 'NET LOSS'}</b> — "
            f"{stats['net_bps']:+,.0f} bps after {stats['transaction_bps']:,.0f} bps of "
            f"transaction cost and {-stats['carry_bps']:+,.0f} bps of financing"
            f"<p>{note}Close-only fills on daily bars. Not a live result.</p></div>"
            + "".join(sections) + "</body></html>")


# ---------------------------------------------------------------- cli
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="backtest", description=__doc__.splitlines()[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sel = p.add_argument_group("selection")
    sel.add_argument("-s", "--symbols", required=True)
    sel.add_argument("-a", "--asset-class", default="forex")
    sel.add_argument("-t", "--timeframe", default="1d")
    sel.add_argument("--source", default=None)
    sel.add_argument("--start", default=None)
    sel.add_argument("--end", default=None)

    struct = p.add_argument_group("structure - choose once")
    struct.add_argument("--price", default="log", choices=("log", "raw"))
    struct.add_argument("--hedge", default="ols", choices=("ols",))
    struct.add_argument("--hedge-source", default="rolling", choices=("static", "rolling"))
    struct.add_argument("--signal", default="strategy", choices=("strategy", "random"),
                        help="random is the calibration control, not a strategy")

    search = p.add_argument_group("searched - every value is a trial")
    search.add_argument("--split", type=float, default=0.70)
    search.add_argument("--entry-z", type=float, default=2.0)
    search.add_argument("--exit-z", type=float, default=0.5)
    search.add_argument("--stop-z", type=float, default=4.0)
    search.add_argument("--max-holding-bars", type=int, default=20)
    search.add_argument("--min-bars-between-trades", type=int, default=0)
    search.add_argument("--fit-window", type=int, default=250)
    search.add_argument("--rehedge-every", type=int, default=5)
    search.add_argument("--warmup", type=int, default=260,
                        help="bars reserved for the first fit, never traded")

    given = p.add_argument_group("given by reality")
    given.add_argument("--broker", required=True)
    given.add_argument("--costs-dir", default=str(cost_model.DEFAULT_COSTS))
    given.add_argument("--bars-per-night", type=float, default=None,
                       help="nights of financing per bar; defaults to the asset class and timeframe, which is 1.45 for a daily equity bar and 1.0 only for crypto")
    given.add_argument("--lag", type=int, default=1,
                       help="bars between the decision and the fill; 1 is next close")
    given.add_argument("--leave-open", action="store_true",
                       help="do not close a position still open at the last bar")

    gate = p.add_argument_group("health gate - step 2 driving step 1")
    gate.add_argument("--health-gate", action="store_true",
                      help="consult the relationship health monitor each bar: flat while "
                           "broken, no new entries while degraded")
    gate.add_argument("--health-lookback", type=int, default=500)
    gate.add_argument("--health-every", type=int, default=10)
    gate.add_argument("--health-max-pvalue", type=float, default=0.05)
    gate.add_argument("--health-degraded-pvalue", type=float, default=0.20)
    gate.add_argument("--health-break-z", type=float, default=4.0)
    gate.add_argument("--health-max-beta-drift", type=float, default=3.0)

    out = p.add_argument_group("output")
    out.add_argument("-o", "--out", default=None)
    out.add_argument("--store", default=str(pr.DEFAULT_STORE))
    out.add_argument("--trials", default=str(DEFAULT_TRIALS))
    out.add_argument("--no-trial-log", action="store_true")
    out.add_argument("--bins", type=int, default=30)
    out.add_argument("--max-trade-rows", type=int, default=60)
    out.add_argument("--bars-per-year", type=float, default=252.0)
    out.add_argument("--seed", type=int, default=0, help="for --signal random")
    out.add_argument("--dry-run", action="store_true")
    out.add_argument("--brief", action="store_true",
                     help="print only the headline lines, without the risk and "
                          "profit detail")
    out.add_argument("--json", action="store_true")
    out.add_argument("--open", action="store_true")
    out.add_argument("-q", "--quiet", action="store_true")
    out.add_argument("-v", "--verbose", action="store_true")
    out.add_argument("--min-half-life", type=float, default=2.0, help=argparse.SUPPRESS)
    out.add_argument("--max-half-life", type=float, default=1e9, help=argparse.SUPPRESS)
    return p


def append_trial(path: Path, args, stats: dict, params: sig.SignalParams,
                 pair: str, out: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"run": 0, "run_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "pair": pair, "timeframe": args.timeframe,
           # Without the window, two rows with identical parameters and
           # different date ranges are indistinguishable in the log. That
           # happened: runs 9 and 11 below both read "XLP ~ XLB 1d entry 2.0",
           # one on 1,934 bars and one on 6,972, and nothing on the row said so.
           "start": args.start or "", "end": args.end or "",
           "signal": args.signal,
           "broker": args.broker, "entry_z": params.entry_z, "exit_z": params.exit_z,
           "stop_z": params.stop_z, "max_holding_bars": params.max_holding_bars,
           "hedge_source": params.hedge_source, "fit_window": params.fit_window,
           "health_gate": "yes" if args.health_gate else "no",
           "rehedge_every": params.rehedge_every, "lag": args.lag,
           # Financing is charged per bar times this, so it scales the carry
           # term and nothing else. Leaving it out of the row made run 5 of this
           # log irreproducible: same pair, same thresholds, same gross to the
           # basis point, and a carry 45% smaller, because that run charged 1.45
           # nights a bar for weekends and the row did not say so.
           "bars_per_night": args.bars_per_night, "warmup": args.warmup,
           "split": args.split, "trades": stats["trades"],
           "gross_bps": round(stats["gross_bps"], 1),
           "transaction_bps": round(stats["transaction_bps"], 1),
           "carry_bps": round(stats["carry_bps"], 1),
           "net_bps": round(stats["net_bps"], 1),
           "net_oos_bps": round(stats["net_out_of_sample_bps"], 1),
           "sharpe": round(stats["sharpe"], 3),
           "max_dd_bps": round(stats["max_drawdown_bps"], 1),
           "win_rate": round(stats["win_rate"], 4), "report": out.name}
    existing = 0
    if path.exists():
        with path.open(newline="", encoding="utf-8") as fh:
            header = next(csv.reader(fh), [])
            existing = sum(1 for _ in csv.reader(fh))
        if header and header != list(row):
            added = [c for c in row if c not in header]
            dropped = [c for c in header if c not in row]
            raise UserError(
                f"{path} was written by an older version of this script "
                f"(added {added or 'none'}, dropped {dropped or 'none'}). "
                "Rename it to keep the history and a fresh log will start. "
                "No report was written for this run.")
    row["run"] = existing + 1
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row))
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    return row["run"]


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))

    profile_path = Path(args.costs_dir) / f"{args.broker}.json"
    profile = cost_model.load_profile(profile_path)
    if not profile:
        raise UserError(f"no cost profile at {profile_path}; run costs.py add first")
    estimated = any(c.estimated for c in profile.values())

    params = sig.SignalParams(
        entry_z=args.entry_z, exit_z=args.exit_z, stop_z=args.stop_z,
        max_holding_bars=args.max_holding_bars,
        min_bars_between_trades=args.min_bars_between_trades,
        hedge_source=args.hedge_source, fit_window=args.fit_window,
        rehedge_every=args.rehedge_every, use_log=args.price == "log")

    prices = pr.load_prices(args)
    if args.bars_per_night is None:
        # One definition of how many nights a bar costs, in costs.py, rather
        # than a 1.0 that silently undercharges every asset class but crypto.
        first_class = args.asset_class.split(",")[0].strip().lower()
        args.bars_per_night = cost_model.nights_per_bar(first_class, args.timeframe)
    split = int(len(prices) * args.split)
    if args.warmup >= len(prices):
        raise UserError(f"--warmup {args.warmup} leaves no bars to trade")

    states = None
    if args.health_gate:
        if len(prices) <= args.health_lookback:
            raise UserError(f"--health-lookback {args.health_lookback} needs more bars "
                            f"than the {len(prices)} available")
        states = health_states(
            prices, lookback=args.health_lookback, every=args.health_every,
            thresholds=dict(max_pvalue=args.health_max_pvalue,
                            degraded_pvalue=args.health_degraded_pvalue,
                            min_half_life=2.0, max_half_life=60.0,
                            break_z=args.health_break_z,
                            max_beta_drift=args.health_max_beta_drift))
        share = {s: float(np.mean(states == s)) for s in ("healthy", "degraded", "broken")}
        log(f"  health gate on: healthy {share['healthy']:.0%}, "
            f"degraded {share['degraded']:.0%}, broken {share['broken']:.0%}")

    result = run_backtest(prices, profile, params, warmup=args.warmup,
                          bars_per_night=args.bars_per_night, signal_mode=args.signal,
                          seed=args.seed, lag=args.lag,
                          close_at_end=not args.leave_open, health=states)
    stats = summarise(result, split, args.bars_per_year)
    pair = " ~ ".join(prices.columns)

    log(f"{pair}  {args.timeframe}  {len(prices):,} bars  signal {args.signal}")
    log(f"  {stats['trades']} trades, {stats['win_rate']:.0%} winners, "
        f"{stats['avg_bars_held']:.1f} bars held on average")
    log(f"  gross {stats['gross_bps']:+,.1f}  transaction {-stats['transaction_bps']:,.1f}"
        f"  carry {stats['carry_bps']:+,.1f}  net {stats['net_bps']:+,.1f} bps")
    log(f"  out of sample {stats['net_out_of_sample_bps']:+,.1f} bps   "
        f"Sharpe {stats['sharpe']:.2f}   max drawdown {stats['max_drawdown_bps']:,.1f} bps")
    if not args.brief:
        show_risk(stats, log)
    if estimated:
        log("  NOTE: the cost profile is an estimate, not a broker sheet")

    if args.json:
        print(json.dumps({"pair": pair, **stats}, indent=2, default=str))
    if args.dry_run:
        log("  dry run: nothing written")
        return 0 if stats["net_bps"] > 0 else 3

    out = Path(args.out) if args.out else DEFAULT_REPORTS / (
        f"backtest-{prices.columns[0]}-{prices.columns[1]}-{args.signal}.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    run = 0 if args.no_trial_log else append_trial(Path(args.trials), args, stats,
                                                   params, pair, out)
    out.write_text(build_html(prices, result, stats, args, split, params, estimated),
                   encoding="utf-8")
    log(f"  wrote {out.resolve()}  ({out.stat().st_size/1024:.1f} KB)")
    if run:
        log(f"  run #{run} logged to {Path(args.trials).resolve()}")
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0 if stats["net_bps"] > 0 else 3


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
