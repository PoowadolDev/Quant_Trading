# Volume Anomaly Detection — 8 Concepts

Source: digests in `research/wiki/volume/`. Each concept below: what it is, how it works with a worked example, and clear Python build steps. Written for a single-symbol OHLCV bar series with columns `open, high, low, close, volume` indexed by UTC datetime (matches `MarketDataLoader` in `dev-tradingsystem.ipynb`).

Test data used in every worked example: 10 bars, volume = `[1000, 2000, 3000, 4000, 2500, 10000, 4000, 3000, 2000, 1000]`, spike at index 5.

---

## 1. Robust baseline (median/MAD) instead of naive z-score

### What is it

A naive anomaly z-score (`(x - mean) / std`) computed **from the same short window that contains the spike** is broken: the spike inflates its own mean and its own std, so it can hide itself ("masking"). The fix is to use **median** and **MAD** (median absolute deviation) instead of mean/std — both are resistant to a single extreme point, so the spike doesn't corrupt its own baseline.

### How it works — example

On the 10-bar test series:

| baseline | center | dispersion | z of bar 5 (value 10000) |
|---|---|---|---|
| naive mean/std | 3250 | 2462 | **2.74** ← fails a z>3 gate |
| robust median/MAD | 2750 | 1000 | **4.89** ← correctly fires |

`MAD = median(|x - median(x)|)`. To make MAD comparable to std under a normal distribution, scale it by `0.6745`:
`z_robust = 0.6745 * (x - median) / MAD`

### How to build it — steps

1. Take a rolling (or full-history) window of volume, **excluding or downweighting the current bar** if possible (see leave-one-out in concept 2 for the strict version).
2. Compute `med = median(window)`.
3. Compute `mad = median(abs(window - med))`. If `mad == 0` (flat/illiquid window), fall back to a small floor value or naive std to avoid division by zero.
4. Compute `z = 0.6745 * (current_volume - med) / mad`.
5. Flag anomaly if `abs(z) > threshold` (start with 3.5, a common robust-z convention).

```python
import numpy as np
import pandas as pd

def robust_z(volume: pd.Series, window: int = 20) -> pd.Series:
    med = volume.rolling(window).median()
    mad = (volume - med).abs().rolling(window).median()
    mad = mad.replace(0, np.nan)  # avoid div-by-zero on flat windows
    return 0.6745 * (volume - med) / mad

def flag_robust(volume: pd.Series, window: int = 20, threshold: float = 3.5) -> pd.Series:
    z = robust_z(volume, window)
    return z.abs() > threshold
```

---

## 2. Leave-one-out (LOO) baseline

### What is it

An even stricter version of concept 1: compute the baseline mean/std from the window **with the candidate bar removed entirely**, not just resistant to it. This guarantees zero self-contamination — the bar being tested never influences its own baseline.

### How it works — example

On the 10-bar series, removing bar 5 (value 10000) before computing stats:

| baseline | mean | std | z of bar 5 |
|---|---|---|---|
| naive (includes bar 5) | 3250 | 2462 | 2.74 |
| **LOO (excludes bar 5)** | 2500 | 1054 | **7.12** |

LOO gives the strongest signal of all three methods here because the spike has zero influence on its own reference stats.

### How to build it — steps

1. Choose a rolling window of length `N` ending at (but not including) the current bar — this is naturally leave-one-out if the window is strictly the *preceding* `N` bars.
2. Compute `mean` and `std` of that trailing window only.
3. Compute `z = (current_volume - mean) / std`.
4. Flag if `abs(z) > threshold`.

```python
def loo_z(volume: pd.Series, window: int = 20) -> pd.Series:
    # shift(1) ensures the window ends at t-1, so bar t never sees itself
    trailing = volume.shift(1).rolling(window)
    return (volume - trailing.mean()) / trailing.std()

def flag_loo(volume: pd.Series, window: int = 20, threshold: float = 3.0) -> pd.Series:
    z = loo_z(volume, window)
    return z.abs() > threshold
```

**Note:** `.shift(1).rolling(window)` is the standard pandas idiom for "trailing window excluding current bar" — it is exactly leave-one-out for streaming/online use, since future bars are never in the window anyway.

---

## 3. Intraday-pattern-normalized volume (ren_zhou Algorithm A)

### What is it

