# Bid Intelligence Assistant

A RAG system over enterprise proposal documents where **the same query returns
different answers depending on the asker's entitlements**.

Retrieval is filtered by clearance during ranking, not stripped from results
afterwards — and when a document is withheld, the user is told it exists.

---

## The problem

A bid manager at 11pm needs to know what security approach the firm proposed to
a healthcare client two years ago. The answer is in a proposal archive of
several thousand sections. Keyword search fails because the document says
"identity-based perimeterless security model" and nobody searches for that.

That part is ordinary RAG. The part that isn't ordinary: the archive also
contains rate cards, margin assumptions and loss reviews. A delivery architect
and a bid partner must not get the same answer to the same question — and the
system has to handle that without becoming unusable for the person with less
clearance.

## What makes this different

Most retrieval systems treat access control as a post-processing step: retrieve,
then remove what the user can't see. That is wrong in two ways.

1. **It leaks.** If filtering happens after generation, restricted content has
   already shaped the wording of the answer.
2. **It lies by omission.** Silently dropping documents teaches the user the
   archive is empty, so they stop asking.

This system applies entitlements during ranking, so the model never receives a
document the asker isn't cleared for. And it returns two lists — what you got,
and what was withheld — so the withheld notice can act as a **confidence
signal**: *better sources exist, and you aren't cleared for them.*

---

## How it works

```
docs/*.txt
    │
    ├─ parse header ──────────► metadata (title, client, year, section,
    │                                     sensitivity, outcome)
    │
    └─ body text ─────────────► embed (BAAI/bge-base-en-v1.5, 768-dim, local)
                                     │
query ─────── embed ─────────────────┤
                                     ▼
                        cosine similarity over all documents
                                     │
                         rank ALL documents, best first
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
          sensitivity ∈ role's tiers      sensitivity ∉ role's tiers
                    │                                 │
                 top_k                      score ≥ cutoff, top_k
                    │                                 │
                  hits                             withheld
                    │                                 │
                    ▼                                 ▼
        grounded generation                 "2 documents withheld
        (Claude Haiku, cited)                at your clearance"
```

Entitlement model:

| Role | Can see |
|---|---|
| Bid Partner | public, internal, confidential, restricted |
| Delivery Lead | public, internal, confidential |

---

## Three findings

These came out of building it, not out of planning it. They are the reason the
project was worth doing.

### 1. Classification coverage decides whether the feature works at all

A missing `Sensitivity:` label is an absence of information, not evidence that a
document is safe — so the parser **fails closed** and defaults to the most
restrictive tier.

Correct policy. Then the corpus was measured:

```
{'restricted': 9, 'confidential': 1}
```

Nine of ten documents restricted, seven of them only because nobody had ever
classified them. A Delivery Lead could see **one document out of ten.** The
product did not work for the role that needed it most.

The policy wasn't the problem. Coverage was — and an archive full of unlabelled
documents is the normal state of any enterprise content store.

> **Permission-aware retrieval is only as good as your classification coverage.
> Coverage is a data-governance problem, not an AI problem — and it determines
> whether the AI feature is usable at all.**

A classification review queue is therefore not a later feature. It is a launch
dependency. After classifying the corpus against an explicit test — *what
happens if the wrong person reads this?* — visible results for a Delivery Lead
went from 1 to 3.

### 2. Permission filtering silently degrades answer quality

Query: *"commercial model and pricing"*, as a Delivery Lead:

```
withheld   0.669  07_pricing_legacy        ← highest score in the corpus
           0.621  04_pricing_meridian      ← second highest
hits       0.585  03_casestudy_retail      ← best the asker can see
           0.573  02_delivery_northwind
           0.570  05_lossreview_apex
```

The two best matches in the archive are the two this user cannot see. The system
answers from the third, fourth and fifth best sources — and the answer is still
fluent, still cited, still grounded in real documents. Nothing in the answer
text reveals that better material existed.

This is the strongest argument for naming withheld documents. Without that
notice, the user walks away believing they received the best answer the archive
had.

### 3. Relevance and entitlement are orthogonal

The embedding model never sees the sensitivity label — only body text is
embedded. It ranks by meaning. The filter cuts by clearance. The two axes are
independent, and a document can be the single best match while being invisible
to the asker.

