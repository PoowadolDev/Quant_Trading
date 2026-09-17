"""Step 2.2 — compare hedge ratio estimators, and check the hedge is a hedge.

Two questions, and the second matters more than the first.

**Which estimator?** A static ratio is one number for the whole sample. A rolling
one refits on a trailing window. A Kalman filter treats the ratio as a hidden
state that moves a little every bar. The filter always fits better in sample, so
the comparison is decided out of sample or not at all.

**Is it a hedge at all?** A spread is `A - beta*B`, so the position is long one
unit of A and short `beta` of B. When `beta` is negative that second leg flips:
both legs sit on the same side of the market and the position is a leveraged
directional bet wearing a spread's clothes. Measured on stored forex data, the
share of time a ratio spends at or below zero separates the two cleanly —
genuine pairs never go there, and the three that did were 33% to 44% of the time.

    python hedge.py -s USDNOK,USDZAR
    python hedge.py -s EURCHF,EURJPY --method all --window 120
    python hedge.py -s BTC-USDT,ETH-USDT -a crypto --kalman-delta 1e-5

Exit codes: 0 the pair is a usable hedge, 3 it is not, 2 usage error.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import paths

paths.ensure_code_importable()
paths.ensure_marketdata_importable()

import relationship as rel
import pair_report as pr                                          # noqa: E402

UserError = pr.UserError
DEFAULT_LOG = paths.LOGS / "hedge.csv"


def net_exposure(beta: float) -> float:
    """Net over gross exposure, from the leg weights (1, -beta).

    Zero means the legs cancel exactly. One means the second leg does nothing
    and the position is a single-name bet. A ratio of 0.10 gives 0.82, which is
    why the ratio alone is not a neutrality test.

    Module level rather than a method because the risk layer needs it for a
    relationship it has not fitted an `Estimate` for, and a second copy of this
    formula is how the screen came to admit a position that was 72% net long.
    """
    if not math.isfinite(beta):
        return float("inf")
    gross = 1.0 + abs(beta)
    return abs(1.0 - beta) / gross if gross else float("inf")


def currency_legs(symbol: str) -> tuple[str, str] | None:
    """The base and quote currency of a six-letter forex symbol, or None."""
    symbol = symbol.upper()
    if len(symbol) != 6 or not symbol.isalpha():
        return None
    return symbol[:3], symbol[3:]


def fx_net_exposure(a: str, b: str, beta: float) -> float:
    """Neutrality of a forex spread measured in currency space, not leg space.

    `net_exposure` assumes both legs are quoted the same way round, which is
    true of two equities and false of two currency pairs. `AUDUSD` is AUD/USD
    and `USDNOK` is USD/NOK: the dollar sits on opposite sides, the two rates
    move oppositely, and the fitted beta comes out negative. The leg weights
    are then `(1, +|beta|)` -- long both -- and `net_exposure` reports 100%,
    reading the position as fully directional.

    It is not. Long AUDUSD plus long USDNOK is long AUD, short NOK, and the
    dollar cancels. Every one of the 28 negative-beta pairs in the 2026-09-18
    forex screen scored exactly 100% for this reason, which is what a
    systematic representation error looks like rather than a run of bad pairs.

    So the exposure is summed per currency instead. Holding `(1, -beta)` of two
    pairs, each long unit of `XXXYYY` is `+1 XXX` and `-1 YYY`, and the
    neutrality that matters is whether the **shared** currency cancels: the
    other two are the spread itself and are supposed to be non-zero.

    Falls back to `net_exposure` when the symbols are not forex or share no
    currency, so a caller can use it unconditionally.
    """
    if not math.isfinite(beta):
        return float("inf")
    legs_a, legs_b = currency_legs(a), currency_legs(b)
    if legs_a is None or legs_b is None:
        return net_exposure(beta)
    shared = set(legs_a) & set(legs_b)
    if len(shared) != 1:
        return net_exposure(beta)
    ccy = shared.pop()

    # +1 when the currency is the base of the quote, -1 when it is the quote.
    sign_a = 1.0 if legs_a[0] == ccy else -1.0
    sign_b = 1.0 if legs_b[0] == ccy else -1.0
    w_a, w_b = 1.0, -beta
    gross = abs(w_a) + abs(w_b)
    if gross == 0:
        return float("inf")
    return abs(w_a * sign_a + w_b * sign_b) / gross


@dataclass
class Estimate:
    method: str
    beta_path: np.ndarray
    beta_final: float
    beta_min: float
    beta_max: float
    negative_share: float
    sign_flips: int
    half_life_is: float
    half_life_oos: float
    spread_sd_bps: float

    def net_exposure(self) -> float:
        """Net over gross exposure for this estimate's final hedge ratio."""
        return net_exposure(self.beta_final)

    def usable(self, min_abs_beta: float, max_negative_share: float,
               max_net_exposure: float = 1.0) -> bool:
        return (abs(self.beta_final) >= min_abs_beta
                and self.negative_share <= max_negative_share
                and self.net_exposure() <= max_net_exposure)


