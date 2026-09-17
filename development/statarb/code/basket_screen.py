"""Screen baskets of three or more instruments the way `screen.py` screens pairs.

A pair is the two-leg case of a basket, and everything that made the pair screen
untrustworthy applies here with more force. Fitting weights across more legs
gives the fit more freedom to manufacture a stationary-looking residual out of
series that have no relationship, so the gates must be at least as strict and
the critical values must know how many legs were fitted.

Three things make this different from running `screen.py` on every combination:

**The critical values account for the extra legs.** The residual of an n-leg fit
is not a series that was handed to us; it was chosen to look stationary. Running
a plain ADF on it would over-reject, and the over-rejection grows with the number
of legs. `statsmodels.coint` takes a two-dimensional second argument and applies
the MacKinnon critical values for that many regressors: measured on independent
random walks, the five per cent critical value moves from -3.344 at one regressor
to -4.433 at four, and the rejection rate stays at or below five per cent
throughout.

**Groups are named, not enumerated.** Eighteen coins admit 816 three-leg
combinations and 3,060 four-leg ones. Screening them all would be a trial
explosion bought with nothing: every extra group raises the deflation benchmark
for whatever survives. The groups below each carry a structural claim that can be
stated in one sentence without reference to any price.

**The economic-link gate does no work in crypto.** Every coin resolves to one
driver, `crypto-beta`, because everything in this market moves with bitcoin.
`--require-link` admits all pairs here honestly, which is why the pair screen
needed the trial count to carry the whole correction. A basket is the attempt to
do better: holding one coin against several of its peers nets out the shared beta
explicitly rather than hoping the regression absorbs it.

The gate order matches `screen.py` exactly, and for the same reasons.
"""
from __future__ import annotations

import argparse
import itertools
import math
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cointegration as ci                                          # noqa: E402
import costs as cs                                                  # noqa: E402
import hedge as hg                                                  # noqa: E402
import pair_report as pr
import relationship as rel                                            # noqa: E402
import paths                                                        # noqa: E402
import triallog                                                     # noqa: E402

UserError = pr.UserError
DEFAULT_LOG = paths.LOGS / "baskets.csv"

#: Named baskets, each with a structural claim that does not mention a price.
#:
#: A group earns its place here by being a story about how the instruments are
#: built or used, not by having looked good in a previous run. Adding a group
#: because it screened well is how a screen comes to confirm its own selection.
GROUPS: dict[str, dict] = {
    "btc-forks": {
        "symbols": ["BTC-USDT", "BCH-USDT", "LTC-USDT"],
        "claim": "BCH is a literal fork of BTC and LTC is a near-copy of its "
                 "codebase; all three are proof-of-work coins with the same "
                 "mining economics",
    },
    "eth-fork": {
        "symbols": ["ETH-USDT", "ETC-USDT"],
        "claim": "ETC is the original Ethereum chain, identical to ETH until the "
                 "2016 split",
    },
    "payments": {
        "symbols": ["XRP-USDT", "XLM-USDT"],
        "claim": "Stellar was created by a Ripple co-founder as a redesign of the "
                 "same idea; both are cross-border payment settlement tokens",
    },
    "alt-l1": {
        "symbols": ["SOL-USDT", "AVAX-USDT", "DOT-USDT", "ATOM-USDT"],
        "claim": "smart-contract layer ones competing for the same developers, "
                 "the same applications and the same locked value",
    },
    "alt-l1-wide": {
        "symbols": ["ADA-USDT", "SOL-USDT", "AVAX-USDT", "DOT-USDT", "ATOM-USDT"],
        "claim": "the alt-l1 group with Cardano, an older entrant to the same "
                 "competition",
    },
    "majors": {
        "symbols": ["BTC-USDT", "ETH-USDT", "BNB-USDT"],
        "claim": "the three deepest order books in the market, where an exchange "
                 "token tracks the volume the other two generate",
    },
    "pow-legacy": {
        "symbols": ["BTC-USDT", "LTC-USDT", "BCH-USDT", "ETC-USDT"],
        "claim": "the surviving proof-of-work coins, whose issuance and miner "
                 "revenue respond to the same hardware and energy costs",
    },
    "eth-ecosystem": {
        "symbols": ["ETH-USDT", "UNI-USDT", "LINK-USDT"],
        "claim": "Uniswap and Chainlink run on Ethereum and are paid for in its "
                 "gas, so their usage and its usage are the same activity",
    },
}