Easy mistake, worth naming: the withheld scores above are not low *because*
those documents are sensitive. The pricing documents scored highest precisely
because the query was about pricing. `06_architecture_apex.txt` scored lowest
because a solution architecture genuinely isn't similar to a pricing question —
a relevance fact that happens to coincide with a clearance fact.

---

## Design decisions

| Decision | Choice | Why | Trade-off accepted |
|---|---|---|---|
| Unlabelled documents | Default to `restricted` | A missing label is unknown risk, not low risk | Needs a review queue to stay usable |
| Entitlement model | Flat list of tiers per role | Real entitlements aren't a clean hierarchy — "finance sees pricing but not loss reviews" breaks a numeric `<=` | More verbose to configure |
| Filter position | During ranking, before the prompt | Post-filtering means restricted content already shaped the answer | Slightly more code in the hot path |
| Withheld documents | Named, not dropped | Silent filtering trains users that the archive is empty | Reveals that a document exists |
| Which withheld to name | Only those scoring ≥ the weakest returned result | Naming irrelevant blocked documents turns the notice into wallpaper | Loses the long tail of blocked matches |
| Threshold type | Relative, not a fixed number | Self-calibrates per query; cosine scores aren't comparable across embedding models | Harder to explain than "0.55" |
| Embedded text | Body only, not header | Header text such as `security_compliance` was inflating relevance for keyword-adjacent queries | Loses metadata as a retrieval signal |
| Generation model | Claude Haiku | Summarising supplied context needs no frontier reasoning; at query volume the cost difference decides viability | Marginally weaker synthesis |

The relative threshold in one line:

```python
cutoff = hits[-1][1] if hits else 0.0
```

No visible results at all means a cutoff of `0.0`, so everything withheld gets
named — a user cleared for nothing still needs to know the archive isn't empty.

---

## Running it

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

python app.py
```

First run downloads the embedding model (~440MB). Embeddings are computed
locally — no document content leaves the machine except the retrieved extracts
sent for generation.

Output:

```
Loaded 10 documents
{'internal': 5, 'restricted': 3, 'confidential': 2}
Embedded 10 documents, 768 dimensions

DL  hits: ['03_casestudy_retail.txt', '02_delivery_northwind.txt', '05_lossreview_apex.txt']
DL  held: ['07_pricing_legacy.txt', '04_pricing_meridian.txt']
BP  hits: ['07_pricing_legacy.txt', '04_pricing_meridian.txt', '03_casestudy_retail.txt']
BP  held: []
```

Same query. Same index. Different answers.

---

## Corpus

Ten synthetic proposal sections across four fictional clients, each with a
metadata header and body text. Deliberately synthetic — real client proposals
cannot leave the firm, and a portfolio project that depends on confidential
material isn't a portfolio project.

The corpus is seeded with cases that exercise the entitlement logic: pricing
documents that outrank everything else on commercial queries, a loss review that
is confidential rather than restricted, and documents whose best match is
invisible to the lower-cleared role.

---

## Not built

Stated plainly, because a portfolio project that claims completeness isn't
credible:

- **Hybrid retrieval** — semantic only. BM25 plus reciprocal rank fusion would
  improve recall on exact identifiers (client names, contract numbers)
- **Chunking** — whole sections are embedded as single units. Fine at this size,
  wrong at thousands of documents
- **Reranking** — a cross-encoder second stage would improve precision at the
  top of the ranking
- **Vector database** — in-memory NumPy. Correct at ten documents, not at ten
  thousand
- **Real authentication** — the role is a function argument, not an identity.
  Production needs SSO and an entitlement service as the source of truth
- **Audit trail** — who asked what, and which documents were withheld from them,
  should be logged. Designed for, not implemented
- **Evaluation harness** — no faithfulness or relevance scoring yet

---

## Stack

Python · `sentence-transformers` (BAAI/bge-base-en-v1.5) · NumPy · Anthropic API
(Claude Haiku) · `python-dotenv`

---

Built by [Yajuwendra Dixit](https://www.linkedin.com/in/yajuwendra-dixit) as an
original portfolio project — product decisions and implementation both.
