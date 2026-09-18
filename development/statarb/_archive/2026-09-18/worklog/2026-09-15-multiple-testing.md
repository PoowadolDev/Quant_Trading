# 2026-09-15 — Step 4.1: how many tests were really run

## Subject

Build the first Step 4 script and point it at the project's own headline number:
144 cointegrated pairs where "noise alone would give about 59".

## Status

**Done. The answer changes what the screen means, and the script caught an error in its own
first draft.**

| Item | Status |
|---|---|
| `screen.py --dump` — per-pair p-values, so corrections need no re-run | ✅ built |
| `multiple_testing.py` — Benjamini-Hochberg, effective tests, block bootstrap | ✅ built |
| `verify_validation.py` | ✅ 49 checks green |
| Mutation test — five deliberate defects | ✅ five caught |
| Run on equities, forex and sector ETFs | ✅ done and logged |
| Follow-through: the shortlist through Step 3 | ✅ both rejected |

## The error the script found in itself

The first draft reported three estimates of the expected rejection count, one of them being
`effective tests × level`. On sector ETFs it printed:

```
naive                        105       5.2   every pair is an independent test
effective (correlation)        5       0.2   pairs sharing legs share errors
```

and then the bootstrap — the one estimate that measures rather than assumes — returned
**4.8**, next to the naive 5.2 and nowhere near 0.2.

The bootstrap was right and the reasoning behind the effective-tests row was wrong.
**Expectation is linear.** Under the null every test rejects with probability `level`
whatever its correlation with the others, so the expected count is `N × level` however
dependent the tests are. What dependence inflates is the **variance**: measured standard
deviation 3.77 against 2.23 for an independent binomial, a factor of 1.7.

The effective count is still useful, in the place it belongs: a family-wise threshold.
Šidák on 4.5 effective tests gives 0.0113, so on that universe a pair needs p below 1.1% to
be significant across the family rather than 5%.

The first draft also printed the self-contradictory line **"NO EXCESS — 6 rejections against
0.2 expected"**, because it collapsed two different questions into one verdict. It now
reports them separately, and they are allowed to disagree:

- **population** — is there more here than chance? Decided by the bootstrap p-value, not by
  comparing a count to a mean. Six against 4.8 reads like an excess and happens 39% of the
  time.
- **individuals** — does any single pair survive a false discovery rate?

## The headline number, corrected

```
equities, within sector — 1,171 pairs with a finite p-value, 250 instruments

observed rejections     144
expected                 58.6   = 1,171 x 0.05, and dependence does not change this
if independent, s.d.      7.46
bootstrap mean           78.8   against 58.6 expected
bootstrap s.d.          17.06   dependence widens it 2.3x
                                25 replicates, standard error of the mean 3.41
```

**The bootstrap mean is 78.8, not 58.6.** Those are meant to agree, and they do not — the
gap is six standard errors. The cause is not the test: measured on clean independent random
walks, Engle-Granger with the screen's fixed lag rejects at 5.33%, inside tolerance of 5%.

```
lags    1    5.33%      lags  aic    4.42%
lags    2    3.83%      lags  bic    4.17%
lags    5    3.75%
```

The cause is the **data**. Real equity returns carry serial correlation, volatility
clustering and fat tails that a random walk does not, and the block bootstrap preserves
them. On series that look like real equities but are unrelated by construction, the test
rejects about 6.7% of the time rather than 5%.

So the honest noise floor for this screen was never 59. It is **79**, and the screen has
been comparing against a number a third too low.

Against the correct floor: **144 observed, 78.8 expected, bootstrap p = 0.038.** A real
excess, and a far smaller one than 144-against-59 implied.

## Benjamini-Hochberg: sixteen names

At a 10% false discovery rate, sixteen pairs survive, threshold p ≤ 0.00123:

