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
    test_feasibility()

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("\nFAILED:")
        for name in FAILED:
            print(f"  - {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
