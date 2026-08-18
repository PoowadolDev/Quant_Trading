# Modeling First Line Of An Order Book With Multivariate Marked Point Processes

## 1. Paper Information

| Fields | Detail |
|---|---|
| Title | Modeling First Line Of An Order Book With Multivariate Marked Point Processes |
| Author | Alexis Fauth, Ciprian A. Tudor |
| Institution | Fauth: (1) SAMM, Université Paris 1 Panthéon-Sorbonne, Paris, France; (2) Invivoo, Courbevoie, France. Tudor: (3) Laboratoire Paul Painlevé, Université de Lille 1, Villeneuve d'Ascq, France; (4) Department of Mathematics, Academy of Economical Studies, Bucharest, Romania. Work supported by CNCS grant **PN-II-ID-PCCE-2011-2-0015** |
| Publisher | **arXiv preprint, q-fin.TR** — arXiv:1211.4157v1, stamped **17 Nov 2012**. (The typeset body carries a recompilation date of "November 27, 2024"; the arXiv margin stamp of 17 Nov 2012 is the real submission date. No journal venue is named in the PDF.) |
| Link | https://arxiv.org/abs/1211.4157 |

Keywords stated by the authors: order book, bid-ask spread, market impact, microstructure, multivariate marked Hawkes processes, trading strategy.

## 2. Summary

Notation used throughout this digest, matching the paper: $N_i(t)$ = cumulative event count of component $i$; $\lambda_i$ = conditional intensity of component $i$ [events·time⁻¹]; $\mu_i$ = baseline ("instantaneous") rate; $\nu_{ij}$ = branching coefficient (mean number of type-$i$ events triggered by a type-$j$ event); $h_i$ = decay kernel; $g_j$ = mark impact function; $v$ = mark = order volume; $f$ = mark density; $p_{tick}$ = tick size; $a/b$ = best ask / best bid; $+/-$ = upward / downward jump; $s$ = bid-ask spread; $\Lambda$ = compensator (integrated intensity).

Two symbol clashes in the paper are worth flagging before reading further, because both are silent: (i) $\alpha_i$ in the decay kernel (3.5) and $\alpha$ in the impact function (3.7)–(3.8) are *different* parameters — this digest writes $\alpha_h$ for the kernel decay rate and keeps $\alpha$ for the impact exponent; (ii) $\lambda$ denotes both an intensity and, in the stationarity condition (3.10), an eigenvalue of the branching matrix.

