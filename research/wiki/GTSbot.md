# Grid Trading System Robot (GTSbot): A Novel Mathematical Algorithm for Trading FX Market

## 1. Paper Information

| Fields | Detail |
|---|---|
| Title | Grid Trading System Robot (GTSbot): A Novel Mathematical Algorithm for Trading FX Market |
| Author | Francesco Rundo, Francesca Trenta, Agatino Luigi di Stallo, Sebastiano Battiato |
| Institution | ADG Central R&D Group, STMicroelectronics S.r.l. (Catania, Italy); IPLAB, Dept. of Mathematics and Computer Science, University of Catania (Italy); GIURIMATICA Lab, Dept. of Applied Mathematics and LawTech (Ragusa, Italy) |
| Publisher | Applied Sciences (MDPI), Vol. 9, Issue 9, Article 1796 — journal article |
| Link | https://doi.org/10.3390/app9091796 |

## 2. Summary

1. **Motivation**: Grid trading is a popular algorithmic technique that opens same-sign (all long or all short) buy/sell orders spaced apart by a "grid distance," averaging losses on wrong-direction trades while compounding gains on correct ones. Because it manages drawdown robustly, the authors argue grid trading is well suited to **high-frequency trading (HFT)**, and propose combining it with machine learning forecasting to build an automated HFT grid system — **GTSbot** — for the FOREX (FX) OTC market.

2. **Pipeline architecture**: GTSbot chains four blocks: (1) a **Regression Network SCG** that forecasts next-period close price, (2) a **Trend Classification Block (TCB)** that turns the forecast into a Long/Short/Null trend call, (3) a **Grid System Manager (GSM)** that opens grid orders subject to spacing constraints, and (4) a **Basket Equity System Manager (BESM)** that monitors account balance/drawdown/margin and closes the whole basket at a target profit.

3. **Regression Network (SCG block)**: A feed-forward neural network (5 input neurons — open, close, low, high, volume; 500 hidden neurons; 1 output neuron predicting next close price) trained with the **Scaled Conjugate Gradient (SCG)** back-propagation variant of conjugate gradient methods. SCG approximates the Hessian instead of computing it exactly each iteration, giving **O(N) memory and O(N·logN)** learning complexity versus O(N²) and O(N²·logN) for classical BP, where N = number of weights. Trained/tested on 1-minute EUR/USD OHLCV data from the Tickstory database (99.9% accuracy), latest 5 years (2014–2018).

4. **Trend Classification Block formula**: Given predicted close price $c_f^{Close}(k)$ from the SCG regression map $R_{SCG}$:
$$c_f^{Close}(k) = R_{SCG}\left(c^{Close}(k-1), c^{Open}(k-1), c^{Low}(k-1), c^{High}(k-1), c^{Volume}(k-1)\right) \quad (1)$$
The trend decision at $k+1$ uses first and second derivatives of the forecast versus a threshold $\delta$ (set equal to broker spread):
$$\text{Long Trend if } \frac{\partial c_f^{Close}(k+1)}{\partial k} > \delta \text{ and } \frac{\partial^2 c_f^{Close}(k+1)}{\partial k^2} > 0$$
$$\text{Short Trend if } \frac{\partial c_f^{Close}(k+1)}{\partial k} < \delta \text{ and } \frac{\partial^2 c_f^{Close}(k+1)}{\partial k^2} < 0 \quad (2)$$
$$\text{Otherwise: Null Trend}$$
Discrete derivative approximations used:
$$\frac{\partial c_f^{Close}(k+1)}{\partial k} \approx c_f^{Close}(k+1) - c_{real}^{Close}(k) \quad (3)$$
$$\frac{\partial^2 c_f^{Close}(k+1)}{\partial k^2} \approx c_f^{Close}(k+1) - c_{real}^{Close}(k-1) - 2c_{real}^{Close}(k) \quad (4)$$
**Worked example**: suppose $\delta = 0.0002$ (2 pips, the assumed broker spread), $c_{real}^{Close}(k-1)=1.1000$, $c_{real}^{Close}(k)=1.1005$, and the SCG network forecasts $c_f^{Close}(k+1)=1.1012$. Then Eq. (3): $1.1012-1.1005=0.0007 > \delta$. Eq. (4): $1.1012 - 1.1000 - 2(1.1005) = 1.1012-1.1000-2.2010 = -2.1998$ — note the raw second-difference is dominated by the price level, so in practice the authors work with detrended/differenced series; qualitatively here the first derivative exceeds $\delta$ and is positive, triggering a **Long Trend** call once the second-derivative sign check (concavity) also confirms upward curvature. On real EUR/USD 2014–2018 1-min data, TCB achieved **73.2% trend forecast accuracy**.

