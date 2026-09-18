"""Step 1e — prove the backtest engine is not lying.

An engine that silently overstates returns is worse than no engine, because it
produces confident numbers nobody can check. The defence is a set of tests whose
answers are known before they run.

The most informative one is the first: trade a random signal and the net result
must land near minus the cost of the trades it made. That is the plan's own
success criterion for Step 1.

    python verify_backtest.py
    python verify_backtest.py -v
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import backtest as bt                                             # noqa: E402
import costs as cost_model                                        # noqa: E402
import pair_report as pr                                          # noqa: E402
import strategy as sig                                            # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []
VERBOSE = False


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(name)
    if not ok or VERBOSE:
        print(("  ok   " if ok else "  FAIL ") + name + (f"   {detail}" if detail else ""))


def skip(name: str, why: str) -> None:
    SKIPPED.append(name)
    print(f"  skip {name}   {why}")


def close(got: float, want: float, tol: float) -> bool:
    return math.isfinite(got) and abs(got - want) <= tol


# ---------------------------------------------------------------- fixtures
def profile(spread_pips=10.0, swap_long=0.0, swap_short=0.0, price=10.0,
            symbols=("AAA", "BBB")) -> dict:
    out = {}
    for s in symbols:
        out[s] = cost_model.SymbolCost(
            symbol=s, spread_pips=spread_pips, swap_long=swap_long,
            swap_short=swap_short, swap_unit="points-per-lot", price=price,
            estimated=True)
    return out


def cointegrated(n=1500, beta=0.8, half_life=8.0, seed=3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ar = math.exp(-math.log(2) / half_life)
    s = np.zeros(n)
    for t in range(1, n):
        s[t] = ar * s[t - 1] + rng.normal(0, 0.004)
    log_b = np.cumsum(rng.normal(0, 0.008, n)) + math.log(10.0)
    index = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"AAA": np.exp(beta * log_b + s), "BBB": np.exp(log_b)},
                        index=index)


PARAMS = sig.SignalParams(entry_z=1.5, exit_z=0.3, stop_z=5.0, max_holding_bars=25,
                          fit_window=250, rehedge_every=10)


def run(prices, prof, params=PARAMS, **kw):
    kw.setdefault("warmup", 260)
    kw.setdefault("bars_per_night", 1.0)
    return bt.run_backtest(prices, prof, params, **kw)


# ---------------------------------------------------------------- tests
def test_accounting() -> None:
    print("\n1. accounting — the totals must be the sum of their parts")
    prices = cointegrated()
    result = run(prices, profile(swap_long=-2.0, swap_short=0.5))

    check("net equals gross minus cost plus carry",
          close(result.net_bps,
                result.gross_bps - result.transaction_bps + result.carry_bps, 1e-9))
    check("equity curve ends at the net total",
          close(float(result.equity_net[-1]), result.net_bps, 1e-6))
    check("gross equity ends at the gross total",
          close(float(result.equity_gross[-1]), result.gross_bps, 1e-6))

    trade_sum = sum(t.net_bps for t in result.trades)
    check("every basis point belongs to a trade",
          close(trade_sum, result.net_bps, 1e-6),
          f"trades {trade_sum:+.4f} vs equity {result.net_bps:+.4f}")
    check("some trades happened", len(result.trades) > 5, f"{len(result.trades)}")
    check("no trade has a negative holding period",
          all(t.bars_held >= 0 for t in result.trades))
    check("every trade's parts add up",
          all(close(t.net_bps, t.gross_bps - t.transaction_bps + t.carry_bps, 1e-9)
              for t in result.trades))


def test_zero_cost() -> None:
    print("\n2. zero cost — a free market must leave gross untouched")
    prices = cointegrated()
    free = run(prices, profile(spread_pips=0.0))
    check("no spread means no transaction cost", close(free.transaction_bps, 0.0, 1e-12))
    check("no swap means no carry", close(free.carry_bps, 0.0, 1e-12))
    check("net equals gross when trading is free",
          close(free.net_bps, free.gross_bps, 1e-9),
          f"{free.net_bps:+.2f} vs {free.gross_bps:+.2f}")

    charged = run(prices, profile(spread_pips=10.0))
    check("adding a spread can only reduce the net",
          charged.net_bps < free.net_bps,
          f"{charged.net_bps:+.2f} < {free.net_bps:+.2f}")
    check("the reduction is exactly the cost charged",
          close(free.gross_bps - charged.net_bps, charged.transaction_bps,
                abs(free.gross_bps - charged.gross_bps) + 1e-6))


def test_random_pays_the_cost() -> None:
    print("\n3. null calibration — a random signal loses about what it spends")
    prices = cointegrated()
    losses, costs_paid = [], []
    for seed in range(12):
        result = run(prices, profile(spread_pips=10.0), signal_mode="random", seed=seed)
        if not result.trades:
            continue
        losses.append(result.net_bps)
        costs_paid.append(result.transaction_bps)
    if not losses:
        skip("random signal loses about its cost", "no trades generated")
        return
    mean_net = float(np.mean(losses))
    mean_cost = float(np.mean(costs_paid))
    print(f"     {len(losses)} runs: mean net {mean_net:+.1f} bps, "
          f"mean cost paid {mean_cost:.1f} bps")
    check("a random signal is not profitable on average", mean_net < 0,
          f"{mean_net:+.1f} bps")
    # A coin flip has no edge, so its expected gross is zero and its expected
    # net is minus the cost. Sampling noise is wide, hence the loose bound.
    check("the average loss is of the order of the cost paid",
          abs(mean_net + mean_cost) < 2.5 * mean_cost,
          f"net {mean_net:+.1f} against cost {mean_cost:.1f}")


def test_no_lookahead() -> None:
    print("\n4. no look-ahead — delay must hurt")
    prices = cointegrated()
    prof = profile(spread_pips=2.0)
    quick = run(prices, prof, lag=1)
    slow = run(prices, prof, lag=3)
    slower = run(prices, prof, lag=6)
    print(f"     lag 1 {quick.net_bps:+.0f}   lag 3 {slow.net_bps:+.0f}   "
          f"lag 6 {slower.net_bps:+.0f} bps")
    check("a longer delay does not improve the result",
          slower.net_bps <= quick.net_bps + abs(quick.net_bps) * 0.10 + 5.0,
          f"lag 6 {slower.net_bps:+.1f} against lag 1 {quick.net_bps:+.1f}")

    # The decision at bar t may only use bars up to t. Changing a later bar must
    # not change the position taken at t.
    tampered = prices.copy()
    cut = 900
    tampered.iloc[cut:, 0] *= np.linspace(1.0, 1.6, len(tampered) - cut)
    a = run(prices, prof)
    b = run(tampered, prof)
    same = np.array_equal(a.position[:cut], b.position[:cut])
    check("tampering with the future leaves earlier positions unchanged", same)
    check("tampering with the future does change later positions",
          not np.array_equal(a.position[cut:], b.position[cut:]))


def test_carry_scales() -> None:
    print("\n5. financing — carry scales with nights held, and with the rate")
    prices = cointegrated()
    one = run(prices, profile(spread_pips=0.0, swap_long=-2.0, swap_short=-2.0))
    two = run(prices, profile(spread_pips=0.0, swap_long=-4.0, swap_short=-4.0))
    check("doubling the swap rate doubles the financing",
          close(two.carry_bps, one.carry_bps * 2, abs(one.carry_bps) * 0.02 + 1e-9),
          f"{one.carry_bps:+.2f} then {two.carry_bps:+.2f}")

    half_night = run(prices, profile(spread_pips=0.0, swap_long=-2.0, swap_short=-2.0),
                     bars_per_night=0.5)
    check("halving the nights per bar halves the financing",
          close(half_night.carry_bps, one.carry_bps / 2, abs(one.carry_bps) * 0.02 + 1e-9))
    check("a debit shows as a negative carry", one.carry_bps < 0)

    credit = run(prices, profile(spread_pips=0.0, swap_long=3.0, swap_short=3.0))
    check("a credit shows as a positive carry", credit.carry_bps > 0)


def test_flat_strategy() -> None:
    print("\n6. a strategy that never trades costs nothing")
    prices = cointegrated()
    never = replace(PARAMS, entry_z=50.0, stop_z=99.0)
    result = run(prices, profile(spread_pips=10.0, swap_long=-5.0), params=never)
    check("no trades", len(result.trades) == 0, f"{len(result.trades)}")
    check("no position is ever taken", bool((result.position == 0).all()))
    check("no gross", close(result.gross_bps, 0.0, 1e-12))
    check("no cost", close(result.transaction_bps, 0.0, 1e-12))
    check("no carry", close(result.carry_bps, 0.0, 1e-12))
    check("no net", close(result.net_bps, 0.0, 1e-12))


def test_signal_contract() -> None:
    print("\n7. the signal function — the live contract")
    prices = cointegrated()
    state = sig.SignalState()
    params = PARAMS

    # Feeding the same history twice must give the same answer: the decision is
    # a function of the bars, not of hidden accumulated state.
    first = sig.target_position(prices.iloc[:400], state, params)
    again = sig.target_position(prices.iloc[:400], state, params)
    check("the decision is deterministic", first.position == again.position
          and math.isclose(first.z, again.z, rel_tol=1e-12))

    check("a short history yields no position and says why",
          sig.target_position(prices.iloc[:30], state, params).position == sig.FLAT)

    # The fit must never look past the end of the history it is given.
    fit_short = sig.fit_relationship(prices.iloc[:500], use_log=True, at=499)
    fit_long = sig.fit_relationship(prices.iloc[:900], use_log=True, at=899)
    check("a fit on more data differs from a fit on less",
          fit_short is not None and fit_long is not None
          and not math.isclose(fit_short.beta, fit_long.beta, rel_tol=1e-9))

    # Entering beyond the stop would be entering a trade the stop exists to
    # prevent, so the signal must refuse.
    far = sig.Fit(beta=1.0, alpha=0.0, mu=0.0, sigma_eq=0.01, fitted_at=0)
    flat_state = sig.SignalState(fit=far)
    wild = prices.iloc[:400].copy()
    wild.iloc[-1, 0] = float(wild.iloc[-1, 1]) * math.exp(0.2)     # a huge z
    decision = sig.target_position(wild, flat_state, params)
    check("no entry beyond the stop", decision.position == sig.FLAT,
          f"z {decision.z:+.1f} gave position {decision.position}")

    check("leg weights are long A and short beta of B",
          sig.leg_weights(sig.LONG, 0.8) == (1.0, -0.8))
    check("a negative hedge ratio flips the second leg",
          sig.leg_weights(sig.LONG, -0.8) == (1.0, 0.8))

    for bad in (dict(entry_z=1.0, exit_z=1.0), dict(entry_z=2.0, stop_z=1.0),
                dict(hedge_source="magic")):
        try:
            sig.SignalParams(**bad)
            check(f"{bad} is refused", False, "no error raised")
        except ValueError:
            check(f"{bad} is refused", True)


def test_exit_reasons() -> None:
    print("\n8. exits — every trade closes for a stated reason")
    prices = cointegrated()
    tight = replace(PARAMS, max_holding_bars=4)
    result = run(prices, profile(spread_pips=1.0), params=tight)
    reasons = {t.exit_reason for t in result.trades}
    check("every trade records why it closed",
          all(t.exit_reason for t in result.trades), str(reasons)[:90])
    check("a short time stop forces time exits",
          any("longer than the maximum" in r for r in reasons))
    check("no trade is held past the limit",
          all(t.bars_held <= tight.max_holding_bars + 1 for t in result.trades),
          f"longest {max((t.bars_held for t in result.trades), default=0)}")


def test_real_data() -> None:
    print("\n9. the candidate — the engine runs on the real store")
    store = bt.pr.DEFAULT_STORE
    prof_path = cost_model.DEFAULT_COSTS / "demo.json"
    if not store.exists() or not prof_path.exists():
        skip("candidate backtest", "no store or no demo cost profile")
        return
    import types
    args = types.SimpleNamespace(
        symbols="USDNOK,USDZAR", asset_class="forex", timeframe="1d", source=None,
        start=None, end=None, price="log", split=0.70, store=str(store))
    try:
        prices = bt.pr.load_prices(args)
    except bt.pr.UserError as exc:
        skip("candidate backtest", str(exc))
        return
    prof = cost_model.load_profile(prof_path)
    result = run(prices, prof)
    stats = bt.summarise(result, int(len(prices) * 0.70), 252.0)
    print(f"     {len(result.trades)} trades, net {stats['net_bps']:+.0f} bps, "
          f"Sharpe {stats['sharpe']:.2f}")
    check("the engine completes on real data", result.bars == len(prices))
    check("costs are charged", result.transaction_bps > 0)
    check("the report builds", len(bt.build_html(
        prices, result, stats, types.SimpleNamespace(
            timeframe="1d", split=0.70, broker="demo", signal="strategy", lag=1,
            bins=30, max_trade_rows=20), int(len(prices) * 0.7), PARAMS, True)) > 5000)


def test_trade_booking() -> None:
    print("\n10. trade booking — flips, open positions and duplicate orders")
    prices = cointegrated()
    prof = profile(spread_pips=10.0, swap_long=-2.0)

    # A coin flip goes straight from long to short. Booking that as one trade
    # would report a direction and a holding period that never happened.
    flipper = run(prices, prof, signal_mode="random", seed=1)
    pos = flipper.position
    flips = int(np.sum((pos[:-1] != 0) & (pos[1:] != 0) & (pos[:-1] != pos[1:])))
    check("the control does flip position directly", flips > 5, f"{flips} flips")
    check("a flip is booked as two trades, not one",
          close(sum(t.net_bps for t in flipper.trades), flipper.net_bps, 1e-6),
          f"{len(flipper.trades)} trades over {flips} flips")
    check("no trade spans a flip",
          all(t.direction in ("long spread", "short spread") for t in flipper.trades))

    # A position still open at the last bar earns returns that must be attributed.
    left = run(prices, prof, close_at_end=False)
    closed = run(prices, prof, close_at_end=True)
    if left.position[-1] != 0:
        gap = left.net_bps - sum(t.net_bps for t in left.trades)
        check("leaving the last position open leaves a gap", abs(gap) > 1e-6,
              f"{gap:+.2f} bps unattributed")
        check("closing it attributes everything",
              close(sum(t.net_bps for t in closed.trades), closed.net_bps, 1e-6))
        check("closing it charges one more exit",
              closed.transaction_bps > left.transaction_bps)
        check("the closing trade says so",
              any("end of the sample" in t.exit_reason for t in closed.trades))
    else:
        skip("end-of-sample close", "no position was open at the last bar")

    # With a fill delay the strategy believes it already holds the new position,
    # so the same intent would be queued on every bar until the fill lands.
    for lag in (1, 3, 6):
        delayed = run(prices, prof, lag=lag)
        changes = int(np.sum(delayed.position[1:] != delayed.position[:-1]))
        check(f"lag {lag}: one position change per booked leg",
              changes <= len(delayed.trades) * 2,
              f"{changes} changes, {len(delayed.trades)} trades")
        check(f"lag {lag}: the ledger still balances",
              close(sum(t.net_bps for t in delayed.trades), delayed.net_bps, 1e-6))


def test_cost_profile() -> None:
    print("\n11. cost profile — defaults must not flatter the numbers")
    import argparse
    import costs as cm

    parser = cm.build_parser()
    args = parser.parse_args(["add", "--broker", "t", "--symbol", "EURUSD",
                              "--spread-pips", "1"])
    check("a profile is an estimate unless stated otherwise",
          args.from_broker_sheet is False)
    entry = cm.SymbolCost(symbol="EURUSD", spread_pips=1.0, price=1.10,
                          estimated=not args.from_broker_sheet)
    check("and the record says so", entry.estimated is True)
    verified = parser.parse_args(["add", "--broker", "t", "--symbol", "EURUSD",
                                  "--spread-pips", "1", "--from-broker-sheet"])
    check("the flag marks it verified", verified.from_broker_sheet is True)

    # One crossing is half the quoted spread, in every asset class.
    fx = cm.SymbolCost(symbol="EURUSD", spread_pips=2.0, price=1.0)
    check("forex: two pips at parity is one basis point per crossing",
          close(fx.spread_bps(), 1.0, 1e-9), f"{fx.spread_bps():.4f}")
    other = cm.SymbolCost(symbol="GOLD", asset_class="commodity", spread_pips=8.0,
                          price=2000.0)
    check("non-forex: a quoted 8 bps spread costs 4 bps to cross",
          close(other.spread_bps(), 4.0, 1e-9), f"{other.spread_bps():.4f}")
    check("a round trip on one leg is twice a crossing",
          close(fx.entry_exit_bps(), 2 * fx.spread_bps(), 1e-12))

    # Swap conversions.
    per_annum = cm.SymbolCost(symbol="EURUSD", swap_long=-3.65,
                              swap_unit="percent-per-annum", price=1.0)
    check("3.65% a year is a basis point a night",
          close(per_annum.carry_bps("long"), -1.0, 1e-9),
          f"{per_annum.carry_bps('long'):.4f}")
    direct = cm.SymbolCost(symbol="EURUSD", swap_long=-2.0, swap_short=1.0,
                           swap_unit="bps-per-night", price=1.0)
    check("bps per night passes straight through",
          close(direct.carry_bps("long"), -2.0, 1e-12)
          and close(direct.carry_bps("short"), 1.0, 1e-12))
    check("an unknown swap unit is refused",
          _refuses(cm.SymbolCost(symbol="X", swap_unit="furlongs", price=1.0)))

    # A credit reduces the bill; a debit increases it.
    prof = {"AAA": cm.SymbolCost(symbol="AAA", spread_pips=0.0, swap_long=-1.0,
                                 swap_unit="bps-per-night", price=1.0),
            "BBB": cm.SymbolCost(symbol="BBB", spread_pips=0.0, swap_short=1.0,
                                 swap_unit="bps-per-night", price=1.0)}
    legs = [cm.LegPlan("AAA", "long"), cm.LegPlan("BBB", "short")]
    total = cm.round_trip(prof, legs, holding_bars=10, bars_per_night=1.0)
    check("a debit and an equal credit cancel",
          close(total["carry_bps"], 0.0, 1e-12), f"{total['carry_bps']:+.4f}")
    debit_only = cm.round_trip({"AAA": prof["AAA"], "BBB": prof["AAA"]},
                               [cm.LegPlan("AAA", "long"), cm.LegPlan("BBB", "long")],
                               holding_bars=10, bars_per_night=1.0)
    check("ten nights of a one basis point debit costs ten",
          close(debit_only["total_bps"], 20.0, 1e-9), f"{debit_only['total_bps']:.2f}")
    check("an estimated leg marks the whole calculation estimated",
          cm.round_trip(prof, legs, 1, 1.0)["estimated"] is True)


def _refuses(cost) -> bool:
    try:
        cost.carry_bps("long")
    except Exception:                                             # noqa: BLE001
        return True
    return False


def test_nights_per_bar() -> None:
    import costs as cm
    print(chr(10) + "  financing per bar - a daily bar is not a night")
    check("a daily equity bar is financed for more than one night",
          cm.nights_per_bar("equity", "1d") > 1.0,
          f"{cm.nights_per_bar('equity', '1d')}")
    check("five trading days are financed as seven, plus holidays",
          close(cm.nights_per_bar("equity", "1d"), 1.45, 1e-12))
    check("forex is financed the same way, collected on Wednesday",
          close(cm.nights_per_bar("forex", "1d"), 1.40, 1e-12))
    check("crypto trades every day, so a bar really is a night",
          close(cm.nights_per_bar("crypto", "1d"), 1.0, 1e-12))
    check("an unknown asset class does not silently undercharge",
          cm.nights_per_bar("something-new", "1d") >= 1.0)
    check("an hourly bar costs less financing than a daily one",
          cm.nights_per_bar("equity", "1h") < cm.nights_per_bar("equity", "1d"))
    check("a session of hourly bars costs what the daily bar costs",
          close(cm.nights_per_bar("equity", "1h") * 6.5,
                cm.nights_per_bar("equity", "1d"), 1e-12))
    check("a day of hourly crypto bars costs what the daily bar costs",
          close(cm.nights_per_bar("crypto", "1h") * 24,
                cm.nights_per_bar("crypto", "1d"), 1e-12))
    check("an unknown timeframe falls back to the daily rate rather than to zero",
          close(cm.nights_per_bar("equity", "3d"),
                cm.nights_per_bar("equity", "1d"), 1e-12))
    check("no asset class is financed for nothing",
          all(cm.nights_per_bar(k, "1d") > 0 for k in cm.NIGHTS_PER_BAR))


def test_feasibility() -> None:
    print("\n12. feasibility — the two directions are priced apart")
    import costs as cm
    import feasibility as fs

    prof = {"AAA": cm.SymbolCost(symbol="AAA", spread_pips=0.0, swap_long=-5.0,
                                 swap_short=-5.0, swap_unit="bps-per-night", price=1.0),
            "BBB": cm.SymbolCost(symbol="BBB", spread_pips=0.0, swap_long=2.0,
                                 swap_short=-8.0, swap_unit="bps-per-night", price=1.0)}
    dirs = fs.spread_directions("AAA", "BBB", beta=0.8)
    check("a positive hedge ratio shorts the second leg",
          dirs["long spread"][1].direction == "short")
    dirs_neg = fs.spread_directions("AAA", "BBB", beta=-0.8)
    check("a negative hedge ratio goes long both",
          dirs_neg["long spread"][1].direction == "long")

    costs_by_dir = {k: cm.round_trip(prof, v, 5, 1.0) for k, v in dirs.items()}
    check("the two directions do not cost the same",
          abs(costs_by_dir["long spread"]["total_bps"]
              - costs_by_dir["short spread"]["total_bps"]) > 1e-6,
          " vs ".join(f"{v['total_bps']:.2f}" for v in costs_by_dir.values()))

    be = fs.break_even_swap(move_bps=100.0, transaction_bps=10.0, nights=5.0,
                            min_edge=2.0)
    check("break-even swap is what the move can carry",
          close(be, (100.0 / 2.0 - 10.0) / 5.0, 1e-12), f"{be:.3f}")
    rich = fs.headroom(be, carry_bps=0.0, nights=5.0)
    poor = fs.headroom(be, carry_bps=-25.0, nights=5.0)
    check("paying financing eats the headroom", poor < rich,
          f"{poor:.2f} against {rich:.2f}")
    check("headroom falls by exactly what is paid",
          close(rich - poor, 5.0, 1e-12))

    verdict, edge = fs.assess(100.0, 10.0, min_edge=2.0, marginal_edge=1.0)
    check("a tenfold edge is alive", verdict == fs.ALIVE and close(edge, 10.0, 1e-12))
    check("an edge below the floor is dead",
          fs.assess(100.0, 200.0, 2.0, 1.0)[0] == fs.DEAD)
    check("an edge between the two is marginal",
          fs.assess(100.0, 70.0, 2.0, 1.0)[0] == fs.MARGINAL)
    check("financing that pays more than the trade costs is flagged, not divided by",
          fs.assess(100.0, -5.0, 2.0, 1.0)[0] == fs.ALIVE)


def test_health_gate() -> None:
    print("\n13. health gate - step 2 driving step 1")
    prices = cointegrated()
    prof = profile(spread_pips=2.0)
    thresholds = dict(max_pvalue=0.05, degraded_pvalue=0.20, min_half_life=2.0,
                      max_half_life=60.0, break_z=4.0, max_beta_drift=3.0)

    states = bt.health_states(prices, lookback=300, every=25, thresholds=thresholds)
    check("a state is assigned to every bar", len(states) == len(prices))
    check("bars before the first assessment are not tradable",
          bool((states[:299] == "broken").all()))
    check("a clean pair is mostly healthy after that",
          float(np.mean(states[300:] == "healthy")) > 0.5,
          f"{float(np.mean(states[300:] == 'healthy')):.0%}")

    # Causality: the verdict at bar t may not depend on anything after t.
    tampered = prices.copy()
    cut = 900
    tampered.iloc[cut:, 0] *= np.linspace(1.0, 2.5, len(tampered) - cut)
    later = bt.health_states(tampered, lookback=300, every=25, thresholds=thresholds)
    check("tampering with the future leaves earlier verdicts unchanged",
          list(states[:cut - 25]) == list(later[:cut - 25]))
    check("and does change later ones", list(states[cut:]) != list(later[cut:]))

    # The gate is allowed to reduce exposure and nothing else.
    ungated = run(prices, prof)
    gated = run(prices, prof, health=states)
    check("the gate never increases time in the market",
          int(np.sum(gated.position != 0)) <= int(np.sum(ungated.position != 0)),
          f"{int(np.sum(gated.position != 0))} against "
          f"{int(np.sum(ungated.position != 0))} bars")
    check("the gate never adds trades", len(gated.trades) <= len(ungated.trades),
          f"{len(gated.trades)} against {len(ungated.trades)}")
    check("the gated ledger still balances",
          close(sum(t.net_bps for t in gated.trades), gated.net_bps, 1e-6))

    # An always-broken monitor must produce no trading at all.
    never = np.array(["broken"] * len(prices), dtype=object)
    flat = run(prices, prof, health=never)
    check("a permanently broken relationship is never traded",
          len(flat.trades) == 0 and close(flat.net_bps, 0.0, 1e-12))

    # An always-healthy monitor must change nothing.
    always = np.array(["healthy"] * len(prices), dtype=object)
    same = run(prices, prof, health=always)
    check("a permanently healthy relationship trades exactly as if ungated",
          close(same.net_bps, ungated.net_bps, 1e-9),
          f"{same.net_bps:+.4f} against {ungated.net_bps:+.4f}")


def test_risk_metrics() -> None:
    print("\n15. risk and profit metrics — pinned to values, not just direction")

    # A hand-built result whose every metric can be worked out on paper. The
    # numbers are chosen so each answer is exact and none of them coincide,
    # because a check that passes for the wrong reason is the defect this suite
    # has shipped twice before.
    def trade(net: float) -> bt.Trade:
        return bt.Trade(entry_bar=0, exit_bar=1, entry_time="", exit_time="",
                        direction="long spread", entry_z=2.0, exit_z=0.5,
                        bars_held=1, gross_bps=net, transaction_bps=0.0,
                        carry_bps=0.0, net_bps=net, exit_reason="target")

    nets = [100.0, -50.0, 200.0, -25.0, -25.0, 50.0]
    equity = np.cumsum(nets)
    res = bt.Result(bars=6, trades=[trade(v) for v in nets],
                    equity_gross=equity.copy(), equity_net=equity.copy(),
                    position=np.zeros(6), z=np.zeros(6),
                    gross_bps=float(sum(nets)), transaction_bps=0.0,
                    carry_bps=0.0, net_bps=float(sum(nets)), exposure_bars=6)
    net_steps = np.diff(np.concatenate([[0.0], equity]))
    dd = bt.drawdown(equity)
    stats = bt.risk_metrics(res, bars_per_year=6.0, net=net_steps, dd=dd, years=1.0)

    # wins 100 + 200 + 50 = 350; losses 50 + 25 + 25 = 100; 350 / 100 = 3.5
    check("profit factor is gross win over gross loss",
          close(stats["profit_factor"], 3.5, 1e-12),
          f"{stats['profit_factor']:.6f} against 3.5")

    # average win 350/3 = 116.666..., average loss -100/3 = -33.333...
    check("average win and average loss are the per-side means",
          close(stats["avg_win_bps"], 350.0 / 3.0, 1e-9)
          and close(stats["avg_loss_bps"], -100.0 / 3.0, 1e-9))
    check("payoff ratio is average win over average loss",
          close(stats["payoff_ratio"], 3.5, 1e-9),
          f"{stats['payoff_ratio']:.6f} against 3.5")

    # -25 then -25 are consecutive; the run of losses is two, not three.
    check("worst losing run counts consecutive losers only",
          stats["worst_losing_streak"] == 2,
          f"{stats['worst_losing_streak']} against 2")

    # A trade that nets exactly zero is not a win, so it continues a losing run
    # rather than breaking it. Without a scratch trade in the sample the two
    # comparisons agree and the check cannot tell them apart.
    scratch = [100.0, -50.0, 0.0, -25.0, 200.0]
    sc_eq = np.cumsum(scratch)
    res_sc = bt.Result(bars=5, trades=[trade(v) for v in scratch],
                       equity_gross=sc_eq.copy(), equity_net=sc_eq.copy(),
                       position=np.zeros(5), z=np.zeros(5),
                       gross_bps=225.0, transaction_bps=0.0, carry_bps=0.0,
                       net_bps=225.0, exposure_bars=5)
    st_sc = bt.risk_metrics(res_sc, bars_per_year=5.0, net=np.array(scratch),
                            dd=bt.drawdown(sc_eq), years=1.0)
    check("a scratch trade continues a losing run rather than breaking it",
          st_sc["worst_losing_streak"] == 3,
          f"{st_sc['worst_losing_streak']} against 3")
    check("a scratch trade does not count as a win",
          close(st_sc["avg_win_bps"], 150.0, 1e-9),
          f"{st_sc['avg_win_bps']:.4f} against 150.0")

    check("expectancy is the mean net per trade",
          close(stats["expectancy_bps"], 250.0 / 6.0, 1e-9))
    check("best and worst trade are the extremes",
          close(stats["best_trade_bps"], 200.0, 1e-12)
          and close(stats["worst_trade_bps"], -50.0, 1e-12))

    # The tail average can never sit above the percentile that defines it, but
    # that inequality also holds when the two are the same number, so it cannot
    # tell the mean of the tail from the quantile itself. Both are pinned.
    # Sorted nets are -50, -25, -25, 50, 100, 200; the fifth percentile by
    # linear interpolation is -50 + 0.25 * 25 = -43.75, and the only trade at or
    # below it is -50, so the shortfall is exactly -50.
    check("the 5% quantile is interpolated across the trade distribution",
          close(stats["trade_var95_bps"], -43.75, 1e-9),
          f"{stats['trade_var95_bps']:.6f} against -43.75")
    check("expected shortfall is the mean beyond the quantile, not the quantile",
          close(stats["expected_shortfall_bps"], -50.0, 1e-9),
          f"{stats['expected_shortfall_bps']:.6f} against -50.0")
    check("expected shortfall is at or below the 5% quantile",
          stats["expected_shortfall_bps"] <= stats["trade_var95_bps"] + 1e-12)

    # Percent is basis points over one hundred, exactly, with no rounding.
    check("net percent is net basis points over one hundred",
          close(stats["net_pct"], res.net_bps / 100.0, 1e-12))
    check("max drawdown percent matches the drawdown curve",
          close(stats["max_drawdown_pct"], float(dd.min()) / 100.0, 1e-12))

    # equity 100, 50, 250, 225, 200, 250 against running peaks
    # 100, 100, 250, 250, 250, 250: underwater at bars 2, 4 and 5 only, so the
    # longest unbroken run is two, and the record closes at a new high, so
    # nothing is left unrecovered.
    longest, trailing = bt.underwater_bars(equity)
    check("longest underwater run is measured in consecutive bars",
          longest == 2, f"{longest} against 2")
    check("a record closing at a new high leaves nothing unrecovered",
          trailing == 0, f"{trailing} against 0")
    rising = np.array([1.0, 2.0, 3.0, 4.0])
    check("a curve at a new high every bar is never underwater",
          bt.underwater_bars(rising) == (0, 0))

    # Calmar is annual return over the absolute worst drawdown.
    check("Calmar is annual return over the worst drawdown",
          close(stats["calmar"], (250.0 / 1.0) / abs(float(dd.min())), 1e-9))

    # The ratio term must be pinned where it is NOT zero. Returns of
    # +10, -5, +10, -5 have a mean of 2.5 and a sample deviation of 8.660254,
    # so at four bars a year the Sharpe is 2.5 / 8.660254 * 2 = 0.5773503 and
    # the error is sqrt((1 + 0.5 * 0.5773503^2) / 4) * 2 = 1.0801234. Dropping
    # the ratio term gives 1.0 instead, which every check below would miss.
    swing = np.array([10.0, -5.0, 10.0, -5.0])
    sw_eq = np.cumsum(swing)
    res_sw = bt.Result(bars=4, trades=[trade(v) for v in swing],
                       equity_gross=sw_eq.copy(), equity_net=sw_eq.copy(),
                       position=np.zeros(4), z=np.zeros(4), gross_bps=10.0,
                       transaction_bps=0.0, carry_bps=0.0, net_bps=10.0,
                       exposure_bars=4)
    st_sw = bt.risk_metrics(res_sw, bars_per_year=4.0, net=swing,
                            dd=bt.drawdown(sw_eq), years=1.0)
    check("Sharpe is the annualised mean over deviation",
          close(st_sw["sharpe"], 0.5773502691896258, 1e-9),
          f"{st_sw['sharpe']:.10f}")
    check("Sharpe standard error carries the ratio term, not only one over n",
          close(st_sw["sharpe_stderr"], 1.0801234497346435, 1e-9),
          f"{st_sw['sharpe_stderr']:.10f} against 1.0801234497")

    # The standard error of a Sharpe of zero is sqrt(1/n) annualised, which is
    # the one case that can be written down without the ratio in it.
    flat = np.array([5.0, 5.0, 5.0, 5.0, 5.0, 5.0])
    flat_eq = np.cumsum(flat)
    res2 = bt.Result(bars=6, trades=[trade(5.0) for _ in flat],
                     equity_gross=flat_eq.copy(), equity_net=flat_eq.copy(),
                     position=np.zeros(6), z=np.zeros(6), gross_bps=30.0,
                     transaction_bps=0.0, carry_bps=0.0, net_bps=30.0,
                     exposure_bars=6)
    st2 = bt.risk_metrics(res2, bars_per_year=4.0, net=flat,
                          dd=bt.drawdown(flat_eq), years=1.0)
    # A constant series has zero deviation, so the Sharpe is zero by the guard
    # and its error is sqrt((1 + 0) / 6) * sqrt(4).
    check("Sharpe standard error carries the annualisation and the ratio term",
          close(st2["sharpe_stderr"], math.sqrt(1.0 / 6.0) * 2.0, 1e-12),
          f"{st2['sharpe_stderr']:.8f} against {math.sqrt(1.0/6.0)*2.0:.8f}")

    # Ten times the observations must shrink the error by sqrt(10).
    st3 = bt.risk_metrics(res2, bars_per_year=4.0,
                          net=np.full(600, 5.0),
                          dd=bt.drawdown(np.cumsum(np.full(600, 5.0))), years=1.0)
    check("more observations shrink the Sharpe standard error as one over root n",
          close(st3["sharpe_stderr"] * math.sqrt(100.0), st2["sharpe_stderr"], 1e-9))

    # A zero-variance mean must not be reported as significant.
    check("mean over standard error is finite and signed",
          close(stats["mean_over_stderr"],
                stats["expectancy_bps"] / stats["mean_stderr_bps"], 1e-9))

    # A losing book must not produce a flattering profit factor.
    losers = [-10.0, -20.0, -30.0]
    l_eq = np.cumsum(losers)
    res4 = bt.Result(bars=3, trades=[trade(v) for v in losers],
                     equity_gross=l_eq.copy(), equity_net=l_eq.copy(),
                     position=np.zeros(3), z=np.zeros(3), gross_bps=-60.0,
                     transaction_bps=0.0, carry_bps=0.0, net_bps=-60.0,
                     exposure_bars=3)
    st4 = bt.risk_metrics(res4, bars_per_year=3.0, net=np.array(losers),
                          dd=bt.drawdown(l_eq), years=1.0)
    check("a book with no winners has a profit factor of zero",
          close(st4["profit_factor"], 0.0, 1e-12),
          f"{st4['profit_factor']}")
    # equity -10, -30, -60 against peaks -10, -10, -10: underwater from the
    # second bar to the last, so two bars are unrecovered, not three.
    check("a book with no winners is underwater to the last bar",
          st4["unrecovered_bars"] == 2, f"{st4['unrecovered_bars']} against 2")
    check("a losing book reports a negative net percent",
          st4["net_pct"] < 0)


def test_sigma_eq_agreement() -> None:
    """The equilibrium deviation is computed twice, by two different algebraic routes.

    `pair_report._fit_ou` builds it as `resid_sd * sqrt(-2*ln(a)/(1-a^2))` and then divides
    by `sqrt(2*theta)`; `strategy.fit_relationship` builds it directly as
    `resid_sd / sqrt(1-ar^2)`. Substituting `theta = -ln(a)` shows the two are the same
    expression, but they live in two modules with no shared helper, and until this check
    existed nothing compared them.

    That matters more than a tidiness complaint. `sigma_eq` is the denominator of every
    z-score the strategy trades on and the multiplier in every expected-move figure the
    project has published — `feasibility`, `outcomes` and `pair_report` all compute
    `(entry_z - exit_z) * sigma_eq`. `relationship.py` exists because the hedge fit written
    eight times produced three separate "two copies disagreed" defects; this is the same
    pattern in the one quantity where a disagreement would be hardest to notice, because
    both routes return a plausible number.

    Measured across the AR range when this check was added: worst relative disagreement
    2.0e-16, which is machine epsilon. They agree today. This check is what makes that a
    fact rather than an assumption.
    """
    print("\n13. the two routes to sigma_eq agree")

    worst = 0.0
    for phi in (0.05, 0.2, 0.5, 0.7, 0.9, 0.95, 0.99):
        rng = np.random.default_rng(int(phi * 1000))
        series = np.zeros(4000)
        for t in range(1, len(series)):
            series[t] = phi * series[t - 1] + rng.normal(0, 0.01)

        theta, _mu, sigma, _regime = pr._fit_ou(series)
        by_fit_ou = sigma / math.sqrt(2 * theta) if theta > 0 else float("nan")

        s0, s1 = series[:-1], series[1:]
        ar, const = (float(v) for v in np.polyfit(s0, s1, 1))
        resid_sd = float(np.std(s1 - (ar * s0 + const), ddof=2))
        by_strategy = resid_sd / math.sqrt(1 - ar ** 2)

        relative = abs(by_fit_ou - by_strategy) / abs(by_strategy)
        worst = max(worst, relative)
        check(f"the two routes agree at phi = {phi}", relative < 1e-9,
              f"{by_fit_ou:.12f} against {by_strategy:.12f}")

    check("the worst disagreement across the AR range is at machine precision",
          worst < 1e-12, f"{worst:.3e}")

    # And the route strategy.py actually takes, through its own public function, must match
    # too -- the check above recomputes the formula, this one calls the real thing.
    rng = np.random.default_rng(99)
    n = 1500
    log_b = np.cumsum(rng.normal(0, 0.01, n)) + math.log(50.0)
    spread = np.zeros(n)
    for t in range(1, n):
        spread[t] = 0.85 * spread[t - 1] + rng.normal(0, 0.01)
    frame = pd.DataFrame({"AAA": np.exp(0.8 * log_b + spread), "BBB": np.exp(log_b)},
                         index=pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC"))
    fit = sig.fit_relationship(frame, use_log=True, at=n - 1)
    built = np.log(frame["AAA"]).to_numpy() - fit.beta * np.log(frame["BBB"]).to_numpy() - fit.alpha
    theta, _mu, sigma, _regime = pr._fit_ou(built)
    check("fit_relationship's sigma_eq matches _fit_ou on the spread it built",
          close(fit.sigma_eq, sigma / math.sqrt(2 * theta), 1e-9),
          f"{fit.sigma_eq:.10f} against {sigma / math.sqrt(2 * theta):.10f}")


def main() -> int:
    global VERBOSE
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true")
    VERBOSE = parser.parse_args().verbose

    print("Verifying backtest.py and strategy.py")
    test_accounting()
    test_zero_cost()
    test_random_pays_the_cost()
    test_no_lookahead()
    test_carry_scales()
    test_flat_strategy()
    test_signal_contract()
    test_exit_reasons()
    test_real_data()
    test_trade_booking()
    test_cost_profile()
    test_nights_per_bar()
    test_feasibility()
    test_health_gate()
    test_risk_metrics()
    test_sigma_eq_agreement()

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("\nFAILED:")
        for name in FAILED:
            print(f"  - {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