1. **Motivation and the gap the paper attacks.** Orders do not arrive in continuous time, so tick-by-tick prices are flagrantly discontinuous and are naturally described by point processes. The paper's complaint about the existing high-frequency literature is that it uses *self-exciting* point processes keyed only to **arrival frequency**, so that "at the same frequency, 'small' or 'large' volumes traded will impact the market in the same way." The dominant count-only formulation is
   $$p(t) = N^{+}(t) - N^{-}(t) \tag{2.1}$$
   where $p(t)$ is the (last or mid) price and $N^{\pm}(t)$ count upward and downward jumps. Its defect is that it yields no bid and no ask, hence no spread, whereas the spread
   $$s = p_{ask} - p_{bid}$$
   is a first-order cost: an agent who buys $k$ contracts at the ask for $k\,p_{ask} = x\$k$ and must unwind immediately sells at $k\,p_{bid} = (x\$-s)k$, so the round-turn transaction cost is $k\,s\$$, before broker fees and market impact. The complementary timing variable is the intertrade duration
   $$d_k = t_k - t_{k-1} \tag{4.1}$$
   *Worked example.* With $p_{ask}=1.32011$, $p_{bid}=1.32003$ and $p_{tick}=10^{-5}$ (the paper's FX tick), $s = 8\times10^{-5}$ = **8 ticks**; a $k=300{,}000$ EUR round turn costs $300000\times8\times10^{-5}=\mathbf{24.00}$ USD in spread alone. Two consecutive events at $t_{k-1}=0.300$ s and $t_k=0.500$ s give $d_k=\mathbf{0.200}$ s = 200 ms.

2. **The Hawkes toolkit the model is built from.** The conditional intensity of a $d$-dimensional point process is defined as
   $$\lambda(t\mid\mathcal{F}_t)=\lim_{\delta t\searrow 0}\frac{1}{\delta t}\,\mathbb{E}\!\left[N(t+\delta t)-N(t)\mid \mathcal{F}_t\right] \tag{3.1}$$
   i.e. the conditional probability per unit time of a new event at $t+\delta t$ given the history $\mathcal{F}_t$. A multivariate Hawkes process specialises this to
   $$\lambda_i(t\mid\mathcal{F}_t)=\mu_i+\sum_{j=1}^{d}\nu_{ij}\int_{-\infty}^{t}h_i(t-s)\,N_j(ds) \tag{3.2}$$
   with $h_i(t)\ge 0$ the **decay kernel**, $\nu_{ij}$ the **branching coefficient** quantifying the ability of an event of type $j$ to trigger one of type $i$ ($j=i$ is self-excitation, $j\neq i$ mutual excitation), and $\mu_i$ the rate of instantaneous (exogenous) events. For $d=2$ the **branching matrix** is
   $$\nu=\begin{pmatrix}\nu_{11} & \nu_{12}\\ \nu_{21} & \nu_{22}\end{pmatrix} \tag{3.3}$$
   The kernel integral collapses to a finite sum over past arrival times,
   $$\int_{-\infty}^{t}h_i(t-s)N(ds)=\sum_{k\,\mid\, t_k<t}h_i(t-t_k) \tag{3.4}$$
   and the standard kernel choice is exponential,
   $$h_i(t-t_k)=\alpha_h\exp\!\left(-\alpha_h (t-t_k)\right),\qquad \alpha_h\ge 0 \tag{3.5}$$
   so a fresh event lifts the kernel to $\approx\alpha_h$ and, absent new events, it decays to $0$ exponentially. The kernel must also satisfy the finite-mean-lag condition
   $$\int_0^{\infty} t\,h_i(t)\,dt<\infty \tag{3.11}$$
   *Worked example.* With $\alpha_h=2$ s⁻¹: $h(0.5)=2e^{-1}=\mathbf{0.7358}$, $h(0.2)=2e^{-0.4}=\mathbf{1.3406}$, and (3.11) evaluates to $\int_0^\infty t\cdot 2e^{-2t}dt=1/\alpha_h=\mathbf{0.5}$ s $<\infty$ ✓. With $\mu=0.5$ s⁻¹, $\nu=0.8$ and events at $t_1=0$, $t_2=0.3$ s, the *unmarked* intensity at $t=0.5$ s is $\lambda=0.5+0.8(0.7358+1.3406)=\mathbf{2.161}$ events·s⁻¹.

3. **The paper's actual contribution — putting the volume in as a mark.** A **mark** is an extra value attached to each point; here it is the order volume $v_t$. The marked intensity becomes
   $$\lambda_i(t,v\mid\mathcal{F}_t)=\mu_i+\sum_{j=1}^{d}\nu_{ij}\int_{(-\infty,t)\times\mathbb{R}_+}h_i(t-s)\,g_j(v)\,N_j(ds\times dv) \tag{3.6}$$
   with the discrete equivalent
   $$\lambda_i(t,v\mid\mathcal{F}_t)=\mu_i+\sum_{j=1}^{d}\nu_{ij}\sum_{k\,\mid\, t^{(j)}_k<t}h_i\!\left(t-t^{(j)}_k\right)g_j\!\left(v\!\left(t^{(j)}_k\right)\right) \tag{3.9}$$
   where $\mathcal{F}_t$ is now the history of arrival times *and* marks $\{t_i,v(t_i)\}$, and $g_j$ is the **impact function of marks** — it "characterizes the impact of the volume on the financial asset fluctuation". It must be normalised,
   $$\int_{\mathbb{R}^d} g(v)\,f(v)\,dv = 1$$
   with $f$ the mark density, so that the branching coefficients keep their interpretation as mean offspring counts. The two candidate shapes are power law and exponential,
   $$\tilde g(x)=x^{\alpha},\ \alpha>0,\qquad \tilde g(x)=\exp(\alpha x),\ \alpha>0 \tag{3.7}$$
   normalised as
   $$g(x)=\frac{x^{\alpha}}{\mathbb{E}X},\ \alpha>0,\qquad g(x)=\frac{\exp(\alpha x)}{\mathbb{E}X},\ \alpha>0 \tag{3.8}$$
   where $X$ has density $f$. Without the mark, the intensity's jump depends only on elapsed time; with it, the intensity — and therefore the price — responds to **how much** was traded, not just **when**.
   *Worked example (Series D1, single component, used again in points 4 and 7).* Take $\mu=0.5$ s⁻¹, $\nu=0.8$, $\alpha_h=2$ s⁻¹, marks exponential with $\beta=1$ (volumes in millions of USD), power impact with $\alpha=0.5$; the correctly normalised impact function (see (5.4) in point 7) is $g(x)=1.12838\sqrt{x}$. Events: $t_1=0$ s with $v=1.0$M, $t_2=0.3$ s with $v=4.0$M. Then $g(1.0)=1.1284$, $g(4.0)=2.2568$ and
   $\lambda(0.5)=0.5+0.8\left[0.7358\times1.1284+1.3406\times2.2568\right]=0.5+0.8\left[0.8302+3.0255\right]=0.5+3.0846=\mathbf{3.585}$ events·s⁻¹,
   versus $\mathbf{2.161}$ for the unmarked process of point 2 — a **66 % higher** firing rate produced purely by the 4M-unit second order. That gap is the whole point of the paper.
   *Correction note.* (3.8) as printed is wrong for $\alpha\neq 1$: the normalisation condition is $\mathbb{E}[g(X)]=1$, which requires dividing by $\mathbb{E}[X^{\alpha}]$, not by $\mathbb{E}X$. The paper's own equation (5.4) uses the correct $\mathbb{E}[X^{\alpha}]$ normalisation, so (3.8) is a typo. Check: for $X\sim\mathrm{Exp}(1)$ and $\alpha=0.5$, $\mathbb{E}[X^{0.5}]=\Gamma(1.5)=0.8862$, and $\mathbb{E}[g(X)]=1.12838\times0.8862=\mathbf{1.0000}$ ✓, whereas dividing by $\mathbb{E}X=1$ would give $\mathbb{E}[g(X)]=0.8862\neq1$.

4. **Stationarity condition and the two free goodness-of-fit tests.** The multivariate marked Hawkes process is well defined and stationary when the **spectral radius** of the branching matrix is below one:
   $$\max_i |\lambda_i| < 1,\qquad i=1,\dots,n \tag{3.10}$$
   where $\lambda_1,\dots,\lambda_n$ are the eigenvalues of $\nu$ (note the symbol clash with the intensities). The paper stresses that (3.10) evaluated at the estimated $\hat\nu$ is a **necessary but not sufficient** validation. Two further diagnostics come free with the point-process structure. First, the integrated intensity between consecutive events is standard exponential:
   $$\int_{t_{k-1}}^{t_k}\lambda(t,v\mid\mathcal{F}_t)\,dt\times dv \sim \mathrm{Exp}(1) \tag{3.12}$$
   Second, the **random time change theorem** (Daley & Vere-Jones, Prop. 7.4.VI(b)): if $\int_0^{\infty}\lambda_j(t,v_t\mid\mathcal{F}_t)=\infty$ for all $j$, then under
   $$(t,v)\mapsto(\Lambda(t,v),v) \tag{3.13}$$
   the marked point process becomes a **compound Poisson process** $\tilde N$ with unit ground rate and stationary mark distribution $f$.
   *Worked example (3.10).* Take the intra-asset up-block $\nu=\begin{pmatrix}0.50&0.31\\0.31&0.50\end{pmatrix}$. Its eigenvalues are $0.50\pm0.31$, i.e. $\mathbf{0.81}$ and $\mathbf{0.19}$, so the spectral radius is $0.81<1$ ✓ — deliberately set to the paper's own reported average (point 7).
   *Worked example (3.12).* Continue Series D1 with a third event at $t_3=0.7$ s, $v=2.5$M. Over the first inter-event interval $[0,0.3]$: $\Lambda_1=0.5(0.3)+0.8\,g(1)\!\left(1-e^{-0.6}\right)=0.15+0.8\times1.1284\times0.45119=0.15+0.40728=\mathbf{0.5573}$. Over $[0.3,0.7]$: $\Lambda_2=0.5(0.4)+0.8\left[1.1284\left(e^{-0.6}-e^{-1.4}\right)+2.2568\left(1-e^{-0.8}\right)\right]=0.2+0.8\left[0.3410+1.2427\right]=0.2+1.2670=\mathbf{1.4670}$. Both residuals are plausible $\mathrm{Exp}(1)$ draws — $P(\Lambda>0.5573)=e^{-0.5573}=0.573$ and $P(\Lambda>1.4670)=e^{-1.4670}=0.231$ — and their sample mean $ (0.5573+1.4670)/2=\mathbf{1.012}$ sits on the $\mathrm{Exp}(1)$ mean of 1 ✓, so this two-point sample gives no evidence against the fit.

5. **The first-line order-book model (the paper's central construction).** Rather than modelling the whole limit order book (Large's ten order types, Toke's two-agent model — both stated to be hard to extend to two dimensions with Epps/lead-lag effects), the paper models exactly **four** components: upward and downward jumps of the best ask and of the best bid.
   $$\text{Ask:}\ \begin{cases}\lambda_{a,+}(t)=\mu_{a,+}+\displaystyle\sum_{j=a+,\,b+}\nu_{a,+,j,+}\int_{(-\infty,t)\times\mathbb{R}}h_{a,+}(t-s)g_j(v)N_j(ds\times dv)\\[2mm] \lambda_{a,-}(t)=\mu_{a,-}+\displaystyle\sum_{j=a-,\,b-}\nu_{a,-,j,-}\int_{(-\infty,t)\times\mathbb{R}}h_{a,-}(t-s)g_j(v)N_j(ds\times dv)\end{cases}$$
   $$\text{Bid:}\ \begin{cases}\lambda_{b,+}(t)=\mu_{b,+}+\displaystyle\sum_{j=a+,\,b+}\nu_{b,+,j,+}\int_{(-\infty,t)\times\mathbb{R}}h_{b,+}(t-s)g_j(v)N_j(ds\times dv)\\[2mm] \lambda_{b,-}(t)=\mu_{b,-}+\displaystyle\sum_{j=a-,\,b-}\nu_{b,-,j,-}\int_{(-\infty,t)\times\mathbb{R}}h_{b,-}(t-s)g_j(v)N_j(ds\times dv)\end{cases} \tag{4.2}$$
   Two structural choices are imposed: **no interaction between upward and downward jumps**, $\nu_{\cdot,+,\cdot,-}=\nu_{\cdot,-,\cdot,+}=0$, on the reasoning that the ask side governs increases and the bid side decreases; and **upward jumps on bid and ask are coupled** (likewise downward), because an empirically unbounded spread is impossible, so one side must follow the other. The economic reading of the four channels: an upward jump on the **ask** is a buy market order that consumed the whole first limit; a downward jump on the **bid** is a sell market order that did the same; a downward jump on the **ask** and an upward jump on the **bid** are new **limit orders inside the spread**. Orders that do not move the price (partial fills, limit orders outside the quotes) are handled implicitly, as "no event". Cancellations — about **80 %** of all orders per SEC/AMF reports — are explicitly excluded because they are unobservable from the first line. Prices are then rebuilt from the counts:
   $$p_a(t)=p(0)+\left(N_{a,+}(t)-N_{a,-}(t)\right)p_{tick},\qquad p_b(t)=p(0)+\left(N_{b,+}(t)-N_{b,-}(t)\right)p_{tick} \tag{4.3}$$
   with $p_{tick}=10^{-5}$ for the paper's parities. Two counting conventions are contrasted: the simple marked counter
   $$N(t)=\sum_{i=1}^{n}\mathbf{1}_{\{t_i\le t;\,v(t_i)=x\}} \tag{4.4}$$
   whose value equals the unmarked count (only its *frequency* is volume-driven), and the **compound** counter
   $$N_g(t)=\sum_{i=1}^{N(t)}v(t_i),\qquad N(t)=\sum_{i=1}^{n}\mathbf{1}_{t_i\le t} \tag{4.5}$$
   which would make the price move by the traded volume itself. The paper keeps (4.4) because (4.5) is incompatible with (4.3) — "the price fluctuation is not exactly the sum of the exchanged volume" — and defers (4.5) to future work.
   *Worked example.* Shared toy calibration: $\mu_{a,+}=\mu_{b,+}=0.5$, $\mu_{a,-}=\mu_{b,-}=0.4$ s⁻¹, $\nu_{a+,a+}=\nu_{b+,b+}=0.50$, $\nu_{a+,b+}=\nu_{b+,a+}=0.31$, $\alpha_h=2$ s⁻¹, $g(x)=1.12838\sqrt{x}$, $p(0)=1.32000$, $p_{tick}=10^{-5}$. History: **ask-up** at $t=0.0$ with $v=1.0$M, **bid-up** at $t=0.3$ with $v=4.0$M. At $t=0.5$ s,
   $\lambda_{a,+}(0.5)=0.5+0.50\times(0.7358\times1.1284)+0.31\times(1.3406\times2.2568)=0.5+0.4151+0.9379=\mathbf{1.853}$ events·s⁻¹,
   while $\lambda_{a,-}(0.5)=\mu_{a,-}=\mathbf{0.400}$ exactly, because no downward event has occurred and $\nu_{\cdot,+,\cdot,-}=0$ severs the up-channel from the down-channel. Note the ask intensity rose **without the ask price moving** — the excitation came from the bid — which is precisely the effect the paper points out in its Figures 5–6. Price reconstruction: after $N_{a,+}=11$, $N_{a,-}=4$, $N_{b,+}=6$, $N_{b,-}=3$, (4.3) gives $p_a=1.32000+7\times10^{-5}=\mathbf{1.32007}$ and $p_b=1.32000+3\times10^{-5}=\mathbf{1.32003}$, hence $s=4\times10^{-5}$ = 4 ticks. Compound counter (4.5) with marks $1.0,4.0,2.5$M at $t=0,0.3,0.7$: $N(0.8)=\mathbf{3}$ but $N_g(0.8)=1.0+4.0+2.5=\mathbf{7.5}$M — the two conventions diverge immediately, which is why the choice matters.

6. **Multivariate (cross-asset) extension, and why it is kept sparse.** To reproduce the **Epps effect** (correlation decaying with frequency) and the **lead-lag effect**, the four-component model of (4.2) is replicated per asset and coupled across assets. The paper deliberately refuses a fully connected specification — "a very complicated model will be very difficult to calibrate, unstable, serve mainly for academics and not for practitioners" — and admits only two cross-asset channels: same-sign coupling (up-with-up, down-with-down) for positively dependent pairs, and opposite-sign coupling for negatively dependent pairs. Writing $\lambda_j(t)$ for the univariate intensities of (4.2), asset $i$ is
   $$\lambda^{(i)}_{a,+}(t)=\lambda_{a,+}(t)+\sum_{j\neq i=1}^{d}\nu^{(j)}_{a,+}\int_{(-\infty,t)\times\mathbb{R}}h_{a,+}(t-s)g^{(j)}_{a,+}(v)N^{(j)}_{a,+}(ds\times dv)+\sum_{j\neq i=1}^{d}\nu^{(j)}_{a,-}\int_{(-\infty,t)\times\mathbb{R}}h_{a,-}(t-s)g^{(j)}_{a,-}(v)N^{(j)}_{a,-}(ds\times dv)$$
   $$\lambda^{(i)}_{a,-}(t)=\lambda_{a,-}(t)+\sum_{j\neq i=1}^{d}\nu^{(j)}_{a,-}\int h_{a,-}(t-s)g^{(j)}_{a,-}(v)N^{(j)}_{a,-}(ds\times dv)+\sum_{j\neq i=1}^{d}\nu^{(j)}_{a,+}\int h_{a,+}(t-s)g^{(j)}_{a,+}(v)N^{(j)}_{a,+}(ds\times dv)$$
   $$\lambda^{(i)}_{b,+}(t)=\lambda_{b,+}(t)+\sum_{j\neq i=1}^{d}\nu^{(j)}_{b,+}\int h_{b,+}(t-s)g^{(j)}_{b,+}(v)N^{(j)}_{b,+}(ds\times dv)+\sum_{j\neq i=1}^{d}\nu^{(j)}_{b,-}\int h_{b,-}(t-s)g^{(j)}_{b,+}(v)N^{(j)}_{b,-}(ds\times dv)$$
   $$\lambda^{(i)}_{b,-}(t)=\lambda_{b,-}(t)+\sum_{j\neq i=1}^{d}\nu^{(j)}_{b,-}\int h_{b,-}(t-s)g^{(j)}_{b,-}(v)N^{(j)}_{b,-}(ds\times dv)+\sum_{j\neq i=1}^{d}\nu^{(j)}_{b,+}\int h_{b,+}(t-s)g^{(j)}_{b,+}(v)N^{(j)}_{b,+}(ds\times dv) \tag{4.6}$$
   So each intensity has three parts: the univariate self/cross-side term, a positive-dependence cross-asset term, and a negative-dependence cross-asset term. Because all branching coefficients are constrained to be $\ge 0$, negative dependence can *only* be expressed by wiring up-jumps of asset $i$ to down-jumps of asset $j$. The paper's **Table 1** enumerates the permitted interactions as an $8\times8$ pattern for $d=2$ (4 components per asset), with exactly **four** live entries per row — self, same-sign other side, and the two same-side channels of the other asset. Its stated prediction: for EUR/USD versus EUR/GBP (or USD/JPY versus GBP/JPY) the up-jump ask coefficient should be **positive** and the down-jump one **near zero**, whereas for EUR/USD versus USD/CHF the signs reverse.
   *Worked example.* Continue point 5 (asset 1 = EUR/USD, $\lambda_{a,+}(0.5)=1.853$) and add asset 2 = EUR/GBP with an **ask-up** at $t=0.4$ s, $v=2.0$M, $\nu^{(2)}_{a,+}=0.20$, and an **ask-down** at $t=0.45$ s, $v=1.0$M, $\nu^{(2)}_{a,-}=0.02$ (near zero, as the paper predicts for a positively co-moving pair). Then $h(0.1)=2e^{-0.2}=1.6375$, $g(2.0)=1.5958$, contribution $0.20\times1.6375\times1.5958=0.5226$; and $h(0.05)=2e^{-0.1}=1.8097$, $g(1.0)=1.1284$, contribution $0.02\times1.8097\times1.1284=0.0408$. Total
   $\lambda^{(1)}_{a,+}(0.5)=1.8530+0.5226+0.0408=\mathbf{2.416}$ events·s⁻¹,
   a **+30.4 %** lift over the single-asset value. That lift, decaying at rate $\alpha_h$, is the mechanism that generates cross-asset correlation at coarse sampling and lets it vanish at fine sampling — the Epps effect of point 9.

7. **Estimation: maximum likelihood, the mark law, the impact function, and the reported stability result.** The parameter set is $\Theta=\{f,g,h,\nu,\mu\}$ over the window $I=[T^-,T^+]$ containing all arrival times. The likelihood and compensator are
   $$L(\{t_i,v_i\};\Theta)=\prod_{j=1}^{d}\int_{I\times\mathbb{R}}\lambda_j(t,v(t)\mid\mathcal{F}_t)\,N_j(dt\times dv)\,\exp\!\left(-\Lambda_j(T^+)\right) \tag{5.1}$$
   $$\Lambda_j(T)=\int_{-\infty}^{T}\lambda_j(t,v\mid\mathcal{F}_t)\,dt\times dv,\qquad j\in\{1,\dots,d\} \tag{5.2}$$
   with the discretised log-likelihood actually maximised
   $$\log L(\{t_i,v_i\};\Theta)=\sum_{j=1}^{d}\sum_{k=1}^{N}\log\lambda_j\!\left(t_k,v(t_k)\mid\mathcal{F}_{t_k}\right)-\sum_{j=1}^{d}\Lambda_j(T^+) \tag{5.3}$$
   by "a classical optimization algorithm". (Bacry et al.'s alternative — fit $\Theta$ empirically, then minimise MSE between the empirical signature plot and its model estimate — is noted but not used.) To normalise $g$ the mark law must be known, so the paper fits the empirical cumulative volume distributions $P(V>x)$ against a **Gaussian**
   $$f_G(x)=\frac{1}{\sigma\sqrt{2\pi}}\exp\!\left(-\frac{(x-\mu)^2}{2\sigma^2}\right)$$
   and an **exponential**
   $$f_E(x)\propto\exp(-\beta x),\ \beta>0$$
   The Gaussian "gives the worst fitting, tails are not described correctly, they vanish too quickly"; the exponential "provides a very good fit". Combining the exponential mark law $\beta e^{-\beta x}$ with a power-law impact $x^{\alpha}$ and the normalisation $\mathbb{E}[g(X)]=1$ yields the paper's working impact function
   $$g(x)=\frac{\beta^{\alpha}}{\Gamma(\alpha+1)}x^{\alpha} \tag{5.4}$$
   justified by Lillo–Farmer–Mantegna's empirical power-law price impact and by Almgren's power-law execution-cost work. Deci-second series are built with the **tick (previous-tick) estimator**
   $$t=\arg\max_{t_i}\{t_i\le t\},\qquad i=1,2,\dots \tag{5.5}$$
   on the regular grid $\Lambda_t=\{0.10\text{ s},0.20\text{ s},\dots\}$. To stop bid and ask diverging in simulation, two identification constraints are imposed by hand: $\mu^{(i)}_{a+}=\mu^{(i)}_{b+}$ and $\mu^{(i)}_{a-}=\mu^{(i)}_{b-}$. **Headline calibration result:** across the weekly blocks of EUR/USD and EUR/GBP the estimated spectral radius lies between **0.71 and 0.84**, averaging **0.81** — so (3.10) holds and the process is well defined.
   *Worked example (5.4).* $\beta=1$, $\alpha=0.5$, $\Gamma(1.5)=0.886227$ give $g(x)=1.12838\sqrt{x}$; $g(1)=1.1284$, $g(2)=1.5958$, $g(4)=2.2568$, $g(2.5)=1.7841$. Normalisation check: $\mathbb{E}[g(X)]=1.12838\times\Gamma(1.5)=\mathbf{1.0000}$ ✓.
   *Worked example (5.3), Series D1.* $\mu=0.5$, $\alpha_h=2$, marks $1.0,4.0,2.5$M at $t=0.0,0.3,0.7$, window $I=[0,1]$. At $\nu=0.8$: $\lambda(t_1)=0.5$, $\lambda(t_2)=1.4908$, $\lambda(t_3)=2.5677$, so $\sum\log\lambda=-0.6931+0.3993+0.9430=0.6492$; and $\Lambda(1)=0.5+0.8\left[1.1284(1-e^{-2})+2.2568(1-e^{-1.4})+1.7841(1-e^{-0.6})\right]=0.5+0.8\left[0.9757+1.7002+0.8050\right]=0.5+2.7847=3.2847$; hence $\log L=0.6492-3.2847=\mathbf{-2.636}$. Re-evaluating at $\nu=0.5$: $\sum\log\lambda=-0.6931+0.1127+0.5835=0.0030$, $\Lambda(1)=0.5+0.5\times3.4809=2.2405$, $\log L=\mathbf{-2.237}$. Since $-2.237>-2.636$, the optimiser prefers $\nu=0.5$ over $\nu=0.8$ on this three-event sample — a concrete illustration of how (5.3) trades the $\sum\log\lambda$ reward for excitation against the $\Lambda$ penalty for it.
   *Worked example (5.5).* Grid points $\{0.10,0.20,0.30\}$ s with ticks recorded at $0.07,0.13,0.19,0.26$ s: the interpolated series takes the tick at $0.07$ for grid $0.10$, at $0.19$ for grid $0.20$, and at $0.26$ for grid $0.30$.

8. **Data and the paper's most interesting empirical by-product.** The study uses two FX parities recorded in **milliseconds** from **January 30, 2012 00:00:00 to March 09, 2012 21:59:00** (one month and one week): **3,352,809 trades in EUR/USD** and **2,178,009 in EUR/GBP**, cleaned by the classical Dacorogna et al. procedure. Because the sample is too large to fit in one pass, it is cut into weekly blocks — **5 weeks per parity** — and results averaged. Figure 3 (volume variation against duration, EUR/USD and EUR/GBP, 30-01-2012 to 10-03-2012, variations in millions of USD) shows that a **big volume variation goes with a short duration**, the empirical motivation for marking. Figure 4 then plots $P(V>x)$ separately for the four channels, and reports a striking near-coincidence: the ask-volume distribution conditional on an **upward** jump nearly equals the bid-volume distribution conditional on a **downward** jump, and the ask-volume-on-downward nearly equals the bid-volume-on-upward. The reading is mechanical: the first pair are the two **market-order** channels (a buy or sell market order sweeping the whole first limit), the second pair the two **limit-order-inside-the-quotes** channels. The paper also observes that the **quantity offered by a new limit order inside the quotes exceeds the quantity offered by the "old" limit that becomes the new best quote**. Figures 5–6 show realised marked intensities for 2000 deci-second points of EUR/USD (3 min 23 s, 30-01-2012 00:12:53 → 00:16:32) and confirm that an intensity can move while its own price stays put, via the bid↔ask coupling.
   *Worked example (quantifying "tails vanish too quickly").* With the fitted exponential $\beta=1$ (volumes in millions), $P(V>3)=e^{-3}=\mathbf{4.98\,\%}$, while a Gaussian with $\mu=1,\sigma=1$ gives $P(V>3)=1-\Phi(2)=\mathbf{2.28\,\%}$ — the Gaussian understates by a factor **2.2**. At $x=5$: exponential $e^{-5}=6.74\times10^{-3}$ versus Gaussian $1-\Phi(4)=3.17\times10^{-5}$, a factor of **213**. This is exactly the failure mode the paper reports, and it matters because large volumes are the ones that drive the intensity through $g$.

9. **Stylized-fact validation.** Writing $X(t)=\log p(t)$, the **signature plot** (Andersen et al.) measures realised volatility per unit time against sampling frequency,
   $$V_X(\tau)=\frac{1}{T}\sum_{n=0}^{\lfloor T/\tau\rfloor}\left(X((n+1)\tau)-X(n\tau)\right)^2 \tag{6.1}$$
   which decreases in power law as the lag $\tau$ grows: at very high frequency prices are discontinuous and jumpy, inflating measured volatility; at coarse scale fluctuations smooth out toward an equilibrium value. Figure 8 (EUR/USD mid-price, weekly averages, $\tau$ from 0 to 100 s) shows empirical, simulated and power-law-fit curves declining from roughly **0.06 to 0.02**. The **Epps effect** measures cross-asset correlation against frequency,
   $$\rho_{1,2}(\tau)=\frac{Co_{1,2}(\tau)}{\sqrt{V_{X_1}(\tau)V_{X_2}(\tau)}} \tag{6.2}$$
   $$Co_{1,2}(\tau)=\frac{1}{T}\sum_{n=0}^{\lfloor T/\tau\rfloor}\left(X_1((n+1)\tau)-X_1(n\tau)\right)\left(X_2((n+1)\tau)-X_2(n\tau)\right)$$
   with correlation vanishing as frequency increases, because even for two very liquid assets there is always a lag. Figure 9 (EUR/USD versus EUR/GBP, empirical in black, simulation in red, power-law fit, $\tau$ from 0 to 100 s) shows the measure rising from ~**0.000 to ~0.015**. The paper's claim is that the *simulated* curves track the empirical ones on both plots, which is its main evidence that the model is realistic.
   *Worked example (6.1), Series S1.* Log-price increments over four deci-second steps ($\tau=0.1$ s, $T=0.4$ s): $+2,-1,+2,-2$ in units of $10^{-5}$. At $\tau=0.1$: $\sum r^2=(4+1+4+4)\times10^{-10}=1.3\times10^{-9}$, so $V_X(0.1)=1.3\times10^{-9}/0.4=\mathbf{3.25\times10^{-9}}$ s⁻¹. At $\tau=0.2$ the aggregated increments are $+1$ and $0$: $\sum r^2=1\times10^{-10}$ and $V_X(0.2)=\mathbf{2.5\times10^{-10}}$ s⁻¹ — a **13-fold** drop for a doubling of $\tau$, i.e. the downward-sloping signature plot.
   *Worked example (6.2), Series E1/E2.* Asset 1 increments $+2,+1,-1,+2$ and asset 2 increments $0,+2,+1,-1$ (asset 2 lags asset 1 by one deci-second), units $10^{-5}$, $T=0.4$ s. At $\tau=0.1$: $Co=\frac{1}{0.4}\left[0-2-1-2\right]\times10^{-10}=-2.5\times10^{-10}$, $V_{X_1}=2.5\times10^{-9}$, $V_{X_2}=1.5\times10^{-9}$, so $\rho(0.1)=-2.5\times10^{-10}/\sqrt{3.75\times10^{-18}}=\mathbf{-0.129}$. At $\tau=0.2$ the aggregates are $(+3,+1)$ and $(+2,0)$: $Co=\frac{1}{0.4}\left[6+0\right]\times10^{-10}=1.5\times10^{-9}$, $V_{X_1}=2.5\times10^{-9}$, $V_{X_2}=1.0\times10^{-9}$, so $\rho(0.2)=1.5\times10^{-9}/1.5811\times10^{-9}=\mathbf{+0.949}$. Correlation goes from essentially nil at 100 ms to 0.95 at 200 ms purely because of a one-step lag — the Epps effect in three lines of arithmetic.

10. **Application to cost-aware stress testing and forecasting, and the paper's own limitations.** The stated payoff is that simulating bid and ask *jointly* delivers the spread, and therefore a realistic **stress test for high-frequency strategies**: "it is not very complicated to find some 'rules' to deduce the next market move, but if one includes the broker fees, market impact and bid-ask spread, the detected gains probabilities will reduce to zero." Broker fees are a percentage of value held. **Market impact** is modelled by walking the book: a buy of $k=\sum_{i=1}^{n}k_i$ units filled across $n$ limits costs
   $$V=\sum_i k_i\left(p_a+x_i p_{tick}\right)$$
   where $x_i$ measures the distance in ticks from the best price, $x_1=0$, $x_i\in\mathbb{N}^*$, so the impact component of the cost is
   $$\sum_{i=1}^{n}k_i x_i p_{tick}$$
   and, assuming a liquid market where consecutive limits sit one tick apart, the paper simplifies this to $\sum_{i=1}^{n}k_i p_{tick}$. The **spread cost** of a $k$-share round turn closed at $t+\delta t$ is $k\,s(t+\delta t)$. **Forecasting** uses Vere-Jones' next-event probability
   $$P(\tau^*>\tau)=\exp\!\left(-\int_0^{\tau}\int_{\mathbb{R}}\lambda(s,v\mid\mathcal{F}_s)\,dv\,ds\right) \tag{7.1}$$
   evaluated for all 4 intensities of (4.2) (or all $4d$ of (4.6)); the history must be rolled forward from $t+\delta t$ to $t+\tau$, generating each intermediate mark from
   $$f(v)=\frac{\lambda(t+\delta t,v\mid\mathcal{F}_{t+\delta t})}{\int_{\mathbb{R}}\lambda(t+\delta t,v\mid\mathcal{F}_{t+\delta t})\,dv}$$
   Knowing *which side* jumps next, rather than only the mid-price direction, additionally yields the **expected spread**, which is what tells you whether the trade can be profitable. **Limitations the paper itself states:** cancellations (~80 % of orders) are outside the model; only one broker's book is visible, which is why the analysis is restricted to best bid/ask on FX; the available volume at deeper limits is unknown, so for simulation it is simply drawn from an exponential law, and "statistical properties of the exchanged volume are very rich and need an extensive study to build a robust model"; the compound formulation (4.5) is left for future work; and extending to VaR or Monte-Carlo option pricing is stated only as a prospect.
    *Worked example (market impact).* $p_a=1.32011$, $p_{tick}=10^{-5}$, three consecutive limits of 100,000 EUR each, order $k=300{,}000$: cost $=100000(1.32011+1.32012+1.32013)=396{,}036$ USD versus $300000\times1.32011=396{,}033$ USD at the touch, so impact $=\mathbf{3.00}$ USD $=10^{-5}\times100000\times(0+1+2)$ ✓. Add the spread: $k\,s=300000\times8\times10^{-5}=\mathbf{24.00}$ USD.
    *Worked example (7.1), Series D1 at $t=1.0$ s.* $\lambda(1.0)=0.5+0.8\left[1.1284\cdot 2e^{-2}+2.2568\cdot 2e^{-1.4}+1.7841\cdot 2e^{-0.6}\right]=0.5+0.8\left[0.3054+1.1130+1.9583\right]=\mathbf{3.201}$ events·s⁻¹, and since the excitation decays as $e^{-2u}$, $\Lambda(\tau)=0.5\tau+1.35069\left(1-e^{-2\tau}\right)$. At $\tau=0.1$ s: $\Lambda=0.05+0.2448=0.2948$, so $P(\tau^*>0.1)=e^{-0.2948}=\mathbf{0.745}$, i.e. a **25.5 %** chance of a new event within 100 ms. At $\tau=0.5$ s: $\Lambda=0.25+0.8538=1.1038$, $P(\tau^*>0.5)=e^{-1.1038}=\mathbf{0.332}$, i.e. **66.8 %** within 500 ms.

## 3. Key Importance Topics

### Volume as a mark: excitation that scales with size, not just with timing

The paper's single organising idea is that market "excitation" differs between low-volume and high-volume periods, so the arrival intensity must depend on **how much** traded and not only on **when**. Formally the unmarked kernel sum $\sum_k h_i(t-t_k)$ of (3.2) is replaced by the mark-weighted sum $\sum_k h_i(t-t_k)g_j(v_k)$ of (3.9). Because $g$ is normalised so that $\mathbb{E}[g(V)]=1$, the branching coefficients keep their "mean offspring" meaning, and the marks act as a mean-one multiplicative random weight on each event's contribution. Empirically the justification is Figure 3: on both EUR/USD and EUR/GBP, large volume variations coincide with short durations.

**Why it matters:** this is the difference between a model that treats a 1M and a 4M order identically and one where the 4M order raises the next-event rate by a factor $g(4)/g(1)=2.2568/1.1284=\mathbf{2.0}$. In the worked example of Section 2 point 3 the marked intensity is **3.585** versus **2.161** events·s⁻¹ unmarked — a **66 %** difference in predicted arrival rate from the same timestamps. Any downstream quantity built on the intensity (execution scheduling, short-horizon direction, expected spread) inherits that difference, so the mark is not a refinement but a first-order term.

### Modelling the first line jointly, so the spread is an output rather than an assumption

Almost all comparable work models a single price series, $p(t)=N^+(t)-N^-(t)$, and so has to *assume* a spread when costs are computed. This paper models four counting processes — ask-up, ask-down, bid-up, bid-down — and rebuilds both prices from (4.3), so the spread $s(t)=p_a(t)-p_b(t)$ falls out of the simulation. The structural choices that make this tractable are (i) severing up-channels from down-channels within an asset ($\nu_{\cdot,+,\cdot,-}=0$), on the reasoning that the ask side drives increases and the bid side decreases, and (ii) coupling up-jumps of bid and ask (likewise down), because a spread cannot diverge in practice. Each of the four channels also maps onto a real order type: ask-up and bid-down are **market orders** that consumed a full limit; ask-down and bid-up are **limit orders posted inside the quotes**.

**Why it matters:** the paper's own verdict is blunt — profitable-looking rules "reduce to zero" once fees, impact and spread are charged, and the round-turn spread cost is $k\,s$, which for $k=300{,}000$ and an 8-tick spread is **24.00 USD** on a position whose 1-tick correct prediction is worth **3.00 USD**. A model that emits the spread endogenously is therefore the difference between a **backtest** and a **stress test**. It is also the reason the paper's four-channel decomposition is more useful than its stylized-fact results: the channel labels tell you *which* order type is arriving.

### The empirical volume-distribution symmetry between market and limit orders

The paper's most quotable empirical finding is in Figure 4. Fitting $P(V>x)$ per channel on both parities, the ask-volume distribution conditional on an **upward** jump nearly coincides with the bid-volume distribution conditional on a **downward** jump, and the ask-on-downward nearly coincides with the bid-on-upward. Two distributions, not four. The mechanical explanation is that the first pair are both market orders sweeping the touch and the second pair are both limit orders posted inside the quotes. A second, quantitative observation: the volume offered by a **new limit order inside the quotes exceeds** the volume that had been sitting on the old limit which becomes the new best quote. On distributional shape, the exponential $f_E(x)\propto e^{-\beta x}$ fits well and the Gaussian fails in the tails.

**Why it matters:** it collapses the four mark distributions the model nominally needs into **two**, halving the mark-estimation burden, and it gives a testable microstructure statement that is independent of the Hawkes machinery — anyone with first-line data can check it. It also disciplines the Gaussian-versus-exponential choice with a number: at $x=5$ mean-volumes the Gaussian underestimates the exceedance probability by a factor of **213**, and since the intensity is driven through $g(v)$, a mark law that kills the tail kills exactly the events that matter.

### Choice and normalisation of the impact function

The impact function $g$ is where volume enters. The paper takes an exponential mark law and a power-law impact, and imposes $\int g(v)f(v)dv=1$, arriving at $g(x)=\beta^{\alpha}x^{\alpha}/\Gamma(\alpha+1)$ (5.4). The power law is chosen because empirical price impact is a power law (Lillo–Farmer–Mantegna's master curve; Almgren's execution-cost work). The normalisation is described as being "mainly for a comprehensive way": it makes the branching coefficients appear explicitly, so stability can be read off the eigenvalues of $\nu$ alone.

**Why it matters:** the normalisation is what keeps the stability condition (3.10) interpretable — without $\mathbb{E}[g(V)]=1$ the mean offspring count per event would be $\nu\,\mathbb{E}[g(V)]$ and the spectral-radius test would be reading the wrong matrix. It also concentrates all the volume nonlinearity into a **single exponent** $\alpha$: $\alpha<1$ is concave (diminishing excitation from ever-larger orders), $\alpha=1$ linear, $\alpha>1$ convex. That one number governs how violently the model reacts to a block trade, which makes it the most consequential — and, in this paper, the **least reported** — parameter.

### Stationarity as a diagnostic, and the identification constraints needed to make simulation behave

Stability requires the spectral radius of $\nu$ below 1 (3.10), plus a finite-mean kernel (3.11). The paper reports estimated radii of **0.71–0.84** per week, averaging **0.81**, and is careful to call this necessary but not sufficient. Two further free diagnostics are available: inter-event compensator increments should be $\mathrm{Exp}(1)$ (3.12), and the random time change (3.13) should turn the process into a unit-rate compound Poisson process. Separately, because nothing in (4.2) bounds the spread, the authors impose $\mu_{a+}=\mu_{b+}$ and $\mu_{a-}=\mu_{b-}$ by hand to stop bid and ask drifting apart in simulation.

**Why it matters:** 0.81 is not a comfortable number. The mean number of events triggered per exogenous event is $1/(1-\rho)$, so $\rho=0.81$ implies **5.26** events per exogenous arrival, and the count dispersion index is $1/(1-\rho)^2=\mathbf{27.7}$ — a Hawkes-calibrated market is nearly 28 times more bursty than a Poisson one with the same mean rate. The weekly spread of 0.71–0.84 maps to amplification factors of **3.45 to 6.25**, so the radius itself is a regime variable. And the hand-imposed $\mu$ equalities are a warning sign: they are a symptom of a missing stabilising mechanism, not a modelling choice (see Section 5, Idea 2).

### Stylized-fact validation and the cost-aware forecast loop

The model is judged by whether simulations reproduce two frequency-dependent facts: the **signature plot** (6.1), volatility per unit time falling in power law as $\tau$ grows, plotted from ~0.06 down to ~0.02 over $\tau\in[0,100]$ s; and the **Epps effect** (6.2), cross-asset correlation rising with $\tau$ from ~0.000 to ~0.015 over the same range. Simulated curves are reported to track empirical ones on both. On top of this, Section 7 builds a forecast: evaluate (7.1) for each of the $4d$ intensities, roll the history forward generating marks from $f(v)=\lambda/\int\lambda\,dv$, and read off both the next likely side/direction and the expected spread.

**Why it matters:** the two stylized facts are *frequency-dependent*, which no static-correlation or i.i.d.-return model reproduces; passing both is meaningful evidence that the excitation structure and the cross-asset coupling are doing real work rather than curve-fitting a single moment. The forecast loop matters because it is the only part of the paper that turns the model into a decision: knowing $P(\text{next jump is ask-up})$ *and* the expected spread simultaneously is exactly the information needed to decide whether to take liquidity or post. That said, this is also the paper's thinnest section — no accuracy statistics, no out-of-sample test, and (as Section 4 notes) the stated $\tau$-maximisation criterion is degenerate as written.

## 4. Algorithm Logic — Step-by-Step

All worked examples in this section share one **toy calibration**, so the reader can chain them:

| Quantity | Value | Source |
|---|---|---|
| Tick size $p_{tick}$ | $10^{-5}$ | paper's value for its FX parities |
| Mark (volume) law | $\mathrm{Exp}(\beta)$, $\beta=1$, volumes in millions of USD | paper's fitted law, illustrative rate |
| Impact function | $g(x)=\beta^{\alpha}x^{\alpha}/\Gamma(\alpha+1)$ with $\alpha=0.5$, i.e. $g(x)=1.12838\sqrt{x}$ | eq. (5.4), illustrative exponent |
| Decay kernel | $h(u)=\alpha_h e^{-\alpha_h u}$, $\alpha_h=2$ s⁻¹ | eq. (3.5), illustrative rate |
| Baselines | $\mu_{a,+}=\mu_{b,+}=0.5$, $\mu_{a,-}=\mu_{b,-}=0.4$ s⁻¹ | paper's constraint $\mu_{a\pm}=\mu_{b\pm}$ |
| Intra-asset branching (up block) | $\nu_{a+,a+}=\nu_{b+,b+}=0.50$, $\nu_{a+,b+}=\nu_{b+,a+}=0.31$ | eigenvalues 0.81 / 0.19, matching the paper's average radius 0.81 |
| Cross-asset branching | $\nu^{(2)}_{a,+}=0.20$, $\nu^{(2)}_{a,-}=0.02$ | paper's predicted sign pattern for a co-moving pair |
| Starting price | $p(0)=1.32000$ | Figures 5–7 price range |

Reference event history (asset 1 = EUR/USD): **ask-up** at $t=0.0$ s, $v=1.0$M; **bid-up** at $t=0.3$ s, $v=4.0$M; **ask-up** at $t=0.7$ s, $v=2.5$M. Asset 2 = EUR/GBP: **ask-up** at $t=0.4$ s, $v=2.0$M; **ask-down** at $t=0.45$ s, $v=1.0$M. "Series D1" denotes the simplified one-component version ($\mu=0.5$, $\nu=0.8$, all three asset-1 events in one channel), used where a single-channel illustration is clearer.

### Algorithm A — The four-channel marked Hawkes model of the first line

**Goal:** given the history of price-moving orders on the best bid and best ask, compute the instantaneous arrival rate of each of the four possible next moves, and rebuild both quoted prices and the spread from the resulting event counts.

**Inputs:** the event history $\{(t_k, \text{channel}_k, v_k)\}$ where channel $\in\{a+,a-,b+,b-\}$ and $v_k$ is the order volume; parameters $\mu_{a\pm},\mu_{b\pm}$, branching coefficients $\nu$, kernel rate $\alpha_h$, impact exponent $\alpha$, mark rate $\beta$, tick size $p_{tick}$, and the opening price $p(0)$.
**Outputs:** the four intensities $\lambda_{a,+},\lambda_{a,-},\lambda_{b,+},\lambda_{b,-}$ at any query time $t$; the counts $N_{a,\pm},N_{b,\pm}$; the reconstructed $p_a(t)$, $p_b(t)$ and spread $s(t)$.

**Steps:**

1. **Classify each observed event into one of four channels.** This is the step that replaces the usual single price series. A buy market order that consumes the entire volume at the best ask makes the ask jump **up** ($a+$); a sell market order that consumes the whole best bid makes the bid jump **down** ($b-$); a new limit buy order posted inside the spread lifts the bid ($b+$); a new limit sell order posted inside the spread lowers the ask ($a-$). Orders that do not move a quote — partial fills, limit orders outside the spread — are deliberately *not* recorded; they are absorbed as "no event occurred". Cancellations are not observable from the first line and are excluded.
2. **Attach the volume as a mark.** Every recorded event carries $v_k$, the volume added or removed. The paper argues this is always well defined here, since "a new price fluctuation is necessarily associated to a new quantity of volume added or removed".
3. **Map each mark through the impact function.** Compute $g(v_k)=\beta^{\alpha}v_k^{\alpha}/\Gamma(\alpha+1)$. The normalisation $\mathbb{E}[g(V)]=1$ means $g$ is a *mean-one* weight: an average-sized order behaves exactly like an unmarked event, a large order counts for more, a small one for less.
4. **Sum the decayed, mark-weighted history into each intensity.** For each channel $i$, add its baseline $\mu_i$ to the excitation from every permitted source channel $j$:
   $$\lambda_i(t,v\mid\mathcal{F}_t)=\mu_i+\sum_j \nu_{ij}\sum_{k\,\mid\, t^{(j)}_k<t} h_i\!\left(t-t^{(j)}_k\right)g_j\!\left(v_k\right)$$
   using $h_i(u)=\alpha_h e^{-\alpha_h u}$. The permitted sources are fixed by the model's two structural rules: **up-channels feed only up-channels, down-channels only down-channels** ($\nu_{\cdot,+,\cdot,-}=0$), and within a sign the ask and bid channels feed **each other** as well as themselves.
5. **Reconstruct the quotes from the counts.** $p_a(t)=p(0)+\left(N_{a,+}(t)-N_{a,-}(t)\right)p_{tick}$ and $p_b(t)=p(0)+\left(N_{b,+}(t)-N_{b,-}(t)\right)p_{tick}$; the spread is their difference. Note that under the simple counting convention (4.4) the volume affects only the *rate* of jumps, never the *size* of a jump, which is always exactly one tick. The compound convention (4.5), $N_g(t)=\sum_{i\le N(t)}v(t_i)$, would let volume set the jump size, but the paper rejects it as incompatible with (4.3).

**Worked example (end-to-end).** Query time $t=0.5$ s, using the toy calibration and asset-1 history above (two events have occurred by then: ask-up at 0.0 with 1.0M, bid-up at 0.3 with 4.0M).

- Step 1–2 give the history $\{(0.0, a+, 1.0),\ (0.3, b+, 4.0)\}$.
- Step 3: $g(1.0)=1.12838\times1=\mathbf{1.1284}$; $g(4.0)=1.12838\times2=\mathbf{2.2568}$.
- Step 4, kernel values: $h(0.5-0.0)=2e^{-1.0}=\mathbf{0.7358}$; $h(0.5-0.3)=2e^{-0.4}=\mathbf{1.3406}$. Weighted terms: $0.7358\times1.1284=\mathbf{0.8302}$ (from the ask-up), $1.3406\times2.2568=\mathbf{3.0255}$ (from the bid-up).
- Step 4, the four intensities:
  $\lambda_{a,+}(0.5)=0.5+0.50\times0.8302+0.31\times3.0255=0.5+0.4151+0.9379=\mathbf{1.853}$ s⁻¹
  $\lambda_{b,+}(0.5)=0.5+0.31\times0.8302+0.50\times3.0255=0.5+0.2574+1.5128=\mathbf{2.270}$ s⁻¹
  $\lambda_{a,-}(0.5)=\mu_{a,-}=\mathbf{0.400}$ s⁻¹ and $\lambda_{b,-}(0.5)=\mu_{b,-}=\mathbf{0.400}$ s⁻¹ — untouched, because no down-event has occurred and the up-block cannot feed them.
- Interpretation: the total rate is $1.853+2.270+0.400+0.400=\mathbf{4.923}$ s⁻¹, so the expected wait to the next quote change is $1/4.923=\mathbf{203}$ ms, and the upward channels now carry $(1.853+2.270)/4.923=\mathbf{83.8\,\%}$ of the total rate. Note that $\lambda_{a,+}$ was lifted from 0.5 to 1.853 with **no ask-price movement at all** — the 4M bid-side order did it through $\nu_{a+,b+}=0.31$. This is exactly the effect the paper highlights in its Figures 5–6.
- Step 5: suppose the run continues to $N_{a,+}=11$, $N_{a,-}=4$, $N_{b,+}=6$, $N_{b,-}=3$. Then $p_a=1.32000+(11-4)\times10^{-5}=\mathbf{1.32007}$, $p_b=1.32000+(6-3)\times10^{-5}=\mathbf{1.32003}$, $s=4\times10^{-5}$ = **4 ticks**. Compound alternative (4.5) on the three asset-1 marks: $N(0.8)=3$ but $N_g(0.8)=1.0+4.0+2.5=\mathbf{7.5}$M.

*Issue found.* In (3.6) the mark space is $\mathbb{R}_+$, but in (4.2) and (4.6) the integrals run over $\mathbb{R}$. With the power-law $g(x)=x^{\alpha}$ and non-integer $\alpha$, a negative mark makes $g$ complex, so signed volume variations (which is what Figure 3 actually plots) cannot be fed to (4.2) as written. The consistent reading is that marks are the absolute volumes on $\mathbb{R}_+$ and the *sign* is carried by the channel label, not by the mark.

### Algorithm B — Cross-asset (multivariate) extension

**Goal:** couple several assets' first-line models so the simulation reproduces cross-asset dependence that varies with sampling frequency (the Epps effect) and lead-lag structure, without exploding the parameter count.

**Inputs:** per-asset histories and per-asset parameter blocks from Algorithm A; cross-asset branching coefficients $\nu^{(j)}_{a,\pm},\nu^{(j)}_{b,\pm}$ for each pair $i\neq j$; the sparsity pattern of the paper's Table 1.
**Outputs:** the $4d$ intensities $\lambda^{(i)}_{a,\pm},\lambda^{(i)}_{b,\pm}$ for $i=1,\dots,d$.

**Steps:**

1. **Start from the single-asset intensity.** For asset $i$, the first term of each of its four intensities is exactly the univariate $\lambda_{a,+}(t)$, $\lambda_{a,-}(t)$, $\lambda_{b,+}(t)$, $\lambda_{b,-}(t)$ computed by Algorithm A on asset $i$'s own history.
2. **Add a same-sign cross-asset term (positive dependence).** For every other asset $j\neq i$, add $\nu^{(j)}_{a,+}\sum_k h_{a,+}(t-t_k)g^{(j)}_{a,+}(v_k)$ over asset $j$'s ask-up events into $\lambda^{(i)}_{a,+}$, and similarly for the other three channels. This is the channel that transmits "EUR/USD ticked up, so EUR/GBP is more likely to tick up".
3. **Add an opposite-sign cross-asset term (negative dependence).** Because all branching coefficients are constrained non-negative, a negatively correlated pair can only be represented by wiring asset $j$'s **down**-events into asset $i$'s **up**-intensity. Hence $\lambda^{(i)}_{a,+}$ also receives $\nu^{(j)}_{a,-}\sum_k h_{a,-}(t-t_k)g^{(j)}_{a,-}(v_k)$.
4. **Apply the Table 1 sparsity pattern.** For $d=2$ the branching structure is an $8\times8$ matrix (4 channels × 2 assets) with exactly **four** live entries per row: the channel itself (self-excitation), the same-sign channel on the other side of the *same* asset, and the two same-side channels of the *other* asset. Everything else is zero. The upper-left and lower-right quadrants are the two univariate models; the off-diagonal quadrants carry the cross-asset coupling.
5. **Set the sign pattern from the economics.** For pairs that co-move (EUR/USD with EUR/GBP; USD/JPY with GBP/JPY) the same-sign coefficients should estimate positive and the opposite-sign ones near zero. For pairs that move against each other (EUR/USD with USD/CHF) the pattern reverses.

**Worked example (end-to-end).** Compute $\lambda^{(1)}_{a,+}(0.5)$ for EUR/USD given the EUR/GBP history.

- Step 1: from Algorithm A, $\lambda_{a,+}(0.5)=\mathbf{1.8530}$ s⁻¹.
- Step 2: EUR/GBP ask-up at $t=0.4$, $v=2.0$M. $h(0.5-0.4)=2e^{-0.2}=1.6375$; $g(2.0)=1.12838\times\sqrt{2}=1.5958$; contribution $=0.20\times1.6375\times1.5958=\mathbf{0.5226}$.
- Step 3: EUR/GBP ask-down at $t=0.45$, $v=1.0$M. $h(0.5-0.45)=2e^{-0.1}=1.8097$; $g(1.0)=1.1284$; contribution $=0.02\times1.8097\times1.1284=\mathbf{0.0408}$ — small, as intended for a positively co-moving pair.
- Step 4–5 total: $\lambda^{(1)}_{a,+}(0.5)=1.8530+0.5226+0.0408=\mathbf{2.416}$ s⁻¹, a **+30.4 %** lift over the single-asset value.
- Why this produces the Epps effect: the lift decays as $e^{-\alpha_h u}$ with $\alpha_h=2$ s⁻¹, so it is half-gone after $\ln 2/2=\mathbf{347}$ ms. Sampled at $\tau\ll347$ ms the two assets' moves land in *different* buckets and measured correlation is near zero; sampled at $\tau\gg347$ ms they land in the *same* bucket and correlation appears. The Series E1/E2 arithmetic in Section 2 point 9 shows the resulting numbers: $\rho(0.1\text{ s})=-0.129$ against $\rho(0.2\text{ s})=+0.949$.
- Parameter budget at $d=2$: 32 non-zero $\nu$ entries (8 rows × 4), 8 baselines reduced to 4 by the $\mu_{a\pm}=\mu_{b\pm}$ constraints, 8 kernel rates, and 2 mark parameters per asset — roughly **48** free parameters against 5.53M observed trades.

### Algorithm C — Calibration by maximum likelihood, with mark-law fitting and stability checks

**Goal:** estimate the whole parameter set $\Theta=\{f,g,h,\nu,\mu\}$ from recorded tick data, and verify that the fitted process is a valid, stationary Hawkes process.

**Inputs:** cleaned tick-by-tick data (times, channel labels, volumes) over a window $I=[T^-,T^+]$.
**Outputs:** fitted $\hat\mu$, $\hat\nu$, $\hat\alpha_h$, $\hat\alpha$, $\hat\beta$; the spectral radius of $\hat\nu$; the $\mathrm{Exp}(1)$ residuals for goodness of fit.

**Steps:**

1. **Clean and block the data.** Apply the classical high-frequency cleaning procedure of Dacorogna et al. Because the full sample is too large for one pass, cut it into weekly blocks and average the per-block estimates.
2. **Fit the mark (volume) distribution per channel.** Plot the empirical exceedance $P(V>x)$ for each of the four channels and fit candidates: Gaussian $f_G(x)=\frac{1}{\sigma\sqrt{2\pi}}e^{-(x-\mu)^2/2\sigma^2}$ and exponential $f_E(x)\propto e^{-\beta x}$. The paper selects the exponential, $\beta e^{-\beta x}$, because the Gaussian tails "vanish too quickly". This step must come first because $g$ cannot be normalised without $f$.
3. **Normalise the impact function.** With $V\sim\mathrm{Exp}(\beta)$ and a power-law impact $x^\alpha$, enforce $\mathbb{E}[g(V)]=1$. Since $\mathbb{E}[V^{\alpha}]=\Gamma(\alpha+1)/\beta^{\alpha}$, this gives $g(x)=\beta^{\alpha}x^{\alpha}/\Gamma(\alpha+1)$ (5.4).
4. **Impose the identification constraints.** Set $\mu^{(i)}_{a+}=\mu^{(i)}_{b+}$ and $\mu^{(i)}_{a-}=\mu^{(i)}_{b-}$. Without these, simulated bid and ask can drift apart without bound, since nothing else in (4.2) ties the two price levels together.
5. **Maximise the log-likelihood.** Evaluate
   $$\log L=\sum_{j=1}^{d}\sum_{k=1}^{N}\log\lambda_j\!\left(t_k,v(t_k)\mid\mathcal{F}_{t_k}\right)-\sum_{j=1}^{d}\Lambda_j(T^+)$$
   with $\Lambda_j$ the compensator (5.2), and optimise with a classical numerical optimiser. The two terms pull in opposite directions: the first rewards high intensity at observed event times, the second penalises high intensity everywhere else. (Bacry et al.'s alternative — match the empirical signature plot by minimising MSE — is mentioned as a substitute.)
6. **Check stationarity.** Compute the eigenvalues of $\hat\nu$ and require $\max_i|\lambda_i|<1$ (3.10); also confirm $\int_0^\infty t\,h(t)\,dt=1/\alpha_h<\infty$ (3.11). The paper reports radii of **0.71–0.84** per week, averaging **0.81**. It stresses this is necessary, not sufficient.
7. **Check fit with the point-process residuals.** Compute the compensator increment over each inter-event interval; under a correct model these are i.i.d. $\mathrm{Exp}(1)$ (3.12), equivalently the random time change (3.13) turns the data into a unit-rate compound Poisson process. Test the residuals against $\mathrm{Exp}(1)$.

**Worked example (end-to-end, Series D1).** One channel, $\mu=0.5$, $\alpha_h=2$, $\beta=1$, $\alpha=0.5$; events at $t=0.0,0.3,0.7$ s with marks $1.0,4.0,2.5$M; window $I=[0,1]$ s.

- Step 2–3: $\Gamma(1.5)=0.886227$, so $g(x)=1.12838\sqrt{x}$; check $\mathbb{E}[g(V)]=1.12838\times0.886227=\mathbf{1.0000}$ ✓. Tail comparison at $x=3$: exponential $e^{-3}=\mathbf{4.98\,\%}$ versus Gaussian($1,1$) $1-\Phi(2)=\mathbf{2.28\,\%}$; at $x=5$, $\mathbf{0.674\,\%}$ versus $\mathbf{0.0032\,\%}$ — a factor **213**, quantifying step 2's rejection of the Gaussian.
- Step 5 at a trial $\nu=0.8$: intensities at the event times are $\lambda(t_1)=0.5$ (empty history), $\lambda(t_2)=0.5+0.8(1.0976\times1.1284)=\mathbf{1.4908}$, $\lambda(t_3)=0.5+0.8(0.4932\times1.1284+0.8987\times2.2568)=0.5+0.8(0.5565+2.0281)=\mathbf{2.5677}$. So $\sum\log\lambda=-0.6931+0.3993+0.9430=\mathbf{0.6492}$.
  Compensator: $\Lambda(1)=\mu\cdot1+\nu\sum_k g(v_k)\left(1-e^{-\alpha_h(1-t_k)}\right)=0.5+0.8\left[1.1284\times0.8647+2.2568\times0.7534+1.7841\times0.4512\right]=0.5+0.8\left[0.9757+1.7002+0.8050\right]=\mathbf{3.2847}$.
  Hence $\log L(\nu=0.8)=0.6492-3.2847=\mathbf{-2.636}$.
- Step 5 at a trial $\nu=0.5$: $\sum\log\lambda=-0.6931+0.1127+0.5835=\mathbf{0.0030}$, $\Lambda(1)=0.5+0.5\times3.4809=\mathbf{2.2405}$, $\log L=\mathbf{-2.237}$. Since $-2.237>-2.636$, the optimiser moves **down** from 0.8 toward 0.5 on this sample — the compensator penalty dominates when only three events are observed.
- Step 6: for the two-channel up-block $\nu=\begin{pmatrix}0.50&0.31\\0.31&0.50\end{pmatrix}$, eigenvalues $0.50\pm0.31=\{\mathbf{0.81},0.19\}$, radius $0.81<1$ ✓, matching the paper's reported average. Kernel check: $1/\alpha_h=0.5$ s $<\infty$ ✓.
- Step 7: residuals from Section 2 point 4 are $\Lambda_1=\mathbf{0.5573}$ over $[0,0.3]$ and $\Lambda_2=\mathbf{1.4670}$ over $[0.3,0.7]$; their mean is $\mathbf{1.012}$ against the $\mathrm{Exp}(1)$ mean of 1, and both sit in the bulk of the distribution ($P(\Lambda>0.5573)=0.573$, $P(\Lambda>1.4670)=0.231$) — no evidence against the fit on this (tiny) sample.

*Issues found.* (i) Equation (5.1) is printed as a **product of integrals**, $\prod_j\int\lambda_j\,N_j(dt\times dv)\exp(-\Lambda_j)$; an integral against a counting measure is a *sum*, $\sum_k\lambda_j(t_k)$, so (5.1) does not exponentiate to the correct (5.3). The consistent form is $L=\prod_j\left[\prod_k\lambda_j(t_k,v_k)\right]e^{-\Lambda_j(T^+)}$, i.e. $\exp\left(\int\log\lambda_j\,N_j(dt\times dv)\right)e^{-\Lambda_j}$. Equation (5.3) is the correct one and is what a reimplementation should use. (ii) (5.2) integrates from $-\infty$ although the window starts at $T^-$; in practice the compensator must be taken over $I$ with a burn-in for the pre-history. (iii) The $\lambda_i(t,v\mid\mathcal{F}_t)$ of (3.6) does **not** depend on the current mark $v$ — the impact function is applied only to *past* marks under the integral — so the mark integrals "$dt\times dv$" in (5.2) and (3.12) are formally infinite unless a mark density is inserted. Read them as integrals over $t$ only. (iv) The paper reports **no** fitted values for $\mu$, $\nu$, $\alpha_h$, $\alpha$, $\beta$, no standard errors, no likelihood values, and no numerical outcome of the residual test (3.12) — only the spectral radius. That makes the calibration unreproducible from the paper alone.

### Algorithm D — Simulation and stylized-fact validation

**Goal:** generate synthetic bid/ask paths from the fitted model and check that they reproduce the frequency-dependent stylized facts of real tick data.

**Inputs:** the fitted $\Theta$ from Algorithm C; a simulation horizon $T$; the sampling grid.
**Outputs:** simulated event sequences $\{t_i,v(t_i)\}$ per channel, the counts $N$, the paths $p_a(t),p_b(t),s(t)$, and the simulated signature plot and Epps curve for comparison against the empirical ones.

**Steps:**

1. **Simulate the marked point process by thinning.** Because the intensities fully characterise the marked point process, knowing $\lambda_j$ is enough to draw a sequence $\{t_i,v(t_i)\}_{i=1,\dots,T}$. The paper cites Ogata's (Lewis) thinning method and the treatments in Daley–Vere-Jones and Liniger rather than specifying its own: propose candidate times from a dominating Poisson rate, accept each with probability $\lambda_j(t)/\bar\lambda$, and draw the mark from $f$ at each accepted point.
2. **Accumulate the counting processes.** From the accepted events build $N_{a,+},N_{a,-},N_{b,+},N_{b,-}$ (and their per-asset versions in the multivariate case).
3. **Rebuild prices and the spread.** Apply (4.3) to get $p_a$ and $p_b$; the spread is the difference of the two simulated paths. Figure 7 shows exactly this, with the spread in an inset ranging roughly **0.00006 to 0.00014**, i.e. 6 to 14 ticks.
4. **Resample onto a regular grid with the tick estimator.** Use $t=\arg\max_{t_i}\{t_i\le t\}$ (5.5) on the deci-second grid $\{0.10,0.20,\dots\}$ — the previous-tick rule — so that irregular event times become an evenly spaced series.
5. **Compute the signature plot and compare.** Evaluate $V_X(\tau)$ from (6.1) on log mid-prices for a range of $\tau$, on the empirical data and on the simulation, and fit both with a power law. The expected pattern is a decreasing curve.
6. **Compute the Epps curve and compare.** Evaluate $\rho_{1,2}(\tau)$ from (6.2) for the two parities, again empirically and on the simulation. The expected pattern is correlation rising with $\tau$.

**Worked example (end-to-end).**

- Step 1 (thinning, one accept/reject cycle): at $t=0.5$ s take the dominating rate $\bar\lambda=\lambda_{a,+}(0.5)=1.853$ s⁻¹ (valid going forward, since the intensity only decays between events). Draw an exponential candidate gap with $u_1=0.35$: $\Delta=-\ln(0.35)/1.853=1.0498/1.853=0.566$ s, so the candidate time is $t'=1.066$ s. The true intensity there is $\lambda_{a,+}(1.066)=0.5+1.353\,e^{-2(1.066-0.5)}=0.5+1.353\times0.3223=0.936$ s⁻¹. Accept with probability $0.936/1.853=0.505$; with $u_2=0.42<0.505$ the candidate is **accepted**. Draw the mark from $\mathrm{Exp}(1)$ with $u_3=0.20$: $v=-\ln(0.20)=\mathbf{1.609}$M.
- Step 2–3: appending this ask-up event moves $N_{a,+}$ from 11 to 12, so $p_a$ goes from $1.32007$ to $\mathbf{1.32008}$ and the spread from 4 ticks to **5 ticks** ($5\times10^{-5}$), inside the range shown in Figure 7's inset.
- Step 4: on the deci-second grid, ticks at $0.07,0.13,0.19,0.26$ s map to grid points $0.10\to$ tick@$0.07$, $0.20\to$ tick@$0.19$, $0.30\to$ tick@$0.26$.
- Step 5 (Series S1): increments $+2,-1,+2,-2$ ($\times10^{-5}$), $T=0.4$ s. $V_X(0.1)=1.3\times10^{-9}/0.4=\mathbf{3.25\times10^{-9}}$ s⁻¹; aggregating to $\tau=0.2$ gives increments $+1,0$ and $V_X(0.2)=1\times10^{-10}/0.4=\mathbf{2.5\times10^{-10}}$ s⁻¹. Ratio **13×** for one doubling of $\tau$ — the decreasing signature plot.
- Step 6 (Series E1/E2): asset 1 increments $+2,+1,-1,+2$; asset 2 lagged by one step, $0,+2,+1,-1$. At $\tau=0.1$ s: $Co=-2.5\times10^{-10}$, $V_{X_1}=2.5\times10^{-9}$, $V_{X_2}=1.5\times10^{-9}$, $\rho=\mathbf{-0.129}$. At $\tau=0.2$ s: $Co=1.5\times10^{-9}$, $V_{X_1}=2.5\times10^{-9}$, $V_{X_2}=1.0\times10^{-9}$, $\rho=\mathbf{+0.949}$. Correlation appears only once the sampling interval exceeds the lag — the Epps effect.

*Issue found.* The summation index in (6.1)/(6.2) runs $n=0$ to $\lfloor T/\tau\rfloor$, so the last term uses $X\left((\lfloor T/\tau\rfloor+1)\tau\right)$, which lies beyond $T$ — an off-by-one that matters only for small $T/\tau$. Also, Figure 9's vertical axis is labelled as the Epps correlation but tops out near **0.015**, which is implausibly low for EUR/USD against EUR/GBP at 100-second sampling; it reads more like a covariation than a normalised correlation, and neither axis is given units.

### Algorithm E — Forecast and risk-management / cost loop

**Goal:** from the current fitted state, predict which quote will move next and when, and simultaneously price the transaction costs (spread plus market impact) that the predicted trade would incur, so that a strategy can be judged net of costs.

**Inputs:** the fitted $\Theta$; the live history $\mathcal{F}_t$; a horizon $\tau$; the intended order size $k$; the tick size; assumed depth at deeper limits.
**Outputs:** $P(\tau^*>\tau)$ per channel; the most likely next channel and its probability; the projected spread; the projected market-impact cost; a go/no-go on the trade.

**Steps:**

1. **Evaluate all channel intensities at the current time.** Run Algorithm A (or B for the multi-asset case) to get the 4 (or $4d$) intensities at $t$.
2. **Convert intensity into a next-event probability.** Use Vere-Jones' survival formula $P(\tau^*>\tau)=\exp\left(-\int_0^{\tau}\int_{\mathbb{R}}\lambda(s,v\mid\mathcal{F}_s)\,dv\,ds\right)$ (7.1), i.e. the survival function is the exponential of minus the compensator over the horizon. For an exponential kernel with no intervening events this is closed form: $\Lambda(\tau)=\mu\tau+\frac{E_0}{\alpha_h}\left(1-e^{-\alpha_h\tau}\right)$ where $E_0$ is the current excitation.
3. **Pick the channel.** The paper says to "find such $\tau$ that maximizes the probability for all the 4 intensities". Because $P(\tau^*>\tau)$ is monotone decreasing in $\tau$, maximising it returns $\tau=0$; the well-posed version of the step is to compare channels at a fixed horizon, or equivalently to take the competing-risks first-firing probability $\lambda_j(t)/\sum_m\lambda_m(t)$.
4. **Roll the history forward.** To reach horizon $t+\tau$ the history must be updated at every $t+\delta t$; each simulated intermediate event needs a mark, generated from $f(v)=\lambda(t+\delta t,v\mid\mathcal{F}_{t+\delta t})/\int_{\mathbb{R}}\lambda(t+\delta t,v\mid\mathcal{F}_{t+\delta t})\,dv$. Adding each pair $(t+\delta t,v(t+\delta t))$ back into the history is what makes the forecast self-consistent.
5. **Project the spread.** Because both quotes are simulated, the predicted next spread follows directly from which channel fires: an ask-up widens the spread by a tick, a bid-up narrows it, and so on.
6. **Price the market impact.** Walk the book: $V=\sum_i k_i(p_a+x_ip_{tick})$ with $x_1=0$, so the impact component is $\sum_i k_i x_i p_{tick}$. Assuming consecutive limits one tick apart makes the next prices $p_a+p_{tick}$, $p_a+2p_{tick}$, …; depth at each limit is unknown from the first line, so the paper draws it from an exponential law.
7. **Decide.** Compare the expected gross edge (ticks captured × $p_{tick}$ × size) against the projected spread cost $k\,s$ plus impact plus broker fees. Trade only if positive.

**Worked example (end-to-end).** State: Series D1 history at $t=1.0$ s for the ask-up channel; current quotes $p_a=1.32011$, $p_b=1.32003$ ($s=8$ ticks); intended size $k=300{,}000$ EUR; three visible limits of 100,000 each.

- Step 1: $\lambda_{a,+}(1.0)=0.5+0.8\left[1.1284\times0.2707+2.2568\times0.4932+1.7841\times1.0976\right]=0.5+0.8\left[0.3054+1.1130+1.9583\right]=\mathbf{3.201}$ s⁻¹. Suppose the other channels evaluate to $\lambda_{b,+}=2.100$, $\lambda_{a,-}=0.400$, $\lambda_{b,-}=0.400$ s⁻¹.
- Step 2: excitation $E_0=2.701$, so $\Lambda(\tau)=0.5\tau+1.3507\left(1-e^{-2\tau}\right)$. At $\tau=0.1$ s: $\Lambda=0.05+0.2448=0.2948$ and $P(\tau^*>0.1)=e^{-0.2948}=\mathbf{0.745}$ → **25.5 %** chance of an ask-up within 100 ms. At $\tau=0.5$ s: $\Lambda=0.25+0.8538=1.1038$, $P=e^{-1.1038}=\mathbf{0.332}$ → **66.8 %** within 500 ms.
- Step 3: total rate $=3.201+2.100+0.400+0.400=\mathbf{6.101}$ s⁻¹, so the expected wait to *any* quote change is $1/6.101=\mathbf{164}$ ms, and the first-firing probabilities are $3.201/6.101=\mathbf{52.5\,\%}$ ask-up, $34.4\,\%$ bid-up, $6.6\,\%$ each for the two down-channels. Prediction: **the next move is an upward tick on the ask**, at 52.5 % against a 25 % uninformed baseline — a **2.1×** edge.
- Step 4: to project to $\tau=0.5$ s, generate the intervening events; e.g. one accepted intermediate event with mark drawn as in Algorithm D step 1, $v=1.609$M, appended to $\mathcal{F}$ before re-evaluating.
- Step 5: if the ask-up fires and the bid does not move, the spread widens from 8 to **9 ticks**, so the projected round-turn spread cost rises from $300000\times8\times10^{-5}=\mathbf{24.00}$ USD to $300000\times9\times10^{-5}=\mathbf{27.00}$ USD.
- Step 6: filling 300,000 across three one-tick-apart limits costs $100000(1.32011+1.32012+1.32013)=396{,}036$ USD against $396{,}033$ USD at the touch, i.e. impact $=\mathbf{3.00}$ USD $=10^{-5}\times100000\times(0+1+2)$ ✓.
- Step 7: the gross edge from a correct 1-tick call on 300,000 units is $300000\times10^{-5}=3.00$ USD, weighted by 0.525 gives $\mathbf{1.58}$ USD expected. Against $27.00$ USD spread $+3.00$ USD impact $=30.00$ USD of cost, the expected net is $\mathbf{-28.42}$ USD. **No-go** by liquidity-taking; the signal is only monetisable by posting passively. This is precisely the paper's own point that detected gain probabilities "reduce to zero" once costs are charged.

*Issues found.* (i) The step-3 criterion as printed ("find such $\tau$ that maximizes the probability") is degenerate: $P(\tau^*>\tau)$ decreases monotonically in $\tau$, so its maximum is at $\tau=0$. Even the natural repair — maximise the next-event *density* $f(\tau)=\lambda(\tau)e^{-\Lambda(\tau)}$ — is degenerate for a decaying exponential kernel, because the stationarity condition $\lambda'(\tau)=\lambda(\tau)^2$ has no solution when $\lambda'<0$ everywhere; the density is monotone decreasing and its mode is again $\tau=0$. The usable statistic is the cross-channel comparison of step 3 (argmax of $\lambda_j$, or the first-firing probabilities). (ii) The impact simplification $\sum_i k_ix_ip_{tick}=\sum_ik_ip_{tick}$ is not an identity. With consecutive ticks $x_i=i-1$, so for uniform slice sizes $k_i=k/n$ the true impact is $k\,p_{tick}(n-1)/2$ whereas the paper's expression gives $k\,p_{tick}$; they agree **only at $n=3$**. At $n=5$ with 100,000 per limit: true impact $=10^{-5}\times100000\times(0+1+2+3+4)=\mathbf{10.00}$ USD versus the paper's $10^{-5}\times500000=\mathbf{5.00}$ USD — a **2× understatement**, growing linearly in the number of levels consumed.

## 5. Ideas for Development

- **Mark-weighted excitation feature for any event-driven signal** — take Step 3–4 of **Algorithm A** (map volume through the normalised impact function $g(x)=\beta^{\alpha}x^{\alpha}/\Gamma(\alpha+1)$, then sum decayed mark-weighted history) and use it as a standalone feature generator on any event stream where size is recorded: trade prints, liquidation cascades, futures blocks. The output is a single real-valued "excitation" series $E(t)=\sum_k h(t-t_k)g(v_k)$ that can be fed to any downstream model, replacing the usual count-per-bucket feature.
  - **Strong:** very high frequency data on liquid instruments where volume and duration are jointly recorded — Figure 3 shows on both EUR/USD and EUR/GBP that large volume variations coincide with short durations, so the mark carries information the timestamps do not. *(From paper)*
  - **Strong:** regimes where order sizes are dispersed rather than uniform — the marked weight adds variance $\mathrm{Var}[g(V)]=\Gamma(2\alpha+1)/\Gamma(\alpha+1)^2-1$ to each event's contribution; at $\alpha=0.5$ that is $1/0.7854-1=0.273$, so the mark-weighted feature is strictly more informative than the count, whereas in a uniform-size regime $\mathrm{Var}[g(V)]\to0$ and the feature collapses back to the count. *(From AI)*
  - **Weak:** convex impact exponents combined with a near-critical branching ratio — cluster-size variance is $\mathrm{Var}[T]=\mathrm{Var}[K]/(1-\rho)^3$ with $\mathrm{Var}[K]=\rho+\rho^2(\mathbb{E}[g^2]-1)$; at the paper's $\rho=0.81$ and $\alpha=1$ ($\mathbb{E}[g^2]=\Gamma(3)/\Gamma(2)^2=2$) this is $1.4661/0.006859=\mathbf{214}$ against $118$ for the unmarked case, an **81 % inflation** of burst-size variance, while the mean $1/(1-\rho)=5.26$ is unchanged. The spectral-radius test (3.10) cannot see this, so a model that passes the paper's check can still produce wildly heavy-tailed bursts. *(From AI)*
  - **Weak:** venues where order sizes are quantised or capped (iceberg orders, minimum lot sizes) — $g$ then maps a near-degenerate mark distribution, $\mathbb{E}[g(V)]=1$ still holds by construction but $g(v_k)\approx1$ for every event, so the marked model reduces to the unmarked one while carrying extra parameters ($\alpha$, $\beta$) that the likelihood cannot identify. *(From AI)*

- **Endogenous-spread simulator as a cost layer for strategy stress testing** — reuse **Algorithm A** Step 5 together with **Algorithm D** Step 3 to generate correlated bid and ask paths and charge a *simulated*, time-varying spread in backtests instead of a constant assumed spread. This is the paper's own stated application and is usable on its own: it needs no forecast, only a calibrated four-channel model.
  - **Strong:** liquid FX or futures where the paper's core assumption holds that consecutive limits sit one tick apart — Section 7 states the spread "is directly deduced as the difference of the two simulations", and Figure 7's inset shows a simulated spread of roughly 6–14 ticks, in the right region for EUR/USD. *(From paper)*
  - **Strong:** strategies whose gross edge is small relative to the spread — the paper's own arithmetic is the argument: a correct 1-tick call on 300,000 units earns 3.00 USD while an 8-tick round turn costs 24.00 USD, so a cost layer that varies the spread by even ±2 ticks changes net PnL by ±6.00 USD per trade, i.e. **2× the entire gross edge**. Any strategy whose backtest ignores spread dynamics is therefore untested, not merely imprecise. *(From AI)*
  - **Weak:** long simulation horizons — nothing in (4.2) mean-reverts the spread. In tick units $S(t)=N_{a,+}-N_{a,-}-N_{b,+}+N_{b,-}$ is a difference of four counting processes, so $\mathrm{Var}[S]$ grows linearly in $t$: at four channels each running near 3 s⁻¹ over 100 s, a Poisson benchmark gives $\mathrm{Var}[S]=4\times300=1200$ ticks², sd $=34.6$ ticks, and the Hawkes dispersion index $1/(1-\rho)^2=27.7$ at $\rho=0.81$ inflates this to $\mathrm{Var}\approx33{,}240$, sd $\approx\mathbf{182}$ ticks — against a mean spread of 8 ticks, crossed (negative) quotes become near-certain. The paper's hand-imposed $\mu_{a\pm}=\mu_{b\pm}$ equalises drift but adds no restoring force, so the simulator needs a spread floor or an explicit mean-reverting term for horizons beyond a few seconds. *(From AI)*
  - **Weak:** any venue where cancellations drive the quote — the paper excludes them outright, noting SEC/AMF evidence that about **80 %** of orders are cancelled, so a simulated spread built only from market orders and inside-spread limit orders omits the dominant quote-changing mechanism on many equity venues. *(From paper)*

- **Spectral radius as a market-fragility monitor** — take Step 6 of **Algorithm C** and run it as a rolling statistic rather than a one-off validation gate: refit $\hat\nu$ on a sliding window, report the spectral radius $\hat\rho$, and translate it into the endogeneity amplification $1/(1-\hat\rho)$. This is standalone: it needs the calibration but no simulation, no forecast, and no cost model.
  - **Strong:** cross-week comparison on a stable instrument, where the statistic's variation is the signal — the paper's own estimates range **0.71 to 0.84** across five weeks per parity with mean 0.81, i.e. the radius genuinely moves week to week rather than being a constant of the market. *(From paper)*
  - **Strong:** as an early-warning statistic, because the mapping to amplification is strongly convex — $\mathbb{E}[\text{cluster size}]=1/(1-\rho)$ gives 3.45 at $\rho=0.71$, 5.26 at 0.81 and 6.25 at 0.84, and the sensitivity $d/d\rho\left[1/(1-\rho)\right]=1/(1-\rho)^2$ is 39 at $\rho=0.84$ versus 12 at $\rho=0.71$. A monitor therefore reacts far more sharply exactly where fragility is highest. *(From AI)*
  - **Weak:** the same convexity destroys precision near criticality — a ±0.02 standard error on $\hat\rho$ maps to ±0.78 events (±12.5 %) of amplification at $\rho=0.84$, but to ±1.6 events at $\rho=0.90$ and ±5 events at $\rho=0.95$, so the monitor's error bars widen faster than its signal. The paper reports no standard errors at all, which makes its 0.71–0.84 range impossible to distinguish from estimation noise. *(From AI)*
  - **Weak:** intraday non-stationarity biases the statistic upward — the paper fits a **constant** $\mu$ per weekly block, yet notes itself that durations near one minute correspond to midnight GMT, i.e. the baseline rate is strongly time-of-day dependent. When a time-varying $\mu(t)$ is fitted as a constant, the extra count autocovariance contributed by $\mathrm{Var}_t[\mu(t)]$ has nowhere to go but the excitation term, so $\hat\rho\ge\rho$: part of the reported 0.81 is intraday seasonality misread as self-excitation. Fixing this requires a deterministic seasonality factor before the Hawkes fit. *(From AI)*

- **Order-type inference from the four-channel volume distributions** — build a classifier that labels each observed quote change as *market order* versus *inside-spread limit order*, using the Figure 4 finding (see Section 3, topic 3) plus the channel label produced by **Algorithm A** Step 1. The payoff is a real-time aggressor/passive flow ratio computable from first-line data only.
  - **Strong:** first-line-only feeds on liquid FX pairs, where the paper reports the four conditional volume distributions collapse into exactly two pairs on **both** EUR/USD and EUR/GBP — ask-volume-on-up ≈ bid-volume-on-down (the market-order pair) and ask-volume-on-down ≈ bid-volume-on-up (the limit-order pair). *(From paper)*
  - **Strong:** the classification is nearly free of estimation risk when the channel label is used, because the mapping channel → order type is *mechanical*, not statistical: an ask-up can only be a buy sweep of the full first limit, an ask-down can only be a new sell limit inside the quotes. No parameters are involved. *(From paper)*
  - **Weak:** attempting the same classification from **volume alone**, without the channel label, barely beats a coin flip. With two exponential mark laws, rates $\beta_L=0.8$ (limit, larger orders) and $\beta_M=1.2$ (market), the Bayes threshold is $x^*=\ln(\beta_L/\beta_M)/(\beta_L-\beta_M)=1.014$ and the equal-prior error rate is $\tfrac12\left(1-e^{-\beta_Lx^*}\right)+\tfrac12e^{-\beta_Mx^*}=0.278+0.148=\mathbf{42.6\,\%}$ — a 50 % difference in mean order size buys only 7.4 points over chance. The channel label is doing essentially all the work. *(From AI)*
  - **Weak:** the inference is blind to the ~**80 %** of order flow that is cancelled, and to the depth beyond the first limit, which the paper states is simply unobservable from its data and must be drawn from an exponential law in simulation. Any aggressor-ratio built this way measures only price-moving flow. *(From paper)*

- **Cross-asset excitation matrix as a lead-lag detector for FX pairs and triangles** — estimate the off-diagonal quadrants of the **Algorithm B** Step 4 branching pattern and read them as a directed lead-lag graph: a large $\nu^{(j\to i)}$ with a small $\nu^{(i\to j)}$ says $j$ leads $i$. Useful on its own as a research output (which pairs lead which, at what decay timescale) before any trading logic is attached.
  - **Strong:** currency pairs sharing a leg, where the paper gives a directional prediction to test — positive same-sign coefficients for EUR/USD with EUR/GBP and for USD/JPY with GBP/JPY, near-zero opposite-sign ones; and the reverse for EUR/USD with USD/CHF, whose sign pattern flips because coefficients are constrained non-negative. *(From paper)*
  - **Strong:** the timescale is read off directly from the kernel rather than scanned by grid search — with $h(u)=\alpha_he^{-\alpha_hu}$ the cross-excitation half-life is $\ln2/\alpha_h$, i.e. **347 ms** at $\alpha_h=2$ s⁻¹, and the Epps arithmetic confirms that correlation is invisible for $\tau\ll$ half-life ($\rho=-0.129$ at 100 ms) and near-total for $\tau\gg$ it ($\rho=+0.949$ at 200 ms). The lead-lag horizon is therefore a fitted parameter, not a hyperparameter. *(From AI)*
  - **Weak:** the non-negativity constraint on all $\nu$ makes negative dependence representable only by cross-signing (up-$i$ with down-$j$), so a pair whose correlation *changes sign* over the sample cannot be fitted by a single parameter set — the fit will average the two regimes toward zero and report "no lead-lag" where there is in fact a regime-switching one — the paper states this constraint and its consequence explicitly. *(From paper)*
  - **Weak:** the baseline-versus-excitation identification problem worsens as the model grows. Because the stationary mean rate satisfies $\bar\lambda=\mu/(1-\rho)$, every pair $(\mu,\rho)$ on the line $\mu=\bar\lambda(1-\rho)$ reproduces the same average event count; the likelihood separates them only through the clustering signature, so individual $\nu_{ij}$ estimates are weakly identified and highly correlated with each other. At $d=2$ the model already carries roughly **48** free parameters (32 non-zero $\nu$, 4 constrained baselines, 8 kernel rates, 4 mark parameters), and the paper reports no standard errors on any of them. *(From AI)*

- **Competing-risks next-tick predictor with an explicit cost gate** — implement **Algorithm E** Steps 1, 3, 5 and 7 only: evaluate the four intensities, take the first-firing probabilities $\lambda_j/\sum_m\lambda_m$, project the resulting spread, and gate on net-of-cost expected value. This is standalone and much cheaper than the paper's full forecast, since it skips the history roll-forward of Step 4.
  - **Strong:** whenever the intensities are strongly asymmetric, the edge is large and directly computable — in the worked example the ask-up channel carries $3.201/6.101=\mathbf{52.5\,\%}$ of the total rate against a 25 % uninformed baseline, a **2.1×** edge, with an expected wait of 164 ms to the next quote change. *(From AI)*
  - **Strong:** the model predicts *which side* moves, not just direction, so the expected spread comes with the direction — Section 7 argues this is exactly the information that "indicates if the trade has a chance or not to be profitable", which a mid-price model cannot supply. *(From paper)*
  - **Weak:** the edge is not monetisable by taking liquidity at these tick/spread ratios. Expected gross per trade is $P(\text{correct})\times1$ tick $=0.525$ ticks against a round-turn cost of 8–9 ticks of spread plus impact, i.e. $\mathbf{-7.5}$ ticks expected; the predictor is only usable for *passive* order placement (choosing which side to post on, capturing $s/2$) or for execution timing, never for aggressive entry. *(From AI)*
  - **Weak:** the paper's own selection rule is ill-posed and must be replaced. "Find such $\tau$ that maximizes the probability" applied to $P(\tau^*>\tau)$ returns $\tau=0$ since the survival function decreases monotonically; and the natural repair (maximise the next-event density $f(\tau)=\lambda(\tau)e^{-\Lambda(\tau)}$) is also degenerate for a decaying exponential kernel, because $\lambda'(\tau)=-\alpha_hE_0e^{-\alpha_h\tau}<0$ can never equal $\lambda(\tau)^2>0$, so the density has no interior mode. The cross-channel comparison used above is the well-posed substitute. *(From AI)*
  - **Weak:** no accuracy evidence exists in the paper — the forecast section reports no hit rate, no out-of-sample test, no PnL, and the full version requires re-simulating the history at every $t+\delta t$ up to $t+\tau$ with marks drawn from $f(v)=\lambda/\int\lambda\,dv$, which is a nested Monte Carlo at every decision point. *(From paper)*

## 6. Tools & Data Used in This Research

### Software & Library

| Tools | Purpose in paper |
|---|---|
| None reported | — |

The paper names **no** software, language, or library. The only computational tooling it mentions is generic and unattributed: "a classical optimization algorithm" for maximising the log-likelihood (5.3), and the thinning algorithm for simulation, which is cited to references (Ogata 1981; Daley & Vere-Jones 2003; Liniger 2009) rather than to an implementation. The figures are unattributed as well.

### Data Source

| Source | Description |
|---|---|
| EUR/USD tick data | Recorded in **milliseconds**, 30 January 2012 00:00:00 → 09 March 2012 21:59:00 (one month and one week); **3,352,809 trades**. Cleaned with the classical procedure of Dacorogna et al. Cut into **5 weekly blocks**, results averaged. Tick size $p_{tick}=10^{-5}$ |
| EUR/GBP tick data | Same period and treatment; **2,178,009 trades**. Tick size $10^{-5}$ |
| EUR/USD log-return sample (Figure 2) | 14:00:00 → 14:10:00 on 06 February 2012, **deci-second** sampling, used to display return clustering |
| EUR/USD and EUR/GBP volume-variation vs duration (Figure 3) | 30 January 2012 → 10 March 2012, millisecond records, ask and bid volume changes in **millions of USD**, second-scale durations. Durations near 1 minute correspond to prices recorded around midnight GMT |
| EUR/USD conditional-intensity sample (Figures 5–6) | **2000 deci-second points** = 3 min 23 s, 30 January 2012 00:12:53 → 00:16:32; ask/bid volumes, prices, and the four fitted marked intensities |
| Cumulative volume distributions (Figure 4) | $P(V>x)$ in log scale for ask/bid volume conditional on upward/downward jumps, both parities, over the full sample; Gaussian and exponential fits overlaid |
| Signature plot and Epps curves (Figures 8–9) | Mid-price quotes, averaged week by week, $\tau$ from 0 to 100 seconds, empirical vs simulated vs power-law fit |
| SEC and AMF regulatory reports | Cited qualitatively for the finding that about **80 %** of orders are cancelled — the quantity the model explicitly cannot observe or include |
| Interbank liquidity pools (qualitative) | Named as sources of differing "last prices" on OTC FX: Bloomberg, Reuters, Yahoo, Google, IB; major interbank participants Deutsche Bank, Citi, Barclays Investment Bank |

### Models & Algorithms

| Model/Algorithm | Role |
|---|---|
| Multivariate marked Hawkes process | The paper's core object; intensity (3.6)/(3.9), stationarity via spectral radius (3.10) |
| Exponential decay kernel $h_i(u)=\alpha_he^{-\alpha_hu}$ | Memory of past events (3.5); satisfies the finite-mean-lag condition (3.11) |
| Power-law mark impact function $g(x)=\beta^{\alpha}x^{\alpha}/\Gamma(\alpha+1)$ | Converts order volume into excitation (3.7)/(5.4); chosen on the empirical power-law impact evidence |
| Exponential impact function $\exp(\alpha x)$ | Alternative impact shape offered in (3.7)/(3.8) but not selected |
| Exponential mark (volume) law $\beta e^{-\beta x}$ | Selected volume distribution; needed to normalise $g$ |
| Gaussian mark law $f_G$ | Competing volume distribution, **rejected** — tails vanish too quickly |
| Four-channel first-line order-book model (4.2) + price map (4.3) | The paper's proposed model: ask-up/ask-down/bid-up/bid-down with a tick-quantised price reconstruction |
| Multivariate cross-asset extension (4.6) + Table 1 sparsity pattern | Generates Epps and lead-lag effects across parities |
| Compound counting process $N_g(t)=\sum_{i\le N(t)}v(t_i)$ (4.5) | Discussed alternative where volume sets jump size; rejected as incompatible with (4.3), flagged for future work |
| Maximum-likelihood estimation via log-likelihood (5.1)–(5.3) | Parameter estimation, maximised with an unnamed classical optimiser |
| Bacry et al. signature-plot MSE calibration | Alternative estimation route mentioned but not used |
| Thinning (Lewis/Ogata) simulation algorithm | Generates $\{t_i,v(t_i)\}$ from the fitted intensities |
| Random time change theorem / $\mathrm{Exp}(1)$ residuals (3.12)–(3.13) | Two built-in goodness-of-fit tests for the fitted point process |
| Previous-tick (tick) interpolation estimator (5.5) | Maps irregular event times onto the regular deci-second grid |
| Signature plot estimator (6.1) | Stylized-fact test: realised volatility versus sampling frequency |
| Epps correlation and covariation estimators (6.2) | Stylized-fact test: cross-asset correlation versus sampling frequency |
| Vere-Jones next-event survival probability (7.1) | Forecast primitive; converts intensity into a waiting-time distribution |
| Mark-generating density $f(v)=\lambda/\int\lambda\,dv$ | Draws the volume for each simulated future event during the forecast roll-forward |
| Book-walking market-impact model $V=\sum k_i(p_a+x_ip_{tick})$ | Prices execution cost beyond the touch |
| Count-only price model $p(t)=N^+(t)-N^-(t)$ (2.1) | Baseline formulation the paper argues against (no bid, no ask, no spread) |
| Large's ten-order-type limit-order-book model | Literature baseline; ten counting processes $N_i$ with intensities $\lambda_i$, used to measure book resiliency |
| Toke's two-agent order-book model | Literature baseline; one patient limit-order agent (with cancellation probability $\delta$) and one impatient market-order agent, volumes drawn from an exponential law |

## 7. Key References Worth Exploring

| Reference | Relevance |
|---|---|
| Hawkes, A. G. (1971), "Point spectra of some mutually exciting point processes" | The origin of the process class the entire paper is built on; also Hawkes (1971b), Hawkes (1972) on mutually exciting processes with associated variables, and Hawkes & Oakes (1974) on the cluster-process representation that underlies the $1/(1-\rho)$ amplification arithmetic |
| Daley, D. J. & Vere-Jones, D. (2003), "An Introduction to the Theory of Point Processes, Vol. I" | The paper's standing reference for marked intensities, the random time change theorem (Prop. 7.4.VI(b)) used as goodness-of-fit test (3.13), and for simulation by thinning. The single most necessary companion text |
| Liniger, T. J. (2009), "Multivariate Hawkes Processes", PhD thesis, ETH Zurich No. 18403 | Cited repeatedly for marked intensities, the normalisation of impact functions, the explicit appearance of branching coefficients, and simulation. This is where the mechanics behind (3.6)–(3.8) actually live |
| Bacry, E., Delattre, S., Hoffmann, M., Muzy, J. F. (2011), "Modelling microstructure noise with mutually exciting point processes" | The main comparator: the count-only $p(t)=N^+-N^-$ approach that this paper argues is insufficient, and the source of the alternative signature-plot-MSE calibration method |
| Toke, I. M. (2010), "'Market making' in an order book model and its impact on the spread" | The closest prior order-book model: two agents, exponential order volumes, explicit cancellation probability $\delta$. Useful precisely because it *does* model cancellations, the ~80 % of flow this paper omits |
| Large, J. (2007), "Measuring the Resiliency of an Electronic Limit Order Book", J. Financial Markets 10(1), 1–25 | The ten-order-type Hawkes formulation of a full book, including cancelled bids and asks; the natural next step for anyone wanting to extend beyond the first line |
| Ogata, Y. (1981), "On Lewis' simulation method for point processes", IEEE Trans. Inf. Theory IT-27, 23–31 | The simulation algorithm (thinning) the paper relies on but does not specify — required reading to reimplement Algorithm D |
| Vere-Jones, D. (1995), "Forecasting Earthquakes and Earthquake Risk", Int. J. Forecasting 11, 503–538 | Source of the next-event probability formula (7.1) on which the paper's entire forecast section rests, including the degenerate $\tau$-maximisation issue flagged in Algorithm E |
| Dacorogna, M. M., Gençay, R., Müller, U. A., Olsen, R., Pictet, O. V. (2001), "An Introduction to High Frequency Finance" | The data-cleaning procedure applied to both parities and the previous-tick interpolation estimator (5.5); needed to reproduce the data pipeline |
| Epps, T. W. (1979), "Comovements in stock prices in the very short run", JASA 74, 291–298 | Origin of the Epps effect, one of the two stylized facts used to validate the model (6.2) |
| Andersen, T. G., Bollerslev, T., Diebold, F. X., Labys, P. (2000), "Great Realizations", Risk Magazine, 105–108 | Origin of the signature plot (6.1), the other validation target |
| Lillo, F., Farmer, J. D., Mantegna, R. N. (2003), "Master Curve for Price Impact Function", Nature 421, 129–130 | The empirical evidence used to justify choosing a **power-law** impact function rather than an exponential one — i.e. the justification for (5.4) |
| Almgren, R. (2009), "Execution Costs", Encyclopedia of Quantitative Finance | Cited as the seminal treatment of optimal liquidation with a power-law impact function; the bridge from this model to execution scheduling |
| Gopikrishnan, P., Plerou, V., Gabaix, X., Stanley, H. E. (2000), "Statistical Properties of Share Volume Traded in Financial Markets", Phys. Rev. E 62, R4493 | Flagged by the paper itself as the study needed to replace its crude "draw deeper-limit depth from an exponential law" assumption |
| Eisler, Z., Bouchaud, J.-P., Kockelkoren, J. (2010), "The price impact of order book events: market orders, limited orders and cancellations", Quantitative Finance | Decomposes impact by order type — directly comparable to this paper's four-channel decomposition, and covers the cancellation channel it omits |
| Moro, E. et al. (2009), "Market impact and trading profile of hidden orders in stock markets", Phys. Rev. E 80, 066102 | Cited for the market-impact/volume-duration dependence that motivates marking the process with volume |
| Hautsch, N. (2012), "Econometrics of Financial High-Frequency Data", Springer | Standing reference for intertrade duration modelling; the econometric context for (4.1) and for the duration-based alternatives to Hawkes models |

---
Report generated on: 2026-08-17
Source PDF: [fauth_tudor_2012_order_book_marked_point_processes.pdf](file:d:\Repository\Quant_Trading\research\paper\volume\fauth_tudor_2012_order_book_marked_point_processes.pdf)






