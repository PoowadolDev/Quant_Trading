"""Screen a whole universe: every pair, every gate, ranked, with the noise counted.

This replaces the throwaway sweep scripts that kept being written one per
question. Eight of them were produced in a single session, none reproducible
afterwards, and the results were reported anyway. A screen is now a logged run
like any other.

The gates are the ones the rest of the project already uses, applied in order:

1. **cointegration** — Engle-Granger, and again on the held-out tail
2. **hedge quality** — is the ratio a hedge, or are both legs on the same side?
3. **reversion speed** — a half-life inside the intended holding horizon

Every screen prints the number of survivors next to the number noise alone would
produce. A screen that finds five when noise gives five has found nothing.

    python screen.py -u equities --within-sector
    python screen.py -s XLF,XLE,XLK,XLV -a index
    python screen.py -u fx-all -t 4h --max-half-life 30

Exit codes: 0 at least one pair survived every gate, 3 none did, 2 usage error.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import sys
import types
import warnings
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import paths

paths.ensure_code_importable()
paths.ensure_marketdata_importable()

import cointegration as ci                                        # noqa: E402
import hedge as hg                                                # noqa: E402
import pair_report as pr
import scorecard
import relationship as rel                                          # noqa: E402
from marketdata import UNIVERSES                                  # noqa: E402
from marketdata.instruments import (EQUITY_SECTOR_OF,              # noqa: E402
                                    shared_drivers)

UserError = pr.UserError
DEFAULT_LOG = paths.LOGS / "screens.csv"


@dataclass
class Row:
    a: str
    b: str
    bars: int
    pvalue: float
    pvalue_oos: float
    beta: float
    hedge_ok: bool
    half_life: float
    half_life_oos: float
    net_exposure: float = float("nan")
    sector: str = ""
    pvalue_early: float = float("nan")     # reserved window before the screen
    pvalue_late: float = float("nan")      # reserved window after it
    beta_early: float = float("nan")
    beta_late: float = float("nan")

    def holdout_pvalues(self) -> list:
        """The reserved windows that were long enough to test."""
        return [p for p in (self.pvalue_early, self.pvalue_late) if math.isfinite(p)]

    def holds_out_of_window(self, level: float, *, require_early: bool = False) -> bool:
        """Does the relationship exist outside the window it was selected in,
        and is it still there now?

        The **late** reserved window decides, because that is the only one that
        answers the question a trader is asking. "At least one window" was the
        first version of this rule and it was wrong: `NUE~STLD` cleared it on
        p_early = 0.001 with p_late = 0.648, and the era table shows the
        relationship rejecting in 1996-2000 and in no period since. A
        relationship that died in 2001 is not tradeable in 2026, whatever the
        oldest quarter of the record says.

        The early window is still reported, and `require_early` demands it too,
        because a relationship present before *and* after the selection window is
        stronger evidence than one present only after it.
        """
        if not math.isfinite(self.pvalue_late):
            return False
        if not (self.pvalue_late < level):
            return False
        if require_early:
            return math.isfinite(self.pvalue_early) and self.pvalue_early < level
        return True

    def beta_swing(self) -> float:
        """Widest ratio between the hedge ratios fitted on each window.

        A relationship worth trading has roughly the same hedge ratio whenever
        it is measured. `XLP~XLB` ran from +0.079 to +1.343 and `ALL~TRV` from
        +0.147 to +1.331, which is what a coincidence looks like when it is
        measured in more than one place.
        """
        betas = [b for b in (self.beta, self.beta_early, self.beta_late)
                 if math.isfinite(b) and b != 0.0]
        if len(betas) < 2:
            return float("nan")
        lo, hi = min(betas), max(betas)
        if lo <= 0 < hi or hi <= 0 < lo:
            return float("inf")            # the sign changes; not one relationship
        lo, hi = sorted((abs(lo), abs(hi)))
        return hi / lo if lo > 0 else float("inf")

    @property
    def pair(self) -> str:
        return f"{self.a}~{self.b}"

    def stability(self) -> float:
        """Ratio of the slower half-life to the faster. 1.0 is perfect agreement."""
        if not (math.isfinite(self.half_life) and math.isfinite(self.half_life_oos)):
            return math.inf
        lo, hi = sorted((self.half_life, self.half_life_oos))
        return hi / lo if lo > 0 else math.inf


def _window(y: np.ndarray, x: np.ndarray, lags, min_bars: int) -> tuple:
    """Engle-Granger p-value and hedge ratio on one slice, or NaN if too short."""
    if len(y) < min_bars:
        return float("nan"), float("nan")
    p = ci.engle_granger(y, x, trend="c", lags=lags).pvalue
    beta, _ = rel.ols_beta(y, x)
    return p, beta


def evaluate(a: str, b: str, args) -> Row:
    sel = types.SimpleNamespace(
        symbols=f"{a},{b}", asset_class=args.asset_class, timeframe=args.timeframe,
        source=args.source, start=args.start, end=args.end, price=args.price,
        split=args.split, store=args.store)
    px = pr.load_prices(sel)
    lp = np.log(px) if args.price == "log" else px
    y_all, x_all = lp[a].to_numpy(float), lp[b].to_numpy(float)

    # Reserve a slice at each end and never look at it while ranking. The whole
    # of this project's history of false candidates is the same mistake: the
    # window was chosen along with the pair, so "out of sample" was still inside
    # the choice. A tail split of the screening window cannot catch that; only
    # data the screen never saw can.
    n = len(px)
    cut = int(n * args.holdout)
    lo, hi = (cut, n - cut) if cut > 0 else (0, n)
    if hi - lo < args.min_screen_bars:
        raise UserError(f"{a}~{b}: --holdout {args.holdout:g} leaves {hi - lo} bars "
                        f"to screen on, below --min-screen-bars {args.min_screen_bars}")

    y, x = y_all[lo:hi], x_all[lo:hi]
    split = int(len(y) * args.split)

    p = ci.engle_granger(y, x, trend="c", lags=args.lags).pvalue
    tail = len(y) - split
    p_oos = (ci.engle_granger(y[split:], x[split:], trend="c", lags=args.lags).pvalue
             if tail >= args.min_tail else float("nan"))
    p_early, beta_early = _window(y_all[:lo], x_all[:lo], args.lags, args.min_tail)
    p_late, beta_late = _window(y_all[hi:], x_all[hi:], args.lags, args.min_tail)

    est = hg.evaluate("static", hg.static_beta(y, x, split), y, x, split)
    # Forex neutrality is measured in currency space: see `hg.fx_net_exposure`.
    # For every other asset class this returns the ordinary leg-space figure.
    net = hg.fx_net_exposure(a, b, est.beta_final)
    return Row(a=a, b=b, bars=len(y), pvalue=p, pvalue_oos=p_oos,
               beta=est.beta_final,
               hedge_ok=(est.usable(args.min_abs_beta, args.max_negative_share,
                                    args.max_net_exposure)
                         or (net <= args.max_net_exposure
                             and abs(est.beta_final) >= args.min_abs_beta)),
               net_exposure=net,
               half_life=est.half_life_is, half_life_oos=est.half_life_oos,
               sector=EQUITY_SECTOR_OF.get(a, "") if
               EQUITY_SECTOR_OF.get(a) == EQUITY_SECTOR_OF.get(b) else "",
               pvalue_early=p_early, pvalue_late=p_late,
               beta_early=beta_early, beta_late=beta_late)


def survives(r: Row, args) -> bool:
    """Did this pair clear every gate?

    Kept as a boolean because the funnel counts and the exit code are boolean questions.
    It now delegates to `scorecard.assess`, which evaluates every gate rather than
    stopping at the first failure, so the verdict and the reasons come from one place and
    cannot disagree. The old short-circuit is gone; the answer it produced is not.
    """
    return scorecard.assess(r, args).all_pass()


def grade(r: Row, args, *, economics: str | None = None) -> tuple:
    """The full scorecard and the tier that follows from it.

    A pair that fails one gate is not the same as a pair that fails all of them, and it is
    not the same as a pair that could not be tested. `survives` collapses those into one
    `False`; this keeps them apart so a later pass can ask which rejections a book might
    fix and which are final.
    """
    card = scorecard.assess(r, args)
    return card, scorecard.tier(card, economics=economics)


def confirm_with_trades(rows: list, args, log) -> list:
    """Put the statistical survivors through the Step 3 questions.

    The cheap gates run on every pair; this runs on the handful that got past
    them, because it replays the strategy and that costs real time. The order is
    the point: statistics first because they are cheap, trades last because they
    are decisive.

    All three of these killed every candidate this project has ever had, so a
    screen that does not ask them reports pairs that Step 3 will reject an hour
    later.
    """
    import costs as cost_model
    import outcomes as oc
    import sizing as sz
    import strategy as sig
    import thresholds as th
    import backtest as bt

    profile = cost_model.load_profile(Path(args.costs_dir) / f"{args.broker}.json")
    if not profile:
        raise UserError(f"no cost profile named {args.broker!r}")

    kept = []
    missing: set = set()
    log("")
    log(f"  {'pair':20s} {'over by':>10s} {'floor':>7s} {'mu-1se':>9s} {'size':>6s}"
        "  verdict")
    for r in rows:
        # A screen must not stop because one leg has no broker entry. Report the
        # pair as unconfirmed, name what is missing at the end, and carry on with
        # the rest — a run that aborts on pair three tells you nothing about the
        # other hundred.
        absent = [leg for leg in (r.a, r.b) if leg not in profile]
        if absent:
            missing.update(absent)
            log(f"  {r.pair:20s} {'no costs':>10s}"
                f"{'':>25s}  not confirmed")
            continue
        sel = types.SimpleNamespace(
            symbols=f"{r.a},{r.b}", asset_class=args.asset_class,
            timeframe=args.timeframe, source=args.source, start=args.start,
            end=args.end, store=args.store)
        px = pr.load_prices(sel)
        nights = (args.bars_per_night if args.bars_per_night is not None
                  else cost_model.nights_per_bar(
                      (args.asset_class or "index").split(",")[0], args.timeframe))
        params = sig.SignalParams(entry_z=2.0, exit_z=0.5, stop_z=4.0,
                                  max_holding_bars=20, fit_window=250,
                                  rehedge_every=5, use_log=args.price == "log")
        sigma, half_life = oc.traded_sigma(px, params)
        if not (math.isfinite(sigma) and sigma > 0):
            log(f"  {r.pair:20s} {'no OU fit':>10s}")
            continue

        try:
            cmp_, floor, lower, lev = _confirm_one(
                px, profile, params, r, args, nights, sigma, half_life,
                oc, th, sz, bt)
        except Exception as exc:                                  # noqa: BLE001
            log(f"  {r.pair:20s} {type(exc).__name__:>10s}"
                f"{'':>25s}  not confirmed")
            continue
        over_ok = (math.isfinite(cmp_.overstatement)
                   and cmp_.overstatement <= args.max_overstatement)
        ok = over_ok and math.isfinite(floor) and lev > 0
        over = ("sign" if not math.isfinite(cmp_.overstatement)
                else f"{cmp_.overstatement:.1f}x")
        log(f"  {r.pair:20s} {over:>10s} "
            f"{(format(floor, '.2f') if math.isfinite(floor) else 'none'):>7s} "
            f"{lower:>+9.1f} {lev:>6.2f}  {'KEPT' if ok else 'rejected'}")
        if ok:
            kept.append(r)
    if missing:
        log(f"  {len(missing)} instrument(s) have no entry in the {args.broker!r} "
            f"profile: {', '.join(sorted(missing))}")
        log(f"     add them with: python costs.py add -s <SYMBOL> --broker "
            f"{args.broker} ...")
    return kept


def _confirm_one(px, profile, params, r, args, nights, sigma, half_life,
                 oc, th, sz, bt):
    """The three Step 3 questions for one pair.

    Returns the comparison, the measured entry floor, the uncertainty-adjusted
    mean and the leverage it justifies. Raises rather than guessing, so the
    caller can record the pair as unconfirmed and carry on.
    """
    cmp_ = oc.compare(px, profile, params, static_sigma=sigma,
                      static_half_life=half_life, warmup=260,
                      bars_per_night=nights, lag=1)

    beta = r.beta
    direction = bt.cheaper_direction(profile, r.a, r.b, beta)
    grid = th.measure_grid(
        px, profile, params, [1.0, 1.5, 2.0, 2.5, 3.0],
        transaction_bps=bt.round_trip_bps(profile, r.a, r.b, direction, beta),
        carry_per_night_bps=-bt.carry_per_night_bps(profile, r.a, r.b,
                                                    direction, beta),
        bars_per_night=nights, min_edge=2.0, warmup=260, lag=1,
        static_sigma=sigma)
    floor = th.measured_floor(grid, 20)

    result = bt.run_backtest(px, profile, params, warmup=260,
                             bars_per_night=nights, lag=1)
    try:
        size = sz.size_from_trades(r.pair, [t.net_bps for t in result.trades],
                                   confidence=1.0, max_leverage=1.0, equity=1.0)
        lower, lev = size.mu_lower_bps, size.capped_leverage
    except UserError:
        # Too few finished trades to form a mean. Not an error in the screen;
        # an answer about the pair, and the answer is no.
        lower, lev = float("nan"), 0.0

    return cmp_, floor, lower, lev


def resolve_universe(args) -> list[str]:
    if args.universe:
        if args.universe not in UNIVERSES:
            raise UserError(f"unknown universe {args.universe!r}; available: "
                            f"{', '.join(sorted(UNIVERSES))}")
        spec = UNIVERSES[args.universe]
        args.asset_class = args.asset_class or spec["asset_class"]
        return list(spec["symbols"])
    if not args.symbols:
        raise UserError("pass --universe or --symbols")
    if not args.asset_class:
        raise UserError("--asset-class is required with explicit symbols")
    return [s.strip().upper() for s in args.symbols.split(",") if s.strip()]


#: Every gate and structural choice a screen makes, recorded beside each pair it judged.
#:
#: The existing `--dump` carries results without parameters and `logs/screens.csv` carries
#: parameters without per-pair results, so neither can answer "which threshold would have
#: changed this pair's verdict". Keeping both halves in one row is what makes the file a
#: parameter surface rather than an archive.
#:
#: Order matters and is fixed: identity, then result, then the inputs. A reader scanning
#: left to right meets the pair, what happened to it, and only then why.
RESEARCH_PARAMS = (
    "price", "lags", "split", "level", "holdout", "min_tail",
    "min_abs_beta", "max_negative_share", "max_net_exposure",
    "min_half_life", "max_half_life", "max_beta_swing", "min_screen_bars",
    "require_oos", "require_link", "within_sector", "require_early",
    "broker", "bars_per_night", "max_overstatement",
)


def append_research_log(path: Path, args, tested: list, passed: list) -> int:
    """One row per pair tested, with the parameters that produced the verdict.

    Appended rather than overwritten, because the point is the accumulated surface across
    runs. The run number ties a block of rows back to `logs/screens.csv`, so the two files
    join on it.

    `survived` is recorded per pair rather than only counted, which is the column a future
    optimisation actually needs: it turns the file into labelled data instead of a log.
    """
    survivors = {r.pair for r in passed}
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    existing, runs = 0, 0
    if path.exists() and path.stat().st_size:
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            header = reader.fieldnames or []
            seen = set()
            for line in reader:
                existing += 1
                seen.add(line.get("run", ""))
            runs = len(seen)
        if header and header[0] != "run":
            raise UserError(f"{path} was written by an older version; rename it to keep "
                            "the history and a fresh log will start")

    rows = []
    for r in tested:
        row = {"run": runs + 1, "run_utc": stamp,
               "universe": args.universe or "custom",
               "asset_class": args.asset_class, "timeframe": args.timeframe,
               "start": args.start or "", "end": args.end or "",
               "pair": r.pair, "a": r.a, "b": r.b, "sector": r.sector, "bars": r.bars,
               "pvalue": _round(r.pvalue), "pvalue_oos": _round(r.pvalue_oos),
               "pvalue_early": _round(r.pvalue_early), "pvalue_late": _round(r.pvalue_late),
               "beta": _round(r.beta), "beta_early": _round(r.beta_early),
               "beta_late": _round(r.beta_late), "beta_swing": _round(r.beta_swing()),
               "hedge_ok": "yes" if r.hedge_ok else "no",
               "half_life": _round(r.half_life), "half_life_oos": _round(r.half_life_oos),
               "net_exposure": _round(r.net_exposure),
               "survived": "yes" if r.pair in survivors else "no"}
        for name in RESEARCH_PARAMS:
            value = getattr(args, name, "")
            row[name] = "" if value is None else value
        rows.append(row)

    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        if write_header:
            writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def _round(value, places: int = 6):
    """Blank rather than `nan`, so a spreadsheet reads the column as empty not as text."""
    try:
        return round(float(value), places) if math.isfinite(float(value)) else ""
    except (TypeError, ValueError):
        return ""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="screen", description=__doc__.splitlines()[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sel = p.add_argument_group("selection")
    sel.add_argument("-u", "--universe", default=None, help="a named symbol set")
    sel.add_argument("-s", "--symbols", default=None, help="or an explicit list")
    sel.add_argument("-a", "--asset-class", default=None)
    sel.add_argument("-t", "--timeframe", default="1d")
    sel.add_argument("--source", default=None)
    sel.add_argument("--start", default=None)
    sel.add_argument("--end", default=None)
    sel.add_argument("--require-link", action=argparse.BooleanOptionalAction,
                     default=True,
                     help="only pair instruments that share a named driver — the "
                          "same sector, the same currency leg, the same commodity. "
                          "`XLP~XLB` was this project's best result for a day and "
                          "consumer staples share nothing with materials; the "
                          "screen had no way to say so")
    sel.add_argument("--within-sector", action="store_true",
                     help="only pair instruments from the same sector. Fourteen times "
                          "fewer tests on the equity universe, and every test avoided is "
                          "a false positive avoided")

    struct = p.add_argument_group("structure - choose once, not per run")
    struct.add_argument("--price", default="log", choices=("log", "raw"))
    struct.add_argument("--lags", default=1, type=lambda v: int(v) if str(v).isdigit() else v,
                        help="a fixed lag keeps every pair comparable and the screen quick")

    gates = p.add_argument_group("gates - every value is a trial")
    gates.add_argument("--split", type=float, default=0.70)
    gates.add_argument("--level", type=float, default=0.05)
    gates.add_argument("--require-oos", action=argparse.BooleanOptionalAction, default=True)
    gates.add_argument("--min-tail", type=int, default=120,
                       help="bars needed before the held-out tail is tested at all")
    gates.add_argument("--min-abs-beta", type=float, default=0.10)
    gates.add_argument("--max-negative-share", type=float, default=0.10)
    gates.add_argument("--max-net-exposure", type=float, default=0.35,
                       help="net over gross exposure; above this the position is a "
                            "single-name bet rather than a spread")
    gates.add_argument("--min-half-life", type=float, default=2.0)
    gates.add_argument("--max-half-life", type=float, default=60.0)
    gates.add_argument("--holdout", type=float, default=0.25,
                       help="fraction of the record reserved at EACH end and never "
                            "seen while ranking. 0 screens on everything, which is "
                            "how this project produced two candidates that existed "
                            "only in the window that selected them")
    gates.add_argument("--require-holdout", action=argparse.BooleanOptionalAction,
                       default=True,
                       help="the LATE reserved window — the most recent data, which "
                            "the screen never saw — must also reject. The late one "
                            "and not just any one: a relationship that held only in "
                            "the oldest quarter died decades ago")
    gates.add_argument("--require-early", action="store_true",
                       help="also demand the early reserved window. Stronger, and "
                            "rules out a relationship that only began recently")
    gates.add_argument("--max-beta-swing", type=float, default=3.0,
                       help="widest allowed ratio between the hedge ratios fitted on "
                            "each window; a sign change is always refused. The two "
                            "pairs this project rejected swung by 17x and 9x")
    gates.add_argument("--min-screen-bars", type=int, default=400,
                       help="bars that must remain after the holdout is reserved")

    trades = p.add_argument_group("confirmation by replay - needs a broker")
    trades.add_argument("--broker", default=None,
                        help="run the Step 3 questions on whatever survives the "
                             "statistical gates: does the expected move describe "
                             "the trades, does any threshold pay, is any size "
                             "justified. All three killed every candidate so far")
    trades.add_argument("--costs-dir", default=str(paths.COSTS))
    trades.add_argument("--bars-per-night", type=float, default=None)
    trades.add_argument("--max-overstatement", type=float, default=3.0)

    out = p.add_argument_group("output")
    out.add_argument("--store", default=str(paths.STORE))
    out.add_argument("--log", default=str(DEFAULT_LOG))
    out.add_argument("--no-log", action="store_true")
    out.add_argument("--show", type=int, default=15, help="rows printed")
    out.add_argument("--research-log", default=str(paths.LOGS / "pair_research.csv"),
                     metavar="PATH",
                     help="append one row per pair tested, carrying both the result and "
                          "every gate value that produced it, so a later optimisation can "
                          "read the parameter surface without re-running the screen")
    out.add_argument("--no-research-log", action="store_true")
    out.add_argument("--dump", default=None, metavar="PATH",
                     help="write one row per pair, with every p-value, so the "
                          "multiple-testing correction can be computed without "
                          "re-running the screen")
    out.add_argument("--json", action="store_true")
    out.add_argument("-q", "--quiet", action="store_true")
    out.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))
    warnings.filterwarnings("ignore")

    names = resolve_universe(args)
    klass = args.asset_class or ""
    candidates = list(itertools.combinations(names, 2))
    pairs, unlinked = [], []
    for a, b in candidates:
        if args.within_sector and not (
                EQUITY_SECTOR_OF.get(a)
                and EQUITY_SECTOR_OF.get(a) == EQUITY_SECTOR_OF.get(b)):
            continue
        if args.require_link and not shared_drivers(a, b, klass):
            unlinked.append((a, b))
            continue
        pairs.append((a, b))
    if not pairs:
        raise UserError(
            f"no pairs left to screen: {len(unlinked)} of {len(candidates)} share no "
            "driver and the rest were filtered out. Use --no-require-link to screen "
            "them anyway, and read the warning it prints.")

    rows: list[Row] = []
    failures: dict[str, int] = {}
    for a, b in pairs:
        try:
            rows.append(evaluate(a, b, args))
        except Exception as exc:                                  # noqa: BLE001
            key = f"{type(exc).__name__}: {str(exc)[:60]}"
            failures[key] = failures.get(key, 0) + 1

    log(f"{args.universe or 'custom'}  {len(names)} instruments  {args.timeframe}  "
        f"{len(pairs)} pairs"
        + ("  within sector only" if args.within_sector else ""))
    if unlinked:
        log(f"  {len(unlinked)} pair(s) skipped for sharing no driver, "
            f"{len(pairs)} kept. Every test avoided is a false positive avoided.")
        for a, b in unlinked[:3]:
            log(f"     {a}~{b}")
    elif not args.require_link:
        log("  WARNING: --no-require-link. Pairs with no shared driver are being "
            "tested, which is how `XLP~XLB` became a candidate.")
    for why, n in sorted(failures.items(), key=lambda kv: -kv[1])[:3]:
        log(f"  {n} could not be evaluated: {why}")
    if not rows:
        raise UserError("every pair failed to load")

    coint = [r for r in rows if r.pvalue < args.level]
    both = [r for r in coint if r.pvalue_oos < args.level]
    outside = [r for r in both
               if r.holds_out_of_window(args.level,
                                        require_early=args.require_early)]
    stable = [r for r in outside
              if not math.isfinite(args.max_beta_swing)
              or r.beta_swing() <= args.max_beta_swing]
    hedged = [r for r in stable if r.hedge_ok]
    passed = [r for r in rows if survives(r, args)]

    # A screen that finds what noise would find has found nothing. The first
    # gate is the only one with a clean null, so that is where the comparison
    # belongs; the later gates only narrow it further.
    expected = len(rows) * args.level
    # Each reserved window is a second chance to reject, so under a true null the
    # joint probability is the screening rejection times the chance that at least
    # one holdout also rejects. Stating it is the point of the screen.
    windows = max(1, sum(1 for r in rows if r.holdout_pvalues()) and
                  max(len(r.holdout_pvalues()) for r in rows))
    joint = args.level * (1.0 - (1.0 - args.level) ** windows)
    expected_holdout = len(rows) * joint
    log("")
    log(f"  cointegrated          {len(coint):4d}   noise alone would give about "
        f"{expected:.0f}")
    log(f"  and out of sample     {len(both):4d}")
    if args.holdout > 0:
        which = "both reserved windows" if args.require_early else "the late window"
        log(f"  and still there now  {len(outside):4d}   noise would give about "
            f"{expected_holdout:.1f}; gate is {which}")
        log(f"  and a stable ratio    {len(stable):4d}")
    log(f"  and a usable hedge    {len(hedged):4d}")
    log(f"  and reverting in time {len(passed):4d}   <- survivors")
    if len(coint) <= expected:
        log("  The first gate found no more than chance would. Treat everything below "
            "as noise.")
    if args.holdout <= 0:
        log("  WARNING: --holdout 0 screens and tests on the same record. Two "
            "candidates were produced this way and both were wrong.")

    confirmed = None
    if args.broker and passed:
        confirmed = confirm_with_trades(passed, args, log)
        log("")
        log(f"  survived the trades  {len(confirmed):4d}   <- survivors")
        passed = confirmed
    elif args.broker:
        log("")
        log("  nothing reached the replay: no pair survived the statistical gates")

    ranked = sorted(passed or hedged or both or coint,
                    key=lambda r: (r.stability(), r.pvalue))
    log("")
    log(f"  {'pair':20s} {'sector':11s} {'p':>7s} {'p_oos':>7s} {'p_early':>8s} "
        f"{'p_late':>7s} {'beta':>7s} {'swing':>6s} {'net':>5s} {'hl':>6s} "
        f"{'bars':>7s}")
    def num(v, fmt, blank="  —"):
        return format(v, fmt) if math.isfinite(v) else blank

    for r in ranked[: args.show]:
        log(f"  {r.pair:20s} {r.sector:11s} {r.pvalue:7.4f} {r.pvalue_oos:7.3f} "
            f"{num(r.pvalue_early, '8.3f'):>8s} {num(r.pvalue_late, '7.3f'):>7s} "
            f"{r.beta:+7.3f} {num(r.beta_swing(), '6.2f'):>6s} "
            f"{r.net_exposure:5.0%} {num(r.half_life, '6.0f'):>6s} {r.bars:7,d}")

    if args.dump:
        dump = Path(args.dump)
        dump.parent.mkdir(parents=True, exist_ok=True)
        with dump.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(asdict(rows[0])))
            writer.writeheader()
            for r in rows:
                writer.writerow(asdict(r))
        log(f"  {len(rows)} row(s) dumped to {dump.resolve()}")

    if not args.no_research_log:
        written = append_research_log(Path(args.research_log), args, rows, passed)
        log(f"  {written} row(s) appended to {Path(args.research_log).resolve()}")

    if args.json:
        print(json.dumps({"universe": args.universe, "pairs": len(rows),
                          "cointegrated": len(coint), "expected_by_chance": expected,
                          "survivors": [asdict(r) for r in passed]},
                         indent=2, default=str))

    if not args.no_log:
        path = Path(args.log)
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {"run": 0,
               "run_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "universe": args.universe or "custom", "asset_class": args.asset_class,
               "timeframe": args.timeframe, "within_sector": args.within_sector,
               "require_link": args.require_link, "unlinked_skipped": len(unlinked),
               "pairs": len(rows), "level": args.level, "split": args.split,
               "lags": args.lags, "require_oos": args.require_oos,
               "min_half_life": args.min_half_life, "max_half_life": args.max_half_life,
               "holdout": args.holdout, "require_holdout": args.require_holdout,
               "require_early": args.require_early,
               "max_beta_swing": args.max_beta_swing,
               "cointegrated": len(coint), "expected_by_chance": round(expected, 1),
               "out_of_sample": len(both),
               "outside_window": len(outside),
               "expected_outside_by_chance": round(expected_holdout, 2),
               "stable_ratio": len(stable), "hedged": len(hedged),
               "broker": args.broker or "",
               "confirmed_by_trades": "" if confirmed is None else len(confirmed),
               "survivors": len(passed),
               "top": ";".join(r.pair for r in ranked[:5])}
        existing = 0
        if path.exists():
            with path.open(newline="", encoding="utf-8") as fh:
                header = next(csv.reader(fh), [])
                existing = sum(1 for _ in csv.reader(fh))
            if header and header != list(row):
                raise UserError(f"{path} was written by an older version; rename it")
        row["run"] = existing + 1
        write_header = not path.exists() or path.stat().st_size == 0
        with path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(row))
            if write_header:
                writer.writeheader()
            writer.writerow(row)
        log(f"\n  screen #{row['run']} logged to {path.resolve()}")
    return 0 if passed else 3


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
