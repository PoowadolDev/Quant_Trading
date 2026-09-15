"""Step 3.5 — prove the Step 3 components are not lying.

The same treatment the other three suites give the rest of the pipeline. The
checks that matter most are the ones with a known answer:

    the OU round trip       simulate a process whose theta, mu and sigma were
                            chosen, and confirm the outcome model recovers the
                            completion rate and payoff that theory predicts. If
                            the prediction fails on a process that really is an
                            OU process, the script is wrong. That is what makes
                            the same script's verdict on real data worth
                            reading.

    the financing inversion a cost profile whose break-even threshold can be
                            worked out on paper, reproduced exactly.

    rank detection          three spreads built from two independent factors.
                            A book of three that contains two bets must be
                            reported as two.

    sizing monotonicity     doubling the estimated variance must at least halve
                            the size, and no input may produce a size that is
                            negative, infinite, or not a number.

    dependency direction    Step 1 and Step 2 must not import Step 3. Step 3
                            builds on them; the reverse would make the
                            verification of either meaningless.

    python verify_signal.py
    python verify_signal.py -v
"""
from __future__ import annotations

import argparse
import ast
import math
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import backtest as bt                                             # noqa: E402
import costs as cost_model                                        # noqa: E402
import hedge as hg                                                # noqa: E402
import outcomes as oc                                             # noqa: E402
import risk as rk                                                 # noqa: E402
import sizing as sz                                               # noqa: E402
import strategy as sig                                            # noqa: E402
import thresholds as th                                           # noqa: E402
import triallog                                                   # noqa: E402

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


def raises(fn, *args, **kwargs) -> bool:
    try:
        fn(*args, **kwargs)
    except Exception:
        return True
    return False


# ---------------------------------------------------------------- fixtures
def ou_pair(n=3000, beta=0.8, half_life=10.0, seed=1, noise=0.004):
    """Two prices whose log spread is an OU process with a chosen half-life."""
    rng = np.random.default_rng(seed)
    ar = math.exp(-math.log(2) / half_life)
    s = np.zeros(n)
    for t in range(1, n):
        s[t] = ar * s[t - 1] + rng.normal(0, noise)
    log_b = np.cumsum(rng.normal(0, 0.01, n)) + math.log(1.2)
    index = pd.date_range("2010-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"AAA": np.exp(beta * log_b + s), "BBB": np.exp(log_b)},
                        index=index)


def random_walks(n=3000, seed=2):
    rng = np.random.default_rng(seed)
    index = pd.date_range("2010-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"AAA": np.exp(np.cumsum(rng.normal(0, 0.01, n))),
                         "BBB": np.exp(np.cumsum(rng.normal(0, 0.01, n)))}, index=index)


def free_profile(*symbols):
    """A cost profile that charges nothing, so gross and net coincide."""
    return {s: cost_model.SymbolCost(symbol=s, asset_class="index", spread_pips=0.0,
                                     commission_bps=0.0, swap_long=0.0,
                                     swap_short=0.0, swap_unit="bps-per-night",
                                     price=100.0) for s in symbols}


def trade(gross=100.0, reason=sig.EXIT_TARGET, held=5, net=None):
    return bt.Trade(entry_bar=0, exit_bar=held, entry_time="2020-01-01",
                    exit_time="2020-01-06", direction="long spread",
                    entry_z=2.0, exit_z=0.5, bars_held=held, gross_bps=gross,
                    transaction_bps=0.0, carry_bps=0.0,
                    net_bps=gross if net is None else net, exit_reason=reason)


# ---------------------------------------------------------------- 1. outcomes
def test_classification():
    print("\n1. outcomes.py - classifying what happened to a trade")
    check("the exit-target reason maps to target",
          oc.categorise(sig.EXIT_TARGET) == oc.TARGET)
    check("the stop reason maps to stop",
          oc.categorise(sig.EXIT_STOP) == oc.STOP)
    check("the holding-limit reason maps to the holding limit",
          oc.categorise(sig.EXIT_TIME) == oc.TIME)
    check("the engine's end-of-sample wording maps to end of sample",
          oc.categorise("exit: end of the sample, closed at the last price")
          == oc.SAMPLE_END)
    check("an unrecognised reason falls into other, not into target",
          oc.categorise("exit: something new") == oc.OTHER)

    trades = [trade(120, sig.EXIT_TARGET), trade(80, sig.EXIT_TARGET),
              trade(-200, sig.EXIT_STOP), trade(-40, sig.EXIT_TIME),
              trade(10, "exit: end of the sample, closed at the last price")]
    m = oc.measure(trades)
    check("every trade is counted once", m.trades == 5, f"{m.trades}")
    check("wins and losses partition the trades", m.wins + m.losses == 5,
          f"{m.wins}+{m.losses}")
    check("the average win is positive and the average loss is negative",
          m.avg_win_bps > 0 > m.avg_loss_bps,
          f"{m.avg_win_bps:+.1f} / {m.avg_loss_bps:+.1f}")
    check("the average win is the mean of the winners only",
          close(m.avg_win_bps, (120 + 80 + 10) / 3, 1e-9), f"{m.avg_win_bps:.3f}")
    check("the average loss is the mean of the losers only",
          close(m.avg_loss_bps, (-200 - 40) / 2, 1e-9), f"{m.avg_loss_bps:.3f}")
    check("the win-to-loss ratio is the ratio of their magnitudes",
          close(m.win_loss_ratio, 70.0 / 120.0, 1e-9), f"{m.win_loss_ratio:.4f}")
    check("the completion rate excludes trades the sample ended",
          close(m.completion_rate, 2 / 4, 1e-12), f"{m.completion_rate:.3f}")
    check("the gross rebuilt from the categories equals the gross of the trades",
          close(m.reconstruct_gross(), sum(t.gross_bps for t in trades), 1e-9),
          f"{m.reconstruct_gross():.3f}")
    check("a trade of exactly zero counts as a loss, not a win",
          oc.measure([trade(0.0)]).losses == 1)
    check("no trades does not raise", oc.measure([]).trades == 0)
    check("the predicted move is the threshold gap times the scale",
          close(oc.predicted_move_bps(2.0, 0.5, 0.01), 150.0, 1e-9))
    check("a zero threshold gap predicts no move",
          close(oc.predicted_move_bps(2.0, 2.0, 0.01), 0.0, 1e-12))


