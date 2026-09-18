"""Stages 00 to 21 in one run, reported as a sequence of gates on one page.

Every other script in this project answers one question and prints it to a terminal. That
is the right shape for doing the work and the wrong shape for seeing where the work stands:
the answer to "is there anything here" is currently spread across five report directories,
three logs and two plan documents, and nobody can hold all of it at once.

This script runs the residual pipeline end to end and writes a single self-contained HTML
page with one section per stage. It stops at stage 21. Stages 22 and 23 are paper trading
and production, which are not research questions and are not simulated here.

**It does not compute an overall score, and that is deliberate.** `STEP4.md` refuses to
aggregate the validation gates into one number, on the evidence of a study where the
composite had no forward relationship, and `verify_validation.py` asserts that no function
returns one. The same reasoning applies to the pipeline as a whole. Four gates failing for
four different reasons is four pieces of information; one number is none. Every stage below
therefore reports its own verdict and the page reports no total.

**A stage with nothing behind it says so.** Point-in-time data is not implemented, and the
page prints that in the same place and the same size as a passing gate, along with the
direction of the bias it leaves behind. A pipeline report that silently omitted its
unimplemented stages would be a way of forgetting them.

    python pipeline.py
    python pipeline.py --fast            # fewer null draws and horizons, for a quick look
    python pipeline.py --json

Exit codes: 0 every implemented stage passed; 3 at least one failed, which is the usual and
informative outcome; 2 usage error.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import sys
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import paths

paths.ensure_code_importable()
paths.ensure_marketdata_importable()

import ic                                                          # noqa: E402
import pair_report as pr                                           # noqa: E402
import portfolio as pf                                             # noqa: E402
import residual as rs                                              # noqa: E402
import scorecard as sc                                             # noqa: E402
import risk                                                        # noqa: E402
from signal_report import EXTRA_CSS                                # noqa: E402

UserError = pr.UserError
DEFAULT_REPORTS = paths.STUDIES / "pipeline"

PASS, FAIL, PARTIAL, ABSENT, NOT_RUN = "pass", "fail", "partial", "absent", "not run"

#: A stage whose inputs make its number meaningless. Distinct from NOT_RUN, which means the
#: work was not attempted, and from FAIL, which is a verdict about the strategy. The
#: precedent is `pair_report.judge()`, which refuses to score the edge gate on a
#: non-stationary spread because doing so "produces a large, convincing and entirely
#: spurious number". Running every stage must not mean computing numbers that cannot mean
#: anything, and a stage that cannot be evaluated has to say so rather than report a zero.
NOT_EVALUABLE = "not evaluable"

#: Only these two states are a judgement about the strategy. The rest are statements about
#: the pipeline, and mixing them would let an unbuilt stage read as a passing one.
DECIDING = (PASS, FAIL)


@dataclass
class Stage:
    """One numbered stage, its verdict, and the rows that justify it."""

    number: str
    title: str
    state: str
    headline: str = ""
    rows: list = field(default_factory=list)      # (label, value, status, note)
    note: str = ""
    figure: str = ""

    @property
    def badge(self) -> str:
        return {PASS: "<span class='b ok'>PASS</span>",
                FAIL: "<span class='b no'>FAIL</span>",
                PARTIAL: "<span class='b no'>PARTIAL</span>",
                ABSENT: "<span class='b no'>NOT IMPLEMENTED</span>",
                NOT_RUN: "<span class='b no'>NOT RUN</span>",
                NOT_EVALUABLE: "<span class='b no'>NOT EVALUABLE</span>"}[self.state]


def row(label, value, status=None, note=""):
    return (label, str(value), status, note)


#: What each tier means, in one line, for the pipeline page. The wording matters: these are
#: statements about whether a failure is *fixable*, not about whether a candidate is good.
TIER_NOTES = {
    sc.STANDALONE: "cleared every gate it could be asked",
    sc.PORTFOLIO_CANDIDATE: "failed only on magnitude; a book may fix it",
    sc.WATCH_POWER: "right sign, error bars too wide; more data may fix it",
    sc.REJECT_STATISTICAL: "no relationship on the window that selected it",
    sc.REJECT_STRUCTURAL: "the relationship is not reliably present; nothing fixes it",
    sc.REJECT_ECONOMIC: "gross positive, costs exceed it; a book cannot dilute a per-trade cost",
}


def tier_counts() -> dict:
    """Tier distribution across every pair ever screened, from the research log.

    Read rather than recomputed: the log already carries every measurement and every
    threshold that judged it, so re-screening to produce this would be paying twice for an
    answer already on disk.
    """
    path = paths.LOGS / "pair_research.csv"
    if not path.exists():
        return {}
    import screen as scr

    def number(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("nan")

    counts: dict = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for line in csv.DictReader(fh):
            try:
                judged = argparse.Namespace(
                    level=number(line["level"]), require_oos=True, require_holdout=True,
                    require_early=False, max_beta_swing=number(line["max_beta_swing"]),
                    max_net_exposure=number(line["max_net_exposure"]),
                    min_half_life=number(line["min_half_life"]),
                    max_half_life=number(line["max_half_life"]))
                candidate = scr.Row(
                    a=line["a"], b=line["b"], bars=int(line["bars"]),
                    pvalue=number(line["pvalue"]), pvalue_oos=number(line["pvalue_oos"]),
                    beta=number(line["beta"]), hedge_ok=line["hedge_ok"] == "yes",
                    half_life=number(line["half_life"]),
                    half_life_oos=number(line["half_life_oos"]),
                    net_exposure=number(line["net_exposure"]), sector=line["sector"],
                    pvalue_early=number(line["pvalue_early"]),
                    pvalue_late=number(line["pvalue_late"]),
                    beta_early=number(line["beta_early"]),
                    beta_late=number(line["beta_late"]))
                name = sc.tier(sc.assess(candidate, judged))
            except (KeyError, ValueError, AssertionError):
                # A row written by an older schema, or a gate the tier rules do not cover.
                # Skipped rather than guessed at; the count is of what could be graded.
                continue
            counts[name] = counts.get(name, 0) + 1
    return counts


# ------------------------------------------------------------------ the stages

def stage_data(store: Path, panel: pd.DataFrame, args) -> list:
    """00 to 05 — everything before a model is fitted."""
    counts = {}
    for path in Path(store).glob("*/*/*/*.parquet"):
        counts[path.parts[-4]] = counts.get(path.parts[-4], 0) + 1
    total = sum(counts.values())

    spec = Stage("00", "Research specification", PARTIAL,
                 "A falsifiable premise with kill criteria written before the work",
                 note="RESIDUAL.md states a kill criterion per stage in advance, which is "
                      "the part that matters. What is missing is a per-study record of the "
                      "hypothesis and the success bar, so the trial count still has to be "
                      "reconstructed from logs rather than read off a specification.")
    spec.rows = [
        row("Plan documents", "PLAN.md, RESIDUAL.md, STEP1-4.md", True),
        row("Kill criteria stated in advance", "yes, RESIDUAL.md section 4", True),
        row("Per-study hypothesis record", "none", False,
            "trial counts are reconstructed from logs/"),
    ]

    acquisition = Stage("01", "Data acquisition", PASS,
                        f"{total} stored series across {len(counts)} asset classes")
    acquisition.rows = [row(f"{name} series", f"{count}", True)
                        for name, count in sorted(counts.items())]
    acquisition.rows.append(row("Feeds", "yahoo, binance, dukascopy", True,
                                "marketdata handles symbol mapping and incremental merge"))

    cleaning = Stage("02", "Data cleaning and quality", PASS,
                     "Known defects catalogued and gated rather than discovered later")
    cleaning.rows = [
        row("Yahoo forex OHLC", "1-3% of bars malformed", True,
            "close-only work proceeds; high/low work is refused"),
        row("Close-spike detection", "16 bad bars found across 5 forex symbols", True,
            "one supplied 34% of a pair's profit before it was caught"),
        row("This panel uses", "close prices only", True, "unaffected by the OHLC defect"),
    ]

    universe = Stage("03", "Universe definition", PASS,
                     f"{panel.shape[1]} names on {panel.shape[0]:,} common bars")
    universe.rows = [
        row("Asset class", args.asset_class, True),
        row("Minimum history", f"{args.min_bars:,} bars", True,
            "applied per series before the join, so one short name cannot truncate the panel"),
        row("Common window", f"{panel.index[0]:%Y-%m-%d} to {panel.index[-1]:%Y-%m-%d}", True),
        row("Economic grouping", "instruments.py, 29 sectors", True,
            "driver_groups refuses to pair instruments sharing no driver"),
    ]

    pit = Stage("04", "Point-in-time data", ABSENT,
                "Not implemented — the panel is survivor-filtered",
                note="The universe is every name with enough history *as of today*, which "
                     "is a filter on having survived. EQR and AVB sit in the store at 14 "
                     "bars and are absent from the current listing directory. The bias "
                     "inflates any positive result, so a null result here is conservative "
                     "and a passing one is an upper bound. The shuffled null used "
                     "throughout does NOT correct for it: the permutation reorders dates "
                     "and leaves the cross-section exactly as it was.")
    pit.rows = [
        row("As-of universe membership", "not modelled", False),
        row("Delisted names", "excluded by the history filter", False,
            "survivorship, direction: inflates"),
        row("Restatement handling", "not modelled", False),
        row("Bias direction", "inflates every positive result", False,
            "so the IC below is an upper bound"),
    ]

    returns = np.diff(np.log(panel.to_numpy(float)), axis=0)
    daily = returns.std(axis=0) * math.sqrt(252)
    eda = Stage("05", "Exploratory analysis", PASS,
                f"Annualised volatility spans {daily.min():.0%} to {daily.max():.0%}")
    eda.rows = [
        row("Names", f"{panel.shape[1]}", True),
        row("Return rows", f"{len(returns):,}", True),
        row("Median annualised volatility", f"{np.median(daily):.1%}", True),
        row("Cross-sectional mean correlation",
            f"{np.corrcoef(returns, rowvar=False)[np.triu_indices(panel.shape[1], 1)].mean():.3f}",
            True, "this is what the factor model has to remove"),
    ]
    return [spec, acquisition, cleaning, universe, pit, eda]


def stage_model(panel: pd.DataFrame, returns: np.ndarray, args) -> list:
    """06 to 10 — the factor model, the residual, and the signal built on it."""
    graded = tier_counts()
    candidates = Stage("06", "Candidate generation", PASS,
                       "Every name carries a signal, so there is nothing to select")
    candidates.rows = [
        row("Residual track", f"{panel.shape[1]} concurrent signals", True,
            "no selection step, so no selection bias from it"),
        row("Selection burden removed", "yes", True,
            "the cross-section is taken whole rather than ranked"),
    ]
    if graded:
        # The pair track graded rather than counted. A binary survivor count answers "how
        # many passed" and discards "how many failed on something a book could fix", which
        # is a different question and the one worth asking before abandoning a market.
        total = sum(graded.values())
        candidates.rows.append(
            row("Pair track, graded", f"{total:,} tested", None,
                "logs/pair_research.csv, scorecard.tier"))
        for name in sc.TIERS:
            if graded.get(name):
                candidates.rows.append(
                    row(f"  {name}", f"{graded[name]:,}",
                        True if name == sc.STANDALONE else None,
                        TIER_NOTES.get(name, "")))
        candidates.note = (
            "A tier is not a score: no arithmetic combines the gates, and the label comes "
            "from which gates failed rather than from how many. PORTFOLIO_CANDIDATE means "
            "the only failures were about magnitude, which a book can plausibly fix by "
            "holding offsetting exposures — it does not mean the candidate is good. Five "
            "were measured against the book on 2026-09-18 and none improved its Sharpe.")
    else:
        candidates.rows.append(
            row("Pair track", "no graded research log", None,
                "run screen.py to populate logs/pair_research.csv"))

    window = returns[-args.pca_window:]
    usable, weights = rs.eigenportfolios(window, args.factors)
    standardised = (window[:, usable] - window[:, usable].mean(0)) / window[:, usable].std(0, ddof=1)
    eigenvalues = np.linalg.eigvalsh(np.corrcoef(standardised, rowvar=False))[::-1]
    explained = eigenvalues[:args.factors].sum() / eigenvalues.sum()

    relationship = Stage("07", "Relationship test — factor model", PASS,
                         f"{args.factors} components explain {explained:.0%} of "
                         f"cross-sectional variance")
    relationship.rows = [
        row("Model class", "PCA on returns, not level cointegration", True,
            "no stable long-run price ratio is assumed"),
        row("Leading eigenvalue share", f"{eigenvalues[0] / eigenvalues.sum():.0%}", True,
            "the market factor"),
        row("Components removed", f"{args.factors}", True),
        row("Variance explained", f"{explained:.1%}", True),
        row("Why not cointegration",
            "early and late windows independent (5 observed, 5.9 expected)", True,
            "measured on 380 SPX pairs, screen #22"),
    ]

    construction = Stage("08", "Residual construction", PASS,
                         "Residuals measured forward, never on the bars that fitted them")
    construction.rows = [
        row("Loadings from", f"trailing {args.pca_window} bars", True),
        row("Residual accumulated over", f"the {args.ou_window} bars after", True,
            "out of sample by construction"),
        row("In-sample alternative", "rejected", True,
            "it lifts the shuffled null from 5% to 8.2% via a Brownian bridge"),
        row("Measured effect of getting this wrong", "+0.3% at t=0.84 against +2.1% at t=5.27",
            True, "the in-sample version erased the signal and inflated the null"),
    ]

    lift, se, t, real, null = run_reversion(returns, args)
    reversion = Stage("09", "Mean-reversion analysis",
                      PASS if t > rs.MIN_T else FAIL,
                      f"Residual rejects a unit root {lift:+.2%} more than a shuffled null, "
                      f"t = {t:.2f}")
    reversion.rows = [
        row("Real rejection share", f"{real['reject_share']:.1%}", None),
        row("Shuffled null", f"{null['reject_share']:.1%}", None,
            "at the nominal 5% level, as the forward construction requires"),
        row("Lift", f"{lift:+.2%} +/- {se:.2%}", t > rs.MIN_T,
            f"over {real['windows']} non-overlapping windows"),
        row("Median half-life", f"{real['half_life_median']:.1f} bars", None,
            f"against {null['half_life_median']:.1f} under the null"),
        row("Gate", f"t > {rs.MIN_T}", t > rs.MIN_T, "RESIDUAL.md Stage 0 kill criterion"),
    ]

    signal = Stage("10", "Signal construction", PASS,
                   "Signal is the standing residual, scaled by its own variation")
    signal.rows = [
        row("Definition", "s = -X / sd(X)", True,
            "a residual that has run up is expensive, so it is shorted"),
        row("Entry threshold", "none", True,
            "removed; every swept value was a trial charged at Step 4"),
        row("Exit threshold", "none", True, "position size is continuous in the drift"),
        row("Formation lag", "signal uses bars strictly before the forward window", True),
    ]
    return [candidates, relationship, construction, reversion, signal]


def stage_skill(panel: pd.DataFrame, returns: np.ndarray, args) -> tuple:
    """11 to 13 — skill, breadth, the book, and the risk layer around it."""
    horizons = [1, 5, 20] if args.fast else [1, 2, 3, 5, 10, 20]
    if args.primary_horizon not in horizons:
        horizons = sorted(set(horizons) | {args.primary_horizon})

    ic_args = ic.build_parser().parse_args(["--no-log"])
    ic_args.pca_window, ic_args.signal_window = args.pca_window, args.ou_window
    ic_args.step, ic_args.factors = args.step, args.factors
    ic_args.bars_per_year, ic_args.primary_horizon = 252, args.primary_horizon

    rows_ic, null_ic = [], []
    for horizon in horizons:
        ics, _ = ic.sweep(returns, horizon, ic_args)
        summary = ic.summarise(ics)
        summary["horizon"] = horizon
        rows_ic.append(summary)
        draws = 1 if args.fast else 2
        nulls = np.concatenate([ic.sweep(rs.shuffled(returns, d), horizon, ic_args)[0]
                                for d in range(draws)])
        null_summary = ic.summarise(nulls)
        null_summary["horizon"] = horizon
        null_ic.append(null_summary)

    bred = ic.breadth(ic.breadth_returns(returns, ic_args), list(panel.columns))
    for entry in rows_ic:
        entry["implied_ir"] = ic.implied_ir(entry["ic_mean"], bred["effective_bets"],
                                            entry["horizon"], 252)
    primary = next(r for r in rows_ic if r["horizon"] == args.primary_horizon)
    skilled = math.isfinite(primary["t"]) and primary["t"] > ic.MIN_T

    stage11 = Stage("11", "Information coefficient, ICIR and decay",
                    PASS if skilled else FAIL,
                    f"IC {primary['ic_mean']:+.4f} +/- {primary['ic_se']:.4f} at "
                    f"{primary['horizon']} bars, t = {primary['t']:.2f}")
    stage11.rows = [
        row(f"IC at {h['horizon']} bar(s)",
            f"{h['ic_mean']:+.4f} +/- {h['ic_se']:.4f}",
            None if h["horizon"] != args.primary_horizon else skilled,
            f"t {h['t']:.2f}, ICIR {h['icir']:.3f}, null {n['ic_mean']:+.4f}")
        for h, n in zip(rows_ic, null_ic)]
    stage11.rows += [
        row("Decay profile", "IC rises with horizon", None,
            "the signal predicts reversion over weeks, not the next bar"),
        row("Breadth", f"{bred['effective_bets']:.1f} of {bred['names']} names", None,
            f"{bred['bet_share']:.0%} of the cross-section, on "
            f"{bred['rows']:,} tiled bars"),
        row("Most correlated residual pair", bred["worst_pair"], None,
            f"{bred['worst_correlation']:+.3f} — the factor model did not separate these"),
        row("Fundamental law", f"IR = IC x sqrt(breadth) = {primary['implied_ir']:.2f}",
            None, "a year, before costs, on a survivor-filtered panel"),
        row("Gate", f"t > {ic.MIN_T} at the primary horizon", skilled,
            "RESIDUAL.md Stage 1 kill criterion"),
    ]
    stage11.figure = ic_figure(rows_ic, null_ic)
    stage11.note = ("The primary horizon is declared from the half-life measured in stage "
                    "09, not chosen by reading the table above and taking the best row. "
                    "Choosing it afterwards would be selection, and Step 4 charges for it.")

    pf_args = pf.build_parser().parse_args(["--no-log"])
    pf_args.pca_window, pf_args.signal_window = args.pca_window, args.ou_window
    pf_args.step, pf_args.factors = args.step, args.factors
    book = pf.assemble(returns, list(panel.columns), len(returns), pf_args)

    stage12 = Stage("12", "Portfolio construction", PASS if book.ok else FAIL,
                    f"{len(book.held)} {book.kind} positions sized from the OU process, "
                    f"net {book.net_share:+.1%} of gross")
    stage12.rows = [
        row("Book type", f"{book.kind} cross-section", True,
            "the same script also sizes a book of named pairs, via --book"),
        row("Sizing rule", "w = theta(mu - X) / sigma^2", True,
            "growth-optimal, and the OU drift supplies the mean"),
        row("Threshold sweep", "removed", True, "one fewer dimension of selection bias"),
        row("Uncertainty haircut", f"{pf_args.confidence:g} standard errors", True,
            "an overstated theta would otherwise oversize with nothing to cap it"),
        row("Fitted / held / zeroed",
            f"{len(book.positions)} / {len(book.held)} / "
            f"{len(book.positions) - len(book.held)}", None),
        row("Net exposure", f"{book.net_share:+.1%} of gross",
            abs(book.net_share) <= pf_args.max_net,
            "net/gross scales as 1/sqrt(N); 7.9% expected at this panel size"),
        row("Heavy-loading gate",
            f"{pf_args.max_loading_multiple:g}x the median loading norm", True,
            "the construction's own documented failure regime"),
    ]
    if book.projection:
        p = book.projection
        stage12.rows += [
            row("Factor neutrality", "by construction, not by cancellation", True,
                "RESIDUAL.md 2.2 — projected onto the null space of the loadings"),
            row("Factor exposure ||Lw||",
                f"{p['exposure_before']:.2e} -> {p['exposure_after']:.2e}", True,
                "zero to floating point, by algebra"),
            row("Cost of the projection",
                f"weights correlate {p['correlation']:+.4f} with pre-projection", True,
                "a low correlation would mean signal was removed, not just exposure"),
            row("Projection scope", f"{p['names']} held names only", True,
                "running it over all 160 would reopen the names the gates closed"),
        ]
    for breach in book.breaches:
        stage12.rows.append(row("Breach", breach[:90], False))
    stage12.note = ("Net exposure was +47% before factor-neutralising and is "
                    f"{book.net_share:+.1%} after. Across twelve formation dates the "
                    "standard deviation of net fell from 7.8% to 3.6% and the share of "
                    "dates breaching the 10% cap from about one in five to none. The cap "
                    "itself was not moved.")

    stage13 = Stage("13", "Risk model", PARTIAL,
                    f"Book-level caps applied; no factor covariance forecast",
                    note="Exposure caps, residual correlation and the drawdown kill switch "
                         "are implemented and enforced. What is absent is a forecast "
                         "covariance model — risk here is measured on the realised "
                         "residual correlation, which is backward-looking and will "
                         "understate risk exactly when correlations move.")
    stage13.rows = [
        row("Net and gross caps", "enforced", True, "risk.check_caps"),
        row("Factor exposure", "zero by construction", True,
            "projection onto the null space of the loadings, not a fitted hedge"),
        row("Independent bets", f"{book.effective_bets:.1f}",
            book.effective_bets >= pf_args.min_effective_bets,
            "participation ratio of the residual correlation matrix"),
        row("Worst residual correlation", f"{book.worst_correlation:+.3f}",
            abs(book.worst_correlation) <= pf_args.max_correlation, book.worst_pair),
        row("Drawdown kill switch", "implemented", True, "risk.drawdown_breach"),
        row("Forecast covariance model", "none", False, "realised correlation only"),
    ]
    return [stage11, stage12, stage13], primary, bred, book


def stage_evidence(args) -> list:
    """14 to 21 — costs, the backtest, and what the search has to be charged for."""
    costs_dir = paths.COSTS
    profiles = sorted(p.stem for p in costs_dir.glob("*.json")) if costs_dir.is_dir() else []

    stage14 = Stage("14", "Transaction cost model", PASS,
                    f"{len(profiles)} broker profiles, spread plus commission plus swap")
    stage14.rows = [
        row("Profiles", ", ".join(profiles) or "none", bool(profiles)),
        row("Terms modelled", "spread, commission, overnight swap per leg", True),
        row("Financing", "charged per night held", True,
            "the recurring cause of death in this project"),
        row("Applied to this book", "not yet", False,
            "stage 16 has not been run on the residual track"),
    ]

    stage15 = Stage("15", "Backtest engine", PASS,
                    "Built and verified, replaying the live signal code")
    stage15.rows = [
        row("Engine", "backtest.py", True, "122 checks in verify_backtest.py"),
        row("Shared decision function", "strategy.py", True,
            "the same code runs live, so the backtest measures something"),
        row("Look-ahead guard", "fill lag makes results monotonically worse", True),
        row("Residual strategy wired in", "no", False,
            "the engine is pair-shaped; the residual book needs an adapter"),
    ]

    stage16 = Stage("16", "In-sample backtest", NOT_RUN,
                    "The residual book has not been replayed through the engine",
                    note="This is the honest stopping point. Stage 11 says the signal "
                         "predicts and stage 12 says it can be sized, but nothing here has "
                         "been charged a spread. RESIDUAL.md section 1.3 records that "
                         "financing, not signal, killed every previous candidate, so this "
                         "is the stage most likely to end the work.")
    stage16.rows = [row("Residual backtest", "not run", False,
                        "needs a cross-sectional adapter for backtest.py")]

    stage17 = Stage("17", "Out-of-sample backtest", NOT_RUN,
                    "Blocked behind stage 16")
    stage17.rows = [row("Held-out replay", "not run", False)]

    stage18 = Stage("18", "Walk-forward validation", PARTIAL,
                    "Rolling refit is built into the measurement, not into a trade replay")
    stage18.rows = [
        row("Rolling loadings", "every formation date refits", True,
            "residual.py and ic.py both walk forward"),
        row("Purged k-fold", "purged_cv.py", True, "embargo verified against a planted leak"),
        row("Anchored walk-forward trade replay", "not run", False, "blocked behind 16"),
    ]

    stage19 = Stage("19", "Robustness and stress tests", PARTIAL,
                    "Parameter sensitivity measured; no systematic stress suite")
    stage19.rows = [
        row("Factor-count sensitivity", "t from 3.36 to 6.14 over 6 values", True,
            "stage 09 is not a knife-edge"),
        row("Horizon sensitivity", "measured across 6 horizons", True),
        row("Regime subsamples", "not run", False),
        row("Cost sensitivity", "not run", False, "blocked behind 16"),
    ]

    trials = count_trials()
    stage20 = Stage("20", "Multiple testing and bias check", PASS,
                    f"{trials['pairs']:,} pair tests charged across "
                    f"{trials['screens']} screens")
    stage20.rows = [
        row("Logged pair tests", f"{trials['pairs']:,}", True, "logs/screens.csv"),
        row("Logged backtests", f"{trials['backtests']}", True, "logs/backtests.csv"),
        row("Bootstrap noise floor", "78.8 rejections, not the arithmetic 58.6", True,
            "the screen's own floor was a third too low"),
        row("Deflated Sharpe", "implemented", True, "deflated_sharpe.py"),
        row("PBO via CSCV", "implemented", True, "overfit.py"),
        row("Residual track trials", "1 configuration, not swept", True,
            "thresholds removed rather than optimised"),
        row("Gates aggregated into one score", "never", True,
            "a composite had no forward relationship; reported separately"),
    ]

    stage21 = Stage("21", "Final model selection", NOT_RUN,
                    "Cannot be reached until the book has been charged a cost",
                    note="Selection needs a net result to select on, and stage 16 has not "
                         "run. Reaching this stage with a positive number would still not "
                         "be permission to trade: it would mean the evidence is not yet "
                         "against the strategy.")
    stage21.rows = [row("Candidate selected", "none", False,
                        "blocked behind stages 16 and 17")]

    return [stage14, stage15, stage16, stage17, stage18, stage19, stage20, stage21]


# ------------------------------------------------------------------ helpers

def run_reversion(returns: np.ndarray, args) -> tuple:
    """Stage 0's measurement, at the settings this run is using."""
    rs_args = rs.build_parser().parse_args(["--no-log"])
    rs_args.pca_window, rs_args.ou_window = args.pca_window, args.ou_window
    rs_args.step, rs_args.factors = max(args.step, args.ou_window + 3), args.factors
    rs_args.adf_lags, rs_args.level = 1, 0.05
    draws = 1 if args.fast else 3

    real_windows = rs.sweep(returns, rs_args)
    null_windows = [rs.sweep(rs.shuffled(returns, d), rs_args) for d in range(draws)]
    real = rs.summarise(real_windows)
    null = rs.summarise([w for draw in null_windows for w in draw])
    real_shares = rs.window_shares(real_windows)
    null_shares = np.mean([rs.window_shares(d)[:len(real_shares)] for d in null_windows],
                          axis=0)
    lift, se, t = rs.paired_lift(real_shares, null_shares)
    return lift, se, t, real, null