def _ou_half_life(spread: np.ndarray) -> float:
    """Half-life in bars, or NaN when the series is not an OU process."""
    s = spread[np.isfinite(spread)]
    if len(s) < 30:
        return float("nan")
    ar = float(np.polyfit(s[:-1], s[1:], 1)[0])
    return math.log(2) / -math.log(ar) if 0.0 < ar < 1.0 else float("nan")


def static_beta(y: np.ndarray, x: np.ndarray, split: int) -> np.ndarray:
    """One ratio for the whole sample, fitted in sample only."""
    beta, _ = rel.ols_beta(y, x, split=split)
    return np.full(len(y), beta)


def rolling_beta(y: np.ndarray, x: np.ndarray, window: int) -> np.ndarray:
    """Refit on a trailing window. The first `window` bars have no estimate."""
    out = np.full(len(y), np.nan)
    for i in range(window, len(y) + 1):
        beta, _ = rel.ols_beta(y[i - window:i], x[i - window:i])
        out[i - 1] = beta
    return out


def kalman_beta(y: np.ndarray, x: np.ndarray, *, delta: float,
                obs_var: float | None, fit_through: int | None = None) -> np.ndarray:
    """Hedge ratio as a hidden state that drifts a little each bar.

    The state is [beta, alpha] and the observation is `y = beta*x + alpha + noise`.
    `delta` sets how much the state is allowed to move between bars: as it goes to
    zero the filter stops moving and reduces to ordinary least squares, which the
    verification suite checks.

    statsmodels ships a Kalman filter, but its state-space extension is blocked by
    an Application Control policy on this machine, so the recursion is written out
    here. It is the standard two-state form and nothing about it is novel.
    """
    n = len(y)
    # Everything the filter is seeded with must come from the start of the
    # sample. Measuring the observation variance over the whole series would let
    # a bar in 2026 change the ratio the filter reports for 2020, which is the
    # look-ahead this design exists to avoid.
    through = n if fit_through is None else max(60, min(fit_through, n))
    if obs_var is None:
        head_x, head_y = x[:through], y[:through]
        head_beta, head_alpha = rel.ols_beta(head_y, head_x)
        resid = rel.build_spread(head_y, head_x, head_beta, head_alpha)
        obs_var = float(np.var(resid, ddof=2)) or 1e-8
    state_cov = delta / (1.0 - delta) * np.eye(2)

    seed_beta, _ = rel.ols_beta(y, x, split=60)
    state = np.array([seed_beta, 0.0])
    cov = np.eye(2) * 1e-3
    out = np.full(n, np.nan)
    for t in range(n):
        obs = np.array([x[t], 1.0])
        cov = cov + state_cov                       # the state may have moved
        resid = y[t] - obs @ state
        var = obs @ cov @ obs + obs_var
        gain = cov @ obs / var
        state = state + gain * resid
        cov = cov - np.outer(gain, obs) @ cov
        out[t] = state[0]
    return out


