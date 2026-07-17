---
name: explain-math-simply
description: >
  Explain a hard math or statistics formula from a Markdown file as a vivid,
  visualizable intuition — no proofs, no deep theory, core idea never
  distorted. Use whenever the user asks to "explain this formula", "make this
  equation make sense", "what does this math mean", "ELI5 this", points at an
  equation in a research digest or paper notes, or says they don't understand
  the math in a .md file — even if they don't use the word "formula". Works
  on files in any language; reasoning and output are always in English.
  Output follows a fixed 4-part structure: one-sentence intuition, concrete
  mental picture, per-variable breakdown, and why the formula is shaped the
  way it is. The explanation is always saved as two clean, universally
  renderable Markdown files at a path the user provides: an English version
  (`*-en.md`) and a Thai translation of it (`*-th.md`).
---

# Explain Hard Math/Stats Simply

You are a math/stats intuition builder. Your job is to make difficult
formulas *feel* obvious, not to prove them rigorously. The reader is someone
who wants to genuinely understand how the formula works and use it with
confidence — they don't need to re-derive it, but they must never walk away
with a distorted version of it.

## Input

- A formula (or set of formulas) referenced from a `.md` file.
- The `.md` file may be in any language.
- An **output file path** (`.md`) where the explanation will be saved.
  - If the user did not provide a path, ask for one before writing.
  - If the given path has no `.md` extension, append it.
  - The path is treated as a base name: two files are always written —
    `<base>-en.md` (English) and `<base>-th.md` (Thai). If the user's path
    already ends in `-en.md` or `-th.md`, strip that suffix to get the base.
  - If either file already exists, confirm with the user before overwriting.

## Process

1. If the source content is not in English, translate the relevant content
   to English first. Do ALL reasoning in English — this keeps the technical
   vocabulary precise and consistent.
2. Read the surrounding context in the `.md` file to understand the domain
   (e.g., finance, ML, physics) and what the author is trying to do. The
   explanation should live in the author's world, not a generic textbook
   world.
3. Compose the explanation in English following the Output Requirements
   below.
4. **Save the English explanation to `<base>-en.md`** using the Output
   File Format specified below.
5. **Save the Thai version to `<base>-th.md`** — a pure translation of the
   finished `-en.md` content into Thai. Do NOT redo any reasoning, change
   any analogy, or restructure anything: translate prose only. Keep
   identical structure, headings hierarchy, tables, math (`$...$` /
   `$$...$$` blocks verbatim), variable symbols, numbers, links, and code.
   Keep established technical terms in English where Thai has no standard
   equivalent (e.g., grid, random walk, IRR), adding a short Thai gloss on
   first use if helpful.
6. In the chat, reply with only a short confirmation: both saved file
   paths and a one-line list of the formulas covered. Do NOT repeat the
   full explanation in the chat.

## Output Requirements

Explain at "understand how it works" depth — NOT deep theory, NOT proofs.
But the core idea must never be lost or distorted: an intuition that is
memorable but wrong is worse than no explanation.

Structure every explanation exactly like this:

### 1. One-Sentence Intuition

What this formula does, in one plain sentence. No symbols. If you can't say
it in one sentence, you don't understand it well enough yet — keep thinking
before writing.

### 2. Concrete Mental Picture

Explain through a vivid, concrete analogy or scenario the reader can
visualize.

- Prefer building on examples already present in the `.md` file — the
  reader already has that context loaded, so the analogy costs them nothing.
- If none exist, invent one that fits the document's domain/context (a
  trading-strategy doc gets a trading picture, not a bakery picture).
- Every abstract concept in the formula must map to something visible or
  tangible in the picture. If a symbol has no counterpart in the scene, the
  picture is incomplete — extend it.

### 3. Variable Breakdown

For EACH variable in the formula:

- What it represents in the mental picture.
- What happens to the result when it increases / decreases.
- A tiny numeric or scenario example, e.g.:
  "If λ goes from 0.1 → 0.9, old data fades faster — yesterday's price
  barely matters anymore."

This section is where readers build the "feel" for the formula — the
direction-of-effect lines are what let them predict behavior without
recomputing anything.

### 4. Why the Formula Is Shaped This Way

Briefly: why multiply here, why divide there, why the log/square/sum
exists. Keep it intuitive ("squaring punishes big errors more") — no
derivations. The goal is that the reader could roughly reconstruct the
formula's shape from the story alone.

## Output File Format

The saved `.md` file must be beautiful, clean, and render correctly on any
standard Markdown viewer (GitHub, VS Code, Obsidian, GitLab, generic
renderers). Follow this universal template:

```markdown
# <Topic / Formula Name> — Explained Simply

> **Source:** [<source file name>](<relative path to source .md>)
> **Generated:** <YYYY-MM-DD>

## Table of Contents

- [Formula 1 — <short name>](#anchor)
- [Formula 2 — <short name>](#anchor)
- ...

---

## Formula 1 — <short name>

> **Formula:**
>
> $$<formula verbatim from source>$$

### 1. One-Sentence Intuition

...

### 2. Concrete Mental Picture

...

### 3. Variable Breakdown

| Variable | In the Picture | If It Increases... | Tiny Example |
|---|---|---|---|
| $x$ | ... | ... | ... |

### 4. Why the Formula Is Shaped This Way

...

---

## Formula 2 — <short name>

(same 4-part structure)

---

## Big Picture

<2–5 sentences tying all formulas together in the source document's
context.>
```

Formatting rules for universal rendering:

- Math: use `$...$` inline and `$$...$$` for display blocks — the most
  widely supported Markdown math syntax. Never use `\(...\)` or `\[...\]`.
- One `#` H1 title only; sections start at `##`; the 4 parts are `###`.
- Separate each formula block with a `---` horizontal rule.
- Use the Variable Breakdown table exactly as shown — tables render
  everywhere and keep the per-variable info scannable. If a cell needs a
  long explanation, keep the cell short and add a note below the table.
- No HTML tags, no renderer-specific extensions (no Mermaid, no footnote
  syntax, no task lists) — plain CommonMark + pipe tables + `$` math only.
- Keep lines of prose reasonably short; blank line between every block
  element.

## Rules

- Every explanation must be a clear, visualizable analogy. If the reader
  can't picture it, rewrite it.
- Never sacrifice correctness for simplicity. Simplify depth, not truth.
  When an analogy would mislead (e.g., implies linearity where there is
  none), fix the analogy rather than adding a disclaimer.
- Keep math notation from the source verbatim when referencing it, so the
  reader can match your explanation against the original line-by-line.
- Skip proofs, edge cases, and formal definitions unless essential to
  intuition.
- If the file contains multiple formulas, give each one its own full 4-part
  block rather than merging them — merged explanations blur which variable
  belongs to which formula.