def test_ou_ground_truth():
    print("\n2. outcomes.py - a process whose answer is known in advance")
    half_life, noise, beta = 10.0, 0.004, 0.8
    px = ou_pair(n=3000, beta=beta, half_life=half_life, noise=noise, seed=1)

    ar = math.exp(-math.log(2) / half_life)
    true_sigma = noise / math.sqrt(1 - ar ** 2)

    params = sig.SignalParams(entry_z=2.0, exit_z=0.5, stop_z=6.0,
                              max_holding_bars=200, fit_window=250,
                              rehedge_every=5)
    sigma, hl = oc.traded_sigma(px, params)
    check("the traded scale recovers the simulated sigma",
          close(sigma, true_sigma, 0.30 * true_sigma),
          f"{sigma:.5f} against {true_sigma:.5f}")
    check("the traded half-life recovers the simulated half-life",
          close(hl, half_life, 0.5 * half_life), f"{hl:.2f} against {half_life}")

    profile = free_profile("AAA", "BBB")
    comparison = oc.compare(px, profile, params, static_sigma=sigma,
                            static_half_life=hl, warmup=260,
                            bars_per_night=0.0, lag=1)
    m = comparison.outcomes
    check("a true OU process produces trades at all", m.trades > 20,
          f"{m.trades}")
    check("nearly every trade on a true OU process reaches its exit",
          m.completion_rate > 0.85, f"{m.completion_rate:.2f}")
    check("almost none of them hit the stop",
          m.by_category.get(oc.STOP, 0) <= 0.05 * m.trades,
          f"{m.by_category.get(oc.STOP, 0)} of {m.trades}")
    check("the realised mean is positive when the process really reverts",
          m.avg_gross_bps > 0, f"{m.avg_gross_bps:+.1f}")
    check("the prediction is within 3x of the result on a true OU process",
          math.isfinite(comparison.overstatement)
          and comparison.overstatement <= 3.0,
          f"{comparison.overstatement:.2f}x")
    check("the overstatement is infinite when the realised mean is not positive",
          not math.isfinite(oc.Comparison(
              entry_z=2.0, exit_z=0.5, sigma_static_bps=1.0, sigma_traded_bps=1.0,
              half_life_static=1.0, half_life_traded=1.0,
              predicted_static_bps=1.0, predicted_traded_bps=1.0,
              realised_bps=-1.0, outcomes=oc.measure([])).overstatement))

    walk = random_walks(n=3000, seed=7)
    walk_sigma, _ = oc.traded_sigma(walk, params)
    walk_cmp = oc.compare(walk, profile, params, static_sigma=walk_sigma,
                          static_half_life=float("nan"), warmup=260,
                          bars_per_night=0.0, lag=1)
    check("two random walks do not produce a prediction that holds",
          walk_cmp.overstatement > 3.0 or not math.isfinite(walk_cmp.overstatement),
          f"{walk_cmp.overstatement:.2f}x")

    engine_gross = sum(t.gross_bps for t in
                       bt.run_backtest(px, profile, params, warmup=260,
                                       bars_per_night=0.0, lag=1).trades)
    check("the outcome breakdown reconstructs the engine's own gross exactly",
          close(m.reconstruct_gross(), engine_gross, 1e-6),
          f"{m.reconstruct_gross():.4f} against {engine_gross:.4f}")


