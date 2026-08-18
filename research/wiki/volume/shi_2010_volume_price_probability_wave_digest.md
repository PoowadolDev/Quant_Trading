# Does Security Transaction Volume-Price Behavior Resemble A Probability Wave?

## 1. Paper Information

| Fields | Detail |
|---|---|
| Title | Does Security Transaction Volume-Price Behavior Resemble A Probability Wave? (the PDF opens with a Chinese title page of the same paper: 证券成交量/价的行为是否像是一种几率波) |
| Author | Leilei Shi (石磊磊) — sole author |
| Institution | (a) Department of Systems Science, School of Management, Beijing Normal University, Beijing 100875, China; (b) Department of Modern Physics, University of Science and Technology of China, Hefei 230026, China; (c) Agents, Generali-China Life Insurance Co. Ltd. (Beijing Branch), Beijing 100738, China |
| Publisher | Published as **Physica A 366 (2006) 419–436**. The PDF itself is the **preprint version dated October 17, 2005** and does *not* name a journal on its title page; it circulates as arXiv preprint **arXiv:1001.0880v1 (q-fin.TR)**. JEL classifications given in the paper: G12; D30; D40 |
| Link | https://doi.org/10.1016/j.physa.2005.10.016 (preprint: https://arxiv.org/abs/1001.0880) |

Keywords stated by the author: price volatility; volume kurtosis; volume-price behavior; coherence; probability wave.

## 2. Summary

Notation used throughout this digest, matching the paper: $p$ = trading price [currency unit·share⁻¹]; $p_0$ = equilibrium price; $\bar p$ = price mean value; $v$ = accumulative transaction volume at price $p$ [share]; $V$ = total transaction volume over the whole trading price range [share]; $t$ = length of the trading time interval [time]; $m=pv$ = transaction amount [currency unit].