@dataclass
class Row:
    """One basket, measured on every window the record allows."""

    name: str
    symbols: list[str]
    bars: int
    pvalue: float
    pvalue_oos: float
    weights: np.ndarray
    half_life: float
    half_life_oos: float
    net_exposure: float
    claim: str = ""
    pvalue_early: float = float("nan")
    pvalue_late: float = float("nan")
    weights_early: np.ndarray | None = None
    weights_late: np.ndarray | None = None
    johansen_rank: int = 0
    cost_bps: float = float("nan")
    trial_id: int = 0

    @property
    def basket(self) -> str:
        return "~".join(s.replace("-USDT", "") for s in self.symbols)

    @property
    def legs(self) -> int:
        return len(self.symbols)

    def holds_out_of_window(self, level: float, *, require_early: bool = False) -> bool:
        """Does the basket cointegrate outside the window that selected it?

        The late window decides, for the reason `screen.py` records: a
        relationship present only in the oldest part of the record died before
        the present and cannot be traded now.
        """
        if not math.isfinite(self.pvalue_late) or not (self.pvalue_late < level):
            return False
        if require_early:
            return math.isfinite(self.pvalue_early) and self.pvalue_early < level
        return True

    def weight_swing(self) -> float:
        """Worst ratio between the same leg's weight fitted on different windows.

        The n-leg form of `Row.beta_swing` in `screen.py`. A basket worth trading
        has roughly the same weights whenever they are measured; a sign change on
        any leg means the windows disagree about which way the leg hedges, which
        is not one relationship measured three times.
        """
        sets = [w for w in (self.weights, self.weights_early, self.weights_late)
                if w is not None and np.all(np.isfinite(w))]
        if len(sets) < 2:
            return float("nan")
        worst = 0.0
        for leg in range(len(self.weights)):
            vals = [float(w[leg]) for w in sets]
            if any(v == 0.0 for v in vals):
                return float("inf")
            if min(vals) <= 0 < max(vals):
                return float("inf")        # the sign changes on this leg
            mags = sorted(abs(v) for v in vals)
            worst = max(worst, mags[-1] / mags[0])
        return worst

    def stability(self) -> float:
        """Ratio of the slower half-life to the faster. 1.0 is perfect agreement."""
        if not (math.isfinite(self.half_life) and math.isfinite(self.half_life_oos)):
            return math.inf
        lo, hi = sorted((self.half_life, self.half_life_oos))
        return hi / lo if lo > 0 else math.inf


def fit_weights(y: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, float]:
    """Least squares of the first leg on the rest, with a constant.

    Returns the hedge weights and the intercept. The traded position is one unit
    of the first leg against `weights` units of each other leg, so a positive
    weight is a short in that leg.

    Delegates to `relationship.ols_hedge`, the one basket-hedge fit this project
    keeps; this module used to run its own copy of the same `lstsq` call.
    """
    return rel.ols_hedge(y, x)


def spread_of(y: np.ndarray, x: np.ndarray, w: np.ndarray, c: float) -> np.ndarray:
    return rel.build_spread_n(y, x, w, c)


def net_exposure(w: np.ndarray) -> float:
    """Net over gross exposure of the whole basket.

    The position is `(1, -w_1, ... -w_k)`, so the net is what fails to cancel.
    Zero means the legs offset exactly; one means the basket is a directional bet
    on its first leg wearing a hedge that does nothing. The pair form of this
    lives in `hedge.net_exposure` and this is its generalisation; both exist
    because the screen once admitted a position that was 72 per cent net long.
    """
    if not np.all(np.isfinite(w)):
        return float("inf")
    gross = 1.0 + float(np.abs(w).sum())
    return abs(1.0 - float(w.sum())) / gross if gross else float("inf")


def _window(y: np.ndarray, x: np.ndarray, lags, min_bars: int) -> tuple:
    """Engle-Granger p-value and weights on one slice, or NaN if it is too short."""
    if len(y) < min_bars:
        return float("nan"), None
    p = ci.engle_granger(y, x, trend="c", lags=lags).pvalue
    w, _ = fit_weights(y, x)
    return p, w