# ---------------------------------------------------------------- 3. thresholds
def test_financing_inversion():
    print("\n3. thresholds.py - the arithmetic, against numbers worked by hand")
    # move = (z - 0.5) * 100 bps must equal 2 * (10 + 1 * 20) = 60, so z = 1.1
    z = th.break_even_z(exit_z=0.5, transaction_bps=10.0,
                        carry_per_night_bps=1.0, nights=20.0,
                        sigma_bps=100.0, min_edge=2.0)
    check("the break-even threshold matches the hand calculation",
          close(z, 1.1, 1e-12), f"{z:.6f}")
    check("with no financing the threshold falls to the transaction term",
          close(th.break_even_z(0.5, 10.0, 0.0, 20.0, 100.0, 2.0), 0.7, 1e-12))
    check("financing received lowers the threshold rather than raising it",
          th.break_even_z(0.5, 10.0, -1.0, 20.0, 100.0, 2.0) < 0.7)
    check("a longer hold raises the threshold",
          th.break_even_z(0.5, 10.0, 1.0, 40.0, 100.0, 2.0) > z)
    check("demanding more edge raises the threshold",
          th.break_even_z(0.5, 10.0, 1.0, 20.0, 100.0, 3.0) > z)
    check("a spread with no scale has no reachable threshold",
          not math.isfinite(th.break_even_z(0.5, 10.0, 1.0, 20.0, 0.0, 2.0)))

    # (2.0 - 0.5) * 100 / 2 - 10 = 65 bps of financing at 1 bps a night
    nights = th.affordable_nights(2.0, 0.5, 100.0, 10.0, 1.0, 2.0)
    check("the affordable hold matches the hand calculation",
          close(nights, 65.0, 1e-12), f"{nights:.6f}")
    check("financing received puts no limit on the hold",
          not math.isfinite(th.affordable_nights(2.0, 0.5, 100.0, 10.0, -1.0, 2.0)))
    check("a move that cannot cover the transaction affords no nights at all",
          close(th.affordable_nights(0.6, 0.5, 100.0, 10.0, 1.0, 2.0), 0.0, 1e-12))
    check("the two functions invert each other",
          close(th.break_even_z(0.5, 10.0, 1.0, nights, 100.0, 2.0), 2.0, 1e-9),
          f"{th.break_even_z(0.5, 10.0, 1.0, nights, 100.0, 2.0):.6f}")

    z_series = np.concatenate([np.linspace(-3, 3, 500), np.full(10, np.nan)])
    region = th.build_region("A~B", "long spread", sigma_bps=100.0, half_life=20.0,
                             transaction_bps=10.0, carry_per_night_bps=1.0,
                             exit_z=0.5, stop_z=4.0, min_edge=2.0,
                             bars_per_night=1.0, z_series=z_series)
    check("the region ignores bars with no fit",
          math.isfinite(region.reached_share))
    check("the region's floor is the break-even threshold",
          close(region.entry_z_min, 1.1, 1e-12), f"{region.entry_z_min:.4f}")
    check("the deviation on offer is a quantile, not the record extreme",
          region.entry_z_available < 3.0, f"{region.entry_z_available:.2f}")
    check("the affordable hold is not simply the half-life again",
          not close(region.max_holding_bars, region.half_life_bars, 1e-6),
          f"{region.max_holding_bars:.1f} against {region.half_life_bars:.1f}")
    check("a region whose floor is above the stop is empty",
          th.build_region("A~B", "long spread", 1.0, 20.0, 10.0, 1.0,
                          exit_z=0.5, stop_z=4.0, min_edge=2.0,
                          bars_per_night=1.0, z_series=z_series).empty)
    check("the recommended hold never exceeds twice the half-life",
          region.recommended_holding_bars() <= 2 * region.half_life_bars + 1,
          f"{region.recommended_holding_bars()}")
    check("the recommended hold is at least one bar",
          th.build_region("A~B", "long", 1e-9, 0.0, 10.0, 1.0, exit_z=0.5,
                          stop_z=4.0, min_edge=2.0, bars_per_night=1.0,
                          z_series=z_series).recommended_holding_bars() >= 1)
    check("financing received is named rather than printed as a negative cost",
          th.build_region("A~B", "long", 100.0, 20.0, 10.0, -1.0, exit_z=0.5,
                          stop_z=4.0, min_edge=2.0, bars_per_night=1.0,
                          z_series=z_series).carry_night_display() == "credit")
    check("a finer bar is what a too-slow spread needs",
          th.build_region("A~B", "long", 100.0, 400.0, 10.0, 1.0, exit_z=0.5,
                          stop_z=4.0, min_edge=2.0, bars_per_night=1.0,
                          z_series=z_series).bar_size_needed() < 1.0)


def test_measured_floor():
    print("\n3b. thresholds.py - the floor read off trades rather than off a model")
    check("the cost of a trade is its round trip plus the nights it was held",
          close(th.cost_per_trade(10.0, 2.0, 5.0, 1.0), 20.0, 1e-12))
    check("a shorter hold costs less",
          th.cost_per_trade(10.0, 2.0, 2.0, 1.0)
          < th.cost_per_trade(10.0, 2.0, 5.0, 1.0))
    check("a finer bar charges less financing for the same number of bars",
          close(th.cost_per_trade(10.0, 2.0, 7.0, 1 / 7), 12.0, 1e-9))
    check("a negative holding time is treated as none",
          close(th.cost_per_trade(10.0, 2.0, -5.0, 1.0), 10.0, 1e-12))

    check("earning twice the cost clears at an edge of two",
          th.clears(20.0, 10.0, 2.0))
    check("earning just under twice the cost does not",
          not th.clears(19.9, 10.0, 2.0))
    check("a loss never clears", not th.clears(-50.0, 10.0, 2.0))
    check("a free trade clears on any profit", th.clears(0.1, 0.0, 2.0))
    check("a free trade does not clear on a loss", not th.clears(-0.1, 0.0, 2.0))
    check("an unmeasurable result does not clear",
          not th.clears(float("nan"), 10.0, 2.0))

    rows = [
        # A handful of trades with a flattering mean, at the lowest threshold on
        # the grid. Without a minimum trade count this would set the floor, and
        # a floor set by five trades is a floor set by luck.
        th.Measured(entry_z=0.5, trades=5, completion_rate=0.80, bars_held=9.0,
                    realised_bps=400.0, predicted_bps=0.0, cost_bps=10.0,
                    min_edge=2.0),
        th.Measured(entry_z=1.0, trades=250, completion_rate=0.45, bars_held=14.0,
                    realised_bps=18.0, predicted_bps=135.0, cost_bps=12.0,
                    min_edge=2.0),                       # too thin an edge
        th.Measured(entry_z=1.5, trades=134, completion_rate=0.31, bars_held=16.0,
                    realised_bps=44.0, predicted_bps=269.0, cost_bps=13.6,
                    min_edge=2.0),                       # clears
        th.Measured(entry_z=2.0, trades=75, completion_rate=0.27, bars_held=16.0,
                    realised_bps=99.0, predicted_bps=404.0, cost_bps=13.6,
                    min_edge=2.0),                       # clears by more
    ]
    check("a threshold that earns too little for its cost does not clear",
          not rows[1].clears)
    check("a threshold that covers its cost twice over clears", rows[2].clears)
    check("the edge is the ratio of what was earned to what was paid",
          close(rows[3].edge, 99.0 / 13.6, 1e-9), f"{rows[3].edge:.3f}")
    check("the floor is the lowest threshold that pays, not the best one",
          close(th.measured_floor(rows, min_trades=20), 1.5, 1e-12),
          f"{th.measured_floor(rows, 20)}")
    check("a thin threshold clears on its own numbers", rows[0].clears)
    check("but too few trades cannot set the floor",
          close(th.measured_floor(rows, min_trades=20), 1.5, 1e-12),
          f"{th.measured_floor(rows, 20)}")
    check("raising the minimum trade count can only raise the floor",
          th.measured_floor(rows, min_trades=100)
          >= th.measured_floor(rows, min_trades=20))
    check("unsorted rows give the same floor",
          close(th.measured_floor(list(reversed(rows)), 20), 1.5, 1e-12))
    check("no threshold that pays means no floor",
          not math.isfinite(th.measured_floor([rows[1]], min_trades=20)))
    check("an empty grid means no floor",
          not math.isfinite(th.measured_floor([], min_trades=20)))

    px = ou_pair(n=2000, half_life=10.0, seed=3)
    profile = free_profile("AAA", "BBB")
    base = sig.SignalParams(entry_z=2.0, exit_z=0.5, stop_z=6.0,
                            max_holding_bars=200, fit_window=250,
                            rehedge_every=5)
    sigma, _ = oc.traded_sigma(px, base)
    grid = th.measure_grid(px, profile, base, [1.5, 2.0, 8.0],
                           transaction_bps=5.0, carry_per_night_bps=0.5,
                           bars_per_night=1.0, min_edge=2.0, warmup=260,
                           lag=1, static_sigma=sigma)
    check("a threshold above the stop is dropped rather than crashing",
          len(grid) == 2, f"{len(grid)} rows")
    check("the sweep reports the holding time it observed",
          all(math.isfinite(r.bars_held) for r in grid))
    check("a real OU process clears its costs somewhere on the grid",
          any(r.clears for r in grid),
          ", ".join(f"{r.entry_z}:{r.edge:.1f}" for r in grid))
    check("a higher threshold places fewer trades",
          grid[0].trades >= grid[1].trades,
          f"{grid[0].trades} then {grid[1].trades}")