5. **Grid System Manager constraints**: GSM opens a new trade only if it clears both a distance-in-time (x) and distance-in-price (y) threshold relative to every existing same-direction open trade, and the total trade count is below a cap $M_0$ (kept odd to avoid perfect long/short hedging, which would make the book market-neutral):
$$\text{Long trade opens iff: } \; k_1 > k + x_{th} \;\forall k; \quad c^{Open}_{real}(k_1) < c^{Opened}_{real}(k_1^0) + y_{th} \;\forall k^0; \quad N_{trades} < M_0 \quad (5)$$
$$\text{Short trade: symmetric condition} \quad (6)$$
Tuned parameters: **x-threshold = 15 candlesticks** (15 min on a 1-min timeframe), **y-threshold = 0.00020** (2 pips), **max operations = 13**. **Worked example**: with an existing long trade opened at candle $k=100$, price 1.1000, a new long signal at candle $k_1=112$ (only 12 candles later, $12 < 15$) is **rejected** regardless of price distance; a new long signal at $k_1=118$ (18 candles later, clears $x_{th}$) with open price 1.1003 (distance 0.0003 > $y_{th}$=0.0002) is **accepted**, provided $N_{trades} < 13$.

6. **Ablation on thresholds**: Disabling the x-threshold check increased average drawdown by **+25%** and cut average daily profit by **−10%**. Disabling the y-threshold check increased drawdown by **+18.3%** and cut daily profit by **−11.25%**, confirming both spacing constraints are load-bearing for the strategy's risk control.

7. **Risk management design choice**: BESM explicitly avoids stop-loss orders — the grid mechanism itself is relied upon to average down/compensate adverse moves — and instead defines a **take-profit** level at which the entire basket of open positions is closed. Account assumptions: $30,000 initial balance, 2-pip bid/ask spread, 1:400 leverage (~$300 margin per lot).