def basket_cost_bps(symbols: list[str], profile: dict, weights: np.ndarray,
                    nights: float, holding_bars: float) -> float:
    """Round trip across every leg, plus financing over the holding period.

    Costs are quoted per unit of spread exposure and so are divided by the gross,
    which is the convention `backtest._turn_cost` and `backtest._carry_bps` use
    for the two-leg case. A basket is not cheaper for being one idea; it is more
    legs to cross and this is the number that says by how much.

    The direction is chosen the cheaper way round. Financing is signed as brokers
    quote swap, so a debit is negative and the cheaper side is the *larger*
    value; taking the minimum picks the most expensive side, which is a bug this
    project has already shipped once.
    """
    units = np.concatenate([[1.0], -np.asarray(weights, dtype=float)])
    gross = float(np.abs(units).sum())
    if gross <= 0 or not np.isfinite(gross):
        return float("nan")

    turn = 0.0
    for symbol, size in zip(symbols, units):
        leg = profile.get(symbol)
        if leg is None:
            return float("nan")
        turn += abs(size) * (leg.spread_bps() + leg.commission_bps)
    round_trip = 2.0 * turn / gross

    carries = []
    for direction in (1, -1):
        total = 0.0
        for symbol, size in zip(symbols, units * direction):
            leg = profile.get(symbol)
            if leg is None:
                return float("nan")
            total += abs(size) * leg.carry_bps("long" if size > 0 else "short")
        carries.append(total / gross)
    carry_per_night = max(carries)

    return round_trip - carry_per_night * nights * holding_bars


def load_basket(symbols: list[str], args) -> pd.DataFrame:
    """Aligned closes for any number of legs.

    `pair_report.load_prices` refuses anything but two symbols, so this is its
    n-leg form. It keeps that function's two protections deliberately: the panel
    is joined on the shared index and any bar missing from any leg is dropped, so
    a leg that listed late shortens the record rather than leaving a hole; and a
    non-positive close is refused outright, because log prices are taken
    throughout and such a bar would turn into a NaN somewhere downstream instead
    of an error here.

    Every leg of a basket shares one asset class and one source, so the
    cross-venue date alignment that function performs does not arise.
    """
    from marketdata import Instrument, ParquetStore, aligned_panel
    from marketdata.instruments import ASSET_CLASSES, DEFAULT_SOURCE

    if args.asset_class not in ASSET_CLASSES:
        raise UserError(f"unknown asset class {args.asset_class!r}; expected one of "
                        f"{', '.join(ASSET_CLASSES)}")
    if len(set(symbols)) != len(symbols):
        raise UserError(f"a basket cannot hold the same symbol twice: {symbols}")

    store = ParquetStore(Path(args.store))
    source = args.source or DEFAULT_SOURCE[args.asset_class]
    frames = {}
    for symbol in symbols:
        inst = Instrument(symbol, asset_class=args.asset_class, source=source,
                          timeframe=args.timeframe)
        hint = (f"{symbol} {args.timeframe} is not in the store at {args.store}. "
                f"Download it first: marketdata download -s {symbol} "
                f"-a {args.asset_class} -t {args.timeframe}")
        try:
            frame = store.read(inst)
        except FileNotFoundError as exc:
            raise UserError(hint) from exc
        if frame is None or frame.empty:
            raise UserError(hint)
        frames[symbol] = frame

    panel = aligned_panel(frames, field="close").dropna()
    if args.start:
        panel = panel[panel.index >= pr.parse_date(args.start)]
    if args.end:
        panel = panel[panel.index <= pr.parse_date(args.end)]
    if len(panel) < 100:
        raise UserError(f"only {len(panel)} overlapping bars across "
                        f"{len(symbols)} legs; need at least 100")
    panel = panel[symbols]
    values = panel.to_numpy(float)
    usable = np.isfinite(values) & (values > 0)
    if not usable.all():
        bad = [c for i, c in enumerate(panel.columns) if not usable[:, i].all()]
        raise UserError(f"non-positive or non-finite close prices in "
                        f"{', '.join(bad)}; the data is unusable")
    return panel