def test_thresholds_match_the_engine():
    print("\n4. thresholds.py - charging what the engine charges")
    profile = {s: cost_model.SymbolCost(symbol=s, asset_class="index",
                                        spread_pips=2.0, commission_bps=0.5,
                                        swap_long=-6.0, swap_short=-0.5,
                                        swap_unit="percent-per-annum", price=50.0)
               for s in ("AAA", "BBB")}
    beta = 0.6
    long_carry = bt.carry_per_night_bps(profile, "AAA", "BBB", 1, beta)
    short_carry = bt.carry_per_night_bps(profile, "AAA", "BBB", -1, beta)
    check("financing is a debit in both directions for this profile",
          long_carry < 0 and short_carry < 0,
          f"{long_carry:.4f} / {short_carry:.4f}")
    check("the two directions do not finance identically when the legs differ",
          not close(long_carry, short_carry, 1e-9),
          f"{long_carry:.4f} against {short_carry:.4f}")
    check("being long the leg that pays more costs more",
          long_carry < short_carry, f"{long_carry:.4f} < {short_carry:.4f}")

    # A debit is negative, so the cheaper direction is the LARGER signed value.
    # Taking the minimum picks the most expensive leg, which silently makes every
    # threshold look unaffordable. That bug shipped once.
    cheaper = bt.cheaper_direction(profile, "AAA", "BBB", beta)
    check("the cheaper direction to finance is the one that pays less",
          bt.carry_per_night_bps(profile, "AAA", "BBB", cheaper, beta)
          > bt.carry_per_night_bps(profile, "AAA", "BBB", -cheaper, beta),
          f"position {cheaper:+d}")
    check("the cheaper direction gives the lower break-even threshold",
          th.break_even_z(0.5, 5.0,
                          -bt.carry_per_night_bps(profile, "AAA", "BBB", cheaper, beta),
                          20.0, 100.0, 2.0)
          < th.break_even_z(0.5, 5.0,
                            -bt.carry_per_night_bps(profile, "AAA", "BBB",
                                                    -cheaper, beta),
                            20.0, 100.0, 2.0))
    check("a debit is signed negative, so financing reduces the equity line",
          bt.carry_per_night_bps(profile, "AAA", "BBB", cheaper, beta) < 0)
    check("the direction is picked by the same function everywhere",
          bt.cheaper_direction(profile, "AAA", "BBB", beta) == cheaper)
    flipped = {k: cost_model.SymbolCost(symbol=k, asset_class="index",
                                        spread_pips=2.0, commission_bps=0.5,
                                        swap_long=(-0.5 if k == "AAA" else -6.0),
                                        swap_short=(-6.0 if k == "AAA" else -0.5),
                                        swap_unit="percent-per-annum", price=50.0)
               for k in ("AAA", "BBB")}
    check("swapping which leg is expensive swaps the chosen direction",
          bt.cheaper_direction(flipped, "AAA", "BBB", beta) == -cheaper,
          f"{bt.cheaper_direction(flipped, 'AAA', 'BBB', beta):+d} against "
          f"{cheaper:+d}")
    check("a profile that finances both legs alike still picks one",
          bt.cheaper_direction(free_profile("AAA", "BBB"), "AAA", "BBB", beta)
          in (1, -1))

    rt = bt.round_trip_bps(profile, "AAA", "BBB", 1, beta)
    check("the round trip is the cost of getting in and out", rt > 0, f"{rt:.3f}")
    check("the round trip is twice the cost of one crossing",
          close(rt, 2 * bt._turn_cost(profile, "AAA", "BBB", 0, 1, beta, beta),
                1e-9))
    check("a bigger hedge ratio does not make the round trip cheaper",
          bt.round_trip_bps(profile, "AAA", "BBB", 1, 1.2) >= rt)