def evaluate(method: str, betas: np.ndarray, y: np.ndarray, x: np.ndarray,
             split: int) -> Estimate:
    valid = np.isfinite(betas)
    spread = np.where(valid, y - betas * x, np.nan)
    spread = spread - np.nanmean(spread[:split][np.isfinite(spread[:split])])
    live = betas[valid]
    flips = int(np.sum(np.sign(live[1:]) != np.sign(live[:-1]))) if len(live) > 1 else 0
    return Estimate(
        method=method, beta_path=betas, beta_final=float(live[-1]) if len(live) else float("nan"),
        beta_min=float(np.min(live)) if len(live) else float("nan"),
        beta_max=float(np.max(live)) if len(live) else float("nan"),
        negative_share=float(np.mean(live <= 0)) if len(live) else float("nan"),
        sign_flips=flips,
        half_life_is=_ou_half_life(spread[:split]),
        half_life_oos=_ou_half_life(spread[split:]),
        spread_sd_bps=float(np.nanstd(spread) * 1e4))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hedge", description=__doc__.splitlines()[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sel = p.add_argument_group("selection")
    sel.add_argument("-s", "--symbols", required=True)
    sel.add_argument("-a", "--asset-class", default="forex")
    sel.add_argument("-t", "--timeframe", default="1d")
    sel.add_argument("--source", default=None)
    sel.add_argument("--start", default=None)
    sel.add_argument("--end", default=None)

    struct = p.add_argument_group("structure - choose once, not per run")
    struct.add_argument("--method", default="all",
                        choices=("all", "static", "rolling", "kalman"))
    struct.add_argument("--price", default="log", choices=("log", "raw"))

    search = p.add_argument_group("searched - every value is a trial")
    search.add_argument("--split", type=float, default=0.70)
    search.add_argument("--window", type=int, default=250, help="rolling window in bars")
    search.add_argument("--kalman-delta", type=float, default=1e-4,
                        help="how much the ratio may move per bar; smaller is stiffer")
    search.add_argument("--kalman-obs-var", type=float, default=None,
                        help="observation variance; measured from the data when unset")

    gate = p.add_argument_group("hedge quality gate")
    gate.add_argument("--min-abs-beta", type=float, default=0.10,
                      help="below this the second leg barely participates, so the "
                           "position is effectively a single-instrument trade")
    gate.add_argument("--max-negative-share", type=float, default=0.10,
                      help="share of the sample the ratio may spend at or below zero "
                           "before the pair is not a hedge")
    gate.add_argument("--max-net-exposure", type=float, default=0.35,
                      help="net exposure as a share of gross. A hedge ratio of 0.10 "
                           "leaves 82%% net, which is a single-name bet wearing a "
                           "spread's name; 0.35 corresponds to a ratio of about 0.48")

    out = p.add_argument_group("output")
    out.add_argument("--store", default=str(paths.STORE))
    out.add_argument("--log", default=str(DEFAULT_LOG))
    out.add_argument("--no-log", action="store_true")
    out.add_argument("--json", action="store_true")
    out.add_argument("-q", "--quiet", action="store_true")
    out.add_argument("-v", "--verbose", action="store_true")
    out.add_argument("--hedge", default="ols", help=argparse.SUPPRESS)
    out.add_argument("--min-half-life", type=float, default=2.0, help=argparse.SUPPRESS)
    out.add_argument("--max-half-life", type=float, default=1e9, help=argparse.SUPPRESS)
    out.add_argument("--entry-z", type=float, default=2.0, help=argparse.SUPPRESS)
    out.add_argument("--exit-z", type=float, default=0.5, help=argparse.SUPPRESS)
    return p


