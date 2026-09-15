"""Step 3.2 — the feasible region for entry, exit and holding period.

This is deliberately not an optimiser. Sweeping entry thresholds on `XLP~XLB`
over twenty-eight years produced a net ranging from -3,678 to +3,747 basis
points across twelve parameter cells, three of them positive. A surface like
that has no maximum worth finding: whichever cell is picked is a draw from
noise, and picking it is exactly the behaviour Step 4 exists to catch.

What can be computed rather than searched is a *bound*. Three of them:

    entry threshold    the z below which a trade cannot pay for its own
                       financing. Arithmetic, from measured cost and measured
                       holding time — not a value anyone chose.

    holding period     how many nights the expected move can afford. A spread
                       whose half-life exceeds that number cannot be traded at
                       this bar size, whatever its statistics say.

    bar size           the same constraint read the other way. `XLP~XLB` paid
                       -1,058 bps of carry on daily bars and -75 on hourly,
                       because the hold fell from sixteen days to two and a
                       half. Shortening the hold is the only lever that has
                       ever moved the financing term in this project, and the
                       exit rule is what controls it.

The scale used throughout is the spread as the strategy sees it, from
`outcomes.traded_sigma`, not the static in-sample fit the reports print. The
two differ by up to 5.7x, and a bound computed from the wrong one is not a
bound.

    python thresholds.py -s XLP,XLB -a index --broker etf
    python thresholds.py -s ALL,TRV -a equity --broker equity --min-edge 2
    python thresholds.py -s XLP,XLB -a index -t 1h --broker etf \\
        --bars-per-night 0.144

Exit codes: 0 a feasible region exists, 3 it is empty, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

import paths

paths.ensure_code_importable()

import backtest as bt                                             # noqa: E402
import costs as cost_model                                        # noqa: E402
import outcomes as oc                                             # noqa: E402
import pair_report as pr                                          # noqa: E402
import strategy as sig                                            # noqa: E402
import triallog                                                   # noqa: E402

UserError = pr.UserError
DEFAULT_LOG = paths.LOGS / "thresholds.csv"


def break_even_z(exit_z: float, transaction_bps: float, carry_per_night_bps: float,
                 nights: float, sigma_bps: float, min_edge: float) -> float:
    """Entry threshold at which the move is `min_edge` times the cost.

    Solving `(z - exit_z) * sigma = min_edge * (transaction + carry * nights)`
    for z. Every term is measured: nothing here is a preference.

    `carry_per_night_bps` is a positive debit. Financing that is *received*
    enters as a negative debit and lowers the threshold, which is correct and
    is why the sign is not clamped.
    """
    if sigma_bps <= 0 or not math.isfinite(sigma_bps):
        return float("inf")
    total = transaction_bps + carry_per_night_bps * max(0.0, nights)
    return exit_z + min_edge * total / sigma_bps


def affordable_nights(entry_z: float, exit_z: float, sigma_bps: float,
                      transaction_bps: float, carry_per_night_bps: float,
                      min_edge: float) -> float:
    """How many nights the move at `entry_z` can pay for.

    Infinite when financing is a credit rather than a debit: that position is
    paid to exist, and the limit on holding it is not a financial one. Say so
    rather than returning a large number that looks measured.
    """
    move = (entry_z - exit_z) * sigma_bps
    allowed = move / min_edge - transaction_bps
    if carry_per_night_bps <= 0:
        return float("inf")
    if allowed <= 0:
        return 0.0
    return allowed / carry_per_night_bps


def cost_per_trade(transaction_bps: float, carry_per_night_bps: float,
                   bars_held: float, bars_per_night: float) -> float:
    """What one round trip costs, using the holding time actually observed.

    The modelled floor charges financing for the fitted half-life. Trades do not
    run for the half-life: on `XLP~XLB` only 27% of them reach the exit at all,
    and the rest end at the stop or the holding limit. Charging the measured
    holding time is the difference between costing the trade that was modelled
    and costing the trade that happened.
    """
    return transaction_bps + carry_per_night_bps * max(0.0, bars_held) * bars_per_night


def clears(realised_bps: float, cost_bps: float, min_edge: float) -> bool:
    """Whether what a trade actually earned covers what it actually cost.

    No model appears here. `realised_bps` is the mean gross of the trades that
    were placed, and the comparison is against their own cost. A threshold that
    fails this has been shown not to pay, rather than argued not to.
    """
    if not math.isfinite(realised_bps) or not math.isfinite(cost_bps):
        return False
    if cost_bps <= 0:
        return realised_bps > 0
    return realised_bps >= min_edge * cost_bps


@dataclass
class Measured:
    """One entry threshold, as the trades at that threshold turned out."""

    entry_z: float
    trades: int
    completion_rate: float
    bars_held: float
    realised_bps: float
    predicted_bps: float
    cost_bps: float
    min_edge: float

    @property
    def clears(self) -> bool:
        return clears(self.realised_bps, self.cost_bps, self.min_edge)

    @property
    def edge(self) -> float:
        if self.cost_bps <= 0:
            return float("inf")
        return self.realised_bps / self.cost_bps


@dataclass
class Region:
    """The feasible region for one pair at one bar size, or the absence of one."""

    pair: str
    direction: str
    sigma_bps: float
    half_life_bars: float
    bars_per_night: float
    transaction_bps: float
    carry_per_night_bps: float
    min_edge: float
    exit_z: float
    stop_z: float
    entry_z_min: float                         # break-even floor, from cost
    entry_z_available: float                   # the deviation the spread actually offers
    max_holding_bars: float
    reached_share: float                       # share of bars at or beyond entry_z_min

    @property
    def nights_needed(self) -> float:
        """Nights of financing a trade held for its own half-life would pay."""
        return self.half_life_bars * self.bars_per_night

    @property
    def empty(self) -> bool:
        """True when no entry threshold can both pay and ever occur."""
        return (not math.isfinite(self.entry_z_min)
                or self.entry_z_min >= self.stop_z
                or self.reached_share <= 0.0)

    @property
    def holding_ok(self) -> bool:
        """Whether the spread reverts faster than the financing can be paid.

        The affordable hold is measured at `entry_z_available` — the deviation
        the spread genuinely offers — not at the break-even floor. Evaluating it
        at the floor would be circular: the floor is derived from the half-life,
        so the answer would always come back as the half-life and the test would
        pass or fail on rounding.
        """
        return self.half_life_bars <= self.max_holding_bars

    def recommended_holding_bars(self) -> int:
        """Bars to hold before giving up, as an integer the strategy accepts.

        The smaller of what the financing affords and twice the half-life. The
        half-life is the time to close half the gap, so a limit at twice it
        gives the average trade room to finish without funding the tail of the
        distribution indefinitely.
        """
        by_money = self.max_holding_bars
        by_reversion = 2.0 * self.half_life_bars
        chosen = min(by_money, by_reversion)
        if not math.isfinite(chosen) or chosen < 1:
            return 1
        return int(max(1, round(chosen)))

    def carry_night_display(self) -> str:
        """Nightly financing as a debit, or the word for being paid to hold."""
        if self.carry_per_night_bps <= 0:
            return "credit"
        return f"{self.carry_per_night_bps:.3f}"

    def bar_size_needed(self) -> float:
        """Nights per bar at which the half-life would become affordable.

        A hold of `half_life_bars` bars must fit inside `max_holding_bars`
        nights of financing. Below one, the answer is a finer bar.
        """
        if self.half_life_bars <= 0:
            return float("inf")
        if not math.isfinite(self.max_holding_bars):
            return float("inf")
        return self.max_holding_bars * self.bars_per_night / self.half_life_bars


def build_region(pair: str, direction: str, sigma_bps: float, half_life: float,
                 transaction_bps: float, carry_per_night_bps: float, *,
                 exit_z: float, stop_z: float, min_edge: float,
                 bars_per_night: float, z_series: np.ndarray) -> Region:
    nights = half_life * bars_per_night
    entry_min = break_even_z(exit_z, transaction_bps, carry_per_night_bps,
                             nights, sigma_bps, min_edge)

    finite = np.abs(z_series[np.isfinite(z_series)])
    # The largest deviation the spread routinely offers, rather than its record.
    # A single extreme bar is not a trade that can be planned around.
    available = float(np.quantile(finite, 0.95)) if finite.size else float("nan")

    nights_afford = affordable_nights(available, exit_z, sigma_bps,
                                      transaction_bps, carry_per_night_bps,
                                      min_edge) if math.isfinite(available) else 0.0
    max_bars = (float("inf") if not math.isfinite(nights_afford)
                else nights_afford / bars_per_night if bars_per_night > 0
                else float("inf"))
    reached = (float(np.mean(finite >= entry_min))
               if finite.size and math.isfinite(entry_min) else 0.0)
    return Region(pair=pair, direction=direction, sigma_bps=sigma_bps,
                  half_life_bars=half_life, bars_per_night=bars_per_night,
                  transaction_bps=transaction_bps,
                  carry_per_night_bps=carry_per_night_bps, min_edge=min_edge,
                  exit_z=exit_z, stop_z=stop_z, entry_z_min=entry_min,
                  entry_z_available=available,
                  max_holding_bars=max_bars, reached_share=reached)


def spread_z(prices, params: sig.SignalParams) -> np.ndarray:
    """The z-score series the strategy would have seen, bar by bar.

    Refit on the same trailing window and at the same cadence as the strategy,
    so "how often does the spread reach this threshold" is answered about the
    spread that is actually traded rather than about a static fit of it.
    """
    window = params.fit_window
    n = len(prices)
    out = np.full(n, np.nan)
    px = np.log(prices) if params.use_log else prices
    values = px.to_numpy(float)
    fit = None
    for t in range(window, n):
        if fit is None or t - fit.fitted_at >= params.rehedge_every:
            refit = sig.fit_relationship(prices.iloc[t - window:t],
                                         use_log=params.use_log, at=t)
            fit = refit if refit is not None else fit
        if fit is None:
            continue
        out[t] = fit.z(values[t, 0], values[t, 1])
    return out


def measure_grid(prices, profile: dict, base: sig.SignalParams, grid: list, *,
                 transaction_bps: float, carry_per_night_bps: float,
                 bars_per_night: float, min_edge: float, warmup: int,
                 lag: int, static_sigma: float) -> list:
    """Run the strategy at each candidate threshold and keep what happened.

    This is a sweep and it is not an optimisation. Nothing here picks the best
    cell: the grid exists so the *floor* can be read off measured results
    instead of from a formula that over-predicts the move by an order of
    magnitude, and so the reader can see whether the surface has a shape or is
    flat noise.
    """
    rows = []
    for entry_z in grid:
        try:
            params = replace(base, entry_z=entry_z)
        except ValueError:
            continue                    # above the stop, or below the exit
        comparison = oc.compare(prices, profile, params,
                                static_sigma=static_sigma,
                                static_half_life=float("nan"), warmup=warmup,
                                bars_per_night=bars_per_night, lag=lag)
        m = comparison.outcomes
        held = (float(np.mean(m.bars_held)) if m.bars_held else float("nan"))
        rows.append(Measured(
            entry_z=entry_z, trades=m.trades,
            completion_rate=m.completion_rate, bars_held=held,
            realised_bps=m.avg_gross_bps,
            predicted_bps=comparison.predicted_traded_bps,
            cost_bps=cost_per_trade(transaction_bps, carry_per_night_bps,
                                    held, bars_per_night),
            min_edge=min_edge))
    return rows


def measured_floor(rows: list, min_trades: int) -> float:
    """The lowest threshold whose own trades paid for themselves.

    Lowest rather than best, deliberately. Picking the most profitable cell of a
    swept grid is fitting noise — on twenty-eight years of `XLP~XLB` that grid
    ran from -3,678 to +3,747 basis points. The lowest cell that clears is a
    boundary, and boundaries move less than maxima.
    """
    for row in sorted(rows, key=lambda r: r.entry_z):
        if row.trades >= min_trades and row.clears:
            return row.entry_z
    return float("nan")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="thresholds", description=__doc__.splitlines()[0],
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
    struct.add_argument("--fit-window", type=int, default=250)
    struct.add_argument("--rehedge-every", type=int, default=5)

    search = p.add_argument_group("searched - every value is a trial")
    search.add_argument("--exit-z", type=float, default=0.5)
    search.add_argument("--stop-z", type=float, default=4.0)
    search.add_argument("--min-edge", type=float, default=2.0,
                        help="how many times the cost the move must be worth")
    search.add_argument("--entry-grid", default="1.0,1.5,2.0,2.5,3.0",
                        help="thresholds to measure; the floor is read off these "
                             "results rather than off the model")
    search.add_argument("--min-trades", type=int, default=20,
                        help="a threshold with fewer trades than this has not "
                             "been shown to pay, whatever its mean")
    search.add_argument("--no-measure", action="store_true",
                        help="skip the replay and report only the modelled "
                             "floor, which over-predicts the move")
    search.add_argument("--min-reached", type=float, default=0.005,
                        help="the break-even threshold must be reached on at least "
                             "this share of bars, or there is no trade to place")

    given = p.add_argument_group("given by reality")
    given.add_argument("--broker", required=True)
    given.add_argument("--warmup", type=int, default=260)
    given.add_argument("--lag", type=int, default=1)
    given.add_argument("--costs-dir", default=str(cost_model.DEFAULT_COSTS))
    given.add_argument("--bars-per-night", type=float, default=None,
                       help="nights of financing per bar; defaults to the asset "
                            "class and timeframe, which is 1.45 for a daily "
                            "equity bar and 1.0 only for crypto")

    out = p.add_argument_group("output")
    out.add_argument("--store", default=str(paths.STORE))
    out.add_argument("--log", default=str(DEFAULT_LOG))
    out.add_argument("--no-log", action="store_true")
    out.add_argument("--json", action="store_true")
    out.add_argument("-q", "--quiet", action="store_true")
    out.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))

    profile_path = Path(args.costs_dir) / f"{args.broker}.json"
    profile = cost_model.load_profile(profile_path)
    if not profile:
        raise UserError(f"no cost profile at {profile_path}; run costs.py add first")
    estimated = any(c.estimated for c in profile.values())

    if args.min_edge <= 0:
        raise UserError(f"--min-edge {args.min_edge:g} would accept a trade that "
                        "earns less than it costs, which is what this gate exists "
                        "to refuse. Use 1 to break even, 2 for the default margin.")
    if not 0.0 <= args.min_reached <= 1.0:
        raise UserError(f"--min-reached {args.min_reached:g} is a share of bars, "
                        "so it lies between 0 and 1.")
    if args.min_trades < 1:
        raise UserError(f"--min-trades {args.min_trades} would let a threshold "
                        "with no trades set the floor.")
    grid_levels = oc.parse_levels(args.entry_grid, "--entry-grid")

    prices = pr.load_prices(args)
    if args.bars_per_night is None:
        # One definition of how many nights a bar costs, in costs.py, rather
        # than a 1.0 that silently undercharges every asset class but crypto.
        first_class = args.asset_class.split(",")[0].strip().lower()
        args.bars_per_night = cost_model.nights_per_bar(first_class, args.timeframe)
    a, b = prices.columns
    pair = f"{a} ~ {b}"

    params = sig.SignalParams(entry_z=2.0, exit_z=args.exit_z, stop_z=args.stop_z,
                              fit_window=args.fit_window,
                              rehedge_every=args.rehedge_every,
                              use_log=args.price == "log")
    sigma, half_life = oc.traded_sigma(prices, params)
    if not math.isfinite(sigma) or sigma <= 0:
        raise UserError(f"{pair} has no usable OU fit on a {args.fit_window}-bar "
                        "window, so there is no spread to set thresholds on")
    if not math.isfinite(half_life) or half_life <= 0:
        raise UserError(f"{pair} has no finite half-life on a "
                        f"{args.fit_window}-bar window")
    sigma_bps = sigma * 1e4

    z = spread_z(prices, params)

    # The hedge ratio decides which way each leg goes, so costs are per
    # direction. A spread short the high-yielding leg pays financing that the
    # opposite direction collects, and the two can differ by more than the
    # transaction cost.
    beta = 0.0
    for t in range(len(prices) - 1, args.fit_window - 1, -1):
        fit = sig.fit_relationship(prices.iloc[t - args.fit_window:t],
                                   use_log=params.use_log, at=t)
        if fit is not None:
            beta = fit.beta
            break

    log(f"{pair}  {args.timeframe}  {len(prices):,} bars  broker {args.broker}")
    log(f"  spread as traded: sigma {sigma_bps:,.0f} bps, half-life "
        f"{half_life:.1f} bars, hedge ratio {beta:+.3f}")
    log("")

    # Costs come from the engine's own functions rather than from a second
    # calculation of the same thing. The leg weights are (1, -beta), so the two
    # directions do not cost the same whenever the two legs finance differently,
    # and an unweighted round trip would hide that.
    regions = []
    for direction, position in (("long spread", 1), ("short spread", -1)):
        transaction = bt.round_trip_bps(profile, a, b, position, beta)
        # Signed as brokers quote swap: negative is a debit, so a debit becomes
        # a positive cost here.
        carry_night = -bt.carry_per_night_bps(profile, a, b, position, beta)
        regions.append(build_region(
            pair, direction, sigma_bps, half_life, transaction, carry_night,
            exit_z=args.exit_z, stop_z=args.stop_z, min_edge=args.min_edge,
            bars_per_night=args.bars_per_night, z_series=z))

    log(f"  {'direction':<13} {'txn':>6} {'carry/nt':>9} {'entry >=':>9} "
        f"{'offered':>8} {'reached':>8} {'affords':>8} {'needs':>6}  verdict")
    for r in regions:
        hold = ("none" if not math.isfinite(r.max_holding_bars)
                else f"{r.max_holding_bars:,.0f}")
        if r.empty:
            verdict = "DEAD - the break-even threshold is never reached"
        elif not r.holding_ok:
            verdict = (f"DEAD - reverts in {r.half_life_bars:.0f} bars, "
                       f"financing affords {r.max_holding_bars:,.0f}")
        else:
            verdict = f"ALIVE - hold at most {r.recommended_holding_bars()} bars"
        log(f"  {r.direction:<13} {r.transaction_bps:6.1f} {r.carry_night_display():>9} "
            f"{r.entry_z_min:9.2f} {r.entry_z_available:8.2f} {r.reached_share:8.1%} "
            f"{hold:>8} {r.half_life_bars:6.1f}  {verdict}")

    # ---- the model's floor is only half the answer, and the optimistic half.
    # Financing it charges assumes the trade runs for the fitted half-life, and
    # the move it credits assumes the trade completes. Neither holds: on this
    # data barely a quarter of trades reach their exit. So the operative floor
    # is read off trades that were actually placed.
    measured: list = []
    floor = float("nan")
    if not args.no_measure:
        grid = grid_levels
        # The same choice the report makes, from the same function, so the two
        # can never disagree about which direction a floor was priced for.
        want = bt.cheaper_direction(profile, a, b, beta)
        cheapest = next(r for r in regions
                        if r.direction == ("long spread" if want > 0
                                           else "short spread"))
        measured = measure_grid(
            prices, profile, params, grid,
            transaction_bps=cheapest.transaction_bps,
            carry_per_night_bps=cheapest.carry_per_night_bps,
            bars_per_night=args.bars_per_night, min_edge=args.min_edge,
            warmup=args.warmup, lag=args.lag, static_sigma=sigma)
        floor = measured_floor(measured, args.min_trades)

        log("")
        log("  measured at each threshold - what the trades placed there did")
        log(f"  {'entry':>6} {'trades':>7} {'done':>6} {'held':>6} "
            f"{'predicted':>10} {'realised':>9} {'cost':>7} {'edge':>7}  pays?")
        for row in measured:
            edge = "-" if not math.isfinite(row.edge) else f"{row.edge:7.2f}"
            log(f"  {row.entry_z:6.2f} {row.trades:7d} {row.completion_rate:6.0%} "
                f"{row.bars_held:6.1f} {row.predicted_bps:10.0f} "
                f"{row.realised_bps:+9.1f} {row.cost_bps:7.1f} {edge:>7}  "
                f"{'yes' if row.clears else 'no'}")

    alive = [r for r in regions
             if not r.empty and r.holding_ok and r.reached_share >= args.min_reached]
    log("")
    if alive and not args.no_measure and not math.isfinite(floor):
        best = min(regions, key=lambda r: r.entry_z_min)
        log("  NO THRESHOLD PAYS.")
        log(f"    The model puts the floor at z {best.entry_z_min:.2f}, but no "
            f"threshold on the grid earned {args.min_edge:g} times its own cost "
            "on trades that were actually placed.")
        log("    The model's floor charges financing for the fitted half-life "
            "and credits a move the trade only collects if it completes.")
        if measured:
            done = max(measured, key=lambda r: r.completion_rate)
            log(f"    Completion peaks at {done.completion_rate:.0%} "
                f"(entry {done.entry_z:g}); the model assumes 100%.")
        alive = []
    elif alive:
        best = max(alive, key=lambda r: r.reached_share)
        entry = floor if math.isfinite(floor) else best.entry_z_min
        source = ("measured" if math.isfinite(floor)
                  else "modelled, and not measured because --no-measure was given")
        log(f"  FEASIBLE going {best.direction}:")
        log(f"    --entry-z {entry:.2f} or above ({source})")
        log(f"    --exit-z {best.exit_z:g}   --stop-z {best.stop_z:g}")
        log(f"    --max-holding-bars {best.recommended_holding_bars()}")
        log(f"    the model's floor alone would have said {best.entry_z_min:.2f}, "
            f"reached on {best.reached_share:.1%} of bars")
        log("  These are bounds, not an optimum. Nothing here was searched.")
    else:
        log("  NO FEASIBLE REGION at this bar size.")
        tight = min(regions, key=lambda r: r.entry_z_min)
        if not tight.holding_ok and math.isfinite(tight.bar_size_needed()):
            log(f"    The spread reverts in {tight.half_life_bars:.0f} bars and the "
                f"financing affords {tight.max_holding_bars:,.0f}.")
            log(f"    It would need {tight.bar_size_needed():.3f} nights per bar "
                f"against the {args.bars_per_night:g} charged here — "
                "that is a finer bar, not a different threshold.")
        elif tight.reached_share < args.min_reached:
            log(f"    The break-even threshold is z {tight.entry_z_min:.2f}, reached on "
                f"{tight.reached_share:.2%} of bars, below the "
                f"{args.min_reached:.2%} required.")
    if estimated:
        log("  NOTE: the cost profile is an estimate, not a broker sheet")

    if not args.no_log:
        run = 0
        for r in regions:
            row = {
                "run": 0, "run_utc": triallog.stamp(), "pair": pair,
                "timeframe": args.timeframe, "broker": args.broker,
                "start": args.start or "", "end": args.end or "",
                "bars_per_night": args.bars_per_night, "warmup": args.warmup,
                "direction": r.direction,
                "sigma_bps": round(r.sigma_bps, 1),
                "half_life": round(r.half_life_bars, 2),
                "bars_per_night": r.bars_per_night,
                "transaction_bps": round(r.transaction_bps, 2),
                "carry_per_night_bps": round(r.carry_per_night_bps, 4),
                "min_edge": r.min_edge,
                "exit_z": r.exit_z, "stop_z": r.stop_z,
                "entry_z_min": round(r.entry_z_min, 4),
                "entry_z_available": round(r.entry_z_available, 4),
                "reached_share": round(r.reached_share, 5),
                "max_holding_bars": (None if not math.isfinite(r.max_holding_bars)
                                     else round(r.max_holding_bars, 1)),
                "recommended_holding_bars": r.recommended_holding_bars(),
                "measured_floor": (None if not math.isfinite(floor)
                               else round(floor, 3)),
            "feasible": "yes" if alive else "no",
            }
            try:
                run = triallog.append(Path(args.log), row)
            except triallog.SchemaChanged as exc:
                raise UserError(str(exc)) from exc
        log(f"  {len(regions)} row(s) logged to {Path(args.log)}, last run #{run}")

    if args.json:
        print(json.dumps({
            "pair": pair, "bars": len(prices),
            "sigma_bps": sigma_bps, "half_life_bars": half_life, "beta": beta,
            "regions": [{
                "direction": r.direction,
                "transaction_bps": r.transaction_bps,
                "carry_per_night_bps": r.carry_per_night_bps,
                "entry_z_min": r.entry_z_min,
                "entry_z_available": r.entry_z_available,
                "reached_share": r.reached_share,
                "max_holding_bars": (None if not math.isfinite(r.max_holding_bars)
                                     else r.max_holding_bars),
                "recommended_holding_bars": r.recommended_holding_bars(),
                "holding_ok": r.holding_ok,
                "empty": r.empty,
            } for r in regions],
            "measured_floor": (None if not math.isfinite(floor) else floor),
            "measured": [{"entry_z": m.entry_z, "trades": m.trades,
                          "completion_rate": m.completion_rate,
                          "bars_held": m.bars_held,
                          "predicted_bps": m.predicted_bps,
                          "realised_bps": m.realised_bps,
                          "cost_bps": m.cost_bps, "clears": m.clears}
                         for m in measured],
            "feasible": bool(alive),
        }, indent=2, default=str))

    return 0 if alive else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