# ---------------------------------------------------------------- 5. risk
def test_book_structure():
    print("\n5. risk.py - how many bets a book contains")
    rng = np.random.default_rng(11)
    n = 800
    index = pd.date_range("2015-01-01", periods=n, freq="D", tz="UTC")
    f1 = pd.Series(rng.normal(0, 1, n), index=index)
    f2 = pd.Series(rng.normal(0, 1, n), index=index)

    def rel(name, series, beta=0.8):
        a, b = name.split("~")
        return rk.Relationship(a=a, b=b, asset_class="index", beta=beta,
                               spread_returns=series)

    three_from_two = [rel("AAA~BBB", f1), rel("CCC~DDD", f2),
                      rel("EEE~FFF", f1 + f2)]
    corr = rk.correlation_matrix(three_from_two)
    bets = rk.effective_bets(corr)
    check("three spreads built from two factors are not three bets",
          bets < 2.9, f"{bets:.3f}")
    check("they are not one bet either", bets > 1.5, f"{bets:.3f}")

    independent = [rel("AAA~BBB", f1), rel("CCC~DDD", f2)]
    check("two independent spreads are two bets",
          close(rk.effective_bets(rk.correlation_matrix(independent)), 2.0, 0.25),
          f"{rk.effective_bets(rk.correlation_matrix(independent)):.3f}")
    identical = [rel("AAA~BBB", f1), rel("CCC~DDD", f1 * 2.0)]
    check("the same spread held twice is one bet",
          close(rk.effective_bets(rk.correlation_matrix(identical)), 1.0, 0.05),
          f"{rk.effective_bets(rk.correlation_matrix(identical)):.4f}")
    check("the identity matrix gives exactly as many bets as positions",
          close(rk.effective_bets(pd.DataFrame(np.eye(5))), 5.0, 1e-9))

    check("a shared leg is found",
          rk.shared_legs([rel("AAA~BBB", f1), rel("AAA~CCC", f2)]) != [])
    check("the shared instrument is named",
          rk.shared_legs([rel("AAA~BBB", f1), rel("AAA~CCC", f2)])[0][2] == ["AAA"])
    check("unrelated relationships share nothing",
          rk.shared_legs([rel("AAA~BBB", f1), rel("CCC~DDD", f2)]) == [])
    check("a leg shared in the second position is found too",
          rk.shared_legs([rel("AAA~BBB", f1), rel("CCC~BBB", f2)]) != [])

    worst = rk.worst_correlation(rk.correlation_matrix(three_from_two))
    check("the most correlated pair is reported by magnitude",
          abs(worst[2]) >= abs(rk.correlation_matrix(three_from_two)
                               .to_numpy()[np.triu_indices(3, 1)]).max() - 1e-12,
          f"{worst[2]:+.3f}")

    check("a negative hedge ratio is fully net exposed",
          close(rk.Relationship("A", "B", "index", -0.5,
                                f1).net_exposure(), 1.0, 1e-12))
    check("a hedge ratio of one is perfectly neutral",
          close(rk.Relationship("A", "B", "index", 1.0, f1).net_exposure(),
                0.0, 1e-12))
    check("a hedge ratio of 0.165 leaves the position mostly directional",
          close(rk.Relationship("A", "B", "index", 0.165, f1).net_exposure(),
                0.835 / 1.165, 1e-12))
    check("the risk layer and the hedge gate agree on neutrality",
          close(rk.Relationship("A", "B", "index", 0.4, f1).net_exposure(),
                hg.net_exposure(0.4), 1e-15))

    check("the bet share is bets over positions",
          close(rk.bet_share(corr), rk.effective_bets(corr) / 3.0, 1e-12),
          f"{rk.bet_share(corr):.4f}")
    check("a perfectly uncorrelated book is entirely distinct bets",
          close(rk.bet_share(pd.DataFrame(np.eye(4))), 1.0, 1e-12))
    check("the same spread held twice is half distinct",
          close(rk.bet_share(rk.correlation_matrix(identical)), 0.5, 0.03),
          f"{rk.bet_share(rk.correlation_matrix(identical)):.4f}")
    check("the bet share does not tighten as the book grows",
          close(rk.bet_share(pd.DataFrame(np.eye(2))),
                rk.bet_share(pd.DataFrame(np.eye(9))), 1e-12))

    verdict = rk.check_caps(three_from_two, corr, max_net=0.35, max_book_net=0.35,
                            max_correlation=0.99, min_effective_bets=3.0)
    check("a book with too few independent bets is refused", not verdict.ok)
    check("the refusal says which cap was breached",
          any("independent bets" in b for b in verdict.breaches))
    concentrated = rk.check_caps(three_from_two, corr, max_net=0.35,
                                 max_book_net=0.35, max_correlation=0.99,
                                 min_effective_bets=0.5, min_bet_share=0.95)
    check("a book that is mostly one bet is refused on its share",
          not concentrated.ok
          and any("distinct bets" in b for b in concentrated.breaches))
    check("the share test is silent when it is not asked for",
          rk.check_caps(three_from_two, corr, max_net=0.35, max_book_net=0.35,
                        max_correlation=0.99, min_effective_bets=0.5).ok)

    ok_verdict = rk.check_caps(independent,
                               rk.correlation_matrix(independent),
                               max_net=0.35, max_book_net=0.35,
                               max_correlation=0.99, min_effective_bets=1.5,
                               min_bet_share=0.6)
    check("a book that passes every cap is accepted", ok_verdict.ok,
          "; ".join(ok_verdict.breaches))
    directional = rk.check_caps([rel("AAA~BBB", f1, beta=-0.5)],
                                pd.DataFrame(np.eye(1), columns=["AAA~BBB"],
                                             index=["AAA~BBB"]),
                                max_net=0.35, max_book_net=1.01,
                                max_correlation=0.99, min_effective_bets=0.5)
    check("a directional relationship is refused on net exposure",
          not directional.ok and any("net exposed" in b
                                     for b in directional.breaches))