8. **Performance metrics and formulas**:
$$ROI = 100 \times \frac{Gain - Investment}{Investment} \quad (7) \qquad MD = \frac{|Balance_{Valley} - Balance_{Peak}|}{Balance_{Peak}} \quad (8)$$
**Worked example**: Investment = $30,000, Gain (ending balance) = $34,128 → $ROI = 100 \times (34128-30000)/30000 = 13.76\%$ (this matches the paper's Table 3 "Proposed" result). If BalancePeak = $32,000 and BalanceValley = $29,500, then $MD = |29500-32000|/32000 = 7.8\%$.

9. **Benchmark results (EUR/USD, 2004–2018 backtest windows)**: Against De Brito & Oliveira's GHSOM+SVR system [11]: at matched low-risk settings, GTSbot achieved **ROI 94.11% vs 60.77%** with **MD 11.25% vs 21%** (Table 1); at higher position sizing (10 lots), GTSbot underperformed on raw ROI (350.62%–500.73% vs 607.75%) but at much lower drawdown (38.75–65.11% vs 64.86%) (Table 2). Against Ichimoku support/resistance strategies [12]: GTSbot ROI **13.76%** vs 13.33%/14.08% (Table 3), with drawdown capped under 9%. Against a Directional-Changes HFT strategy [13]: GTSbot returned **$72,541 profit at 10.91% drawdown**, competitive with the comparator's $62,707/9.93% and clearly better risk-adjusted than its $97,687/50.47% variant (Table 4).

10. **Limitations & future work**: The SCG regression block's raw price-forecasting accuracy was described as "not optimal" even though directional (trend) prediction was usable. The grid radius (x/y thresholds) and max-operations count were fixed/heuristic, not adaptive. Stated future directions: dynamically regulate grid spacing via the **Sharpe ratio**, add cross-currency correlation analysis, and replace the SCG network with deeper architectures (Stacked AutoEncoders, CNNs, LSTMs).

## 3. Key Importance Topics

### Grid trading as a drawdown-management mechanism, not just an entry strategy
The paper frames grid trading's core value proposition as *financial sustainability*: opening same-direction orders spaced by grid distance lets the system "average" a wrong directional call rather than getting stopped out, while still compounding gains when the call is right.

**Why it matters:** This reframes grid trading from a "set of price levels" heuristic into a formal drawdown-control layer that can be bolted onto any directional forecasting model — directly relevant if you're evaluating grid trading as a wrapper strategy around your own signal generator rather than a standalone system.

### Coupling trend classification to grid order admission (GSM)
Orders are not placed purely on the grid's fixed spacing — they require agreement from the TCB's directional forecast AND clearing the x/y spacing thresholds AND staying under the max-operations cap. All three gates must pass.

**Why it matters:** This is the mechanism that keeps the grid from blindly martingale-ing into a trend; it's a concrete blueprint for adding a "regime/trend filter" gate to a naive grid bot, which is often the single highest-leverage change to a vanilla grid strategy's risk profile.

### Odd max-operations cap to avoid market-neutral hedging
The authors deliberately choose an odd $M_0$ so the book can never have equal long and short counts (which would zero out directional exposure).

**Why it matters:** A subtle, easy-to-miss design detail — worth checking against any grid implementation, since an even-numbered cap could silently neutralize a system that was designed to be directional.

### No stop-loss; profit-target-only basket exit (BESM)
The paper explicitly rejects stop-loss orders in favor of relying on the grid's averaging behavior, closing the entire basket only at a pre-set take-profit.

**Why it matters:** This is a real tail-risk decision, not an oversight — it trades bounded per-trade loss for a claim of long-run drawdown control via averaging. It is the single biggest risk assumption in the paper and should be stress-tested (e.g., trending/one-directional markets) before reuse.

### Threshold ablation as an empirical validation method
Rather than just reporting final performance, the authors disable x-threshold and y-threshold checks independently and measure the drawdown/profit degradation (+25% DD / −10% profit; +18.3% DD / −11.25% profit).

**Why it matters:** This is a reusable validation pattern — ablating individual grid-spacing rules to quantify their marginal contribution — that's directly applicable to auditing your own grid/DGT strategy's parameter choices instead of treating them as black-box hyperparameters.

## 4. Ideas for Development

- **Trend-gated grid entries** — Add a directional forecast gate (even a simple derivative-sign trend classifier like TCB) in front of any grid order-placement logic, so grid orders only fire in the direction the model currently favors rather than symmetrically.
- **Dual spacing constraint (time + price)** — Reuse the x-threshold (candles since last same-direction trade) and y-threshold (price distance from last same-direction trade) as a two-dimensional admission filter for grid orders, instead of a single price-only grid spacing.
- **Odd-cap position limits for directional grids** — When building a directional (non-market-neutral) grid bot, cap total concurrent positions at an odd number to structurally prevent accidental full hedging.
- **Threshold ablation testing** — Before deploying a grid strategy's chosen spacing/threshold parameters, run controlled ablations (disable one constraint at a time) on historical data and report the drawdown/profit delta, as a lightweight sensitivity-analysis alternative to full grid search.
- **Basket-level exit instead of per-trade stop-loss** — Evaluate a take-profit-on-whole-basket exit rule (rather than per-position stops) specifically for grid/averaging strategies, since the paper reports competitive drawdown control using this approach on EUR/USD.
- **Sharpe-ratio-adaptive grid radius** — Explore dynamically resizing the grid distance based on a rolling Sharpe ratio (the paper's stated future work), rather than a static x/y threshold, as a way to adapt grid spacing to changing volatility regimes.

## 5. Tools & Data Used in This Research

### Software & Library

| Tools | Purpose in paper |
|---|---|
| MATLAB (rel. 2018a) | Implementation platform for the full GTSbot pipeline and GUI |

### Data Source

| Source | Description |
|---|---|
| Tickstory database | 1-minute OHLCV historical FX data (99.9% accuracy) for EUR/USD, spanning 2004–2018 for benchmarking, latest 5 years (2014–2018) for training/testing |

### Models & Algorithms

| Model/Algorithm | Role |
|---|---|
| Feed-forward neural network (5-500-1 topology) | Regresses next-period close price from OHLCV |
| Scaled Conjugate Gradient (SCG) back-propagation | Training algorithm for the regression network, approximates Hessian for O(N)/O(N·logN) complexity |
| Trend Classification Block (TCB) | First/second-derivative-based rule converting price forecast into Long/Short/Null trend signal |
| Grid System Manager (GSM) | Rule-based order admission engine enforcing x/y spacing thresholds and max-operations cap |
| Basket Equity System Manager (BESM) | Account-level monitor for drawdown, margin, and take-profit-triggered basket closure |

## 6. Key References Worth Exploring

| Reference | Relevance |
|---|---|
| De Brito, R.F.B.; Oliveira, A.L.I. — "A foreign exchange market trading system by combining GHSOM and SVR" (WCCI 2012) | Primary ROI/MD benchmark comparator used in Tables 1–2; useful for comparing grid-averaging vs. SVR-based FX systems on the same currency pair |
| Ye, A. et al. — "Developing sustainable trading strategies using directional changes with high frequency data" (IEEE Big Data 2017) | The HFT benchmark comparator in Table 4; introduces "Directional Changes" event-based (as opposed to fixed-interval) sampling, a complementary alternative to grid-based HFT |
| Deng, S.; Sakurai, A. — "Short-term foreign exchange rate trading based on support/resistance level of Ichimoku Kinkohyo" (2014) | Classic technical-indicator benchmark (Table 3); useful contrast for evaluating grid trading against support/resistance-based systems |
| Moller, M.F. — "A Scaled Conjugate Gradient Algorithm for Fast Supervised Learning" (Neural Networks, 1993) | Foundational SCG algorithm reference; needed to fully understand the regression network's training complexity claims |
| Rundo, F. et al. — "Advanced Markov-Based Machine Learning Framework for Making Adaptive Trading System" (Computation, 2019) | Same author group's related prior work combining multi-LSTM with adaptive trading strategy; useful for tracing this research line's evolution |

---
Report generated on: 2026-07-15
Source PDF: [applsci-09-01796-v2.pdf](file:D:\ClaudeCode Project\Quant_Trading\research\paper\applsci-09-01796-v2.pdf)