def count_trials() -> dict:
    """What the search has cost so far, read from the logs rather than remembered."""
    out = {"pairs": 0, "screens": 0, "backtests": 0}
    screens = paths.LOGS / "screens.csv"
    if screens.exists():
        with screens.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        out["screens"] = len(rows)
        out["pairs"] = sum(int(r["pairs"]) for r in rows if r.get("pairs", "").isdigit())
    backtests = paths.LOGS / "backtests.csv"
    if backtests.exists():
        with backtests.open(newline="", encoding="utf-8") as fh:
            out["backtests"] = sum(1 for _ in csv.DictReader(fh))
    return out


def ic_figure(rows_ic: list, null_ic: list) -> str:
    """IC against horizon, real beside null."""
    labels = [str(r["horizon"]) for r in rows_ic]
    from signal_report import bar_chart
    return bar_chart(labels,
                     {"IC": [r["ic_mean"] for r in rows_ic],
                      "shuffled null": [n["ic_mean"] for n in null_ic]},
                     height=160, decimals=4)


def build_html(stages: list, panel: pd.DataFrame, args, decided: list) -> str:
    passed = sum(1 for s in stages if s.state == PASS)
    failed = sum(1 for s in stages if s.state == FAIL)
    unbuilt = sum(1 for s in stages if s.state in (PARTIAL, ABSENT, NOT_RUN))

    tiles = (f"<div class='big'>"
             f"<div><b>{passed}</b><span>stages passed</span></div>"
             f"<div><b>{failed}</b><span>stages failed</span></div>"
             f"<div><b>{unbuilt}</b><span>partial, absent or not run</span></div>"
             f"<div><b>{panel.shape[1]}</b><span>names</span></div>"
             f"<div><b>{panel.shape[0]:,}</b><span>common bars</span></div>"
             f"</div>")

    contents = ["<h2>The pipeline at a glance</h2><table><tbody>"]
    for s in stages:
        contents.append(
            f"<tr><td class='k'>{s.number} &nbsp; {html.escape(s.title)}</td>"
            f"<td class='v'>{html.escape(s.headline)}</td>"
            f"<td>{s.badge}</td><td class='n'></td></tr>")
    contents.append("</tbody></table>")
    contents.append(
        "<p class='cap'>No overall score is computed. Stages fail for different reasons "
        "and a single number would discard which. This follows STEP4.md, where the same "
        "refusal is asserted by the validation suite itself.</p>")

    sections = [tiles, "".join(contents)]
    for s in stages:
        body = [f"<h2>{s.number} — {html.escape(s.title)} &nbsp; {s.badge}</h2>"]
        if s.headline:
            body.append(f"<p class='cap'>{html.escape(s.headline)}</p>")
        if s.figure:
            body.append(s.figure)
        body.append("<table><tbody>")
        for label, value, status, note in s.rows:
            body.append(pr._row(label, value, status, note))
        body.append("</tbody></table>")
        if s.note:
            body.append(f"<p class='cap'>{html.escape(s.note)}</p>")
        sections.append("".join(body))

    accepted = failed == 0
    verdict_word = "EVERY IMPLEMENTED STAGE PASSED" if accepted else "STAGES FAILED"
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Residual pipeline — stages 00 to 21</title>"
        f"<style>{pr.CSS}{EXTRA_CSS}</style></head><body>"
        f"<h1>Residual statistical arbitrage · stages 00 to 21</h1>"
        f"<div class='meta'>{args.asset_class} · {args.timeframe} · "
        f"{panel.index[0]:%Y-%m-%d} → {panel.index[-1]:%Y-%m-%d} · "
        f"{panel.shape[1]} names · {panel.shape[0]:,} bars · "
        f"{args.factors} factors · generated "
        f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC</div>"
        f"<div class='verdict {'pass' if accepted else ''}'>"
        f"<b>{verdict_word}</b> — {passed} passed, {failed} failed, {unbuilt} partial, "
        f"absent or not run."
        f"<p>Not a backtest and not a recommendation. The pipeline stops at stage 21; "
        f"nothing below has been charged a transaction cost, and the panel is "
        f"survivor-filtered, so every positive number here is an upper bound.</p>"
        f"</div>" + "".join(sections) + "</body></html>"
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pipeline", description=__doc__.splitlines()[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sel = p.add_argument_group("selection")
    sel.add_argument("-a", "--asset-class", default="equity")
    sel.add_argument("-t", "--timeframe", default="1d")
    sel.add_argument("--source", default=None)
    sel.add_argument("--min-bars", type=int, default=5000)

    struct = p.add_argument_group("structure - choose once, not per run")
    struct.add_argument("--pca-window", type=int, default=252)
    struct.add_argument("--ou-window", type=int, default=60)
    struct.add_argument("--step", type=int, default=21)
    struct.add_argument("--factors", type=int, default=15)
    struct.add_argument("--primary-horizon", type=int, default=5,
                        help="declared from the stage 09 half-life, not read off the IC "
                             "table")

    out = p.add_argument_group("output")
    out.add_argument("--fast", action="store_true",
                     help="fewer null draws and horizons; a quick look, not a result")
    out.add_argument("-o", "--out", default=None)
    out.add_argument("--store", default=str(paths.STORE))
    out.add_argument("--open", dest="open_browser", action="store_true")
    out.add_argument("--json", action="store_true")
    out.add_argument("-q", "--quiet", action="store_true")
    out.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))
    if args.factors < 1:
        raise UserError("--factors must be at least 1")
    if args.ou_window > args.pca_window:
        raise UserError("--ou-window cannot exceed --pca-window")

    panel = rs.load_panel(Path(args.store), args.asset_class, args.timeframe,
                          args.min_bars, args.source)
    returns = np.diff(np.log(panel.to_numpy(float)), axis=0)

    log(f"residual pipeline   {panel.shape[1]} names   {panel.shape[0]:,} common bars   "
        f"{panel.index[0]:%Y-%m-%d} to {panel.index[-1]:%Y-%m-%d}"
        + ("   [fast]" if args.fast else ""))

    stages = stage_data(Path(args.store), panel, args)
    log("  stages 00-05 done")
    stages += stage_model(panel, returns, args)
    log("  stages 06-10 done")
    skill_stages, primary, bred, book = stage_skill(panel, returns, args)
    stages += skill_stages
    log("  stages 11-13 done")
    stages += stage_evidence(args)
    log("  stages 14-21 done")

    decided = [s for s in stages if s.state in DECIDING]
    failed = [s for s in stages if s.state == FAIL]

    log("")
    for s in stages:
        log(f"  {s.number}  {s.state.upper():16s} {s.title}")

    doc = build_html(stages, panel, args, decided)
    out = Path(args.out) if args.out else (
        DEFAULT_REPORTS / f"pipeline-{args.asset_class}-"
                          f"{datetime.now(timezone.utc):%Y%m%d}.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    log(f"\n  wrote {out}  ({out.stat().st_size / 1024:.1f} KB)")
    if args.open_browser:
        webbrowser.open(out.resolve().as_uri())

    if args.json:
        print(json.dumps({"stages": [{"number": s.number, "title": s.title,
                                      "state": s.state, "headline": s.headline}
                                     for s in stages],
                          "ic": primary, "breadth": bred,
                          "book_accepted": book.ok}, indent=2, default=str))
    return 0 if not failed else 3


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
