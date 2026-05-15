# EAU Guidelines — MCQ Generation Pipeline

Scripts per generare quiz a risposta multipla dalle linee guida urologiche EAU.

## Struttura

```
scripts/
├── generate_all.py          # Master: genera tutte le guidelines
├── generate_guideline.py    # 1 guideline → tutte le sezioni
├── generate_section.py      # 1 sezione → MCQs
└── utils/
    ├── splitter.py          # Text → chunks (semantic, sentence-aligned)
    ├── verifier.py          # Verify MCQ against source text
    ├── reranker.py          # Score + rank questions
    └── dedup.py             # Jaccard dedup across chunks
```

## Pipeline

```
Chapter JSON → extract_bullets() → bullet list
                               ↓
                    [1 bullet = 1 MCQ call]
                               ↓
                        [verify] → verified
                               ↓
                        [dedup] → final
                               ↓
                    data/questions/{g}/{s}.json
```

## Usage

```bash
# Generate a single section (test)
python scripts/generate_section.py prostate-cancer treatment#6.4.6

# Generate all sections of one guideline
python scripts/generate_guideline.py prostate-cancer

# Generate all guidelines
python scripts/generate_all.py
```

## Design Principles

- **Sequential LLM calls** — no parallelism (rate limit safety)
- **Bullet extraction** → MCQ per bullet (contesto ridotto, zero troncamento)
- **Verifier** reference = full section text (non il chunk)
- **50% context limit** = ~400K chars working cap (M2.7 = 800K context)
- **No cron, no scheduling** — run manually when guidelines update (~1x/year)