Raw volume has a strong deterministic time-of-day shape (open/close peaks, lunch-return surge). Without removing it, any threshold rule fires every day at the open and never at midday — you'd be detecting the clock, not anomalies. This concept builds a per-minute-of-day average profile and divides it out (division, not subtraction, because volume is positive and multiplicatively scaled).

### How it works — example

Suppose the 10:00 slot's volume over 5 historical days was `400k, 600k, 500k, 700k, 300k`.

1. `A(10:00) = (400k+600k+500k+700k+300k)/5 = 500,000` (the intraday pattern value for that slot).
2. New day, 10:00 bar has `V = 1,300,000` shares → `V' = V / A = 1,300,000 / 500,000 = 2.60`.
3. Scale by the sample std of `V'` (say `σ_V' = 1.118`) → `v = 2.60 / 1.118 = 2.326`.
4. If threshold `q = 2`, this bar is flagged (`2.326 > 2`).

Note the important caveat: step 3 divides by std but does **not** subtract the mean, so `v` is not a z-score — its mean is `≈ 1/σ_V'`, not 0. Two symbols with different `σ_V'` have different *effective* quantiles at the same `q`. If cross-symbol comparability matters, also subtract the mean of `v`.

### How to build it — steps

1. Collect historical intraday bars over many days, each tagged by its **minute-of-day slot** (e.g. `"09:31"`, `"09:32"`, ...).
2. For each slot, compute `A(slot) = mean(volume at that slot across all historical days)`. Use a **rolling** window of days (not the full static history) so the profile adapts to secular volume growth — a static profile computed once over years will drift stale.
3. For each new bar: `V'(t) = V(t) / A(slot_of_t)`.
4. Compute `σ_V' = std(V')` over the same rolling history.
5. `v(t) = V'(t) / σ_V'`.
6. Flag `v(t) > q` for your chosen threshold `q` (start around 2–3; sweep several values as ren_zhou does with `q = 2,3,4,5`).

```python
def build_intraday_profile(volume: pd.Series, lookback_days: int = 60) -> pd.Series:
    """volume: intraday bar series with a datetime index.
    Returns A(slot) keyed by time-of-day, averaged over the trailing lookback_days."""
    df = volume.to_frame("volume")
    df["slot"] = df.index.time
    df["day"] = df.index.date
    recent_days = sorted(df["day"].unique())[-lookback_days:]
    recent = df[df["day"].isin(recent_days)]
    return recent.groupby("slot")["volume"].mean()

def normalize_intraday_volume(volume: pd.Series, lookback_days: int = 60) -> pd.Series:
    profile = build_intraday_profile(volume, lookback_days)
    slot = pd.Series(volume.index.time, index=volume.index)
    A = slot.map(profile)
    v_prime = volume / A
    sigma = v_prime.std()
    return v_prime / sigma

def flag_intraday(volume: pd.Series, q: float = 2.5, lookback_days: int = 60) -> pd.Series:
    v = normalize_intraday_volume(volume, lookback_days)
    return v > q
```

---

## 4. Absolute × relative conjunction filter (mu_2010, inverted for single-bar spikes)

### What is it