| pair | sector | p | p_late | net | swing |
|---|---|---|---|---|---|
| `KEY~RF` | banks | 0.00000 | 0.579 | 8% | 1.44 |
| `CB~TRV` | insurers | 0.00001 | 0.369 | 0% | 1.34 |
| `RF~ZION` | banks | 0.00001 | 0.562 | 11% | 4.17 |
| `RSG~WM` | waste | 0.00002 | **0.021** | 6% | 3.20 |
| `CNC~HUM` | health providers | 0.00002 | 0.247 | 10% | 2.30 |
| `CNC~UNH` | health providers | 0.00003 | 0.152 | 11% | 1.44 |
| `KEY~ZION` | banks | 0.00011 | **0.022** | 4% | 3.97 |
| `FIS~FISV` | payments | 0.00038 | 0.900 | 14% | 3.85 |
| `LRCX~MCHP` | semis | 0.00045 | 0.955 | 11% | 2.55 |
| `JBHT~XPO` | truckers | 0.00052 | 0.608 | 37% | ∞ |
| `CCI~O` | REITs | 0.00053 | 0.834 | 17% | ∞ |
| `CNC~ELV` | health providers | 0.00066 | 0.211 | 25% | 1.79 |
| `ADI~NVDA` | semis | 0.00076 | 0.461 | 66% | 8.28 |
| `AMT~O` | REITs | 0.00085 | 0.228 | 18% | ∞ |
| `JNJ~PFE` | pharma | 0.00118 | 0.784 | 67% | 68.64 |
| `ADSK~SNPS` | software | 0.00123 | 0.210 | 58% | ∞ |

These are not arbitrary. Regional banks against regional banks, the two firms that are the
US waste industry, three health insurers, two payment processors. The economic-link gate
did its job: what came out has reasons to move together.

**Fourteen of the sixteen are gone by the late reserved window.** Only `RSG~WM` and
`KEY~ZION` still cointegrate in the most recent quarter of the record, and both have hedge
ratios that swing by more than the 3× limit.

## Following through

Both survivors went through Step 3:

```
RSG~WM      prediction FAILS 25.9x   no threshold pays   size 0.00
KEY~ZION    prediction FAILS 37.6x   no threshold pays   size 0.00
```

and this time the failure is blunter than usual — not "the sample does not establish a
positive mean" but **the realised mean is negative**. The strongest statistical pairs in the
project, on the cleanest economic stories available, lose money when traded.

## What this establishes

Three things that were previously assumed:

1. **The screen's noise floor was a third too low.** Corrected, the excess over chance is
   real but modest: p = 0.038 rather than the overwhelming margin 144-against-59 suggested.
2. **Statistical strength and tradeability are close to unrelated here.** The sixteen
   strongest pairs in 1,171 include two that are still alive, and both lose money.
3. **Dependence between tests inflates the spread of outcomes by a factor of 2.3.** Any
   future screen reporting "N found against M expected" without that is over-claiming, and
   the bootstrap is the only one of the three estimates that gets it right.

## Verification

49 checks in `verify_validation.py`, bringing the project to **496 across five suites**.

The load-bearing ones: Benjamini-Hochberg against a set worked out by hand and at both
boundaries; the null calibration that caught the expected-count error; a block-resampling
check that the resample keeps each series' own serial correlation *and* destroys the
relation between series, with single-observation resampling shown to fail the first half;
and an assertion that no function returns a single combined score, because the study this
plan cites found a composite has no forward relationship.

**Mutation-tested at five defects, five caught** — but only after one mutation was rewritten.
The first version of "block resampling becomes single-observation resampling" changed how
many block starts were drawn rather than the blocking itself, so the code still blocked and
the suite was right to pass. A mutation that does not mutate proves nothing about the test.

## Next

`deflated_sharpe.py` is the natural follow-on, and the trial count it needs is already
logged. But the more useful question now may be the one this raised: the screen compares
against a floor of `N × level`, and the measured floor is 6.7% rather than 5%. Feeding the
bootstrap estimate back into `screen.py` would stop it over-claiming on every future run.
