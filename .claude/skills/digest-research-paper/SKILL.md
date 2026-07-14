---
name: digest-research-paper
description: >
  Digest a research paper PDF into a structured Markdown summary report. Use
  whenever the user asks to summarize, digest, analyze, or "make a report" of a
  research paper, an academic PDF, or an arXiv download — including phrases
  like "summarize this paper", "digest the paper", "read this PDF and give me
  the key points", or after downloading a paper with a literature_search
  skill. Extracts full text with a bundled Python script, then produces a
  fixed-format digest covering summary, key topics, development ideas, tools &
  data used, and key references.
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
Sections 3–5 of the report (topics, ideas, tools & data) require the methods,
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

## 4. Ideas for Development

[Bulleted list. Each idea must be standalone — usable on its own without
depending on the other ideas or requiring them in sequence. Each one takes a
specific element of the paper and says how it could be applied or extended
elsewhere. 3–6 ideas.]

- **[Idea name]** — [what to take from the paper and where to apply it]

## 5. Tools & Data Used in This Research

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

## 6. Key References Worth Exploring

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

- Every section 1–6 present, in order, with the exact headings above.
- Every topic in section 3 has a **Why it matters** line.
- Every formula found in the paper's methods/results is present in section 2
  verbatim (LaTeX), with a worked numeric example — none dropped or reduced
  to prose-only description.
- All table content comes from the paper text — no invented tools, datasets,
  or references.
- Footer has real date and correct path.

Tell the user where the digest was saved.
