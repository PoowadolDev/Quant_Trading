"""Step 4 report — all four gates on one page.

`multiple_testing.py`, `deflated_sharpe.py`, `overfit.py` and `purged_cv.py`
each answer their question on the command line and leave a row in a log. This
runs them against one pair and writes the evidence out as a single
self-contained HTML file, the way `pair_report.py` does for Step 0,
`relationship_report.py` for Step 2 and `signal_report.py` for Step 3.

Four questions, and they are **not** combined into a score. They answer
different things and are allowed to disagree — `NUE~STLD` holds up on parameter
choice and fails on deflation, which is the whole point of reporting them
separately. `research/paper/validation/2608.23808` found a composite has no
forward relationship.

    is the Sharpe worth the search?   deflated against the expected maximum of
                                      N trials, where N is what this project has
                                      actually logged.

    was the parameter chosen?         probability of backtest overfitting, from
                                      combinatorially symmetric cross-validation
                                      over the sweep.

    does the score survive purging?   plain against purged against purged with
                                      an embargo, with the share of training
                                      rows removed reported so a no-op is
                                      visible rather than implied.

    how many tests were really run?   only when a screen dump is supplied, since
                                      that is a question about a population and
                                      the other three are about one pair.

    python validation_report.py -s NUE,STLD -a equity --broker equity
    python validation_report.py -s RSG,WM -a equity --broker equity --open
    python validation_report.py -s XLP,XLB -a index --broker etf \\
        --dump ../logs/dump-equities.csv

Exit codes: 0 every gate passed, 3 at least one failed, 2 usage error.
"""
from __future__ import annotations

import argparse
import html
import math
import sys
import warnings
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import paths

paths.ensure_code_importable()
paths.ensure_marketdata_importable()

import backtest as bt                                             # noqa: E402
import costs as cost_model                                        # noqa: E402
import deflated_sharpe as ds                                      # noqa: E402
import multiple_testing as mt                                     # noqa: E402
import outcomes as oc                                             # noqa: E402
import overfit as of                                              # noqa: E402
import pair_report as pr                                          # noqa: E402
import purged_cv as pc                                            # noqa: E402
import strategy as sig                                            # noqa: E402
from signal_report import EXTRA_CSS, bar_chart                    # noqa: E402