1. **Motivation and gap.** The paper opens by arguing that no existing price model gives an **explicit, analytical price-formation mechanism**. It surveys efficient markets (Fama), APT (Ross), **Black–Scholes–Merton**, **ARCH/GARCH** (Engle, Bollerslev), econophysics work on price–volume co-movement (Gallant et al. 1928–1987 NYSE daily data; Gervais et al.'s high-volume return premium; Zhang's square-root price/demand relation; spin models; Plerou et al.'s finding that **large price fluctuations occur when demand is very small**), and mechanical analogies (Ausloos & Ivanova's generalized kinetic energy and momentum; Wang & Pandey's trading momentum). The author's complaint is that all of this studies the *correlation between return and total volume in a time interval*, quoting Lee & Swaminathan: *"What is surprising is how little we really know about trading volume."* His question is different — how does total volume **distribute over a trading price range**, and why.

2. **Core empirical observation and the test model.** The author observes that on individual stocks, accumulative trading volume **gradually develops a kurtosis (a single sharp peak) near the price mean value** over the trading price range as the trading time lengthens — *regardless of the actual price path, the time series, or the total volume*. He tests this with the absolute value of a **zero-order Bessel eigenfunction**:
   $$P(p_i)=C_m\left|J_0\left[\omega_m (p_i-p_0)\right]\right|+\varepsilon_i,\qquad i=1,2,3,\dots N \tag{1}$$
   where $J_0[\cdot]$ is the zero-order Bessel function; $C_m$ is a normalization constant; $P(p_i)$ is the **observed** volume probability at price $p_i$ (accumulative volume at $p_i$ divided by total volume $V$); $p_0$ is the equilibrium price if it exists; $\omega_m$ is an eigenvalue constant [price⁻¹]; $\varepsilon_i$ is a random error term.
   *Worked example* (paper's sample 1, stock **600002** on 2003/06/13, fitted parameters $C_m=P1=0.1065$, $\omega_m=P2=31.677$, $p_0=P3=5.742$ yuan): at $p_i=5.76$ yuan, $\omega_m(p_i-p_0)=31.677\times0.018=0.5702$; $J_0(0.5702)=1-\frac{0.5702^2}{4}+\frac{0.5702^4}{64}-\frac{0.5702^6}{2304}=1-0.08128+0.00165-0.00001=0.92035$; so the model predicts $P=0.1065\times0.92035=\mathbf{0.0980}$, i.e. **9.8 %** of the day's volume in that price bin. If the observed bin probability were $0.095$, then $\varepsilon_i=0.095-0.098=-0.003$.

3. **Empirical results with concrete numbers.** The sample is the **first 30 individual stocks in the Shanghai 180 Index, June 2003**, one sample per stock per trading day: $30\times21=\mathbf{630}$ samples, minus **11 halted** samples and **1 lost** sample, leaving **618 tested samples**. Fitting was done in **Origin 6.0 Professional**. Headline result: **94.34 % of the samples are significant at the 95 % level** (618 − 35 = 583 significant; $583/618=94.34\%$). Three representative fits: sample 1 (**600002**, 2003/06/13) $\chi^2=0.00062$, $R^2=0.73917$, mean price 5.74 yuan, looking *normal*; sample 2 (**000682**, 2002/01/08) $\chi^2=0.00012$, $R^2=0.596$, $C=0.0457$, $\omega=22.55$, $p_0=6.128$, mean 6.08 yuan, looking *wave-like*; sample 3 (**600008**, 2003/06/09) $\chi^2=0.00074$, $R^2=0.82767$, $C=0.2555$, $\omega=211.42$, $p_0=10.85254$, mean 10.87 yuan, looking *exponential*. The width of the central peak follows directly from $\omega$: the first zero of $J_0$ is at 2.405, so sample 1's main lobe half-width is $2.405/31.677=\mathbf{0.076}$ yuan while sample 3's is $2.405/211.42=\mathbf{0.0114}$ yuan — the same functional form covers both a broad and a needle-sharp volume profile.

4. **Transaction energy bookkeeping (the dimensional scaffolding).** To reason "in terms of physics" the author defines a chain of quantities. **Transaction volume liquidity**:
   $$v_t=\frac{v}{t} \tag{2}$$
   [share·time⁻¹]. **Transaction amount liquidity** (the paper's benchmark quantity, "cash is king"):
   $$m_t=\frac{m}{t}=\frac{pv}{t}=p\,v_t \tag{3}$$
   [currency·time⁻¹]. **Transaction energy** — the rate of change of amount liquidity, i.e. transaction amount acceleration:
   $$E=\dot m_t=\frac{p\,v_t}{t}=p\,\dot v_t \tag{4}$$
   [currency·time⁻²], with **transaction volume liquidity rate / volume acceleration**
   $$\dot v_t=\frac{v_t}{t}=\frac{v}{t^2} \tag{5}$$
   [share·time⁻²]; and the **transaction volume probability**
   $$P=\frac{v}{V}. \tag{6}$$
   *Worked example (running example "S", reused in points 5–7).* Take one price bin of stock 600002: $p=5.78$ yuan, bin volume $v=40{,}000$ shares, total day volume $V=1{,}000{,}000$ shares, session length $t=4\text{ h}=14{,}400$ s. Then $v_t=40000/14400=\mathbf{2.7778}$ share·s⁻¹; $m=pv=5.78\times40000=231{,}200$ yuan and $m_t=p v_t=5.78\times2.7778=\mathbf{16.056}$ yuan·s⁻¹; $\dot v_t=40000/14400^2=\mathbf{1.9290\times10^{-4}}$ share·s⁻²; $E=p\dot v_t=5.78\times1.9290\times10^{-4}=\mathbf{1.1150\times10^{-3}}$ yuan·s⁻²; $P=40000/1000000=\mathbf{0.04}$.

5. **The transaction energy hypothesis.** The author splits transaction energy into a **dynamic (distribution) energy** $T$ and a **potential energy** $W$:
   $$E\equiv E(1-P)+PE\equiv T(p,v_t)+W(p,v_t), \tag{7}$$
   and for a *stationary* trading state (time-independent potential) writes it as the differential constraint
   $$-E+\frac{v}{V}\,p\,\dot v_t+W(p)=0. \tag{8}$$
   Reading (8) against (7): the term $\frac{v}{V}p\dot v_t=P\cdot E$ is the **dynamic energy** $T$, so the **potential energy** is $W=(1-P)E$. This is the pairing that reproduces the paper's own statement: *if $v/V=1$ there is no price volatility and $W(p)=0$; if $W(p)>0$ then $v/V<1$, i.e. price is volatile.* Equation (8) is declared a **holonomic constraint** at the price coordinate, so with two generalized coordinates (price, volume liquidity) and one constraint the system has **one degree of freedom** — the author picks **price** as the independent coordinate, turning a two-dimensional problem into a one-dimensional one.
   *Worked example (continuing S).* $T=P\,E=0.04\times1.1150\times10^{-3}=\mathbf{4.460\times10^{-5}}$ yuan·s⁻²; $W=(1-P)E=0.96\times1.1150\times10^{-3}=\mathbf{1.0704\times10^{-3}}$ yuan·s⁻². Check (8): $-1.1150\times10^{-3}+4.460\times10^{-5}+1.0704\times10^{-3}=0$ ✓.

6. **Linear potential and the supply–demand restoring force.** Economically: demand quantity is capped by buyers' cash, supply quantity by sellers' shares. When price rises above equilibrium, the same remaining cash buys fewer shares, demand falls, and price reverses; below equilibrium the same cash buys more shares, demand rises, and price reverses again — an oscillation about $p_0$ with "price motion inertia" carrying it through the equilibrium each time. Because the potential is proportional to price, it is a **linear potential**:
   $$W(p)=A(p-p_0)\approx A(p-\bar p), \tag{9}$$
   where $A$ is the **transaction coefficient** [share·time⁻²], $p_0$ the equilibrium price and $\bar p$ the price mean value used as its proxy. Differentiating (8) with (4) and (9) gives the **transaction restoring force**:
   $$F_R=-\frac{\partial W}{\partial p}=-A=-\left(\dot v_t-\frac{v}{V}\dot v_t\right)=-\dot v_t\left(1-\frac{v}{V}\right), \tag{10}$$
   so $A$ *is* the magnitude of the effective supply–demand restoring force, and the minus sign means the force always points back toward $p_0$. Appendix B treats $p'\le 0$ by the substitution $p'\to-p'$ (eq. B-20), i.e. the effective potential is the **V-shape** $W=A|p-p_0|$.
   *Worked example (continuing S).* $A=\dot v_t(1-v/V)=1.9290\times10^{-4}\times0.96=\mathbf{1.8518\times10^{-4}}$ share·s⁻². Consistency check against (8), measuring the potential from the price-zero origin: $A\cdot p=1.8518\times10^{-4}\times5.78=1.0703\times10^{-3}=W$ ✓. In the shifted coordinate of (9) with $p_0=5.742$: $W=1.8518\times10^{-4}\times(5.78-5.742)=\mathbf{7.04\times10^{-6}}$, and $F_R=-1.8518\times10^{-4}$ share·s⁻² (pointing down, toward $p_0$).

7. **Wave function, Hamilton–Jacobi equation and transaction momentum.** The author posits a **volume-price probability wave function**
   $$\psi(p)=R\cdot e^{iS/B}, \tag{11}$$
   with $R$ the wave amplitude, $S$ the action (Hamilton's principal function) describing volume-price behavior, and $B$ a constant that makes the phase dimensionless. From (11),
   $$\frac{\partial S}{\partial p}=-iB\,\frac{1}{\psi}\frac{\partial \psi}{\partial p}, \tag{12}$$
   and the behavior is assumed to satisfy a **Hamilton–Jacobi equation**
   $$\frac{\partial S}{\partial t}+H\!\left(p,\frac{\partial S}{\partial p}\right)=0, \tag{13}$$
   with the Hamiltonian built as dynamic plus potential energy,
   $$H\!\left(p,\frac{\partial S}{\partial p}\right)=T\!\left(p,\frac{\partial S}{\partial p}\right)+W(p). \tag{14}$$
   Separation of variables gives $S(p,t)=S_1(p)-Et$ (15), equivalently $\partial S/\partial t=-E$ (16); dimensional matching gives $S(p,t)=\alpha\left(v_t p-Et\right)+\beta$ (17) with $\alpha$ dimensionless and $\beta$ [currency·time⁻¹], and setting $\alpha=1,\beta=0$:
   $$S\equiv v_t\,p-Et. \tag{18}$$
   The **transaction momentum** at the price coordinate and the **transaction force** are then
   $$Q\equiv\frac{\partial S}{\partial p}=v_t, \tag{19}\qquad
     F_T\equiv\frac{dQ}{dt}=\frac{dv_t}{dt}=\dot v_t. \tag{20}$$
   Substituting (19) into (8) rewrites the hypothesis as
   $$-E+\frac{p}{V}\left(\frac{\partial S}{\partial p}\right)^2+W(p)=0. \tag{21}$$
   *Worked example (continuing S, with $B=1$).* $Q=v_t=\mathbf{2.7778}$ share·s⁻¹ and $F_T=\dot v_t=\mathbf{1.9290\times10^{-4}}$ share·s⁻². Check (21): $\frac{p}{V}Q^2=\frac{5.78}{10^6}\times2.7778^2=5.78\times10^{-6}\times7.716=4.460\times10^{-5}$, which equals $T$ exactly, so $-1.1150\times10^{-3}+4.460\times10^{-5}+1.0704\times10^{-3}=0$ ✓. Check (13)/(14): $H=T+W=4.460\times10^{-5}+1.0704\times10^{-3}=1.1150\times10^{-3}=E$ and $\partial S/\partial t=-E$, so (13) sums to zero ✓. Check (11)/(12): with $R=0.1065$ and phase $S/B=0.5$ rad, $\psi=0.1065(\cos0.5+i\sin0.5)=0.0935+0.0511i$, $|\psi|=0.1065$; if $dS/dp=Q=2.7778$ then $d\psi/dp=i\,2.7778\,\psi$ and $-iB\frac{1}{\psi}\frac{d\psi}{dp}=-i(i\,2.7778)=2.7778=Q$ ✓.

8. **The variational step and the probability wave equation.** A **transaction energy functional** is constructed from (12),
   $$G(p,\psi)=\left(W-E\right)\psi^*\psi+\frac{B^2 p}{V}\left(\frac{\partial \psi^*}{\partial p}\right)\left(\frac{\partial \psi}{\partial p}\right), \tag{22}$$
   and the trading-priority rule ("price first, time first" — the next trade is the one that minimizes price volatility relative to the current price $p_c$) is expressed as the **variational principle**
   $$\delta\!\int G(p,\psi)\,dp=0. \tag{23}$$
   The Euler–Lagrange equation of (22)–(23) is $-\frac{B^2}{V}\frac{d}{dp}\!\left(p\frac{d\psi}{dp}\right)+(W-E)\psi=0$; dividing by $p$ and inserting the linear potential (9) yields the **time-independent security transaction volume-price probability wave equation**
   $$\frac{B^2}{V}\left(\frac{d^2\psi}{dp^2}+\frac{1}{p}\frac{d\psi}{dp}\right)+\left[E-A(p-p_0)\right]\psi=0, \tag{24}$$
   with natural boundary conditions $\psi(0)=0$, $\psi(p_0)<\infty$, $\psi(+\infty)\to0$. The solution uses $p_0$ as origin, $p'=p-p_0$, and the natural unit $V/B^2=1$.
   *Worked example.* Verify that the fitted sample-1 Bessel profile satisfies (24) in the $p'$ coordinate with $E-A p'=\omega^2$ and $V/B^2=1$. Using $C=0.1065$, $\omega=31.677$ ($\omega^2=1003.4$), at $p'=0.018$ ($x=\omega p'=0.5702$): $\psi=C J_0=0.09802$; $\psi'=-C\omega J_1(x)$ with $J_1(0.5702)=0.27367$, so $\psi'=-0.92325$; using $J_0''=-J_0+J_1/x$, $\psi''=C\omega^2(-0.92035+0.47995)=106.865\times(-0.44040)=-47.064$. Then $\psi''+\frac{1}{p'}\psi'+\omega^2\psi=-47.064-51.291+98.353=\mathbf{-0.002\approx 0}$ ✓ (residual is rounding).

9. **Solution set 1 — Bessel eigenfunctions and "coherence".** If the transaction energy is not constant but takes the form $E=p'\dot v_t$ (with $p'=p-p_0$) — a **dissipative** system in physics terms — (24) has the analytical solutions
   $$\psi_m(p)=C_m J_0\!\left[\omega_m\left(p-p_0\right)\right],\qquad m=0,1,2,\dots \tag{25}$$
   with eigenvalues $\omega_m>0$ satisfying the **coherence condition**
   $$\omega_m^2=\dot v_t-A=F_T+F_R=\frac{v}{V}\dot v_t=\text{const.} \tag{26}$$
   The measurable volume density/probability at price $p$ is the modulus
   $$\left|\psi_m(p)\right|=C_m\left|J_0\!\left[\omega_m(p-p_0)\right]\right|,\qquad m=0,1,2,\dots \tag{27}$$
   which is exactly the model already tested as (1). The interpretation: **transaction force and restoring force are coherent — their sum is a constant eigenvalue across the whole trading price range** — and the observed volume kurtosis is the consequence of that coherence. The author also notes that unlike quantum mechanics, here the **modulus itself** (not its square) is the probability, because the observed kurtosis is not as steep as $|\psi|^2$ would be.
   *Worked example (continuing S).* $F_T+F_R=\dot v_t-A=1.9290\times10^{-4}-1.8518\times10^{-4}=\mathbf{7.72\times10^{-6}}$, and independently $\frac{v}{V}\dot v_t=0.04\times1.9290\times10^{-4}=\mathbf{7.716\times10^{-6}}$ ✓ — the two routes to $\omega_m^2$ agree. Using (27) with the sample-1 fit at $p=5.80$: $x=31.677\times0.058=1.8373$, $J_0(1.8373)=1-0.84392+0.17805-0.01670+0.00088-0.00003=0.3183$, so $|\psi|=0.1065\times0.3183=\mathbf{0.0339}$ (3.4 % of volume), versus $0.1065$ (10.65 %) at the peak $p=p_0$ — and the first node sits at $p=5.742+2.405/31.677=\mathbf{5.818}$ yuan.

10. **Solution set 2 — Kummer eigenfunctions, the random-walk case, jump equilibria, and limits.** If transaction energy (equivalently the restoring-force magnitude) *is* constant over the price range — a **conserved** system — (24) instead gives
    $$\psi_m(p)=C_m e^{-A_m(p-p_0)}\,F\!\left(-m,\,1,\,2A_m(p-p_0)\right),\qquad m=0,1,2,\dots \tag{28}$$
    $$A_m=\frac{E}{1+2m}=\text{const}>0, \tag{29}$$
    $$\left|\psi_m(p)\right|=C_m e^{-A_m(p-p_0)}\left|F\!\left(-m,1,2A_m(p-p_0)\right)\right|, \tag{30}$$
    where $F(-m,1,\xi)$ is the **confluent hypergeometric (first Kummer) function**, $A_m$ the eigenvalue, $C_m$ a normalization constant and $m$ the eigenfunction order. In this branch restoring force is independent of transaction force, **there is no coherence**, and the solution describes a **uniform volume distribution / price random-walk** character. For $m=0$, $F(0,1,\xi)\equiv1$ and $|\psi_0|$ is a pure exponential. Empirically this case is **rare: 1 of 618 samples = 0.16 %**. Of the 35 samples that failed the 95 % test, 34 are explained by an **equilibrium-price jump**, fitted by a superposition of two eigenfunctions:
    $$\psi(p)=C_m\left(\left|J_0[\omega_m(p-p_{01})]\right|+\left|J_0[\omega_m(p-p_{02})]\right|\right),\qquad m=0,1,2,\dots \tag{31}$$
    31 of those 34 needed a single shared eigenvalue (e.g. **600001**, 2003/06/06: $\chi^2=0.00058$, $R^2=0.72535$, $C=0.13061$, $\omega=166.59$, $p_{01}=5.522$, $p_{02}=5.589$) and 3 needed two eigenvalues (e.g. **600018**, 2003/06/24: $R^2=0.49625$, $p_{01}=11.998$, $\omega_2=34.084$, $p_{02}=12.114$). The single remaining sample (**600005**, 2003/06/06) failed the superposition test ($R^2=0.26511<R^2_{crit}=0.29$) but passed the first-order Kummer fit ($R^2=0.3523>R^2_{crit}=0.16$, $C=0.11529$, $A_1=29.694$, $p_0=6.15089$). Stated conclusion: price waves around an equilibrium price that itself **steps or jumps from time to time**; an eigenvalue plus an equilibrium price determines a stationary state; **randomness is an extreme special case**, not the norm. Appendix A derives the companion **time-dependent** equation
    $$-i\frac{V}{B}\frac{\partial\psi}{\partial t}=\frac{\partial\psi}{\partial p}+p\frac{\partial^2\psi}{\partial p^2}-\frac{V}{B^2}W(p)\psi, \tag{A-11}$$
    which reduces to (24) when $iB\,\partial\psi/\partial t=E\psi$ (A-7). Limitations the author himself flags: the model is validated only "**at this early stage**", $R^2$ is modest in many fits, dynamic energy is treated as an "error item" that is negligible only when total volume is large, and both transaction energy and potential energy are *assumed constant at first* in the derivation.
    *Worked example.* Take the paper's own first-order fit (sample 600005): $m=1$, $F(-1,1,\xi)=1-\xi$, $C=0.11529$, $A_1=29.694$, $p_0=6.15089$. At $p=6.10$, $|p'|=0.05089$: $e^{-A_1|p'|}=e^{-1.5112}=0.22064$; $\xi=2A_1|p'|=3.02244$; $|1-\xi|=2.02244$; hence $|\psi_1|=0.11529\times0.22064\times2.02244=\mathbf{0.0514}$ (5.1 % of volume in that bin). Its nodes lie at $|p'|=1/(2A_1)=0.01684$, i.e. at $p=6.134$ and $p=6.168$ — a flat, twin-shouldered profile, which is why this "uniform-looking" sample fits the $m=1$ eigenfunction rather than the single-peak Bessel model. From (29), $E=A_1(1+2m)=29.694\times3=89.08$ in the paper's natural units, which then implies $A_0=89.08$, $A_2=17.82$, $A_{10}=4.24$ — higher orders have decay length $1/A_m\propto(1+2m)$ and $m$ nodes, matching the widening, more oscillatory shapes plotted in Fig. 3 for $m=0,1,2,10$. Worked example for (31), sample 600001 at $p=5.55$: $|J_0(166.59\times0.028)|+|J_0(166.59\times(-0.039))|=|J_0(4.6645)|+|J_0(6.4970)|=0.2789+0.2600=0.5389$, so $\psi=0.13061\times0.5389=\mathbf{0.0704}$ (7.0 %).

## 3. Key Importance Topics

### Stationary volume kurtosis over a trading price range

The paper's central empirical claim is that intraday accumulative volume, plotted **against price rather than against time**, converges to a stable single-peaked (leptokurtic) distribution centred near the price mean, and does so *independently of the path price took, of the time ordering of trades, and of the total volume traded*. 94.34 % of 618 stock-days in the Shanghai 180 sample fit this shape at the 95 % level.

**Why it matters:** It reframes the volume-price problem. Nearly all of the price–volume literature the paper cites studies a **correlation between return and total volume in a time bucket**; this paper studies the **shape of the volume-versus-price profile** and finds it is a **stable, low-parameter object** (three numbers: $C$, $\omega$, $p_0$). That is precisely the object modern "volume profile" / market-profile trading uses heuristically — the paper supplies a closed-form candidate for it.

### The transaction energy hypothesis and the holonomic-constraint trick

Equations (7)–(8) split transaction energy into a dynamic part and a potential part, and the author argues this split is a **holonomic (velocity-independent) constraint** at the price coordinate. With two generalized coordinates (price, volume liquidity) and one constraint, the system has one degree of freedom, so price can be used as the *sole* independent coordinate.

**Why it matters:** This is the move that makes the whole derivation **tractable and analytical**. It converts an apparently two-dimensional volume-and-price problem into a **one-dimensional** ODE with closed-form eigenfunctions, and it is the reason the author can criticise Ausloos & Ivanova and Wang & Pandey — those approaches use a generalized *velocity*, which makes the constraint non-holonomic and forces them back into correlation studies with no analytical solution.

### Price as the independent variable, volume as the function

Section 6.2.1 defends choosing price (not volume) as the independent coordinate with four arguments, two of them citations: **Osborne** observed that price as a function of volume does not exist empirically, and **McCauley** showed it does not exist mathematically. Under this choice, transaction volume acceleration is a **force**, not an acceleration.

**Why it matters:** This is the paper's **methodological hinge** and it is falsifiable. If price were treated as the dependent variable, equation (8) would cease to be a holonomic constraint, generalized forces would no longer be derivable by differentiating a potential, and no analytical solution would exist. Any reuse of this framework inherits that choice: the model tells you **where volume goes given price**, never **where price goes given volume**.

### Coherence between transaction force and restoring force

The Bessel branch exists only when $\omega_m^2=F_T+F_R=\text{const}$ over the price range (eq. 26): the pushing force (volume acceleration) and the pulling force (supply–demand restoration) sum to a **constant eigenvalue**. The author calls this **coherence**, and reads the empirical 94.34 % success rate as evidence that coherence is the normal state of the market, while the coherence-free conserved-energy branch — the one that produces uniform/random-walk profiles — occurs in only **1 of 618 samples (0.16 %)**.

**Why it matters:** It **inverts the standard null hypothesis**. Mainstream finance treats random walk as the baseline and structure as the anomaly; this paper's measurement says structured, coherent volume distributions are the baseline and randomness is the **rare** special case. It also gives a *measurable* coherence quantity, which the author proposes as a quantitative handle on behavioral finance — a field he notes is otherwise hard to separate from rational theory because of "mathematical and predictive similarities".

### Transaction momentum = volume liquidity, and jumping equilibrium prices

Equation (19) identifies the generalized momentum at the price coordinate as the **volume liquidity $v_t$** itself, and (20) makes volume acceleration the transaction force. The paper uses this to explain Plerou et al.'s puzzle that **large price fluctuations occur when demand is very small**: with little liquidity, a small volume carries large momentum weight and can move — or discontinuously jump — the equilibrium price. Section 6.1 shows 34 of the 35 misfitting samples are exactly such **equilibrium-price step/jump** days, fitted by the two-centre superposition (31).

**Why it matters:** It links a **measurable state variable** (volume per unit time) to **regime change**, and it turns the model's failures into a signal: when the single-peak fit breaks down and a two-centre fit takes over, the market has **relocated its equilibrium price** — an event definition rather than an unexplained residual.

## 4. Algorithm Logic — Step-by-Step

### 4.1 Volume-profile fitting and significance test (the empirical protocol)

**Goal:** Decide whether a single day's accumulative volume, viewed as a function of price, has one dominant peak of the predicted Bessel shape, and extract the three numbers that describe it.

**Inputs:** For one stock and one trading day, all intraday trades aggregated into price bins: price levels $p_1,\dots,p_N$ and the volume traded at each. **Outputs:** the fitted normalization $C_m$, eigenvalue $\omega_m$, equilibrium price $p_0$, plus $\chi^2$, $R^2$ and a pass/fail verdict at the 95 % level.

**Steps:**

1. **Build the observed profile** — For each traded price $p_i$, sum the day's volume executed at that price, then divide by the day's total volume $V$: $P(p_i)=v_i/V$. This is a proper probability distribution over the price range ($\sum_i P(p_i)=1$) and, crucially, it discards time ordering entirely.
2. **Fit the theoretical shape** — Regress the observed profile on the absolute zero-order Bessel model, $P(p_i)=C_m\left|J_0[\omega_m(p_i-p_0)]\right|+\varepsilon_i$ (eq. 1), estimating three free parameters simultaneously by nonlinear least squares (the paper uses Origin 6.0's user-defined model "Probawave", whose reported parameters are $P1=C_m$, $P2=\omega_m$, $P3=p_0$).
3. **Read the economic content of the parameters** — $p_0$ is the day's **equilibrium price**; $\omega_m$ sets the **width** of the volume peak, since the first zero of $J_0$ occurs at argument 2.405, giving a main-lobe half-width of $2.405/\omega_m$ in price units; $C_m$ is the **peak probability** (the share of the day's volume in the modal price bin).
4. **Test significance** — Compare $R^2$ with the critical value for the sample's degrees of freedom at the 95 % level. Because $R^2=\frac{kF}{kF+(N-k-1)}$ for an $F$-test with $k$ fitted parameters and $N$ price bins, the threshold rises with the number of parameters — the paper's own thresholds behave this way ($R^2_{crit}=0.16$ for the 3-parameter fit versus $0.29$ for the 5-parameter superposition fit).
5. **Route the failures** — If the fit fails, do not discard the day: hand it to the superposition algorithm (§4.4) for a jumped equilibrium, and if that also fails, to the Kummer branch (§4.3) for a flat/random profile.

**Worked example (paper's sample 1, stock 600002, 2003/06/13):**
Step 1 produces a profile spanning roughly 5.64–5.84 yuan with a peak near 5.74. Step 2 returns $C_m=0.1065\pm0.01008$, $\omega_m=31.677\pm2.21972$, $p_0=5.74198\pm0.0047$, with $\chi^2=0.00062$ and $R^2=0.73917$. Step 3: main-lobe half-width $=2.405/31.677=0.0759$ yuan, so the model says essentially all of the day's volume sits between $5.742-0.076=5.666$ and $5.742+0.076=5.818$ yuan — which matches the plotted data range. Peak probability $=10.65\,\%$ of the day's volume at 5.742. Evaluating the fitted curve: at $p=5.76$, $|\psi|=0.1065\times J_0(0.5702)=0.1065\times0.92035=0.0980$; at $p=5.78$, $x=1.1403$, $J_0=0.6944$, $|\psi|=0.0740$; at $p=5.80$, $x=1.8373$, $J_0=0.3183$, $|\psi|=0.0339$; at $p=5.818$, $|\psi|=0$. Step 4: $R^2=0.739$ clears the 95 % threshold, so this day is one of the 583 significant samples. Step 5 is not needed.

### 4.2 Deriving the volume-price probability wave equation (the theory pipeline)

**Goal:** Turn the accounting identity "transaction energy = dynamic energy + potential energy" into a second-order differential equation whose solutions are volume distributions over price.

**Inputs:** price $p$, bin volume $v$, total volume $V$, interval length $t$, and the assumption of a restoring force toward an equilibrium price. **Outputs:** equation (24) plus its boundary conditions $\psi(0)=0$, $\psi(p_0)<\infty$, $\psi(+\infty)\to0$.

**Steps:**

1. **Define the liquidity ladder** — Compute $v_t=v/t$ (2), $m_t=pv_t$ (3), $\dot v_t=v/t^2$ (5) and $E=p\dot v_t$ (4). Every later quantity has consistent dimensions because of this ladder; $E$ is "cash liquidity energy", the acceleration of transaction amount.
2. **Split the energy** — Write $E=T+W$ with $T=PE=\frac{v}{V}p\dot v_t$ and $W=(1-P)E$, giving the constraint $-E+\frac{v}{V}p\dot v_t+W(p)=0$ (8). This is the *hypothesis*: the share of energy that shows up as volume at this price is the dynamic part; the rest is potential, and it is exactly the part that expresses price volatility.
3. **Choose a potential shape** — Argue that the potential is proportional to price and set $W(p)=A(p-p_0)$ (9), so the restoring force is the constant-magnitude $F_R=-A=-\dot v_t(1-v/V)$ (10). Note it vanishes precisely when $v/V=1$, i.e. when supply and demand are permanently balanced.
4. **Introduce a wave ansatz** — Write $\psi=Re^{iS/B}$ (11); then $\partial S/\partial p=-iB\psi^{-1}\partial\psi/\partial p$ (12). The paper stresses that an exponential ansatz would give the same final equation, as in Schrödinger's own derivation.
5. **Impose Hamilton–Jacobi** — Require $\partial S/\partial t+H(p,\partial S/\partial p)=0$ (13) with $H=T+W$ (14); separate variables as $S=S_1(p)-Et$ (15)–(16) and fix $S=v_tp-Et$ (17)–(18) by dimensional matching.
6. **Identify momentum and force** — Read off $Q=\partial S/\partial p=v_t$ (19), so transaction momentum *is* volume liquidity, and $F_T=dQ/dt=\dot v_t$ (20) is the transaction force. Substituting into the constraint gives $-E+\frac{p}{V}(\partial S/\partial p)^2+W=0$ (21).
7. **Vary an energy functional** — Build $G(p,\psi)=(W-E)\psi^*\psi+\frac{B^2p}{V}\psi^*_{,p}\psi_{,p}$ (22) and impose $\delta\int G\,dp=0$ (23), justified by the exchange's **price-priority/time-priority** rule: the next trade is the one that minimizes price deviation from the current price. The Euler–Lagrange equation of this functional is (24).
8. **Normalize the coordinates** — Shift the origin to $p_0$ via $p'=p-p_0$ and adopt the natural unit $V/B^2=1$, leaving $\frac{d^2\psi}{dp'^2}+\frac{1}{p'}\frac{d\psi}{dp'}+\left(E-Ap'\right)\psi=0$ (eq. B-1) to be solved.

**Worked example (end-to-end with running example S):** inputs $p=5.78$, $v=40{,}000$, $V=1{,}000{,}000$, $t=14{,}400$ s.
Step 1: $v_t=2.7778$, $m_t=16.056$, $\dot v_t=1.9290\times10^{-4}$, $E=1.1150\times10^{-3}$.
Step 2: $P=0.04$, $T=4.460\times10^{-5}$, $W=1.0704\times10^{-3}$; constraint residual $=-1.1150\times10^{-3}+4.460\times10^{-5}+1.0704\times10^{-3}=0$.
Step 3: $A=1.9290\times10^{-4}\times0.96=1.8518\times10^{-4}$; $F_R=-1.8518\times10^{-4}$; sanity check $A\cdot p=1.0703\times10^{-3}=W$.
Step 4–5: with $B=1$ and phase $0.5$ rad, $\psi=0.0935+0.0511i$; $S=v_tp-Et=16.0556-16.0560\approx0$ (see the caveat in §5).
Step 6: $Q=2.7778$, $F_T=1.9290\times10^{-4}$; check (21): $\frac{5.78}{10^6}(2.7778)^2=4.460\times10^{-5}=T$ ✓.
Step 7–8: with $E-Ap'\to\omega^2$ and $V/B^2=1$, substituting the fitted $\psi=0.1065\,J_0(31.677\,p')$ at $p'=0.018$ gives $\psi''+\frac{1}{p'}\psi'+\omega^2\psi=-47.064-51.291+98.353\approx0$ ✓ — the fitted empirical curve satisfies the derived equation.

### 4.3 Solving the equation — the Kummer (conserved-energy) branch, Appendix B

**Goal:** Solve $\psi''+\frac{1}{p'}\psi'+(E-Ap')\psi=0$ in closed form when $E$ is a **constant**, and find which eigenvalues $A_m$ are allowed.

**Inputs:** constant transaction energy $E$, restoring-force magnitude $A>0$, boundary conditions $\psi(0)<\infty$, $\psi(\pm\infty)\to0$. **Outputs:** eigenvalues $A_m=E/(1+2m)$ and eigenfunctions $\psi_m(p')=C_me^{-A_mp'}F(-m,1,2A_mp')$.

**Steps:**

1. **Classify the singular points** — $p'=0$ is a regular singular point; $p'=\pm\infty$ are irregular. Treat $p'\ge0$ first and mirror the result for $p'\le0$.
2. **Behaviour at the origin** — Try $\psi_0(p')\propto p'^{\rho}$; substitution gives the indicial equation $\rho(\rho-1)+\rho=0$, hence $\rho=0$, so $\psi$ tends to a **constant** at the equilibrium price (no divergence, no forced zero).
3. **Behaviour at infinity** — For large $p'$ the equation becomes $\frac{d^2\psi}{dp'^2}-A p'\,\psi\approx0$ whose solutions behave like $e^{\pm\sqrt{A}\,p'}$; the boundary condition keeps only the **decaying** branch $e^{-\sqrt{A}p'}$ (written $e^{-Ap'}$ in the paper's normalization).
4. **Peel off the asymptotics** — Write $\psi(p')=e^{-Ap'}u(p')$; the equation for $u$ becomes $\frac{d^2u}{dp'^2}+\left(\frac{1}{p'}-2A\right)\frac{du}{dp'}+\left(\frac{E}{p'}-A\right)u=0$ (B-9).
5. **Change variable to a standard form** — Substitute $\xi=2Ap'$ to get $\xi u''+(1-\xi)u'-\frac{1}{2}\left(1-\frac{E}{A}\right)u=0$ (B-10), which is the **confluent hypergeometric equation** $\xi u''+(\gamma-\xi)u'-\alpha u=0$ with $\gamma=1$ and $\alpha=\frac{1}{2}\left(1-\frac{E}{A}\right)$ (B-12).
6. **Quantize** — The Kummer series $F(\alpha,\gamma,\xi)=\sum_{k\ge0}\frac{(\alpha)_k}{(\gamma)_k}\frac{\xi^k}{k!}$ terminates into a polynomial of order $m$ — the only way to satisfy the decay condition — exactly when $\alpha=-m$, $m=0,1,2,\dots$. Solving $-m=\frac12(1-E/A)$ gives the **eigenvalues** $A_m=\frac{E}{1+2m}$ (B-16), i.e. $A_m^2=\frac{E^2}{(1+2m)^2}$ (B-17).
7. **Assemble and mirror** — $\psi_m(p')=C_me^{-A_mp'}F(-m,1,2A_mp')$ for $p'\ge0$ (B-19); repeating with $p'\to-p'$ for $p'\le0$ (B-20)–(B-23) and noting the footnote that $E<0$ when $p'\le0$ gives the same functional form, so the general solution over $-\infty<p'<+\infty$ is (B-24) with $A_m^2=E^2/(1+2m)^2$ (B-25).

**Worked example:** take $A=1$, $E=3$, i.e. $m=1$ since $A=E/(1+2m)\Rightarrow 1=3/3$ ✓. Then $F(-1,1,\xi)=1-\xi$ and $\psi_1(p')=e^{-p'}(1-2p')$.
At $p'=0.5$: $\psi=e^{-0.5}(1-1)=0$; $\psi'=e^{-Ap'}(2A^2p'-3A)=0.60653\times(1-3)=-1.21306$; $\psi''=e^{-Ap'}(-2A^3p'+5A^2)=0.60653\times(-1+5)=2.42612$. Check B-1: $2.42612+\frac{1}{0.5}(-1.21306)+(3-0.5)\times0=2.42612-2.42612+0=\mathbf{0}$ ✓.
At $p'=1$: $\psi=e^{-1}(1-2)=-0.36788$; $\psi'=e^{-1}(2-3)=-0.36788$; $\psi''=e^{-1}(-2+5)=1.10364$. Check: $1.10364-0.36788+(3-1)(-0.36788)=1.10364-0.36788-0.73576=\mathbf{0}$ ✓.
The eigenfunction has its node at $p'=0.5$ and decays afterwards — one node for $m=1$, and in general $m$ nodes with decay length $1/A_m=(1+2m)/E$ growing linearly in $m$, which is why the paper's Fig. 3 curves for $m=0,1,2,10$ become progressively broader and more oscillatory.

### 4.4 Handling abnormal days — the two-centre superposition test

**Goal:** Explain and fit the days whose volume profile has **two or more peaks**, which the single Bessel model rejects.

**Inputs:** the same observed volume profile $P(p_i)$ for a failed day. **Outputs:** two equilibrium prices $p_{01},p_{02}$ (and one or two eigenvalues), plus a pass/fail verdict.

**Steps:**

1. **Detect the failure mode** — A day fails when the imbalance between supply and demand became large enough that the **equilibrium price itself stepped or jumped**; price then oscillated first around one centre and later around another, so the accumulated profile has at least two kurtoses.
2. **Fit the superposition** — Regress on $\psi(p)=C_m\left(|J_0[\omega_m(p-p_{01})]|+|J_0[\omega_m(p-p_{02})]|\right)$ (eq. 31), i.e. two Bessel peaks sharing one eigenvalue (Origin model "Probawave200", 4 parameters), or, if that fails, allow **two distinct eigenvalues** (Origin model "Probawave3", 5 parameters).
3. **Fall back to the Kummer branch** — If even the two-centre fit fails, refit with the first-order eigenfunction (30); a pass here means the day was a genuinely **flat / random-walk** day, the conserved-energy case.
4. **Interpret** — The number of centres is the number of equilibrium prices the market visited; the paper concludes that a stationary state is pinned down by an **eigenvalue plus an equilibrium price**, and that a known eigenvalue alone still leaves the state uncertain.

**Worked example (paper's failure cascade):** 35 of 618 samples fail step 1's single-peak test. Step 2 with one shared eigenvalue rescues **31** of them — e.g. stock **600001** on 2003/06/06: $C=0.13061$, $\omega=166.59$, $p_{01}=5.522$, $p_{02}=5.589$, $\chi^2=0.00058$, $R^2=0.72535$; evaluating the fit at $p=5.55$ gives $0.13061\times(|J_0(4.6645)|+|J_0(6.4970)|)=0.13061\times(0.2789+0.2600)=0.0704$, i.e. 7.0 % of volume in that bin, and the two peaks lie $5.589-5.522=0.067$ yuan apart. Step 2 with two eigenvalues rescues **3** more (e.g. **600018**, 2003/06/24: $p_{01}=11.998$, $p_{02}=12.114$, second eigenvalue 34.084, $R^2=0.49625$). That leaves **1** sample, **600005** on 2003/06/06, which fails the superposition ($R^2=0.26511$ against $R^2_{crit}=0.29$) and is finally caught by step 3, the first-order Kummer fit ($R^2=0.3523$ against $R^2_{crit}=0.16$, $C=0.11529$, $A_1=29.694$, $p_0=6.15089$). Final tally: 583 single-peak + 34 jumped-equilibrium + 1 random = 618.

## 5. Ideas for Development

- **Bessel volume-profile fair-value estimator** — Reuse §4.1 steps 1–3 as a daily (or rolling-window) estimator that compresses an entire volume profile into three numbers: equilibrium price $p_0$, peak concentration $C_m$, and half-width $2.405/\omega_m$. Use $p_0$ as a mean-reversion anchor and $2.405/\omega_m$ as the expected containment band instead of an ATR or standard-deviation band.
  - **Strong:** Liquid large-cap intraday ranges — the paper's 618 stock-days from the Shanghai 180 give a **94.34 % fit rate at 95 % significance**, and both a broad profile ($\omega=31.7$, half-width 0.076 yuan) and a needle profile ($\omega=211.4$, half-width 0.011 yuan) are captured by the same three parameters (Section 2, Fig. 2). *(From paper)*
  - **Strong:** Thin, low-tick-count sessions where a Gaussian band overstates the range — the Bessel main lobe has **compact support**: $|J_0|$ first vanishes at $2.405/\omega_m$ and the model assigns *zero* probability there, whereas a normal band with matched peak assigns positive mass to infinity, so the Bessel band is the tighter (and falsifiable) containment claim. *(From AI)*
  - **Weak:** Trending sessions — the estimator is derived from a **time-independent** equation ($\partial S/\partial t=-E$, eq. 16) and is fitted to path-independent aggregates, so a session with drift $\mu$ over length $t$ spreads volume over a range of order $\mu t$ and produces either a flat or a twin-peaked profile; the paper's own 35 failures are exactly these "equilibrium jump" days. *(From AI)*
  - **Weak:** Real-time intraday use — $p_0$, $C_m$ and $\omega_m$ are estimated from the **completed** day's profile, so using them as same-day signals is look-ahead; the paper itself states the kurtosis only "**gradually emerges … when it takes a longer trading time**" (Section 1 and Section 7), so early-session estimates are the least reliable. *(From paper)*

- **Coherence indicator $\omega_m^2=F_T+F_R$ as a market-stability gauge** — Take equation (26) from §4.2 step 6 and §2 point 9 and compute the two forces directly from tape data: $F_T=\dot v_t=v/t^2$ and $F_R=-\dot v_t(1-v/V)$, then monitor whether their sum stays constant across price bins within a window. A drifting sum flags loss of coherence before the profile visibly breaks.
  - **Strong:** Normal two-sided markets — the paper reports coherence holding in the great majority of samples, with the coherence-free conserved-energy case occurring in only **1 of 618 days (0.16 %)**, so a departure from constancy is genuinely a **rare-event flag** rather than everyday noise. *(From paper)*
  - **Strong:** Cross-sectional screening — the identity $F_T+F_R=\frac{v}{V}\dot v_t=\frac{v^2}{Vt^2}$ is computable from three tape numbers per bin with no fitting, so it can be evaluated on hundreds of names in $O(N)$ per bin and used to rank stability without an optimizer. *(From AI)*
  - **Weak:** Very low-participation names — the indicator scales as $v^2/(Vt^2)$, so its relative sampling error is roughly $2\,\sigma_v/v$; with a handful of prints per bin the estimate's variance dominates its level, and constancy cannot be distinguished from noise. *(From AI)*
  - **Weak:** Any use requiring absolute levels — the paper works in the natural unit $V/B^2=1$ and never pins $B$ down empirically, and the fitted $\omega$ values (22–301 per yuan) are orders of magnitude away from the force-based $\omega^2$ computed from raw tape units, so only **relative changes** of the indicator are meaningful, not its level. *(From AI)*

- **Regime classifier from the fit cascade** — Reuse the §4.4 cascade verbatim as a three-state daily label: *single-peak coherent* (Bessel fit passes) → *equilibrium jump* (two-centre superposition (31) passes) → *random/uniform* (first-order Kummer (30) passes). Trade mean reversion in state 1, breakout/relocation in state 2, and stand aside in state 3.
  - **Strong:** Discriminating power is empirically demonstrated — the cascade classified **583 / 34 / 1** of 618 days with each stage rescuing the previous stage's failures, and the two-centre fits recovered $R^2$ from failing values up to 0.725 (stock 600001). *(From paper)*
  - **Strong:** State 2 is directly actionable — the fit returns the two equilibrium prices, e.g. $p_{01}=5.522$ and $p_{02}=5.589$ for stock 600001, so the jump size (0.067 yuan, 1.2 %) is an explicit target/stop distance rather than a discretionary level. *(From AI)*
  - **Weak:** The stages are not statistically comparable as stated — moving from the 3-parameter to the 5-parameter model raises the critical $R^2$ (0.16 versus 0.29 in the paper's own footnotes to Figs. 5–6) because $R^2=\frac{kF}{kF+(N-k-1)}$ grows with $k$; without penalizing parameters (AIC/BIC) or nesting the tests, a "state 2" label can be pure overfitting of a two-peak model to noise. *(From AI)*
  - **Weak:** Label lag — every stage is fitted to the completed profile, so the classifier is retrospective; the jump it detects has already happened, which limits the idea to next-session positioning or to online refitting whose early-session estimates the paper flags as unreliable. *(From paper + AI)*

- **Liquidity-weighted impact model from transaction momentum** — Build on §4.2 step 6: since $Q=v_t$ is the momentum and $F_T=\dot v_t$ the force, size an order by the volume acceleration needed to shift the equilibrium price. The paper explicitly proposes this application: "how much amount of money are we going to use to trade a stock price from current \$5 per share to expected \$10 per share", or to move an index from 1000 to 1500 points.
  - **Strong:** Low-liquidity conditions, where the effect is largest — the framework reproduces Plerou et al.'s empirical finding that **large price fluctuations occur when demand is very small**, because with small $v_t$ a given $\dot v_t$ carries proportionally more weight in the equilibrium price (Section 6.2.1). *(From paper)*
  - **Strong:** Short horizons — $\dot v_t=v/t^2$ is quadratic in the inverse of the interval, so executing the same volume in half the time raises the transaction force **fourfold**, giving a concrete, testable schedule-versus-impact trade-off. *(From AI)*
  - **Weak:** The model provides no price *trajectory* — it is a stationary distribution over price, and the paper concedes price paths are unknowable in its one-dimensional formulation ("we are unable to know exact price path", Section 6.2.3); so it can suggest a size but not a fill schedule or an expected slippage path. *(From AI)*
  - **Weak:** Calibration is unidentified in absolute terms — the impact scale depends on $A$ and $B$, and $A=\dot v_t(1-v/V)$ is itself a function of the very volume being executed, making the relation implicit and self-referential; solving for the required cash requires an external anchor the paper does not supply. *(From AI)*

- **Replication and stress-testing of the coherence claim on modern data** — Rerun the whole §4.1 protocol on high-frequency data from other markets and regimes (US equities, crypto, futures) with tick-level bins, and report the fit rate as a function of regime, instrument liquidity and bin count.
  - **Strong:** The protocol is cheap and fully specified — three parameters, one nonlinear least-squares fit per instrument-day, and the paper's own Origin models ("Probawave", "Probawave200", "Probawave3", "ProbawaveA1") define the exact functional forms to reproduce. *(From paper)*
  - **Weak:** The original evidence base is narrow and internally correlated — 618 samples come from only **30 stocks over 21 days in one month of one index** (June 2003, Shanghai 180, plus one 2002 Shenzhen sample); stock-days in the same month share a market factor, so the effective independent sample size is far below 618 and the 94.34 % figure is not a clean out-of-sample statistic. *(From AI)*
  - **Weak:** The reported goodness-of-fit is modest — accepted fits include $R^2=0.596$, $0.49625$ and even $0.3523$; since the 95 % $R^2$ threshold falls as the bin count $N$ grows ($R^2_{crit}=\frac{kF_{crit}}{kF_{crit}+N-k-1}\to0$ as $N\to\infty$), "significant at 95 %" here means "better than nothing", not "explains the profile". *(From AI)*
  - **Weak:** Two internal inconsistencies should be resolved before building on the derivation. First, under the paper's own definitions $E=p\dot v_t$ (4) and $\dot v_t=v_t/t$ (5), the action $S=v_tp-Et=pv_t-pv_t\equiv0$ identically (numerically, $2.7778\times5.78-1.1150\times10^{-3}\times14400=16.0556-16.0560\approx0$), so the phase $S/B$ in (11) is degenerate unless the Bessel branch's alternative $E=p'\dot v_t$ is used. Second, the term $\frac1p\frac{d\psi}{dp}$ in (24) is **not translation invariant**, so the claim that "the equation is supposed to keep its validation regardless of an origin selection" fails: substituting the fitted $\psi=CJ_0(\omega p')$ into (24) gives a residual of $\approx0.002$ when the $1/p'$ form is used but $\approx51$ when $1/p$ is used at $p=5.76$. *(From AI)*

## 6. Tools & Data Used in This Research

### Software & Library

| Tools | Purpose in paper |
|---|---|
| Origin 6.0 Professional | The only software named; used for the nonlinear curve fitting of every volume distribution and for reporting $\chi^2$, $R^2$ and parameter standard errors ("Origin 6.0 Professional is friendly used in our test", Section 2) |
| User-defined Origin fitting model "Probawave" | The single zero-order Bessel model, eq. (1)/(27); parameters P1 = $C_m$, P2 = $\omega_m$, P3 = $p_0$ (Fig. 2) |
| User-defined Origin fitting model "Probawave200" | Superposition of two Bessel eigenfunctions sharing one eigenvalue, eq. (31); parameters P1–P4 including two equilibrium prices (Fig. 4a) |
| User-defined Origin fitting model "Probawave3" | Superposition of two Bessel eigenfunctions with two eigenvalues, eq. (31); parameters P1–P5 (Figs. 4b, 5) |
| User-defined Origin fitting model "ProbawaveA1" | First-order confluent-hypergeometric eigenfunction fit, eq. (30) with $m=1$ (Fig. 6) |

### Data Source

| Source | Description |
|---|---|
| Shanghai 180 Index constituents — first 30 individual stocks | Primary dataset; daily intraday trading data for **June 2003**, aggregated into accumulative trading volume per price level over each day's trading price range |
| Sample construction | 30 stocks × 21 trading days = **630** samples; **11 halted** samples and **1 lost** sample removed; **618** samples tested; 583 significant at the 95 % level (94.34 %) |
| Named individual stock-days used in figures | 600002 (2003/06/13), 600008 (2003/06/09), 600001 (2003/06/06), 600018 (2003/06/24), 600005 (2003/06/06) |
| 000682 (2002/01/08) | Shenzhen-listed sample shown as Fig. 2(b), the "wave-shaped" volume distribution, price mean RMB 6.08 |
| Author's earlier working papers [29,30] | Cited as the source of the original volume-kurtosis observation, including the 2004 Econophysics Forum working paper "Security transaction probability wave equation—a volume/price probability wave model" |

### Models & Algorithms

| Model/Algorithm | Role |
|---|---|
| Absolute zero-order Bessel eigenfunction model, eqs. (1), (25), (27) | The paper's primary volume-distribution model and its empirical test model; the coherent (dissipative-energy) solution branch |
| Confluent hypergeometric (first Kummer) eigenfunction model, eqs. (28)–(30), (B-19)–(B-25) | The conserved-energy solution branch; describes uniform volume distribution / price random-walk behaviour; eigenvalues $A_m=E/(1+2m)$ |
| Superposition of two Bessel eigenfunctions, eq. (31) | Model for days on which the equilibrium price steps or jumps; rescues 34 of the 35 failing samples |
| Transaction energy hypothesis, eqs. (7)–(8) | The core postulate: transaction energy = dynamic (distribution) energy + potential energy, as a holonomic constraint at the price coordinate |
| Linear potential / supply–demand restoring force, eqs. (9)–(10) | Represents the restoring force $F_R=-A$ that drives trading back toward the equilibrium price |
| Hamilton–Jacobi formulation with wave ansatz, eqs. (11)–(21) | Derivation vehicle; yields transaction momentum $Q=v_t$ and transaction force $F_T=\dot v_t$ |
| Variational principle on a transaction energy functional, eqs. (22)–(24) | Converts the price-priority/time-priority trading rule into the Euler–Lagrange equation that *is* the volume-price probability wave equation |
| Time-dependent volume-price wave equation, Appendix A (A-1)–(A-11) | Companion dynamic equation; reduces to the time-independent equation (24) under $iB\,\partial\psi/\partial t=E\psi$ |
| Series/asymptotic ODE solution method, Appendix B (B-1)–(B-25) | Indicial equation at the regular singular point, asymptotic peeling $e^{-Ap'}$, substitution $\xi=2Ap'$, and polynomial termination of the Kummer series to quantize eigenvalues |
| Nonlinear least squares with $\chi^2$ and $R^2$ significance testing at the 95 % level | Estimation and hypothesis-testing method for all fits; econometric methodology referenced to Wooldridge [31] |
| ARCH / GARCH, Black–Scholes–Merton, spin models, Fokker–Planck models | Discussed as prior art and contrasted with the proposed model; **not** used in the paper's own computations |

## 7. Key References Worth Exploring

| Reference | Relevance |
|---|---|
| V. Plerou, P. Gopikrishnan, X. Gabaix, H.E. Stanley (2002), "Quantifying stock-price response to demand fluctuations," *Physical Review E* 66, 027104 | The empirical puzzle the paper claims to explain — large price fluctuations occur when demand is very small — reinterpreted via transaction momentum in Section 6.2.1 |
| M. Ausloos, K. Ivanova (2002), "Mechanic approach to generalized technical analysis of share prices and stock market indices," *European Physical Journal B* 27, 177–187 | The closest prior mechanical analogy (generalized kinetic energy and momentum from normalized volume); the paper positions itself as fixing this approach's non-holonomic velocity formulation |
| H. Wang, R.B. Pandey (2004), "A momentum trading approach to technical analysis of Dow Jones industrials," *Physica A* 331, 639–650 | Parallel definition of trading momentum as relative price velocity times a volume-based "mass"; useful contrast for anyone implementing the momentum concept |
| A.R. Gallant, P.E. Rossi, G. Tauchen (1992), "Stock prices and volume," *The Review of Financial Studies* 5, 199–242 | The benchmark comprehensive price–volume study (NYSE daily data 1928–1987) that defines the correlation-based tradition this paper departs from |
| C.M. Lee, B. Swaminathan (2000), "Price momentum and trading volume," *Journal of Finance* 55, 2017–2069 | Source of the paper's framing quotation on how little is known about trading volume; the reference point for the volume-literature gap |
| M.F.M. Osborne (1977), *The Stock Market and Finance from a Physicist's Viewpoint* | Empirical basis for the paper's methodological hinge — price as a function of volume does not exist, volume must be modelled as a function of price |
| J.L. McCauley (2000), "The futility of utility: how market dynamics marginalize Adam Smith," *Physica A* 285, 506–538 | The mathematical counterpart to Osborne's claim, used to justify choosing price as the independent generalized coordinate |
| E. Schrödinger (1928), *Collected Papers on Wave Mechanics*, 1–40; and D. Derbes (1996), "Feynman's derivation of the Schrödinger equation," *Am. J. Phys.* 64, 881–884 | The templates for the wave-ansatz-plus-Hamilton–Jacobi derivation in Section 5 and Appendix A, including the exponential-versus-wave function argument |
| D.T. Greenwood (1977), *Classical Dynamics*; H. Goldstein (1980), *Classical Mechanics* (2nd ed.) | Source of the holonomic-constraint and degrees-of-freedom argument that reduces the volume-price problem to one dimension |
| M. Schaden (2002), "Quantum finance," *Physica A* 316, 511–538; E.W. Piotrowski, J. Sladkowski (2005), "Quantum diffusion of prices and profits," *Physica A* 345, 185–195; B.E. Baaquie (2004), *Quantum Finance* | The quantum-finance literature the paper situates itself against — all build on existing quantum formalism, whereas this paper derives its equation from a transaction-energy hypothesis |
| Y.-C. Zhang (1999), "Toward a theory of marginally efficient markets," *Physica A* 269, 30–44 | The square-root relationship between price changes and demand; a competing analytical price–demand law worth benchmarking the wave model against |
| J.M. Wooldridge (2000), *Introductory Econometrics: A Modern Approach* | The stated econometric reference for the error-term specification and significance testing in eq. (1) |
| L.L. Shi (2004), "Security transaction probability wave equation—a volume/price probability wave model," Econophysics Forum working paper | The author's own precursor paper containing the original observation and earlier formulation of the model |

---
Report generated on: 2026-08-13
Source PDF: [shi_2010_volume_price_probability_wave.pdf](file:d:\Repository\Quant_Trading\research\paper\volume\shi_2010_volume_price_probability_wave.pdf)