An anomaly filter that requires **both** an absolute floor (economically meaningful size) **and** a relative condition (large versus the instrument's own recent activity), combined with AND — not either alone. Absolute-only fires constantly on busy names and never on quiet ones; relative-only fires on statistically loud but economically trivial wiggles.

**Important:** the original paper's relative leg (`|R| ≥ 6 × window volatility`) is mathematically proven (via Cauchy-Schwarz) to require at least 36 active minutes contributing — it structurally **excludes single-bar spikes**. Take the design pattern (AND of absolute + relative), not their parameters, when you want to catch single-bar events.

### How it works — example

Using the 10-bar series, define:
- absolute floor: `V(t) ≥ 8000` shares
- relative condition: `V(t) ≥ 3 × robust_std(recent window)` (robust std from concept 1, ≈1000 → threshold 3000)

Bar 5 = 10000: `10000 ≥ 8000` ✓ AND `10000 ≥ 3000` ✓ → **flagged**.
A hypothetical bar of 9000 in a *high-volume* stock where typical volume is 8500 ± 2000: `9000 ≥ 8000` ✓ but `9000 ≥ 3×2000=6000`... actually flags too since ratio small — the point is the relative leg is what prevents flagging *every* busy-stock bar as an "anomaly" just because it clears a fixed absolute number.

### How to build it — steps

1. Define an absolute floor appropriate to the instrument (e.g. a fixed share count, or a percentile of long-run volume like the 90th percentile).
2. Compute a relative dispersion measure from concept 1 or 2 (robust or LOO baseline).
3. Flag `t` only if **both** `V(t) ≥ absolute_floor` **and** `V(t) ≥ k × baseline_dispersion + baseline_center`.
4. Optionally add mu_2010's **window-shrinking** idea: once flagged at a wide window, retest at progressively shorter windows and keep the smallest window that still passes — this localizes the event more sharply.
5. **De-duplicate**: if multiple consecutive bars pass, keep only the first of each cluster (a burst is one event, not N events).

```python
def flag_conjunction(volume: pd.Series, abs_floor: float, k: float = 3.0,
                      window: int = 20) -> pd.Series:
    med = volume.shift(1).rolling(window).median()
    mad = (volume.shift(1) - med).abs().rolling(window).median().replace(0, np.nan)
    relative_ok = volume >= (med + k * 1.4826 * mad)   # 1.4826*MAD ≈ std equivalent
    absolute_ok = volume >= abs_floor
    return relative_ok & absolute_ok

def dedupe_events(flags: pd.Series) -> pd.Series:
    """Keep only the first bar of each consecutive run of flags."""
    return flags & ~flags.shift(1, fill_value=False)
```

---

## 5. Post-event aftermath shape (power-law relaxation vs instant revert)

### What is it

A genuine information/liquidity shock leaves a **slow-decaying tail** afterward — volume stays elevated with a power-law shape `t^-α` (α<1 means no characteristic timescale, elevated conditions persist much longer than an exponential-decay intuition would suggest). A one-off mechanical print (block trade, index rebalance, cross) instead **reverts immediately** with no persistence. This turns detection into **classification**: same-size spike, different meaning, based on what happens *after* it.

### How it works — example

Your 10-bar series: bars 7–10 after the spike are `4000, 3000, 2000, 1000` — dropping straight back to (and below) the pre-spike level within 4 bars, with no sustained elevation. That decay shape is the signature of a **mechanical print**, not a real shock — a genuine shock (per ren_zhou) would keep volume elevated for tens to ~120 bars/minutes before cooling.

### How to build it — steps

1. After each flagged bar (from any of the above detectors), collect the next `H` bars of volume (`H` = your lookahead horizon, e.g. 20–120 bars depending on your bar size).
2. Normalize by the pre-event baseline: `excess(t) = volume(event_time + t) / baseline`.
3. Fit `excess(t) ≈ c * t^-α` via log-log linear regression: `log(excess) = log(c) - α * log(t)`.
4. Classify:
   - **good fit, α < 1** → persistent/real event (information-driven)
   - **fast decay back to baseline within 1-3 bars, poor power-law fit** → mechanical/one-off print
5. Use `scipy.stats.linregress` on the log-log data for the fit; use R² as the fit-quality gate.

```python
from scipy import stats
import numpy as np

def classify_aftermath(volume: pd.Series, event_idx: int, baseline: float,
                        horizon: int = 20, min_r2: float = 0.5) -> dict:
    after = volume.iloc[event_idx + 1: event_idx + 1 + horizon]
    excess = (after / baseline).clip(lower=1e-9)
    t = np.arange(1, len(excess) + 1)
    mask = excess > 1.0  # only fit while still elevated
    if mask.sum() < 3:
        return {"kind": "instant_revert", "alpha": None, "r2": None}

    log_t, log_excess = np.log(t[mask]), np.log(excess[mask])
    slope, intercept, r, _, _ = stats.linregress(log_t, log_excess)
    alpha, r2 = -slope, r ** 2
    kind = "persistent_shock" if (r2 >= min_r2 and 0 < alpha < 1) else "instant_revert"
    return {"kind": kind, "alpha": alpha, "r2": r2}
```

---

## 6. Price-context filter (return leads volume clustering)

### What is it

Volume bursts tend to **follow** large price moves, not the reverse — a directional (asymmetric-in-time) relationship. If a volume spike was preceded by a notable return move, it's likely endogenous/expected (price moved, volume followed). If a spike happens with **no preceding price move**, it's a purer, more unusual volume-only anomaly. Use this as a filter dimension, not a standalone signal — the correlation is weak (documented as explaining only ~3% of variance in the source paper), so treat it as a tilt, never a trade trigger by itself.

### How it works — example

Say bars 1–5 (pre-spike) show `close` moving less than 0.1% per bar (flat, quiet market) and bar 6's own return is also small (the 10000-volume bar isn't a big up/down candle). Then the spike has **no price precursor** → classify as "pure volume anomaly", more interesting for further investigation than a spike that followed a 3% price jump (which would just be "volume caught up to price").