UserError = pr.UserError
DEFAULT_REPORTS = paths.STUDIES / "validation"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="validation_report",
                                description=__doc__.splitlines()[0],
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

    search = p.add_argument_group("searched - every value is a trial")
    search.add_argument("--entry-z", type=float, default=2.0)
    search.add_argument("--exit-z", type=float, default=0.5)
    search.add_argument("--stop-z", type=float, default=4.0)
    search.add_argument("--max-holding-bars", type=int, default=20)
    search.add_argument("--warmup", type=int, default=260)
    search.add_argument("--entry-grid", default="1.0,1.5,2.0,2.5,3.0")
    search.add_argument("--holding-grid", default="10,20,40")
    search.add_argument("--blocks", type=int, default=10)
    search.add_argument("--folds", type=int, default=8)
    search.add_argument("--horizon", type=int, default=400)
    search.add_argument("--embargo", type=int, default=20)

    gates = p.add_argument_group("gates")
    gates.add_argument("--trials", type=int, default=None)
    gates.add_argument("--sweep", default="1.0,1.5,2.0,2.5,3.0")
    gates.add_argument("--level", type=float, default=0.05)
    gates.add_argument("--max-pbo", type=float, default=0.50)
    gates.add_argument("--min-retained", type=float, default=0.50)
    gates.add_argument("--dump", default=None,
                       help="a screen dump, to include the population correction")
    gates.add_argument("--fdr", type=float, default=0.10)

    given = p.add_argument_group("given by reality")
    given.add_argument("--broker", required=True)
    given.add_argument("--costs-dir", default=str(cost_model.DEFAULT_COSTS))
    given.add_argument("--bars-per-night", type=float, default=None)
    given.add_argument("--lag", type=int, default=1)

    out = p.add_argument_group("output")
    out.add_argument("-o", "--out", default=None)
    out.add_argument("--store", default=str(paths.STORE))
    out.add_argument("--open", dest="open_browser", action="store_true")
    out.add_argument("-q", "--quiet", action="store_true")
    out.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    warnings.filterwarnings("ignore")
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))

    if not 0 < args.level < 1:
        raise UserError(f"--level {args.level:g} is a probability")
    if not 0 < args.max_pbo < 1:
        raise UserError(f"--max-pbo {args.max_pbo:g} is a probability")
    if args.trials is not None and args.trials < 1:
        raise UserError(f"--trials {args.trials} is a count")
    sweep_levels = oc.parse_levels(args.sweep, "--sweep")

    profile = cost_model.load_profile(Path(args.costs_dir) / f"{args.broker}.json")
    if not profile:
        raise UserError(f"no cost profile named {args.broker!r}")

    px = pr.load_prices(args)
    if args.bars_per_night is None:
        first = args.asset_class.split(",")[0].strip().lower()
        args.bars_per_night = cost_model.nights_per_bar(first, args.timeframe)
    a, b = px.columns
    pair = f"{a} ~ {b}"

    def params_at(entry_z: float, hold: int | None = None) -> sig.SignalParams:
        return sig.SignalParams(
            entry_z=entry_z, exit_z=args.exit_z, stop_z=args.stop_z,
            max_holding_bars=hold if hold is not None else args.max_holding_bars,
            hedge_source=args.hedge_source, fit_window=args.fit_window,
            rehedge_every=args.rehedge_every, use_log=args.price == "log")

    try:
        base = params_at(args.entry_z)
    except ValueError as exc:
        raise UserError(str(exc)) from exc

    # ---------------------------------------------------------- deflation
    result = bt.run_backtest(px, profile, base, warmup=args.warmup,
                             bars_per_night=args.bars_per_night, lag=args.lag)
    returns = np.array([t.net_bps for t in result.trades], dtype=float)
    if returns.size < 2:
        raise UserError(f"{pair} produced {returns.size} trade(s); nothing to validate")

    trials, per_file = args.trials, {}
    if trials is None:
        trials, per_file = ds.count_trials(paths.LOGS)
        trials = max(trials, 1)

    sweep_sharpes = []
    for value in sweep_levels:
        try:
            p_i = params_at(value)
        except ValueError:
            continue
        r_i = bt.run_backtest(px, profile, p_i, warmup=args.warmup,
                              bars_per_night=args.bars_per_night, lag=args.lag)
        s_i = ds.sharpe(np.array([t.net_bps for t in r_i.trades], dtype=float))
        if math.isfinite(s_i):
            sweep_sharpes.append(s_i)
    trial_sd = (float(np.std(sweep_sharpes, ddof=1))
                if len(sweep_sharpes) > 1 else 0.0)
    verdict = ds.assess(returns, pair=pair, trials=trials, trial_sd=trial_sd,
                        level=args.level)

    # ------------------------------------------------------- overfitting
    entries = oc.parse_levels(args.entry_grid, "--entry-grid")
    holds = [int(v) for v in oc.parse_levels(args.holding_grid, "--holding-grid")]
    columns, labels = [], []
    for entry_z in entries:
        for hold in holds:
            try:
                p_i = params_at(entry_z, hold)
            except ValueError:
                continue
            r_i = bt.run_backtest(px, profile, p_i, warmup=args.warmup,
                                  bars_per_night=args.bars_per_night, lag=args.lag)
            columns.append(np.diff(np.concatenate([[0.0], r_i.equity_net])))
            labels.append(f"z{entry_z:g}/h{hold}")
    if len(columns) < 2:
        raise UserError("the sweep produced fewer than two usable configurations")
    cscv = of.cscv(np.column_stack(columns), args.blocks, labels)

    # ----------------------------------------------------------- leakage
    leak_args = argparse.Namespace(
        price=args.price, fit_window=args.fit_window,
        rehedge_every=args.rehedge_every, horizon=args.horizon,
        max_holding_bars=args.max_holding_bars)
    feature, label, horizon = pc.feature_and_label(px, leak_args)
    scored = pc.run(feature, label, folds=args.folds, horizon=horizon,
                    embargo=args.embargo)
    rows_plain = float(np.mean(scored["plain"].trained_on))
    rows_kept = float(np.mean(scored["purged + embargo"].trained_on))
    removed = 1.0 - rows_kept / rows_plain if rows_plain else float("nan")
    plain, purged = scored["plain"].mean, scored["purged + embargo"].mean
    retained = (purged / plain) if (math.isfinite(plain) and plain > 0) else float("nan")

    # -------------------------------------------------------- population
    population = None
    if args.dump:
        frame = mt.read_dump(Path(args.dump))
        p_values = frame["pvalue"].to_numpy(float)
        survivors, threshold = mt.benjamini_hochberg(p_values, args.fdr)
        population = {
            "tested": p_values.size,
            "observed": int(np.sum(p_values < args.level)),
            "expected": p_values.size * args.level,
            "survivors": int(survivors.sum()),
            "threshold": threshold,
            "named": [f"{r['a']}~{r['b']}" for _, r in
                      frame[survivors].sort_values("pvalue").head(12).iterrows()],
            "this_pair_named": f"{a}~{b}" in {
                f"{r['a']}~{r['b']}" for _, r in frame[survivors].iterrows()},
        }

    gate_deflation = verdict.survives
    gate_overfit = cscv.pbo <= args.max_pbo
    gate_leak = not (math.isfinite(retained) and retained < args.min_retained)
    leak_tested = math.isfinite(removed) and removed >= 0.05
    passed = gate_deflation and gate_overfit and gate_leak

    # ------------------------------------------------------------- page
    tiles = "".join(
        f"<div class='{c}'><b>{html.escape(v)}</b><span>{html.escape(k)}</span></div>"
        for k, v, c in [
            ("deflated Sharpe", f"{verdict.dsr:.1%}",
             "pass" if gate_deflation else "fail"),
            ("overfitting", f"{cscv.pbo:.0%}", "pass" if gate_overfit else "fail"),
            ("leakage", "none" if gate_leak else "found",
             "pass" if gate_leak else "fail"),
            ("probabilistic Sharpe", f"{verdict.psr:.1%}", ""),
            ("trials charged for", f"{trials:,}", ""),
            ("Sharpe", f"{verdict.observed:+.3f}", ""),
        ])

    deflation_rows = "".join(pr._row(k, v, ok, note) for k, v, ok, note in [
        ("trades", f"{verdict.observations}", None, "net of cost and financing"),
        ("Sharpe, per trade", f"{verdict.observed:+.4f}", None, "not annualised"),
        ("skew", f"{verdict.skew:+.2f}", None,
         "negative skew widens the standard error and lowers both figures"),
        ("kurtosis", f"{verdict.kurtosis:.2f}", None,
         "3.0 is normal; fat tails make a Sharpe less certain"),
        ("trials counted", f"{trials:,}", None,
         "strategy configurations logged by this project, excluding screening "
         "tests and this script's own runs"),
        ("spread across trials", f"{trial_sd:.4f}", None,
         ", ".join(f"{v:+.3f}" for v in sweep_sharpes) or "given"),
        ("benchmark Sharpe", f"{verdict.benchmark:.4f}", None,
         f"what the best of {trials:,} trials reaches on noise alone"),
        ("probabilistic Sharpe", f"{verdict.psr:.1%}", None,
         "probability the true Sharpe beats zero"),
        ("deflated Sharpe", f"{verdict.dsr:.1%}", gate_deflation,
         f"probability it beats the benchmark; needs {1 - args.level:.0%}"),
    ])

    counts = cscv.chosen_counts()
    overfit_rows = "".join(pr._row(k, v, ok, note) for k, v, ok, note in [
        ("configurations swept", f"{cscv.configurations}", None,
         f"{args.entry_grid} against {args.holding_grid}"),
        ("splits", f"{cscv.splits}", None,
         f"{cscv.blocks} blocks, {cscv.blocks // 2} against {cscv.blocks // 2}"),
        ("probability of overfitting", f"{cscv.pbo:.1%}", gate_overfit,
         f"share of splits where the in-sample winner lands in the bottom half; "
         f"limit {args.max_pbo:.0%}"),
        ("median log-odds", f"{cscv.median_logit:+.2f}", None,
         "negative means the winner tends to rank below the middle"),
        ("distinct winners", f"{len(counts)}", None,
         "one winner every split is stability, not evidence"),
        ("most frequent winner",
         max(counts, key=counts.get) if counts else "none", None,
         f"{max(counts.values()) if counts else 0} of {cscv.splits} splits"),
    ])

    leak_rows = "".join(pr._row(k, v, ok, note) for k, v, ok, note in [
        ("observations", f"{feature.size:,}", None,
         f"horizon {horizon} bars, {args.folds} folds"),
        ("plain k-fold", f"{plain:+.4f}", None,
         f"trained on {rows_plain:,.0f} rows"),
        ("purged", f"{scored['purged'].mean:+.4f}", None, ""),
        ("purged with embargo", f"{purged:+.4f}", None,
         f"trained on {rows_kept:,.0f} rows, embargo {args.embargo} bars"),
        ("training rows removed", f"{removed:.1%}", leak_tested,
         "below 5% the comparison cannot tell a clean strategy from a leaky one"),
        ("score retained", f"{retained:.0%}" if math.isfinite(retained) else "—",
         gate_leak if leak_tested else None,
         f"needs {args.min_retained:.0%}" if math.isfinite(retained)
         else "the plain score is not positive, so there is nothing to take away"),
    ])

    sections = [f"<div class='big'>{tiles}</div>"]

    if population:
        pop_rows = "".join(pr._row(k, v, None, note) for k, v, note in [
            ("pairs tested", f"{population['tested']:,}", Path(args.dump).name),
            ("rejections", f"{population['observed']}",
             f"against {population['expected']:.1f} expected by N x level, which "
             "dependence does not change"),
            ("survivors at a false discovery rate",
             f"{population['survivors']}",
             f"{args.fdr:.0%} rate"
             + (f", p <= {population['threshold']:.5f}"
                if math.isfinite(population['threshold']) else "")),
            ("is this pair among them",
             "yes" if population["this_pair_named"] else "no",
             "being named is not the same as being tradeable"),
        ])
        sections.append("<h2>Population — how many tests produced this one</h2>"
                        "<table><tbody>" + pop_rows + "</tbody></table>")
        if population["named"]:
            sections.append("<div class='cap'>"
                            + html.escape("Named: " + ", ".join(population["named"]))
                            + "</div>")

    sections += [
        "<h2>Gate 1 — is the Sharpe worth the search behind it?</h2>"
        "<table><tbody>" + deflation_rows + "</tbody></table>",
        "<h2>Gate 2 — was the parameter chosen, or lucky?</h2>"
        "<table><tbody>" + overfit_rows + "</tbody></table>",
        "<h2>Gate 3 — does the score survive purging?</h2>"
        "<table><tbody>" + leak_rows + "</tbody></table>",
    ]

    # How the deflation verdict would change with a different trial count. The
    # point is the shape: the benchmark rises with the logarithm of N, so the
    # first few dozen trials cost far more than the next few hundred.
    ladder = [1, 5, 20, 50, trials, 500, 2000]
    ladder = sorted({n for n in ladder if n >= 1})
    dsr_curve = [ds.assess(returns, pair=pair, trials=n, trial_sd=trial_sd,
                           level=args.level).dsr for n in ladder]
    bench_curve = [ds.expected_max_sharpe(n, trial_sd) for n in ladder]

    charts = [
        ("Deflated Sharpe against the number of trials charged for",
         bar_chart([f"{n:,}" for n in ladder],
                   {"deflated Sharpe": dsr_curve}, decimals=2),
         f"This run charges {trials:,}. The benchmark grows with the logarithm of "
         "the trial count, so the first few dozen cost far more than the next few "
         "hundred."),
        ("The benchmark the Sharpe must beat",
         bar_chart([f"{n:,}" for n in ladder],
                   {"benchmark": bench_curve,
                    "observed": [verdict.observed] * len(ladder)}, decimals=2),
         "Where the benchmark bar rises above the observed bar, the search alone "
         "would have produced this result."),
        ("Out-of-sample log-odds across the splits",
         pr.histogram(cscv.logits, marks=[(0.0, "midpoint")])
         if cscv.logits.size else "",
         "One value per split. Mass to the left of the midpoint is the "
         "probability of backtest overfitting."),
        ("Per-trade net, distribution",
         pr.histogram(returns, marks=[(0.0, "break even")]),
         "Every finished trade at the configured threshold. Skew and kurtosis "
         "from this distribution feed the deflation above."),
        ("Equity, gross and net",
         pr.line_chart(px.index, {"gross": result.equity_gross,
                                  "net": result.equity_net},
                       hlines=[(0.0, "")], decimals=0, sign=True),
         "The gap between the lines is transaction cost and financing."),
    ]
    for title, svg, cap in charts:
        if svg:
            sections.append(f"<h2>{html.escape(title)}</h2>{svg}"
                            f"<div class='cap'>{html.escape(cap)}</div>")

    fails = []
    if not gate_deflation:
        fails.append(verdict.reason())
    if not gate_overfit:
        fails.append(f"the in-sample winner underperforms out of sample on "
                     f"{cscv.pbo:.0%} of splits")
    if not gate_leak:
        fails.append(f"the score falls to {retained:.0%} of the unpurged figure")
    if not leak_tested:
        fails.append("purging removed too little data for the leakage gate to have "
                     "been tested at all")

    summary = html.escape("; ".join(fails)) if fails else (
        "the Sharpe survives deflation, the parameter choice holds up across "
        "splits, and the score survives purging")
    doc = ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
           "<meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>{a} ~ {b} — validation</title>"
           f"<style>{pr.CSS}{EXTRA_CSS}</style></head><body>"
           f"<h1>{a} ~ {b} · validation</h1>"
           f"<div class='meta'>{args.timeframe} · {px.index[0]:%Y-%m-%d} to "
           f"{px.index[-1]:%Y-%m-%d} · {len(px):,} bars · broker {args.broker} · "
           f"{trials:,} trials charged · generated "
           f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC</div>"
           f"<div class='verdict {'pass' if passed else ''}'>"
           f"<b>{'SURVIVES VALIDATION' if passed else 'DOES NOT SURVIVE'}</b> — "
           f"{summary}"
           "<p>These gates are reported separately and never combined: they answer "
           "different questions and are allowed to disagree. Surviving them is not "
           "permission to trade — it means the evidence is not yet against you.</p>"
           "</div>" + "".join(sections) + "</body></html>")

    out = Path(args.out) if args.out else DEFAULT_REPORTS / f"validation-{a}-{b}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")

    log(f"{pair}   {args.timeframe}   {len(px):,} bars   broker {args.broker}")
    log(f"  deflated Sharpe {verdict.dsr:.1%} (PSR {verdict.psr:.1%}, "
        f"{trials:,} trials)   PBO {cscv.pbo:.1%}   "
        f"purging removed {removed:.1%}")
    for f in fails:
        log(f"    - {f}")
    log(f"  wrote {out}  ({out.stat().st_size / 1024:.1f} KB)")
    if args.open_browser:
        webbrowser.open(out.resolve().as_uri())
    return 0 if passed else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