def append_log(path: Path, args, pair: str, best: Estimate, usable: bool) -> int:
    row = {"run": 0, "run_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "pair": pair, "timeframe": args.timeframe, "method": best.method,
           "window": args.window, "kalman_delta": args.kalman_delta,
           "split": args.split, "beta_final": round(best.beta_final, 6),
           "beta_min": round(best.beta_min, 6), "beta_max": round(best.beta_max, 6),
           "negative_share": round(best.negative_share, 4),
           "sign_flips": best.sign_flips,
           "half_life_is": ("" if not math.isfinite(best.half_life_is)
                            else round(best.half_life_is, 2)),
           "half_life_oos": ("" if not math.isfinite(best.half_life_oos)
                             else round(best.half_life_oos, 2)),
           "usable_hedge": "yes" if usable else "no"}
    path.parent.mkdir(parents=True, exist_ok=True)
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
    return row["run"]


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))
    if args.window < 30:
        raise UserError("--window must be at least 30 bars")
    if not 0.0 < args.kalman_delta < 1.0:
        raise UserError("--kalman-delta must be between 0 and 1")

    px = pr.load_prices(args)
    a, b = px.columns
    split = int(len(px) * args.split)
    if args.window >= split:
        raise UserError(f"--window {args.window} leaves no in-sample bars before the "
                        f"split at {split}")
    lp = np.log(px) if args.price == "log" else px
    y = lp[a].to_numpy(float)
    x = lp[b].to_numpy(float)

    wanted = (("static", "rolling", "kalman") if args.method == "all"
              else (args.method,))
    estimates = []
    for method in wanted:
        if method == "static":
            betas = static_beta(y, x, split)
        elif method == "rolling":
            betas = rolling_beta(y, x, args.window)
        else:
            betas = kalman_beta(y, x, delta=args.kalman_delta,
                                obs_var=args.kalman_obs_var, fit_through=split)
        estimates.append(evaluate(method, betas, y, x, split))

    log(f"{a} ~ {b}   {args.timeframe}   {px.index[0]:%Y-%m-%d} to "
        f"{px.index[-1]:%Y-%m-%d}   {len(px):,} bars")
    log("")
    log(f"  {'estimator':10s} {'final':>8s} {'min':>8s} {'max':>8s} {'<= 0':>7s} "
        f"{'net':>6s} {'hl in':>7s} {'hl out':>7s} {'hedge?':>8s}")
    for e in estimates:
        hl_is = f"{e.half_life_is:.1f}" if math.isfinite(e.half_life_is) else "none"
        hl_oos = f"{e.half_life_oos:.1f}" if math.isfinite(e.half_life_oos) else "none"
        ok = e.usable(args.min_abs_beta, args.max_negative_share, args.max_net_exposure)
        log(f"  {e.method:10s} {e.beta_final:+8.3f} {e.beta_min:+8.3f} {e.beta_max:+8.3f} "
            f"{e.negative_share:7.0%} {e.net_exposure():6.0%} {hl_is:>7s} {hl_oos:>7s} "
            f"{('yes' if ok else 'NO'):>8s}")

    # The estimator is chosen on the held-out half. Fitting better in sample is
    # what a filter does by construction, so it cannot be the criterion.
    def score(e: Estimate) -> float:
        if not e.usable(args.min_abs_beta, args.max_negative_share, args.max_net_exposure):
            return math.inf
        if not (math.isfinite(e.half_life_is) and math.isfinite(e.half_life_oos)):
            return math.inf
        lo, hi = sorted((e.half_life_is, e.half_life_oos))
        return hi / lo if lo > 0 else math.inf

    ranked = sorted(estimates, key=score)
    best = ranked[0]
    usable = best.usable(args.min_abs_beta, args.max_negative_share, args.max_net_exposure)

    log("")
    if not usable:
        # Report the reasons for the estimator that was actually ranked first,
        # and name every condition it failed rather than only the first.
        reasons = []
        if abs(best.beta_final) < args.min_abs_beta:
            reasons.append(f"the ratio is {best.beta_final:+.3f}, below the floor of "
                           f"{args.min_abs_beta:g}, so the second leg barely participates")
        if best.net_exposure() > args.max_net_exposure:
            reasons.append(f"net exposure is {best.net_exposure():.0%} of gross, above "
                           f"the {args.max_net_exposure:.0%} limit, so most of the risk "
                           "is directional rather than in the spread")
        if best.negative_share > args.max_negative_share:
            reasons.append(f"the ratio is at or below zero {best.negative_share:.0%} of "
                           f"the time, above the {args.max_negative_share:.0%} limit")
        log(f"  NOT A HEDGE ({best.method}) — " + "; ".join(reasons) + ".")
        log("  A ratio at or below zero puts both legs on the same side of the market,")
        log("  which is a directional position rather than a spread, and no estimator")
        log("  repairs that. Every estimator tried is shown above.")
    elif math.isinf(score(best)):
        log(f"  USABLE HEDGE, but no estimator produced a mean-reverting spread in both "
            f"halves; {best.method} is the least bad.")
    else:
        log(f"  BEST ESTIMATOR: {best.method} — half-life {best.half_life_is:.1f} in "
            f"sample against {best.half_life_oos:.1f} out, a ratio of {score(best):.2f}")
        if best.method != "static":
            static = next((e for e in estimates if e.method == "static"), None)
            if static is not None and math.isfinite(score(static)):
                log(f"  static is the baseline at {score(static):.2f}; "
                    f"{best.method} beats it out of sample")

    if args.json:
        print(json.dumps({"pair": f"{a}~{b}", "usable_hedge": usable,
                          "best": best.method,
                          "estimates": [{k: v for k, v in asdict(e).items()
                                         if k != "beta_path"} for e in estimates]},
                         indent=2, default=str))
    if not args.no_log:
        run = append_log(Path(args.log), args, f"{a}~{b}", best, usable)
        log(f"\n  run #{run} logged to {Path(args.log).resolve()}")
    return 0 if usable else 3


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