def test_kill_switch():
    print("\n6. risk.py - the drawdown kill switch")
    # Two separate breaches of equal depth, so "first" and "last" are different
    # answers. A curve with only one breach cannot tell them apart, and a test
    # that cannot tell them apart is not testing the thing it names.
    equity = np.array([0.0, 100.0, -100.0, 50.0, 300.0, 100.0, 250.0])
    bar, depth = rk.drawdown_breach(equity, 150.0)
    check("the first breach is found, not a later one", bar == 2, f"bar {bar}")
    check("a later breach of the same depth does not displace it",
          rk.drawdown_breach(equity, 150.0)[0]
          < int(np.flatnonzero(equity - np.maximum.accumulate(equity) <= -150.0)[-1]),
          f"bar {bar}")
    check("the depth at the breach is reported", close(depth, -200.0, 1e-9),
          f"{depth:.1f}")
    check("a limit that is never reached returns no bar",
          rk.drawdown_breach(equity, 1000.0)[0] == -1)
    check("the worst drawdown is reported when nothing breached",
          close(rk.drawdown_breach(equity, 1000.0)[1], -200.0, 1e-9))
    check("a rising curve never breaches",
          rk.drawdown_breach(np.array([0.0, 1.0, 2.0, 3.0]), 0.5)[0] == -1)
    check("a shallower limit breaches no later",
          rk.drawdown_breach(equity, 60.0)[0] <= bar)
    check("an empty curve does not raise",
          rk.drawdown_breach(np.array([]), 100.0)[0] == -1)
    check("a limit of zero is refused", raises(rk.drawdown_breach, equity, 0.0))
    check("a negative limit is refused", raises(rk.drawdown_breach, equity, -5.0))


def test_book_inputs():
    print("\n7. risk.py - what the book refuses")
    check("a relationship without an asset class is refused",
          raises(rk.parse_book, "AAA~BBB,CCC~DDD:index", "1d"))
    check("a relationship without a tilde is refused",
          raises(rk.parse_book, "AAABBB:index,CCC~DDD:index", "1d"))
    check("a relationship against itself is refused",
          raises(rk.parse_book, "AAA~AAA:index,CCC~DDD:index", "1d"))
    check("a missing leg is refused",
          raises(rk.parse_book, "AAA~:index,CCC~DDD:index", "1d"))
    check("a book of one is refused", raises(rk.parse_book, "AAA~BBB:index", "1d"))
    check("the same relationship twice is refused",
          raises(rk.parse_book, "AAA~BBB:index,AAA~BBB:index", "1d"))
    check("an entry with too many colons is refused",
          raises(rk.parse_book, "AAA~BBB:index:etf:extra,CCC~DDD:index", "1d"))
    with_broker = rk.parse_book("AAA~BBB:index:etf,CCC~DDD:equity:equity", "1d")
    check("a broker may be named on an entry", len(with_broker) == 2)
    check("the broker is carried through",
          with_broker[0][4] == "etf" and with_broker[1][4] == "equity")
    check("an entry without a broker still parses, with none",
          rk.parse_book("AAA~BBB:index,CCC~DDD:equity", "1d")[0][4] == "")

    parsed = rk.parse_book(" AAA~bbb:index , CCC~DDD:equity ", "1d")
    check("two valid relationships parse", len(parsed) == 2)
    check("symbols are upper-cased", parsed[0][0] == "AAA" and parsed[0][1] == "BBB")
    check("the asset class is carried per relationship",
          parsed[0][2] == "index" and parsed[1][2] == "equity")


# ---------------------------------------------------------------- 8. sizing
def test_book_equity():
    print(chr(10) + "7b. risk.py - the kill switch needs an equity curve to fire on")
    index = pd.date_range("2020-01-01", periods=5, freq="D", tz="UTC")
    rng = np.random.default_rng(1)
    series = pd.Series(rng.normal(0, 1, 5), index=index)

    def rel(name, equity):
        a, b = name.split("~")
        return rk.Relationship(a=a, b=b, asset_class="index", beta=0.8,
                               spread_returns=series, broker="etf" if equity is not None else "",
                               equity_net=equity)

    flat = pd.Series([0.0, 10.0, 20.0, 30.0, 40.0], index=index)
    down = pd.Series([0.0, -10.0, -20.0, -30.0, -40.0], index=index)
    check("a book with no equity curves has none to check",
          rk.book_equity([rel("A~B", None), rel("C~D", None)]) is None)
    check("a book with one curve missing has none either",
          rk.book_equity([rel("A~B", flat), rel("C~D", None)]) is None)
    combined = rk.book_equity([rel("A~B", flat), rel("C~D", down)])
    check("two curves combine equally weighted",
          combined is not None and close(float(combined.iloc[-1]), 0.0, 1e-12),
          "" if combined is None else f"{combined.iloc[-1]:.3f}")
    check("the combined curve keeps the shared index",
          combined is not None and len(combined) == 5)
    only_down = rk.book_equity([rel("A~B", down), rel("C~D", down)])
    bar, depth = rk.drawdown_breach(only_down.to_numpy(float), 25.0)
    check("the kill switch fires on a book that only falls", bar == 3, f"bar {bar}")


