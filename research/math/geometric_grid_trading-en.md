# Geometric Grid Trading — Explained Simply

> **Source:** [2506.11921_dynamic_grid_trading_strategy_digest.md](../wiki/2506.11921_dynamic_grid_trading_strategy_digest.md)
> **Generated:** 2026-07-17

## Table of Contents

- [Formula 1 — Geometric Level Placement](#formula-1--geometric-level-placement)
- [Formula 2 — Initial Capital Allocation](#formula-2--initial-capital-allocation)
- [Formula 3 — Fractional Sell / Buy Rules](#formula-3--fractional-sell--buy-rules)
- [Formula 4 — Upside Profit (Eq. 1)](#formula-4--upside-profit-eq-1)
- [Formula 5 — Downside Loss (Eq. 2)](#formula-5--downside-loss-eq-2)
- [Formula 6 — Expected Value of the Grid (Eq. 3)](#formula-6--expected-value-of-the-grid-eq-3)
- [Formula 7 — Random-Walk Recurrence (Eq. 4)](#formula-7--random-walk-recurrence-eq-4)
- [Formula 8 — Expected Arbitrage Cycles (Eq. 5)](#formula-8--expected-arbitrage-cycles-eq-5)
- [Big Picture](#big-picture)

---

## Formula 1 — Geometric Level Placement

> **Formula:**
>
> $$\text{level}_i = P(1+k)^i, \quad i = -(n-m), \dots, m$$

### 1. One-Sentence Intuition

Every grid line sits a fixed *percentage* above the line below it, so the ladder looks identical whether the coin trades at 100 or at 100,000.

### 2. Concrete Mental Picture

Picture a ladder leaning against the price chart, with the current price $P$ standing on one rung. Each rung above is 5% higher than the one below it — not 5 dollars higher, 5 *percent*. So the rungs get physically farther apart as you climb (100 → 105 → 110.25 → 115.76), but to the trader every step *feels* the same size: "price moved 5%." There are $m$ rungs above your feet (places to sell) and $n-m$ rungs below (places to buy), $n+1$ rungs in total.

### 3. Variable Breakdown

| Variable | In the Picture | If It Increases... | Tiny Example |
|---|---|---|---|
| $P$ | The rung you start standing on | Whole ladder shifts up; shape unchanged | $P: 100 \to 200$ — every level exactly doubles |
| $k$ | Gap between adjacent rungs, in percent | Rungs spread apart; fewer trades, bigger profit each | $k: 5\% \to 10\%$ — top level jumps from 115.76 to 133.1 |
| $i$ | How many rungs above (+) or below (−) you a level is | Farther from start price | $i=3$, $k=5\%$: $100 \cdot 1.05^3 = 115.76$ |
| $n$ | Total rung count minus one (number of gaps) | Wider price range covered | $n: 6 \to 10$ — ladder reaches further both ways |
| $m$ | Rungs above the start | More room to sell on the way up | $m: 3 \to 5$ of $n=6$ — grid skewed bullish |

### 4. Why the Formula Is Shaped This Way

Multiplication by $(1+k)$ repeated $i$ times — a power, not a sum — is what makes the spacing *percentage-constant*. An arithmetic grid ($P + ik$) would make a 5-unit gap feel huge at price 20 and invisible at price 2,000. The geometric form means one grid design works at any price scale, which matters for crypto where price can 10x within the backtest window. Negative $i$ just runs the same multiplication downward: $1.05^{-1} \approx 0.9524$, giving 95.24.

---

## Formula 2 — Initial Capital Allocation

> **Formula:**
>
> $$\text{crypto} = M \cdot \frac{m}{n}, \qquad \text{cash} = M \cdot \frac{n-m}{n}$$

### 1. One-Sentence Intuition

Buy exactly as much crypto as you will need to sell on the rungs above you, and keep exactly as much cash as you will need to buy on the rungs below.

### 2. Concrete Mental Picture

Back on the ladder: each of the $m$ rungs above your feet is a *sell station* — when price climbs there, you must hand over some crypto. Each of the $n-m$ rungs below is a *buy station* — when price falls there, you must hand over some cash. So you stock your backpack in proportion to the stations: 3 sell stations out of 6 total → half the backpack ($M \cdot \frac{3}{6} = 300$ of 600 USDT) is crypto, half is cash. Every station is pre-supplied before the price moves at all.

### 3. Variable Breakdown

| Variable | In the Picture | If It Increases... | Tiny Example |
|---|---|---|---|
| $M$ | Total backpack size (USDT) | Everything scales up proportionally | $M: 600 \to 1200$ — buy 600 of crypto instead of 300 |
| $m$ | Number of sell stations above | More capital goes into crypto upfront | $m: 3 \to 4$ of $n=6$ — crypto share $\frac{4}{6} = 400$ USDT |
| $n$ | Total number of stations (gaps) | Each station's share of $M$ shrinks | $n: 6 \to 12$, same $m=3$ — crypto only $\frac{3}{12} = 150$ |
| $n-m$ | Number of buy stations below | More cash held back | $m: 3 \to 2$ — cash rises to $\frac{4}{6} = 400$ |

### 4. Why the Formula Is Shaped This Way

The split is a simple ratio because each grid gap is designed to command roughly $\frac{M}{n}$ worth of trading. $m$ of the $n$ gaps are above you and need inventory (crypto); the rest need cash. If you held less crypto than $M\frac{m}{n}$, you would run out of coins before reaching the top rung; more, and idle coins sit exposed to downside for no reason. The formula is just "supplies match stations."

---

## Formula 3 — Fractional Sell / Buy Rules

> **Formula:**
>
> $$\text{sell fraction} = \frac{1}{G_i} \text{ of held crypto}, \qquad \text{buy fraction} = \frac{1}{G_j} \text{ of held USDT}$$

### 1. One-Sentence Intuition

At each crossing, spend an equal share of what remains per remaining station — like cutting a cake into as many slices as there are guests still waiting.

### 2. Concrete Mental Picture

Price climbs and crosses a gray (not-yet-traded) rung. Count how many gray rungs there are from the top down to this one — say it is the 3rd, so $G_i = 3$. That number is "guests still waiting above": this rung plus the ones higher up that will also demand crypto. So you sell $\frac{1}{3}$ of the coins in the backpack — one fair slice — leaving exactly enough slices for the remaining rungs. The rung then turns black (served). Falling works mirror-image with cash: cross the 3rd gray rung from the bottom, spend $\frac{1}{3}$ of your USDT.

### 3. Variable Breakdown

| Variable | In the Picture | If It Increases... | Tiny Example |
|---|---|---|---|
| $G_i$ | Count of gray rungs from the top to the crossed one | Smaller slice sold — many sell stations still ahead | $G_i = 3$: sell $\tfrac{1}{3}$ of 3 units = 1 unit; $G_i = 1$ (topmost): sell everything left |
| $G_j$ | Count of gray rungs from the bottom to the crossed one | Smaller cash slice spent | $G_j = 3$, cash 405: spend 135 USDT |

### 4. Why the Formula Is Shaped This Way

Dividing by the *remaining* count instead of the original count is what makes the grid self-balancing. After each trade, inventory shrinks but so does the number of stations left to serve, so "one slice per remaining station" stays true forever — no manual rebalancing, no running dry at the last rung. It also means the topmost crossing ($G_i = 1$) automatically sells $\frac{1}{1} =$ *all* remaining crypto, which is exactly the clean full-liquidation you want at the boundary.

---

## Formula 4 — Upside Profit (Eq. 1)

> **Formula:**
>
> $$P_u = \frac{M}{n} \sum_{i=1}^{n/2} i \tag{1}$$

### 1. One-Sentence Intuition

If price marches straight up and out of the grid, your profit is the sum of ever-taller stacks of level-gaps — 1 gap on the first sold chunk, 2 on the next, and so on.

### 2. Concrete Mental Picture

You start in the middle of the ladder with $n/2$ rungs above ($m = n/2$). Price climbs rung by rung, never dipping. Each rung crossing sells one chunk of roughly $\frac{M}{n}$ worth of crypto. Here is the key: the chunk sold at the 1st rung was bought at the center, so it gained 1 gap of appreciation. By the time the *last* chunk sells at the top, it has ridden up $n/2$ gaps. Line the chunks up and their gains form a staircase: $1 + 2 + \dots + \frac{n}{2}$ gaps, each gap worth about $\frac{M}{n}$ (one gap of appreciation on one chunk).

### 3. Variable Breakdown

| Variable | In the Picture | If It Increases... | Tiny Example |
|---|---|---|---|
| $M$ | Total capital feeding each chunk | Profit scales linearly | $M: 600 \to 1200$ doubles $P_u$ |
| $n$ | Grid count; sets chunk size $\frac{M}{n}$ and staircase height $\frac{n}{2}$ | Profit grows ≈ quadratically in the sum but chunks shrink — net effect ≈ linear in $n$ | $n=6$: $P_u = 100(1+2+3) = 600$ |
| $i$ | Which step of the staircase (gaps of gain on that chunk) | Later-sold chunks carry more gain | chunk 3 gained 3 gaps ≈ 300 |

### 4. Why the Formula Is Shaped This Way

The sum $\sum i$ exists because gains *accumulate per chunk*: each successive chunk is held one gap longer before being sold. The prefactor $\frac{M}{n}$ is the value cycled per gap per chunk. Multiply and sum — a triangle of gains, hence the triangular-number shape $\frac{(n/2)(n/2+1)}{2}$ hiding inside Eq. (1).

---

## Formula 5 — Downside Loss (Eq. 2)

> **Formula:**
>
> $$L_l = \frac{M}{n}\left[\left(\frac{n}{2}\right)^2 + \sum_{i=1}^{\frac{n}{2}-1} i\right] \tag{2}$$

### 1. One-Sentence Intuition

If price slides straight down and out of the grid, you lose a big square-shaped hit on the crypto you started with, plus a smaller staircase of losses on the chunks you bought on the way down.

### 2. Concrete Mental Picture

Same ladder, but price sinks rung by rung. Two things bleed:

1. **The starting inventory.** You began holding $\frac{n}{2}$ chunks of crypto (worth $M/2$), and *every one of them* rides the full $\frac{n}{2}$-gap fall to the bottom. That is $\frac{n}{2}$ chunks × $\frac{n}{2}$ gaps = the $\left(\frac{n}{2}\right)^2$ square block of loss.
2. **The bargain buys that kept falling.** At each rung down you dutifully bought a new chunk. The chunk bought at the 1st rung down then falls $\frac{n}{2}-1$ more gaps; the last one bought barely falls at all. Their losses form a staircase: $\sum_{i=1}^{n/2 - 1} i$.

Square block + staircase, each unit worth $\frac{M}{n}$.

### 3. Variable Breakdown

| Variable | In the Picture | If It Increases... | Tiny Example |
|---|---|---|---|
| $M$ | Capital at risk in every chunk | Loss scales linearly | $M: 600 \to 1200$ doubles $L_l$ |
| $n$ | Sets chunk size and fall depth | Square term grows fastest — deeper grids lose more on a full breakdown | $n=6$: $L_l = 100[9 + (1+2)] = 1200$ |
| $\left(\frac{n}{2}\right)^2$ | The square block: initial crypto × full fall | Dominates for large $n$ | $n=6$: $3\times3 = 9$ units ≈ 900 |
| $\sum_{i=1}^{n/2-1} i$ | Staircase of dip-buys still falling | Adds the smaller triangle | $n=6$: $1+2 = 3$ units ≈ 300 |

### 4. Why the Formula Is Shaped This Way

The asymmetry against Eq. (1) is the whole point: rising, you *shed* inventory as you go (staircase only); falling, you both hold your initial stack through the entire drop (the square) *and* keep adding chunks that continue to fall (the staircase). That is why $L_l = 1200 > P_u = 600$ in the worked example — down-and-out hurts exactly twice as much as up-and-out pays, before counting arbitrage.

---

## Formula 6 — Expected Value of the Grid (Eq. 3)

> **Formula:**
>
> $$E(G) = \frac{1}{2}(P_u - L_l) = -\frac{M}{n}\left(\frac{n^2}{8} - \frac{n}{4}\right) \tag{3}$$

### 1. One-Sentence Intuition

Averaging the up-exit payday against the down-exit disaster leaves a guaranteed deficit — a hole that only the small buy-low/sell-high wins along the way can hope to fill.

### 2. Concrete Mental Picture

Flip a fair coin for the grid's fate: heads, price exits the top and you pocket $P_u = 600$; tails, it exits the bottom and you eat $L_l = 1200$. The average outcome is $\frac{1}{2}(600 - 1200) = -300$. That −300 is a pre-dug hole, measured in units of $\frac{M}{n} = 100$: the hole is $\frac{n^2}{8} - \frac{n}{4} = 3$ units deep. Every completed sell-high/buy-back-low round trip inside the grid shovels one unit ($\approx \frac{M}{n}$ per one-gap cycle) back into the hole. The strategy breaks even only if you complete more than 3 round trips before the coin decides your exit.

### 3. Variable Breakdown

| Variable | In the Picture | If It Increases... | Tiny Example |
|---|---|---|---|
| $P_u$ | The heads payday | Less negative expectation | 600 in the example |
| $L_l$ | The tails disaster | More negative expectation | 1200 in the example |
| $\frac{1}{2}$ | The fair coin — up and down exits equally likely | (fixed by the 50-50 assumption) | biased market breaks this |
| $\frac{n^2}{8} - \frac{n}{4}$ | Depth of the hole, in arbitrage-cycle units | Bigger grids dig deeper holes but also allow more cycles | $n=6$: $4.5 - 1.5 = 3$ cycles needed |

### 4. Why the Formula Is Shaped This Way

The $\frac{1}{2}$ is the fair-coin average over the only two endings. The $n^2$ inside comes from the square block in $L_l$ that has no counterpart in $P_u$ — the structural asymmetry of holding inventory through a fall. Dividing the deficit by the per-cycle profit $\frac{M}{n}$ converts money into "number of round trips needed," which is the form that makes the cancellation in Eq. (5) visible.

---

## Formula 7 — Random-Walk Recurrence (Eq. 4)

> **Formula:**
>
> $$E_i = 2E_{i-1} - E_{i-2} - 2 \tag{4}$$

### 1. One-Sentence Intuition

The expected number of coin flips left shrinks by a perfect square as your lead grows — being 2 flips from the exit is 4 flips "cheaper" than being at the start, not 2.

### 2. Concrete Mental Picture

Reframe price as a coin-flip game: each ±k move is one toss, and the grid dies when heads lead tails by $\frac{n}{2}$ (price out the top) or trail by $\frac{n}{2}$ (out the bottom). Imagine standing on a number line at position $i$ = current lead. $E_i$ is "expected tosses remaining from here." From any spot you step left or right with equal chance, paying 1 toss per step. The recurrence links three neighboring spots: knowing the cost at $i-2$ and $i-1$ pins down the cost at $i$. Solving it gives the clean staircase-of-squares $E_m = E_0 - m^2$: at lead 1 you have used up 1 toss of expectation, at lead 2 you've used 4, at lead 3 (with $n=6$) you've used all 9 — game over, $E_3 = 0$, so $E_0 = \frac{n^2}{4} = 9$.

### 3. Variable Breakdown

| Variable | In the Picture | If It Increases... | Tiny Example |
|---|---|---|---|
| $i$ | Current lead of heads over tails (rungs from center) | Closer to the exit — fewer expected tosses left, dropping as $i^2$ | $E_1 = 8$, $E_2 = 5$, $E_3 = 0$ (for $E_0 = 9$) |
| $E_i$ | Expected remaining tosses from lead $i$ | — | $E_0 = n^2/4$ |
| $-2$ | Cost of tosses burned stepping around | (structural constant from the 50-50 averaging) | remove it and the game never ends |
| $n/2$ | Distance to the absorbing exit | Quadratically more expected tosses | $n: 6 \to 8$ → $E_0: 9 \to 16$ |

### 4. Why the Formula Is Shaped This Way

The shape comes from averaging: from state $i$, one toss (+1) leads to $E_{i-1}$ or $E_{i+1}$ with probability $\frac{1}{2}$ each; rearranging that averaging identity gives exactly $E_i = 2E_{i-1} - E_{i-2} - 2$. The $-2$ is the fingerprint of "every toss costs 1, counted from both neighbors." Quadratic solutions ($E_0 - m^2$) are the natural family for such second-difference equations — the same math as a gambler's-ruin expected duration.

---

## Formula 8 — Expected Arbitrage Cycles (Eq. 5)

> **Formula:**
>
> $$\frac{\frac{n^2}{4} - \frac{n}{2}}{2} = \frac{n^2}{8} - \frac{n}{4} \tag{5}$$

### 1. One-Sentence Intuition

Of all the expected price moves, strip out the ones spent walking out the door, pair up the rest into buy-sell round trips — and the count of round trips exactly equals the deficit from Formula 6, so the whole game is worth zero.

### 2. Concrete Mental Picture

The coin-flip game says the grid will see about $E_0 = \frac{n^2}{4}$ moves before dying ($9$ moves for $n=6$). But $\frac{n}{2}$ of those moves ($3$) are the one-way march that carries price out of the grid — they trade once but never come back, pure directional cost, not profit. The remaining $9 - 3 = 6$ moves come in matched pairs: every up-move that sells finds a down-move that buys back (or vice versa). Divide by 2: $3$ complete round trips, each pocketing about one gap ($\approx \frac{M}{n} = 100$ USDT). Three shovels of profit… into the hole from Formula 6 that is exactly three units deep. Perfectly, cruelly, zero.

### 3. Variable Breakdown

| Variable | In the Picture | If It Increases... | Tiny Example |
|---|---|---|---|
| $\frac{n^2}{4}$ | Total expected moves before the grid dies | More flips, more of everything | $n=6$: 9 moves |
| $\frac{n}{2}$ | The one-way exit march (unpaired moves) | More moves wasted on the exit | $n=6$: 3 moves |
| $\div\, 2$ | Pairing: buy + sell = one round trip | — | 6 paired moves → 3 cycles |
| $\frac{n^2}{8} - \frac{n}{4}$ | Expected round trips = hole depth from Eq. (3) | Grows with $n$, but so does the hole — always equal | $n=6$: 3 = 3 → $E = 0$ |

### 4. Why the Formula Is Shaped This Way

Subtract-then-halve mirrors the physical trade flow: only *paired* crossings generate arbitrage, and each pair needs two moves. The punchline is that this count, $\frac{n^2}{8} - \frac{n}{4}$, is *the same expression* as the deficit in Eq. (3) measured in cycle units. Expected shoveling = hole depth, for every $n$. Add real-world fees (0.0008 per trade) and each shovel carries a little less dirt — expectation goes strictly negative. This is the theorem that motivates DGT: the only escape is to change the game (never terminate, re-center, reinvest), not to tune the parameters of a game that is rigged to zero.

---

## Big Picture

The geometric grid is a beautifully self-balancing machine — percentage-spaced levels (Formula 1), station-matched capital (Formula 2), and self-adjusting slice sizes (Formula 3) let it harvest volatility hands-free. But the paper's central result chains Formulas 4–8 into a proof that the machine earns nothing on average: the down-exit loss is structurally twice the up-exit gain (Eqs. 1–3), and the random-walk analysis (Eqs. 4–5) shows the expected number of arbitrage round trips exactly fills that deficit — zero expectation before fees, negative after. Every formula here is therefore both a design manual for grids and a warning label: profit must come from *changing the rules* (DGT's never-terminate resets), not from the grid mechanism itself.