def evaluate(name: str, symbols: list[str], args, claim: str = "") -> Row:
    """Measure one basket on the screening window and both reserved windows."""
    try:
        px = load_basket(symbols, args)
    except UserError as exc:
        raise UserError(f"{name}: {exc}") from exc
    lp = np.log(px) if args.price == "log" else px
    mat = lp[symbols].to_numpy(float)
    y_all, x_all = mat[:, 0], mat[:, 1:]

    n = len(mat)
    cut = int(n * args.holdout)
    lo, hi = (cut, n - cut) if cut > 0 else (0, n)
    if hi - lo < args.min_screen_bars:
        raise UserError(f"{name}: --holdout {args.holdout:g} leaves {hi - lo} bars to "
                        f"screen on, below --min-screen-bars {args.min_screen_bars}")

    y, x = y_all[lo:hi], x_all[lo:hi]
    split = int(len(y) * args.split)

    p = ci.engle_granger(y, x, trend="c", lags=args.lags).pvalue
    tail = len(y) - split
    p_oos = (ci.engle_granger(y[split:], x[split:], trend="c", lags=args.lags).pvalue
             if tail >= args.min_tail else float("nan"))
    p_early, w_early = _window(y_all[:lo], x_all[:lo], args.lags, args.min_tail)
    p_late, w_late = _window(y_all[hi:], x_all[hi:], args.lags, args.min_tail)

    w, c = fit_weights(y, x)
    spread = spread_of(y, x, w, c)
    hl_is = hg._ou_half_life(spread[:split])
    hl_oos = hg._ou_half_life(spread[split:]) if tail >= args.min_tail else float("nan")

    # Johansen is reported rather than gated on. It answers a different question
    # -- how many cointegrating relationships exist among the columns -- and its
    # eigenvector is famously unstable out of sample, so it is corroboration for
    # the Engle-Granger verdict and never a substitute for it.
    rank = 0
    try:
        for res in ci.johansen(pd.DataFrame(mat[lo:hi], columns=symbols),
                               det_order=0, lags=args.lags):
            if res.reject:
                rank += 1
    except Exception:
        rank = -1

    return Row(name=name, symbols=list(symbols), bars=len(y), pvalue=p,
               pvalue_oos=p_oos, weights=w, half_life=hl_is, half_life_oos=hl_oos,
               net_exposure=net_exposure(w), claim=claim, pvalue_early=p_early,
               pvalue_late=p_late, weights_early=w_early, weights_late=w_late,
               johansen_rank=rank)


def survives(r: Row, args) -> bool:
    """Every gate, in the order `screen.py` applies them."""
    if not (r.pvalue < args.level):
        return False
    if args.require_oos and not (r.pvalue_oos < args.level):
        return False
    if args.require_holdout and not r.holds_out_of_window(
            args.level, require_early=args.require_early):
        return False
    swing = r.weight_swing()
    if math.isfinite(args.max_weight_swing) and not (swing <= args.max_weight_swing):
        return False
    if not (r.net_exposure <= args.max_net_exposure):
        return False
    if not np.all(np.abs(r.weights) >= args.min_abs_weight):
        return False
    return (math.isfinite(r.half_life)
            and args.min_half_life <= r.half_life <= args.max_half_life)