### How to build it — steps

1. Compute the absolute return over a short lookback window ending just before the candidate bar: `pre_move = abs(log(close[t-1]) - log(close[t-1-L]))` for some small `L` (e.g. 3–5 bars).
2. Compute a z-score or percentile of `pre_move` against its own history (same robust-baseline approach as concept 1).
3. Tag each volume anomaly as:
   - **"endogenous"** if `pre_move` z-score is also elevated (say > 2)
   - **"pure"** if `pre_move` is unremarkable
4. Use this tag to prioritize review — "pure" anomalies are the ones worth investigating first since they're not explained by an obvious price catalyst.

```python
def price_precursor_score(close: pd.Series, lookback: int = 5, window: int = 20) -> pd.Series:
    ret = np.log(close).diff(lookback).abs()
    med = ret.shift(1).rolling(window).median()
    mad = (ret.shift(1) - med).abs().rolling(window).median().replace(0, np.nan)
    return 0.6745 * (ret - med) / mad

def tag_anomalies(volume_flags: pd.Series, close: pd.Series,
                   endogenous_threshold: float = 2.0) -> pd.Series:
    precursor_z = price_precursor_score(close)
    tags = pd.Series("pure", index=volume_flags.index)
    tags[volume_flags & (precursor_z.abs() > endogenous_threshold)] = "endogenous"
    tags[~volume_flags] = None
    return tags
```

---

## 7. Volume-vs-price profile shape (shi_2010 Bessel fit) and base-rate anchor

### What is it

Instead of plotting volume against **time**, plot accumulated volume against **price** for one session (or window): for each traded price level, sum the volume executed there, normalize by total volume. A well-behaved session produces one dominant peak (single-centered distribution). A session whose volume profile has **two or more peaks** signals the equilibrium price itself jumped mid-session — a structurally different kind of "abnormal" from a simple single-bar spike. This also gives a useful **calibration anchor**: in the source data, ~94% of sessions fit a single-peak model — if your detector flags a much higher fraction of days as abnormal, it's likely mis-tuned.

### How it works — example

For one session, build the volume-by-price profile: bin executed volume into price buckets, normalize so it sums to 1. If the profile has one clear peak → normal session. If two separated peaks emerge (say, one cluster of volume near price 100.20 and another near 101.50 within the same session) → the market's fair-value anchor visibly shifted mid-session; that session's "spike" isn't noise, it's a regime change.

### How to build it — steps

