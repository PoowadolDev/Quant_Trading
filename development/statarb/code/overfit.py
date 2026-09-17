"""Step 4.3 — the probability that a chosen configuration was chosen by noise.

A parameter sweep always has a best cell. The question is whether that cell is
best because the configuration is good or because the sweep was long enough for
something to look good. `XLP~XLB` swept from -3,678 to +3,747 basis points
across twelve cells; picking the top of that is picking a draw.

Combinatorially symmetric cross-validation answers it without assuming anything
about the return distribution:

1. Cut the return series into S blocks of equal length.
2. For every way of choosing S/2 of them as a training set — hence
   *combinatorially symmetric*, every block appears in training exactly as often
   as in testing — find the configuration with the best in-sample performance.
3. Record where that configuration ranks out of sample.
4. The probability of backtest overfitting is the share of splits where the
   in-sample winner lands in the bottom half out of sample.

A strategy with a real edge keeps its ranking: PBO near zero. A sweep over noise
does not: PBO near or above one half, because the in-sample winner is whichever
cell got lucky and luck does not repeat.

    python overfit.py -s NUE,STLD -a equity --broker equity
    python overfit.py -s XLP,XLB -a index --broker etf --blocks 14
    python overfit.py -s RSG,WM -a equity --broker equity --entry-grid 1,1.5,2,2.5,3

Exit codes: 0 the choice looks robust, 3 it looks overfit, 2 usage error.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import paths

paths.ensure_code_importable()

import costs as cost_model                                        # noqa: E402
import pair_report as pr                                          # noqa: E402
import outcomes as oc                                             # noqa: E402
import strategy as sig                                            # noqa: E402
import triallog                                                   # noqa: E402
from deflated_sharpe import sharpe                                # noqa: E402

UserError = pr.UserError
DEFAULT_LOG = paths.LOGS / "overfit.csv"


@dataclass
class Result:
    """What the splits said about the configuration a sweep would have picked."""

    configurations: int
    blocks: int
    splits: int
    logits: np.ndarray
    chosen: list                    # the in-sample winner of each split
    labels: list

    @property
    def pbo(self) -> float:
        """Share of splits where the in-sample winner underperformed out of sample."""
        if not self.logits.size:
            return float("nan")
        return float(np.mean(self.logits <= 0.0))

    @property
    def median_logit(self) -> float:
        return float(np.median(self.logits)) if self.logits.size else float("nan")

    def chosen_counts(self) -> dict:
        """How often each configuration won in sample.

        A sweep whose winner changes every split has no winner; one that picks
        the same cell every time is at least stable, whatever else it is.
        """
        out: dict = {}
        for i in self.chosen:
            out[self.labels[i]] = out.get(self.labels[i], 0) + 1
        return out


def logit(rank: float, count: int) -> float:
    """Log-odds that an out-of-sample rank is in the upper half.

    `rank` is one-based, with 1 the worst. The relative rank is bounded away
    from zero and one so a clean sweep does not produce an infinite logit and
    take the median with it.
    """
    if count < 2:
        return float("nan")
    w = rank / (count + 1.0)
    w = min(max(w, 1e-9), 1 - 1e-9)
    return math.log(w / (1.0 - w))


def cscv(matrix: np.ndarray, blocks: int, labels: list) -> Result:
    """Combinatorially symmetric cross-validation over a performance matrix.

    `matrix` is observations by configurations: one column per cell of the
    sweep, one row per period, and the columns must be aligned in time. That
    alignment is what lets a split be taken by rows.
    """
    rows, cols = matrix.shape
    if cols < 2:
        raise UserError(f"CSCV needs at least two configurations, got {cols}")
    if blocks < 4 or blocks % 2:
        raise UserError(f"--blocks {blocks} must be even and at least four")
    if rows < blocks * 2:
        raise UserError(f"{rows} observation(s) will not divide into {blocks} "
                        "blocks with enough in each; shorten the block count or "
                        "lengthen the sample")

    edges = np.array_split(np.arange(rows), blocks)
    logits, chosen = [], []
    for train_ids in itertools.combinations(range(blocks), blocks // 2):
        test_ids = [b for b in range(blocks) if b not in train_ids]
        train = np.concatenate([edges[b] for b in train_ids])
        test = np.concatenate([edges[b] for b in test_ids])

        in_sample = np.array([sharpe(matrix[train, c]) for c in range(cols)])
        out_sample = np.array([sharpe(matrix[test, c]) for c in range(cols)])
        if not np.isfinite(in_sample).any() or not np.isfinite(out_sample).any():
            continue

        best = int(np.nanargmax(np.where(np.isfinite(in_sample), in_sample, -np.inf)))
        finite = np.where(np.isfinite(out_sample), out_sample, -np.inf)
        # One-based rank of the chosen column out of sample, 1 being the worst.
        rank = float(np.sum(finite <= finite[best]))
        logits.append(logit(rank, cols))
        chosen.append(best)

    return Result(configurations=cols, blocks=blocks, splits=len(logits),
                  logits=np.array(logits, dtype=float), chosen=chosen,
                  labels=labels)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="overfit", description=__doc__.splitlines()[0],
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
    struct.add_argument("--hedge-source", default="rolling",
                        choices=("static", "rolling"))
    struct.add_argument("--fit-window", type=int, default=250)
    struct.add_argument("--rehedge-every", type=int, default=5)

    sweep = p.add_argument_group("the sweep being judged")
    sweep.add_argument("--entry-grid", default="1.0,1.5,2.0,2.5,3.0")
    sweep.add_argument("--holding-grid", default="20",
                       help="maximum holding periods to cross with the thresholds")
    sweep.add_argument("--exit-z", type=float, default=0.5)
    sweep.add_argument("--stop-z", type=float, default=4.0)
    sweep.add_argument("--warmup", type=int, default=260)
    sweep.add_argument("--blocks", type=int, default=10,
                       help="even number of blocks; the split count is "
                            "'blocks choose blocks/2' and grows fast")
    sweep.add_argument("--max-pbo", type=float, default=0.50,
                       help="above this the choice is called overfit")

    given = p.add_argument_group("given by reality")
    given.add_argument("--broker", required=True)
    given.add_argument("--costs-dir", default=str(cost_model.DEFAULT_COSTS))
    given.add_argument("--bars-per-night", type=float, default=None)
    given.add_argument("--lag", type=int, default=1)

    out = p.add_argument_group("output")
    out.add_argument("--store", default=str(paths.STORE))
    out.add_argument("--log", default=str(DEFAULT_LOG))
    out.add_argument("--no-log", action="store_true")
    out.add_argument("--json", action="store_true")
    out.add_argument("-q", "--quiet", action="store_true")
    out.add_argument("-v", "--verbose", action="store_true")
    return p


def performance_matrix(px, profile, args, log) -> tuple:
    """Bar-by-bar net return for every cell of the sweep, aligned in time.

    Bar returns rather than trade returns, because CSCV splits by period and
    two configurations do not place their trades on the same bars. A matrix of
    trades could not be split by rows at all.
    """
    import backtest as bt

    entries = oc.parse_levels(args.entry_grid, "--entry-grid")
    holds = [int(v) for v in oc.parse_levels(args.holding_grid, "--holding-grid")]
    if any(h < 1 for h in holds):
        raise UserError("--holding-grid counts bars, so every value is at least one")

    columns, labels = [], []
    for entry_z in entries:
        for hold in holds:
            try:
                params = sig.SignalParams(
                    entry_z=entry_z, exit_z=args.exit_z, stop_z=args.stop_z,
                    max_holding_bars=hold, hedge_source=args.hedge_source,
                    fit_window=args.fit_window, rehedge_every=args.rehedge_every,
                    use_log=args.price == "log")
            except ValueError:
                continue                       # outside the stop, or below the exit
            result = bt.run_backtest(px, profile, params, warmup=args.warmup,
                                     bars_per_night=args.bars_per_night,
                                     lag=args.lag)
            equity = np.concatenate([[0.0], result.equity_net])
            columns.append(np.diff(equity))
            labels.append(f"z{entry_z:g}/h{hold}")
    if len(columns) < 2:
        raise UserError("the sweep produced fewer than two usable configurations")
    log(f"  {len(columns)} configuration(s) replayed")
    return np.column_stack(columns), labels


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    warnings.filterwarnings("ignore")
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))

    if not 0 < args.max_pbo < 1:
        raise UserError(f"--max-pbo {args.max_pbo:g} is a probability")

    profile = cost_model.load_profile(Path(args.costs_dir) / f"{args.broker}.json")
    if not profile:
        raise UserError(f"no cost profile named {args.broker!r}")

    px = pr.load_prices(args)
    if args.bars_per_night is None:
        first = args.asset_class.split(",")[0].strip().lower()
        args.bars_per_night = cost_model.nights_per_bar(first, args.timeframe)

    pair = " ~ ".join(px.columns)
    log(f"{pair}  {args.timeframe}  {len(px):,} bars  broker {args.broker}")
    matrix, labels = performance_matrix(px, profile, args, log)
    result = cscv(matrix, args.blocks, labels)

    log(f"  {result.blocks} blocks, {result.splits} split(s) of "
        f"{result.blocks // 2} against {result.blocks // 2}")
    log("")
    log(f"  probability of backtest overfitting  {result.pbo:6.1%}")
    log(f"  median out-of-sample log-odds        {result.median_logit:+6.2f}   "
        "negative means the winner tends to land in the bottom half")
    log("")
    counts = result.chosen_counts()
    log("  which cell won in sample, and how often")
    for label, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        log(f"     {label:<12s} {n:4d} of {result.splits}  "
            f"{n / result.splits:5.0%}")
    if len(counts) == 1:
        log("     One cell wins every split. That is stability, not evidence: a "
            "consistently lucky cell looks exactly like this.")

    overfit = result.pbo > args.max_pbo
    log("")
    if overfit:
        log(f"  OVERFIT — the in-sample winner underperforms out of sample on "
            f"{result.pbo:.0%} of splits, above the {args.max_pbo:.0%} limit.")
        log("  Whatever this sweep selected, it selected noise.")
    else:
        log(f"  HOLDS UP — the in-sample winner keeps its ranking on "
            f"{1 - result.pbo:.0%} of splits.")
        log("  That says the choice is not an artefact of the sweep. It says "
            "nothing about whether the strategy makes money.")

    if not args.no_log:
        row = {
            "run": 0, "run_utc": triallog.stamp(), "pair": pair,
            "timeframe": args.timeframe, "broker": args.broker,
            "start": args.start or "", "end": args.end or "",
            "entry_grid": args.entry_grid, "holding_grid": args.holding_grid,
            "configurations": result.configurations,
            "blocks": result.blocks, "splits": result.splits,
            "pbo": round(result.pbo, 4),
            "median_logit": round(result.median_logit, 4),
            "distinct_winners": len(counts),
            "top_winner": max(counts, key=counts.get) if counts else "",
            "max_pbo": args.max_pbo,
            "verdict": "overfit" if overfit else "holds up",
        }
        try:
            run = triallog.append(Path(args.log), row)
        except triallog.SchemaChanged as exc:
            raise UserError(str(exc)) from exc
        log(f"  run #{run} logged to {Path(args.log)}")

    if args.json:
        print(json.dumps({
            "pair": pair, "configurations": result.configurations,
            "blocks": result.blocks, "splits": result.splits,
            "pbo": result.pbo, "median_logit": result.median_logit,
            "winners": counts, "overfit": overfit,
        }, indent=2, default=str))

    return 3 if overfit else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