def resolve_groups(args) -> list[tuple[str, list[str], str]]:
    """Named groups, an explicit symbol list, or every combination of a size."""
    if args.symbols:
        syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        if len(syms) < 2:
            raise UserError("a basket needs at least two legs")
        return [("custom", syms, "given on the command line")]
    if args.combinations:
        pool = sorted({s.strip().upper()
                       for s in args.pool.split(",") if s.strip()}) if args.pool else None
        if not pool:
            raise UserError("--combinations needs --pool to say which symbols to draw from")
        if args.combinations > len(pool):
            raise UserError(f"--combinations {args.combinations} exceeds the "
                            f"{len(pool)} symbols in --pool")
        return [(f"comb-{'-'.join(c)}", list(c), "enumerated, no structural claim")
                for c in itertools.combinations(pool, args.combinations)]
    if args.group:
        wanted = [g.strip() for g in args.group.split(",") if g.strip()]
        out = []
        for g in wanted:
            if g not in GROUPS:
                raise UserError(f"unknown group {g!r}. Available: "
                                f"{', '.join(sorted(GROUPS))}")
            out.append((g, GROUPS[g]["symbols"], GROUPS[g]["claim"]))
        return out
    return [(name, spec["symbols"], spec["claim"]) for name, spec in GROUPS.items()]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="basket_screen", description=__doc__.splitlines()[0],
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sel = p.add_argument_group("selection")
    sel.add_argument("--group", help="one or more named groups, comma separated")
    sel.add_argument("-s", "--symbols", help="an explicit basket; the first leg is held "
                                             "long and the rest hedge it")
    sel.add_argument("--combinations", type=int, help="enumerate every basket of this "
                                                      "size from --pool. Each one is a "
                                                      "trial and none carries a "
                                                      "structural claim")
    sel.add_argument("--pool", help="symbols --combinations draws from")
    sel.add_argument("-a", "--asset-class", default="crypto")
    sel.add_argument("-t", "--timeframe", default="1d")
    sel.add_argument("--source")
    sel.add_argument("--start")
    sel.add_argument("--end")

    st = p.add_argument_group("structure - choose once, not per run")
    st.add_argument("--price", choices=("log", "raw"), default="log")
    st.add_argument("--lags", type=int, default=1)

    g = p.add_argument_group("gates - every value is a trial")
    g.add_argument("--split", type=float, default=0.7)
    g.add_argument("--level", type=float, default=0.05)
    g.add_argument("--require-oos", action=argparse.BooleanOptionalAction, default=True)
    g.add_argument("--min-tail", type=int, default=120,
                   help="bars needed before a reserved window is tested at all")
    g.add_argument("--min-abs-weight", type=float, default=0.05,
                   help="a leg carrying less than this is not hedging, it is noise "
                        "the fit could not use")
    g.add_argument("--max-net-exposure", type=float, default=0.35)
    g.add_argument("--min-half-life", type=float, default=2.0)
    g.add_argument("--max-half-life", type=float, default=60.0)
    g.add_argument("--holdout", type=float, default=0.25,
                   help="fraction reserved at EACH end and never seen while ranking")
    g.add_argument("--require-holdout", action=argparse.BooleanOptionalAction,
                   default=True, help="the LATE reserved window must also reject")
    g.add_argument("--require-early", action="store_true",
                   help="demand the early reserved window too")
    g.add_argument("--max-weight-swing", type=float, default=3.0,
                   help="widest allowed ratio between a leg's weights across windows; "
                        "a sign change on any leg is always refused")
    g.add_argument("--min-screen-bars", type=int, default=400)

    c = p.add_argument_group("costs")
    c.add_argument("--broker")
    c.add_argument("--costs-dir", type=Path, default=paths.COSTS)
    c.add_argument("--bars-per-night", type=float,
                   help="financing nights per bar; taken from the asset class and "
                        "timeframe when unset")

    o = p.add_argument_group("output")
    o.add_argument("--store", default=str(paths.STORE))
    o.add_argument("--log", type=Path, default=DEFAULT_LOG)
    o.add_argument("--no-log", action="store_true")
    o.add_argument("--show", type=int, default=20)
    o.add_argument("--dump", type=Path, help="one row per basket, with every p-value")
    o.add_argument("--json", action="store_true")
    o.add_argument("-q", "--quiet", action="store_true")
    return p