1. For a session (or rolling window), bin trades/bars by price level (e.g. round to nearest tick or use N equal-width bins spanning the session's high-low range).
2. Sum volume in each price bin, divide by total session volume → `P(price_bin) = volume_in_bin / total_volume`.
3. Fit a simple unimodal shape (a Gaussian, or a peak-finding routine) to `P` vs `price_bin`.
4. Check for a **second peak**: use `scipy.signal.find_peaks` on the profile; if it returns ≥2 significant peaks (height above some minimum, separated by enough bins), classify the session as "multi-centered" / regime-shift day rather than a simple single-peak day.
5. Track the fraction of sessions classified as multi-centered over time as a **calibration check** — expect it in the single-digit percent range for a well-tuned detector; a much higher rate suggests your peak-detection thresholds are too loose.

```python
from scipy.signal import find_peaks
import numpy as np

def volume_price_profile(high: pd.Series, low: pd.Series, close: pd.Series,
                          volume: pd.Series, n_bins: int = 30) -> pd.Series:
    price_range = np.linspace(low.min(), high.max(), n_bins + 1)
    bin_idx = np.digitize(close, price_range) - 1
    bin_idx = bin_idx.clip(0, n_bins - 1)
    profile = pd.Series(volume.values, index=bin_idx).groupby(level=0).sum()
    profile = profile.reindex(range(n_bins), fill_value=0)
    return profile / profile.sum()

def classify_session_shape(profile: pd.Series, min_peak_height: float = 0.05,
                            min_distance: int = 3) -> str:
    peaks, _ = find_peaks(profile.values, height=min_peak_height, distance=min_distance)
    return "multi_centered" if len(peaks) >= 2 else "single_centered"
```

---

## 8. Volume clock reframe (chang_2019)

### What is it

Instead of sampling bars at fixed **time** intervals (1m, 5m, ...), sample bars at fixed **volume** intervals — a bar closes whenever a fixed number of shares/contracts has traded, regardless of how long that took. Under a volume clock, a volume spike simply gets absorbed into more (shorter-duration) bars around that moment rather than showing up as one abnormally large print. This is a **design choice**, not a detector: use it when you want the spike to disappear into normal trading flow (e.g. for execution/backtesting where you want smooth participation), and deliberately avoid it (stay on a time clock) when the goal is to keep the spike **visible** as a detectable event.

### How it works — example

Suppose bucket size is set to 2500 shares. Time-clock bars are `1000, 2000, 3000, 4000, 2500, 10000, 4000, ...`. Under a 2500-share volume clock, that huge 10000 print doesn't create one bar — it gets split into 4 volume-clock bars of exactly 2500 each (using the price path within that print), so no single bar shows "10x normal size." The information is preserved (more bars appear in that stretch, and if you look at *bar count per unit time* that spikes instead) but the raw "one bar = 10000 shares" anomaly is gone by construction.

### How to build it — steps

1. Choose a bucket size `v` (shares/contracts per bar). Two conventions: **intrinsic** (per-instrument bucket size, e.g. `ADV / N` for N buckets/day) or a single shared bucket size across instruments if you need cross-asset comparability.
2. Take the raw trade-level (or highest-resolution available) stream of `(timestamp, price, volume)`.
3. Accumulate volume trade-by-trade; whenever cumulative volume crosses a multiple of `v`, close a bar: OHLC from the prices seen since the last close, volume = `v` (or the actual accumulated amount if trades don't split evenly).
4. If you only have OHLCV bars (not raw trades), approximate by treating each bar's volume as if evenly distributed within it, splitting/merging bars to hit multiples of `v`.
5. Recompute your detectors (concepts 1–7) on the volume-clock series if you want spike-dissolving behavior, or keep them on the original time-clock series if you want the spike to stay visible — pick deliberately based on whether the goal is trading-through-the-event or detecting-the-event.

```python
def build_volume_clock_bars(trades: pd.DataFrame, bucket_size: float) -> pd.DataFrame:
    """trades: DataFrame with columns ['price', 'volume'], datetime index, trade-level resolution."""
    bars = []
    cum_vol, bucket_start_idx = 0.0, 0
    prices_in_bucket = []

    for i, (ts, row) in enumerate(trades.iterrows()):
        prices_in_bucket.append(row["price"])
        cum_vol += row["volume"]
        while cum_vol >= bucket_size:
            seg = prices_in_bucket
            bars.append({
                "close_time": ts,
                "open": seg[0], "high": max(seg), "low": min(seg), "close": seg[-1],
                "volume": bucket_size,
            })
            cum_vol -= bucket_size
            prices_in_bucket = [row["price"]]  # carry remainder into next bucket

    return pd.DataFrame(bars).set_index("close_time")
```

---

## Suggested combination

None of these concepts is sufficient alone. A practical detector composes them:

1. **Baseline** (concept 1 or 2) → is this bar unusual at all, without self-contamination?
2. **Conjunction filter** (concept 4) → is it both absolutely and relatively large?
3. **Aftermath classification** (concept 5) → does it persist (real) or revert instantly (mechanical print)?
4. **Price-context tag** (concept 6) → was it preceded by a price move (endogenous) or not (pure)?
5. **Session shape check** (concept 7) → sanity-check your overall flag rate against the ~5-6% base rate anchor.
6. **Clock choice** (concept 8) → decide upfront whether the pipeline should run on time bars (spike visible) or volume bars (spike absorbed) before applying 1-5.

Minimum data requirement: baselines (concepts 1-3) need enough history that the window isn't dominated by the candidate bar — tens of bars minimum for LOO/robust stats, and many days of same-time-of-day history for the intraday profile (concept 3). A single 10-bar window, as in the worked examples here, is illustrative only, not statistically sufficient on its own.