def test_inputs_refused():
    print(chr(10) + "7c. the numbers the command line refuses")
    import subprocess, sys as _sys
    base = [_sys.executable]
    cases = [
        ("sizing.py", ["-s", "XLP,XLB", "-a", "index", "--broker", "etf",
                       "--confidence", "-3", "--no-log", "-q"],
         "a negative confidence would size up on the weakest evidence"),
        ("sizing.py", ["-s", "XLP,XLB", "-a", "index", "--broker", "etf",
                       "--equity", "-1000", "--no-log", "-q"],
         "a negative account is refused"),
        ("sizing.py", ["-s", "XLP,XLB", "-a", "index", "--broker", "etf",
                       "--max-leverage", "-5", "--no-log", "-q"],
         "a negative leverage cap is refused"),
        ("thresholds.py", ["-s", "XLP,XLB", "-a", "index", "--broker", "etf",
                           "--min-edge", "-2", "--no-log", "-q"],
         "an edge requirement below zero is refused"),
        ("thresholds.py", ["-s", "XLP,XLB", "-a", "index", "--broker", "etf",
                           "--min-reached", "9", "--no-log", "-q"],
         "a share of bars above one is refused"),
        ("thresholds.py", ["-s", "XLP,XLB", "-a", "index", "--broker", "etf",
                           "--entry-grid", "x,y", "--no-log", "-q"],
         "a grid that is not numbers is refused"),
        # A flag that is declared and then ignored is worse than no flag: the
        # caller believes a different cost profile was used. `--costs-dir` read
        # the default location for a while and nothing said so.
        ("risk.py", ["--book", "XLP~XLB:index:etf,SPY~DIA:index:etf",
                     "--costs-dir", "no-such-directory", "--no-log", "-q"],
         "risk.py actually reads --costs-dir"),
    ]
    for script, argv, what in cases:
        proc = subprocess.run(base + [str(HERE / script)] + argv,
                              capture_output=True, text=True, cwd=str(HERE))
        check(what, proc.returncode == 2,
              f"exit {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:70]}")


def test_sizing():
    print("\n8. sizing.py - how much, and why not more")
    check("growth at zero leverage is zero",
          close(sz.growth_rate(0.0, 0.01, 0.1), 0.0, 1e-15))
    check("growth matches the hand calculation",
          close(sz.growth_rate(2.0, 0.01, 0.1), 2 * 0.01 - 0.5 * 4 * 0.01, 1e-15))
    check("the growth-optimal leverage is the mean over the variance",
          close(sz.growth_optimal_leverage(0.01, 0.1), 1.0, 1e-12))
    star = sz.growth_optimal_leverage(0.02, 0.1)
    check("growth is maximised at the growth-optimal leverage",
          all(sz.growth_rate(star, 0.02, 0.1) >= sz.growth_rate(f, 0.02, 0.1)
              for f in np.linspace(-5, 10, 301)), f"{star:.3f}")
    check("a negative mean gives a negative optimum rather than a hidden zero",
          sz.growth_optimal_leverage(-0.01, 0.1) < 0)
    check("no scale means no optimum",
          not math.isfinite(sz.growth_optimal_leverage(0.01, 0.0)))

    check("the lower bound is the mean less k standard errors",
          close(sz.lower_bound_mean(10.0, 20.0, 100, 1.0), 8.0, 1e-12))
    check("more evidence tightens the bound",
          sz.lower_bound_mean(10.0, 20.0, 400, 1.0)
          > sz.lower_bound_mean(10.0, 20.0, 100, 1.0))
    check("demanding more confidence lowers the bound",
          sz.lower_bound_mean(10.0, 20.0, 100, 2.0)
          < sz.lower_bound_mean(10.0, 20.0, 100, 1.0))
    check("zero confidence is the point estimate itself",
          close(sz.lower_bound_mean(10.0, 20.0, 100, 0.0), 10.0, 1e-15))

    rng = np.random.default_rng(5)
    base = list(rng.normal(30.0, 100.0, 400))
    a = sz.size_from_trades("A~B", base, confidence=1.0, max_leverage=100.0,
                            equity=1000.0)
    doubled = sz.size_from_trades("A~B", [x * 2 for x in base], confidence=0.0,
                                  max_leverage=100.0, equity=1000.0)
    point = sz.size_from_trades("A~B", base, confidence=0.0, max_leverage=100.0,
                                equity=1000.0)
    check("doubling the deviation at least halves the size",
          doubled.capped_leverage <= 0.5 * point.capped_leverage + 1e-12,
          f"{doubled.capped_leverage:.4f} against {point.capped_leverage:.4f}")
    check("the uncertainty haircut never increases the size",
          a.capped_leverage <= point.capped_leverage + 1e-12)
    check("the size is never negative", a.capped_leverage >= 0.0)
    check("the size is always a finite number",
          math.isfinite(a.capped_leverage))
    check("the cap is applied",
          sz.size_from_trades("A~B", base, confidence=0.0, max_leverage=0.25,
                              equity=1000.0).capped_leverage <= 0.25 + 1e-12)
    check("notional is leverage against equity",
          close(a.notional, a.capped_leverage * 1000.0, 1e-9))

    losing = sz.size_from_trades("A~B", list(rng.normal(-20.0, 100.0, 400)),
                                 confidence=1.0, max_leverage=100.0,
                                 equity=1000.0)
    check("a losing strategy is sized at zero", losing.capped_leverage == 0.0)
    check("a losing strategy is not justified", not losing.justified)
    check("the reason names the negative mean",
          "not positive" in losing.reason(), losing.reason())

    thin = sz.size_from_trades("A~B", list(rng.normal(30.0, 100.0, 6)),
                               confidence=1.0, max_leverage=100.0, equity=1000.0)
    check("a thin sample is sized more cautiously than a thick one",
          thin.capped_leverage <= a.capped_leverage + 1e-12,
          f"{thin.capped_leverage:.4f} against {a.capped_leverage:.4f}")
    check("the reason explains an unproven mean when the bound crosses zero",
          thin.capped_leverage > 0 or "do not establish" in thin.reason()
          or "not positive" in thin.reason(), thin.reason())

    check("one trade is not enough to size on",
          raises(sz.size_from_trades, "A~B", [10.0], confidence=1.0,
                 max_leverage=1.0, equity=1000.0))
    check("no trades is not enough either",
          raises(sz.size_from_trades, "A~B", [], confidence=1.0,
                 max_leverage=1.0, equity=1000.0))
    check("trades that are not numbers are dropped rather than poisoning the mean",
          raises(sz.size_from_trades, "A~B", [float("nan"), float("nan")],
                 confidence=1.0, max_leverage=1.0, equity=1000.0))


