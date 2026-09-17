# 2026-09-17 — S&P 500 member pair screen, and why the gate that killed it matters

## Subject

Screen equity pairs restricted to current large-cap index membership, as asked.
Intended as a cleaner universe than the earlier equity screens: index members are
liquid, tightly quoted and borrowable, which is the part of §1.3 of
[RESIDUAL.md](../plan/RESIDUAL.md) — financing — that has killed every candidate
this project has produced.

**Membership caveat.** Current S&P 500 membership was sourced and applied (503
names). Nasdaq-100 and Dow Jones constituent lists could not be retrieved — both
Wikipedia articles have moved their component tables elsewhere and the API
reports no components section. The filter applied is therefore SPX membership
alone. The Dow's thirty names and most of the Nasdaq-100 are large-cap US
listings that overlap SPX heavily, but that overlap was not verified here and the
filter should not be described as covering all three.

## Status

**Zero survivors of 380 pairs. Screen #22 in `logs/screens.csv`.**

135 of the 256 stored equities are current SPX members with 5,000+ bars. All 25
sectors had at least two eligible names, giving 380 within-sector pairs.

```
  cointegrated            84   noise alone would give about 19
  and out of sample       11
  and still there now      1   noise would give about 1.9
  and a stable ratio       0
  and a usable hedge       0
  and reverting in time    0   <- survivors
```

## The finding

The cointegration is real. 84 pairs against a noise floor of 19 is not a fluke,
and this is the first equity screen where the top of the funnel was clearly above
noise.

It does not persist, and the persistence is not merely weak — it is
indistinguishable from independent:

| | pairs |
|---|---|
| cointegrated in the early window | 55 |
| cointegrated in the late window | 41 |
| cointegrated in **both** | 5 |
| expected in both if the two windows were independent | 5.9 |

Observing 5 against an expectation of 5.9 (Poisson standard deviation about 2.4)
gives no basis to reject independence. **Knowing a pair was cointegrated early
tells you nothing about whether it is cointegrated now.**

That is the whole problem stated as a measurement rather than an opinion. A
screen selects on the full sample, which is dominated by the early window simply
because there is more of it; the relationship it selects has no better than
chance odds of being present when the position would be held. This is §1.2 of
RESIDUAL.md — the wrong model class — confirmed on the requested universe rather
than argued from `DOT~FIL` alone.

## The eleven that got furthest

All eleven pairs cointegrated on both the full sample and the held-out tail, with
what killed each:

| pair | sector | p | p_oos | p_early | p_late | β early | β late | half-life | killed by |
|---|---|---|---|---|---|---|---|---|---|
| FIS~FISV | payments | 0.0004 | 0.002 | 0.000 | 0.900 | 1.026 | 0.267 | 68 | gone late; ratio walked 3.8× |
| LRCX~MCHP | semis | 0.0005 | 0.014 | 0.270 | 0.955 | 0.741 | 1.887 | 70 | gone late; ratio walked 2.5× |
| HBAN~KEY | banks | 0.0042 | 0.038 | 0.266 | 0.341 | 0.879 | 0.681 | 67 | gone late |
| NUE~STLD | miners | 0.0055 | 0.023 | 0.001 | 0.648 | 0.456 | 0.753 | 86 | gone late |
| ES~WEC | utilities | 0.0070 | 0.020 | 0.155 | 0.594 | −0.708 | 0.240 | 77 | gone late; ratio walked 2.9× |
| NDAQ~SPGI | exchanges | 0.0154 | 0.000 | 0.764 | 0.652 | 2.031 | 1.173 | 81 | gone late |
| CMS~XEL | utilities | 0.0157 | 0.023 | 0.275 | 0.072 | 1.674 | 0.724 | 53 | gone late; net 29% |
| CMS~WEC | utilities | 0.0226 | 0.019 | 0.994 | 0.052 | 0.954 | 0.814 | 109 | gone late |
| MCO~NDAQ | exchanges | 0.0381 | 0.002 | 0.631 | 0.401 | 0.378 | 0.795 | 98 | gone late; ratio walked 2.1× |
| CMS~ES | utilities | 0.0389 | 0.048 | 0.988 | 0.033 | −0.245 | −0.002 | 123 | ratio collapsed to zero, 127× |
| MTB~TFC | banks | 0.0488 | 0.026 | 0.680 | 0.882 | 1.154 | 0.562 | 115 | gone late; ratio walked 2.1× |

Two things are visible beyond the individual verdicts.

**Every half-life is between 53 and 123 bars.** Even had one survived, it would
need to be held for three to six months per round trip. That is §1.3 again:
`SPY~DIA` earned +205 gross against −752 carry on exactly this kind of holding
period. A pair that reverts in eighty days cannot pay eighty nights of retail
financing out of a few hundred basis points of spread movement.

**The one pair that is present in the late window is present because it stopped
being a pair.** `CMS~ES` has a late-window beta of −0.002: the hedge ratio has
collapsed to zero, so the "spread" is now one leg on its own, and its
stationarity says something about `CMS` rather than about a relationship.

## Trials charged

380 within-sector tests, logged as screen #22. The project's running total rises
from 3,629 to 4,009. The deflated-Sharpe benchmark in Step 4 grows with the
logarithm of that count, so this screen has made every future candidate — from
this method or the residual one — slightly harder to establish. That is the
correct accounting and the reason the screen was run at the existing default
gates with nothing tuned.

## What this does not say

It does not say equity pairs never work; it says selection on a long sample does
not find pairs that are still related in the recent window, in this universe, at
these gates. Nor does it bear on Stage 0's result — that measured residuals, not
price-level pairs, and the two are different model classes.

If anything it sharpens the case for the residual redirection. A factor residual
does not need a stable long-run price ratio, which is precisely the property the
era check above shows these pairs do not have.
