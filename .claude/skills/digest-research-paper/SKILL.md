---
name: digest-research-paper
description: >
  Digest a research paper PDF into a structured Markdown summary report. Use
  whenever the user asks to summarize, digest, analyze, or "make a report" of a
  research paper, an academic PDF, or an arXiv download — including phrases
  like "summarize this paper", "digest the paper", "read this PDF and give me
  the key points", or after downloading a paper with a literature_search
  skill. Extracts full text with a bundled Python script, then produces a
  fixed-format digest covering summary, key topics, step-by-step algorithm
  logic, development ideas, tools & data used, and key references.
---

# Digest Research Paper

Turn a research paper PDF into a structured Markdown digest. The digest is a
standalone report a reader can use *instead of* reading the paper, so it must
preserve the paper's key points — never trade completeness for brevity.

## Workflow

### Step 1 — Extract the PDF text

Run the bundled extraction script (handles UTF-8 and chunking; do not write
your own extractor):

```bash
uv run <skill-dir>/scripts/extract_pdf.py --pdf <paper.pdf> --outdir <scratch-dir>/extracted
```

The script prints JSON with `page_count`, `chunk_files` (UTF-8 text files,
each ≤60k chars, split on page boundaries), and any embedded PDF metadata
(title/author). Exit code 2 means a scanned/image-only PDF with no extractable
text — tell the user and stop; do not fabricate a digest.

### Step 2 — Read the full text

Read **every** chunk file, in order. Do not digest from the abstract alone —
Sections 3–6 of the report (topics, algorithm logic, ideas, tools & data)
require the methods,
results, and bibliography sections, which live deep in the paper. While
reading, collect:

- Bibliographic facts: full title, all authors, their institutions, the
  publisher/venue (journal, conference, or "arXiv preprint"), and a canonical
  link (DOI URL preferred; else arXiv abs URL; else publisher URL).
- The core contribution, method, experimental setup, main results (with
  actual numbers), and stated limitations.
- Every software tool, library, dataset, model, and algorithm mentioned in
  the methods/experiments — these feed the report's tables.
- The references the paper leans on most (cited repeatedly or credited as the
  foundation of the method).
- **Condition-dependence evidence** for Section 5's Strong/Weak analysis:
  every statement about when the method works well or poorly (market regime,
  data scale, noise level, parameter sensitivity), where it appears (results
  breakdown, limitation section, ablation), and the formulas whose terms
  reveal failure modes (e.g. a term that grows with volatility or drift).
- **The complete logic of every algorithm/method the paper proposes or
  relies on** — its inputs, each processing step in order, the decision
  rules, and its outputs. Capture enough detail to re-explain the algorithm
  step by step in Section 4 without going back to the paper.
- **Every formula/equation central to the method or results** (loss
  functions, pricing/return formulas, statistical tests, algorithm update
  rules, etc.). Never drop or paraphrase a formula away — carry the exact
  math forward to Step 3. If the paper works a numeric example through the
  formula, capture those numbers too; if it doesn't, prepare your own
  worked example using representative numbers so the formula isn't left
  abstract.

If a bibliographic field genuinely is not in the paper (institutions are
sometimes omitted from preprints), write `Not stated in paper` — never guess.

### Step 3 — Write the digest

Save as `<pdf_basename>_digest.md` in the same directory as the source PDF,
unless the user names a different output location. Use **exactly** this
structure:

```markdown
# [Original Paper Title]

## 1. Paper Information

| Fields | Detail |
|---|---|
| Title | ... |
| Author | ... (all authors, comma-separated) |
| Institution | ... |
| Publisher | ... (venue, or "arXiv preprint" + category) |
| Link | ... (clickable URL) |

## 2. Summary

[A numbered list (1., 2., 3., …) of substantial points, in the paper's
logical order: motivation → method → experimental setup → main results with
concrete numbers → limitations. Each number is a full point of several
sentences, not a one-line fragment. "Not too short": a reader should get
every key point of the paper from this section alone. Typically 6–10
numbered points for a normal-length paper. **Bold** the key terms, model
names, and headline numbers inside each point so the section is skimmable.]

1. [First point...]
2. [Second point...]

**Formulas: mandatory, never omitted.** If the point being described involves
a formula/equation in the paper, the formula MUST appear in that numbered
point — in LaTeX (`$...$` inline or `$$...$$` block), exactly as derived in
the paper, with every symbol defined. Immediately follow it with a worked
example: plug in concrete numbers (from the paper if it gives any, otherwise
representative numbers you choose) and show the resulting value. Never
summarize a formula in prose only ("the return is calculated based on price
difference") — write the actual equation and compute it once.

## 3. Key Importance Topics

### [Topic name]
[What the paper says about it.]

**Why it matters:** [Required for every topic — explain the significance,
not just restate the topic.]

### [Next topic...]
[3–6 topics total, drawn from the paper's actual contributions.]

## 4. Algorithm Logic — Step-by-Step

[One subsection per core algorithm/method in the paper. Explain the logic
step by step, in plain language a reader new to the topic can follow —
never assume the reader has read the paper. Each algorithm gets:]

### [Algorithm/Method name]

**Goal:** [one sentence — what problem this algorithm solves.]

**Inputs:** [what goes in.] **Outputs:** [what comes out.]

**Steps:**

1. **[Step name]** — [what happens in this step and *why*, in plain
   language. If the step uses a formula, show it in LaTeX with symbols
   defined.]
2. [Next step...]

**Worked example:** [Walk the full algorithm once end-to-end with concrete
numbers — from the paper if it gives any, otherwise representative numbers
you choose. Show the intermediate value after each step so the reader can
follow along and check their understanding. This example is mandatory for
every algorithm — never leave the steps abstract.]

## 5. Ideas for Development

[Bulleted list. Each idea must be standalone — usable on its own without
depending on the other ideas or requiring them in sequence. Each one takes a
specific element of the paper and says how it could be applied or extended
elsewhere. Where an idea builds on an algorithm explained in Section 4,
say so explicitly — name the algorithm and which of its steps the idea
modifies, extends, or reuses. 3–6 ideas.]

- **[Idea name]** — [what to take from the paper and where to apply it;
  reference the Section 4 algorithm/step it builds on, when applicable]
  - **Strong:** [condition/regime/situation where the idea performs well,
    e.g. "sideways market, low volatility"] — [one-line reason] *(From paper)*
  - **Strong:** [another favorable condition, if any] — [reason] *(From AI)*
  - **Weak:** [condition/regime/situation where the idea degrades or fails,
    e.g. "trending market, high volatility"] — [one-line reason] *(From AI)*

**Strong/Weak rules — mandatory for every idea:**

- Every idea carries at least one **Strong** and at least one **Weak**
  bullet. More than one of each is allowed and encouraged when the paper or
  the math supports it — strengths and weaknesses are rarely singular.
- Tag every Strong/Weak bullet with its source:
  - *(From paper)* — the paper itself states or demonstrates it (results
    table, limitation section, regime analysis). Point to the evidence:
    section, experiment, or number.
  - *(From AI)* — your own analysis, derived from the paper's formulas or
    from provable math/statistics logic. Attach the one-line derivation,
    e.g. "grid profit per cycle = level spacing − 2×fee, but a trend of
    length > n·k exits the range with all lots underwater, so expected PnL
    turns negative when |drift| exceeds the grid range". Reason from the
    equations captured in Sections 2/4 whenever possible.
- *(From AI)* points must be **provable** — grounded in a formula, a
  statistical property (variance, drift, expectation, sample size), or a
  scientific argument the reader can check. Never write unfalsifiable or
  hand-wavy claims ("markets usually behave", "AI will make it better");
  if a point cannot be argued from math/stats/science, drop it.
- The same condition may appear tagged both ways when the paper states it
  and your analysis extends it — keep the tags separate so the reader knows
  which claims are the paper's and which are yours.

## 6. Tools & Data Used in This Research

### Software & Library

| Tools | Purpose in paper |
|---|---|
| ... | ... |

### Data Source

| Source | Description |
|---|---|
| ... | ... |

### Models & Algorithms

| Model/Algorithm | Role |
|---|---|
| ... | ... |

## 7. Key References Worth Exploring

| Reference | Relevance |
|---|---|
| [Author (Year), "Title"] | [why this reference matters for follow-up reading] |

---
Report generated on: YYYY-MM-DD
Source PDF: [paper_name.pdf](file:Path_of_paper)
```

Footer rules: use today's real date; `paper_name.pdf` is the source PDF's
filename; `Path_of_paper` is its absolute path.

Readability: the digest is meant to be skimmed. Throughout the report,
**bold** the terms a skimming reader's eye should catch — model names,
dataset names, headline numbers/results, and the verdict words in "Why it
matters" lines. Bold the first word(s) of each numbered summary point and
each development idea. Don't bold whole sentences; highlight loses meaning
when everything is highlighted.

If any table has nothing to report (e.g., a pure theory paper with no
software), keep the section and write a single row `| None reported | — |`
rather than dropping it — the fixed structure is the point.

### Step 4 — Verify before finishing

- Every section 1–7 present, in order, with the exact headings above.
- Every topic in section 3 has a **Why it matters** line.
- Every core algorithm/method in the paper has a section 4 subsection with
  Goal, Inputs/Outputs, numbered steps, and a worked end-to-end example
  with intermediate values — none left abstract.
- Every section 5 idea that builds on an algorithm names the section 4
  algorithm/step it relates to.
- Every section 5 idea has at least one **Strong** and one **Weak** bullet,
  each tagged *(From paper)* or *(From AI)*; every *(From AI)* bullet
  carries a checkable math/stats justification — no unprovable claims.
- Every formula found in the paper's methods/results is present in section 2
  verbatim (LaTeX), with a worked numeric example — none dropped or reduced
  to prose-only description.
- All table content comes from the paper text — no invented tools, datasets,
  or references.
- Footer has real date and correct path.

Tell the user where the digest was saved.