# ---------------------------------------------------------------- 9. the log
def test_trial_log(tmp: Path):
    print("\n9. triallog.py - a log that cannot quietly change meaning")
    path = tmp / "verify-log.csv"
    if path.exists():
        path.unlink()
    first = {"run": 0, "pair": "A~B", "value": 1}
    check("the first row is run one", triallog.append(path, first) == 1)
    check("the second row is run two",
          triallog.append(path, {"run": 0, "pair": "A~B", "value": 2}) == 2)
    check("the caller's dictionary is not modified", first["run"] == 0)
    check("a changed set of columns is refused",
          raises(triallog.append, path, {"run": 0, "pair": "A~B", "value": 3,
                                         "extra": 4}))
    check("the refusal names what changed",
          "extra" in _message(triallog.append, path,
                              {"run": 0, "pair": "A~B", "value": 3, "extra": 4}))
    check("a dropped column is refused too",
          raises(triallog.append, path, {"run": 0, "pair": "A~B"}))
    check("a row without a run column is refused",
          raises(triallog.append, tmp / "no-run.csv", {"pair": "A~B"}))
    check("the refused rows were not written",
          sum(1 for _ in path.open(encoding="utf-8")) == 3)
    path.unlink()


def _message(fn, *args) -> str:
    try:
        fn(*args)
    except Exception as exc:
        return str(exc)
    return ""


# ---------------------------------------------------------------- 10. layering
#: Step 1 and Step 2 primitives. None of these may import Step 3.
#:
#: `screen.py` is deliberately absent: it is an orchestrator, not a primitive,
#: and it already reaches across Step 0 and Step 2. It calls Step 3 to confirm
#: whatever survives its statistical gates, which is the right direction — the
#: rule exists so that Step 3's own verification cannot become circular, and a
#: search tool sitting above all three steps does not threaten that.
STEP12 = ("backtest", "costs", "strategy", "pair_report", "hedge", "health",
          "cointegration", "feasibility")
STEP3 = {"outcomes", "thresholds", "risk", "sizing"}


def imported_modules(path: Path) -> set:
    """Top-level module names a file imports, read from the syntax tree.

    Parsed rather than grepped so that the word appearing in a comment or a
    docstring is not mistaken for a dependency — which it is, all over Step 1
    and Step 2, because those files explain why Step 3 exists.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def test_dependency_direction():
    print("\n10. layering - Step 3 builds on Step 1 and Step 2, never the reverse")
    for name in STEP12:
        path = HERE / f"{name}.py"
        if not path.exists():
            skip(f"{name}.py does not import Step 3", "file not present")
            continue
        leaked = imported_modules(path) & STEP3
        check(f"{name}.py does not import Step 3", not leaked,
              f"imports {sorted(leaked)}")
    for name in sorted(STEP3):
        path = HERE / f"{name}.py"
        check(f"{name}.py exists", path.exists())
    # The orchestrator is allowed to call Step 3, but only Step 3 — it must not
    # become a fourth implementation of the gates it is meant to be reusing.
    screen_source = (HERE / "screen.py").read_text(encoding="utf-8")
    screen_imports = imported_modules(HERE / "screen.py")
    check("screen.py still uses the Step 2 primitives",
          {"cointegration", "hedge"} <= screen_imports,
          f"imports {sorted(screen_imports & {'cointegration', 'hedge'})}")
    check("screen.py calls Step 3 rather than reimplementing its gates",
          all(f"{m}." in screen_source for m in ("oc", "th", "sz")),
          "the confirmation step must delegate")
    for formula in ("mu / (sigma ** 2)", "min_edge * total / sigma_bps"):
        check(f"screen.py does not carry its own copy of `{formula}`",
              formula not in screen_source)


def main() -> int:
    global VERBOSE
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true")
    ns = parser.parse_args()
    VERBOSE = ns.verbose

    print("Verifying outcomes.py, thresholds.py, risk.py and sizing.py")
    test_classification()
    test_ou_ground_truth()
    test_financing_inversion()
    test_measured_floor()
    test_thresholds_match_the_engine()
    test_book_structure()
    test_kill_switch()
    test_book_inputs()
    test_book_equity()
    test_inputs_refused()
    test_sizing()
    test_trial_log(HERE.parent / "logs")
    test_dependency_direction()

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("\nFAILED:")
        for name in FAILED:
            print(f"  - {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