def append_log(path: Path, args, r: Row, survived: bool) -> int:
    return triallog.append(path, {
        "run": 0, "stamp": triallog.stamp(), "basket": r.basket, "name": r.name,
        "legs": r.legs, "asset_class": args.asset_class, "timeframe": args.timeframe,
        "price": args.price, "lags": args.lags, "split": args.split,
        "level": args.level, "holdout": args.holdout, "bars": r.bars,
        "p": round(r.pvalue, 6), "p_oos": round(r.pvalue_oos, 6),
        "p_early": round(r.pvalue_early, 6), "p_late": round(r.pvalue_late, 6),
        "weights": ";".join(f"{w:.4f}" for w in r.weights),
        "weight_swing": round(r.weight_swing(), 4),
        "net_exposure": round(r.net_exposure, 4),
        "half_life": round(r.half_life, 3), "half_life_oos": round(r.half_life_oos, 3),
        "johansen_rank": r.johansen_rank, "cost_bps": round(r.cost_bps, 3),
        "survived": int(survived),
    })


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.combinations is not None and args.combinations < 2:
        raise UserError("--combinations needs at least 2 legs")
    if args.holdout < 0 or args.holdout >= 0.5:
        raise UserError("--holdout must be at least 0 and below 0.5")

    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))
    groups = resolve_groups(args)

    profile = None
    if args.broker:
        profile = cs.load_profile(Path(args.costs_dir) / f"{args.broker}.json")
        if not profile:
            raise UserError(f"no cost profile named {args.broker!r}")
    nights = (args.bars_per_night if args.bars_per_night is not None
              else cs.nights_per_bar(args.asset_class, args.timeframe))

    rows, failures = [], []
    for name, syms, claim in groups:
        try:
            r = evaluate(name, syms, args, claim)
        except UserError as exc:
            failures.append(str(exc))
            continue
        if profile is not None and math.isfinite(r.half_life):
            r.cost_bps = basket_cost_bps(syms, profile, r.weights, nights, r.half_life)
        if not args.no_log:
            r.trial_id = append_log(args.log, args, r, survives(r, args))
        rows.append(r)

    if not rows:
        log("no basket could be measured")
        for f in failures:
            log(f"  {f}")
        return 2

    kept = [r for r in rows if survives(r, args)]
    rows.sort(key=lambda r: (not survives(r, args), r.pvalue))

    log(f"\n{len(rows)} basket(s)  {args.timeframe}  "
        f"{args.asset_class}  holdout {args.holdout:g} at each end\n")
    log(f"  {'basket':<26} {'legs':>4} {'p':>8} {'p_oos':>7} {'p_early':>8} "
        f"{'p_late':>7} {'swing':>6} {'net':>5} {'hl':>7} {'rank':>4} {'bars':>8}")
    for r in rows[:args.show]:
        swing = r.weight_swing()
        log(f"  {r.basket:<26} {r.legs:>4} {r.pvalue:>8.4f} {r.pvalue_oos:>7.3f} "
            f"{r.pvalue_early:>8.3f} {r.pvalue_late:>7.3f} "
            f"{swing:>6.2f} {r.net_exposure:>4.0%} {r.half_life:>7.1f} "
            f"{r.johansen_rank:>4} {r.bars:>8,}")

    log("")
    stage = [
        ("cointegrated", sum(1 for r in rows if r.pvalue < args.level)),
        ("and out of sample", sum(1 for r in rows if r.pvalue < args.level
                                  and r.pvalue_oos < args.level)),
        ("and still there now", sum(1 for r in rows if r.pvalue < args.level
                                    and r.pvalue_oos < args.level
                                    and r.holds_out_of_window(args.level))),
        ("and stable weights", sum(1 for r in rows if survives(r, args))),
    ]
    for label, count in stage:
        log(f"  {label:<24} {count:>3}")
    log(f"  noise alone would give about {len(rows) * args.level:.1f} at the first gate")

    if not kept:
        log("\n  no basket survived the statistical gates")
    else:
        log(f"\n  {len(kept)} survivor(s):")
        for r in kept:
            log(f"    {r.basket}  ({r.name}) -- {r.claim}")
            legs = "  ".join(f"{s.replace('-USDT', '')} {w:+.3f}"
                             for s, w in zip(r.symbols[1:], r.weights))
            log(f"      long 1.000 {r.symbols[0].replace('-USDT', '')}  "
                f"against  {legs}")
            log(f"      half-life {r.half_life:.1f} bars in sample, "
                f"{r.half_life_oos:.1f} out; stability {r.stability():.2f}")
            if math.isfinite(r.cost_bps):
                log(f"      round trip plus carry over one half-life: "
                    f"{r.cost_bps:.1f} bps")

    if args.dump:
        args.dump.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([{
            "basket": r.basket, "name": r.name, "legs": r.legs, "bars": r.bars,
            "p": r.pvalue, "p_oos": r.pvalue_oos, "p_early": r.pvalue_early,
            "p_late": r.pvalue_late, "weight_swing": r.weight_swing(),
            "net_exposure": r.net_exposure, "half_life": r.half_life,
            "half_life_oos": r.half_life_oos, "johansen_rank": r.johansen_rank,
            "cost_bps": r.cost_bps, "survived": int(survives(r, args)),
        } for r in rows]).to_csv(args.dump, index=False)
        log(f"\n  {len(rows)} row(s) dumped to {args.dump.resolve()}")

    for f in failures:
        log(f"  skipped: {f}")

    return 0 if kept else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
