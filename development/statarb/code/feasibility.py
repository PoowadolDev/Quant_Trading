"""Step 1b — does the edge survive the financing?

The pair study compared the expected move against transaction cost only. A
mean-reversion trade is held for its half-life, and every night of that hold
pays swap, so the question this script answers is the one that actually decides
whether the trade exists:

    expected move    = (entry_z - exit_z) * sigma_eq
    transaction cost = spread + commission, both legs, in and out
    carry cost       = nightly swap * nights held
    edge             = expected move / (transaction + carry)

Both directions are reported, because a spread that is short the high-yielding
leg pays financing that a spread long the same leg collects.

    python feasibility.py -s USDNOK,USDZAR --broker demo --holding-bars 7
    python feasibility.py -s USDNOK,USDZAR --broker demo --sweep-holding 1,20

Exit codes: 0 alive in at least one direction, 3 dead both ways, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import paths

paths.ensure_code_importable()

import costs as cost_model                                        # noqa: E402
import pair_report as pr                                          # noqa: E402

UserError = pr.UserError

ALIVE, MARGINAL, DEAD = "ALIVE", "MARGINAL", "DEAD"


def spread_directions(a: str, b: str, beta: float) -> dict[str, list]:
    """The two ways to trade the spread, as a direction per leg.

    The spread is `log A - beta * log B`. Buying it means long A and short B
    when beta is positive, and long both when beta is negative, because a
    negative hedge ratio already flips the second leg.
    """
    b_long = beta < 0
    return {
        "long spread": [cost_model.LegPlan(a, "long"),
                        cost_model.LegPlan(b, "long" if b_long else "short")],
        "short spread": [cost_model.LegPlan(a, "short"),
                         cost_model.LegPlan(b, "short" if b_long else "long")],
    }


def assess(move_bps: float, total_bps: float, min_edge: float,
           marginal_edge: float) -> tuple[str, float]:
    if total_bps <= 0:
        # Financing pays more than the trade costs: the edge is unbounded, and
        # that is a carry trade, not a mean-reversion trade. Say so plainly.
        return ALIVE, math.inf
    edge = move_bps / total_bps
    if edge >= min_edge:
        return ALIVE, edge
    if edge >= marginal_edge:
        return MARGINAL, edge
    return DEAD, edge


def break_even_swap(move_bps: float, transaction_bps: float, nights: float,
                    min_edge: float) -> float:
    """Nightly financing, in bps, at which the edge falls to `min_edge`.

    Positive means the trade can absorb that much debit per night; negative
    means the transaction cost alone has already sunk it, before any financing.
    """
    if nights <= 0:
        return math.inf
    allowed_total = move_bps / min_edge
    return (allowed_total - transaction_bps) / nights


def headroom(break_even_bps: float, carry_bps: float, nights: float) -> float:
    """How much worse the nightly financing can get before the edge is gone.

    The break-even figure is a property of the move and the transaction cost,
    so it is the same in both directions. What differs is how much of it each
    direction has already spent, and that is the number worth reading.
    """
    if nights <= 0:
        return math.inf
    paid_per_night = -carry_bps / nights          # a debit is a positive cost here
    return break_even_bps - paid_per_night


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="feasibility", description=__doc__.splitlines()[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sel = p.add_argument_group("selection")
    sel.add_argument("-s", "--symbols", required=True)
    sel.add_argument("-a", "--asset-class", default="forex",
                     help="one class for both legs, or one per leg")
    sel.add_argument("-t", "--timeframe", default="1d")
    sel.add_argument("--source", default=None)
    sel.add_argument("--start", default=None)
    sel.add_argument("--end", default=None)

    fit = p.add_argument_group("structure - must match the pair study")
    fit.add_argument("--price", default="log", choices=("log", "raw"))
    fit.add_argument("--hedge", default="ols", choices=("ols",))
    fit.add_argument("--split", type=float, default=0.70)

    search = p.add_argument_group("searched - every value is a trial")
    search.add_argument("--entry-z", type=float, default=2.0)
    search.add_argument("--exit-z", type=float, default=0.5)
    search.add_argument("--holding-bars", type=float, default=None,
                        help="nights held; defaults to the fitted half-life")
    search.add_argument("--min-edge", type=float, default=2.0,
                        help="edge at or above this is ALIVE")
    search.add_argument("--marginal-edge", type=float, default=1.0,
                        help="edge at or above this is MARGINAL, below it is DEAD")
    search.add_argument("--sweep-holding", default=None, metavar="LO,HI",
                        help="also print the edge across this range of holding periods")

    given = p.add_argument_group("given by reality")
    given.add_argument("--broker", required=True, help="cost profile to use")
    given.add_argument("--costs-dir", default=str(cost_model.DEFAULT_COSTS))
    given.add_argument("--bars-per-night", type=float, default=1.0)

    out = p.add_argument_group("output")
    out.add_argument("--store", default=str(pr.DEFAULT_STORE))
    out.add_argument("--json", action="store_true")
    out.add_argument("-q", "--quiet", action="store_true")
    out.add_argument("-v", "--verbose", action="store_true")
    # pair_report.load_prices reads these; feasibility writes no report of its own.
    out.add_argument("--min-half-life", type=float, default=2.0, help=argparse.SUPPRESS)
    out.add_argument("--max-half-life", type=float, default=1e9, help=argparse.SUPPRESS)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))

    profile_path = Path(args.costs_dir) / f"{args.broker}.json"
    symbols = cost_model.load_profile(profile_path)
    if not symbols:
        raise UserError(f"no cost profile at {profile_path}; run costs.py add first")

    prices = pr.load_prices(args)
    split = int(len(prices) * args.split)
    fit = pr.fit_pair(prices, split=split, use_log=args.price == "log",
                      entry_z=args.entry_z, exit_z=args.exit_z, cost_bps=1.0)
    if fit.regime != pr.REVERTING or not math.isfinite(fit.sigma_eq):
        raise UserError(f"the in-sample spread is {fit.regime}, so there is no expected "
                        "move to compare against cost; this pair is not a candidate")

    a, b = prices.columns
    holding = args.holding_bars if args.holding_bars is not None else fit.half_life
    move_bps = (args.entry_z - args.exit_z) * fit.sigma_eq * 1e4

    log(f"{a} ~ {b}  {args.timeframe}  beta {fit.beta:+.4f}  half-life "
        f"{fit.half_life:.1f} bars  sigma_eq {fit.sigma_eq*1e4:.0f} bps")
    log(f"expected move  {move_bps:.1f} bps   from z {args.entry_z:g} to {args.exit_z:g}")
    log(f"held {holding:.1f} bars, broker {args.broker}"
        + ("   COST PROFILE IS ESTIMATED" if any(c.estimated for c in symbols.values())
           else ""))
    log("")

    results = {}
    for name, legs in spread_directions(a, b, fit.beta).items():
        total = cost_model.round_trip(symbols, legs, holding, args.bars_per_night)
        verdict, edge = assess(move_bps, total["total_bps"], args.min_edge,
                               args.marginal_edge)
        be = break_even_swap(move_bps, total["transaction_bps"], total["nights"],
                             args.min_edge)
        room = headroom(be, total["carry_bps"], total["nights"])
        results[name] = {"verdict": verdict, "edge": edge, "move_bps": move_bps,
                         "break_even_swap_bps_per_night": be,
                         "headroom_bps_per_night": room, **total}
        legs_text = ", ".join(f"{leg.direction} {leg.symbol}" for leg in legs)
        log(f"{name:13s} {legs_text}")
        log(f"  transaction {total['transaction_bps']:8.2f} bps")
        log(f"  carry       {-total['carry_bps']:8.2f} bps over {total['nights']:.1f} nights")
        log(f"  total       {total['total_bps']:8.2f} bps")
        log(f"  edge        {edge:8.2f}x   {verdict}")
        log(f"  break-even  {be:+8.2f} bps per night of financing is the most this "
            f"move can carry")
        log(f"  headroom    {room:+8.2f} bps per night before the edge falls to "
            f"{args.min_edge:g}x, after what this direction already pays")
        log("")

    if args.sweep_holding:
        try:
            lo, hi = (float(v) for v in args.sweep_holding.split(","))
        except ValueError:
            raise UserError("--sweep-holding takes LO,HI") from None
        log(f"{'bars':>6s} " + " ".join(f"{n:>16s}" for n in results))
        step = max((hi - lo) / 9, 1e-9)
        bars = lo
        while bars <= hi + 1e-9:
            cells = []
            for name, legs in spread_directions(a, b, fit.beta).items():
                total = cost_model.round_trip(symbols, legs, bars, args.bars_per_night)
                verdict, edge = assess(move_bps, total["total_bps"], args.min_edge,
                                       args.marginal_edge)
                shown = "inf" if math.isinf(edge) else f"{edge:.1f}x"
                cells.append(f"{shown:>9s} {verdict:>6s}")
            log(f"{bars:6.1f} " + " ".join(cells))
            bars += step
        log("")

    alive = [n for n, r in results.items() if r["verdict"] == ALIVE]
    if args.json:
        print(json.dumps({"pair": f"{a}~{b}", "holding_bars": holding,
                          "half_life": fit.half_life, "beta": fit.beta,
                          "directions": results}, indent=2, default=str))
    log("ALIVE in: " + (", ".join(alive) if alive else "neither direction"))
    return 0 if alive else 3


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
