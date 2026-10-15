# Bid Intelligence Assistant — Product Requirements

**Status:** v1 definition
**Author:** Yajuwendra Dixit
**Prototype:** [this repository](https://github.com/yajuwendra-create/bid-intelligence-assistant)

> This document describes the product the prototype is a first step toward. The
> organisational model, baselines and role titles are illustrative of enterprise
> systems-integration bid processes generally, not a description of any specific
> firm's internal process. The document corpus in the prototype is synthetic.

---

## 1. Summary

A retrieval system over the firm's proposal archive that answers questions
grounded in past bids, and returns different answers to different people
according to what their role is entitled to see.

The long-term goal is not search. It is to compress the bid and solutioning
cycle. Retrieval is the wedge: it is the part of the workflow where the time is
lost today, and the part that can be delivered without changing how anyone
works.

---

## 2. Problem

A solution architect scoping a new opportunity needs to know what the firm has
proposed before — the security model used for a regulated client, the delivery
approach on a comparable programme, why a similar bid was lost. That knowledge
exists, distributed across several thousand proposal sections in a document
store, and is effectively unreachable.

Three things make it unreachable:

**Vocabulary mismatch.** The architect searches for "zero trust." The document
says "identity-based perimeterless security model." Keyword search returns
nothing. This is the ordinary RAG problem and semantic retrieval solves it.

**Mixed sensitivity within a single document.** A proposal contains the solution
architecture and the commercial model in the same file. The architect should
read the first and not the second. File-level permissions cannot express this,
so in practice the archive is either over-restricted (and unused) or
under-restricted (and a commercial risk).

**Tacit knowledge.** What to look for, and which past bids are genuinely
comparable, sits in the experience of the bid team rather than in any process
document. Nothing in the content store captures it.

Today the gap is closed by asking people. The cost is a week of elapsed time
between opportunity qualification and first proposal draft, most of it spent
waiting for someone who knows where to look.

---

## 3. Primary user

**Solution architect / delivery lead**, scoping or reviewing the technical
content of a live opportunity.

Chosen as primary over the bid partner deliberately. The architect is the volume
user, and — because v1 restricts only the commercial tier — they are the user
the entitlement model actually constrains. A product that serves the fully
cleared user well and the constrained user badly is a product that fails for
most of its users.

The bid partner is a secondary user with broader entitlements. They are served
by the same interface with no special handling in v1.

**Job to be done:** *When I am scoping a new opportunity, I want to find what we
have proposed, delivered and learned on comparable bids, so that I can produce a
technically credible response without waiting on someone else's recall.*

---

## 4. Why build

Off-the-shelf enterprise search (SharePoint Copilot, Glean and equivalents)
would be the default answer, and for most document-retrieval problems it is the
right one. Two specific reasons it isn't here.

**Entitlements operate below file granularity.** Platform tools enforce access
control at the file or site level, inherited from the content store. They can
say *you may read this document* or *you may not*. They cannot say *you may read
this document except its commercial section.* Proposal documents routinely
contain both the architecture a delivery lead must see and the pricing they must
not. Expressing that requires sensitivity classification at section level and a
retrieval layer that filters on it — which means owning the retrieval layer.

**Retrieval is phase one of a workflow product, not the product.** The end state
is bid authoring and review: drafting a response against retrieved precedent,
routing it for technical verification, tracking what was reused and what was
written fresh. A search tool cannot become that. Building the retrieval layer in
a system that can is a deliberate choice to take a slower first step toward a
larger product.

Arguments explicitly **not** relied on: that a bespoke build is more secure
(it is not — a platform vendor amortises security investment across thousands of
customers), or that it is cheaper (it is not, at v1 scale).

---

## 5. Scope

### In scope for v1

| Capability | Note |
|---|---|
| Semantic retrieval across the proposal archive | Intent-based, not keyword |
| Grounded answers with source citations | Every claim traceable to a named section |
| Sensitivity classification at section level | Four tiers |
| Role-based filtering during retrieval | Commercial tier restricted to bid partners |
| Named withheld documents | User is told relevant material exists that they cannot see |
| Document-as-query | Submit an RFP and receive matching past proposals |
| Full audit of every retrieval | Who asked, what was asked, what was returned, what was withheld |

### Out of scope for v1

| Deferred | To | Why |
|---|---|---|
| Proposal authoring | Phase 2 | Different product surface; retrieval must prove value first |
| Technical review workflow and routing | Phase 2 | Depends on authoring existing |
| Opportunity-scoped access grants | Phase 2 | v1 restricts one tier globally; per-opportunity scoping needs CRM integration |
| Hybrid retrieval (BM25 + fusion) | Phase 2 | Semantic alone is sufficient to validate the entitlement model |
| Reranking | Phase 2 | Precision tuning, not a correctness requirement |
| Non-proposal content (contracts, delivery artefacts) | Phase 2 | Different classification taxonomy |
| Multi-language | Later | Single-language corpus at launch |

---

## 6. Entitlement model

Four sensitivity tiers, assigned per document section. The test for assignment
is *what happens if the wrong person reads this.*

| Tier | Test | Example content |
|---|---|---|
| `public` | Already published, or we would send it cold to a prospect | Consented case studies, marketing material |
| `internal` | Harmless inside the firm, embarrassing outside it | Solution architectures, delivery approaches, security models, team credentials |
| `confidential` | Damaging if it reached the wrong team internally | Loss reviews, client escalations |
| `restricted` | Reveals margin, rates or negotiating position | Pricing, rate cards, commercial models |

Role entitlements for v1:

| Role | Entitled tiers |
|---|---|
| Bid Partner | public, internal, confidential, restricted |
| Solution Architect / Delivery Lead | public, internal, confidential |

The only difference in v1 is the commercial tier. This is deliberate: a single
restricted tier is enough to validate the mechanism, and every additional
distinction multiplies the classification burden before the product has proven
its value.

### Classification default

A section with no sensitivity label is treated as `restricted`. A missing label
is an absence of information, not evidence of safety.

This is correct policy with a serious operational consequence, covered in
§9.

---

## 7. Product decisions

| Decision | Choice | Trade-off accepted |
|---|---|---|
| Where entitlements are applied | During retrieval, before the prompt is constructed | Slightly more complex retrieval path |
| Unclassified content | Default `restricted` (fail closed) | Unusable without a classification review queue |
| Withheld documents | Named, not silently dropped | Reveals that a document exists |
| Which withheld to name | Only those that would have ranked in the returned set on relevance alone | Loses the long tail of blocked matches |
| Entitlement representation | Flat list of tiers per role | More verbose than a numeric level, but real entitlements are not hierarchical — "finance sees pricing but not loss reviews" breaks any `<=` comparison |
| Generation model | Smallest model that performs the task | Marginally weaker synthesis; at query volume the cost difference decides viability |
| Classification storage | In the document, not in application config | Classification travels with content when it moves or is copied |

### Why withheld documents are named

Filtering after generation leaks: restricted content has already shaped the
wording of the answer. Filtering before generation, and saying nothing, lies by
omission: the user receives a confident, cited, grounded answer with no
indication that better material existed and was withheld.

The prototype demonstrated this concretely. On a commercial query, the two
highest-scoring sections in the corpus were both restricted. The answer returned
to the delivery lead was built from the third, fourth and fifth best sources —
fluent, correctly cited, and materially weaker, with nothing in the output
revealing it.

The withheld notice is therefore a **confidence signal**, not a courtesy. It
tells the user that the answer they are reading is not the best the archive
could give, and that an access request would improve it.

---

## 8. Success metrics

### Primary

**Elapsed time from opportunity qualification to first proposal draft.**
Baseline: approximately one week, measured from CRM workflow timestamps.
Measured as a before/after comparison on comparable opportunity bands.

*Target to be set with bid operations before build. A reduction that does not
clear the cost of classification effort is not worth funding, and that threshold
should be stated explicitly rather than assumed.*

### Secondary

**Tool touchpoints per submitted proposal** — how many retrievals, by how many
distinct users, contributed to each submitted bid. Distinguishes a product in
genuine use from one opened once.

### Counter-metric

**Win rate on bids where the tool was used, against bids where it was not.**

This is the metric that must not move adversely. A system that compresses bid
preparation by 40% while degrading win rate has destroyed value, and speed
metrics alone would report it as a success. If win rate declines on
tool-assisted bids, the product is wrong regardless of what the time metric
says.

### Not used as a metric

User-reported confidence in retrieval results. It is a proxy for satisfaction,
not for outcome, and a user can be confidently wrong. Retrieval quality is
measured against a held-out question set, not by asking users how they felt.

---

## 9. Access grants

v1 restricts the commercial tier globally rather than per opportunity.

**Request flow:** a user without commercial entitlement who needs it raises a
request in the system. Approval sits with the **VP, Commercial** for the
business unit, with second-level confirmation from the **Finance Director, Bid
Operations**. Dual approval reflects that the content is commercially sensitive
rather than merely internal.

**Grant duration:** one week from approval, then automatic expiry. Time-bound by
default rather than revoked manually — standing exceptions accumulate and become
the de facto permission model.

**Audit:** every grant, every retrieval and every withheld document is logged
with the requester, the query and the intent captured at request time. The audit
trail is a v1 requirement, not a later addition: it is what makes the commercial
tier defensible to a security reviewer.

Per-opportunity scoping — grants tied to a specific opportunity ID and expiring
when the bid closes — requires CRM integration and is deferred to phase 2.

---

## 10. Open design questions

**Document-as-query.** A long RFP is not a query. Three candidate approaches:
summarise the document into a small set of queries; embed its sections and
retrieve against each; or extract structured requirements first and retrieve per
requirement. The third is most likely correct and most expensive. This needs a
decision and a spike before it is committed to v1 scope.

**Classification granularity.** Sections are currently classified as whole
units. A section containing one sensitive paragraph is classified by its most
sensitive content, which over-restricts the rest. Sub-section classification
would be more precise and considerably harder to maintain.

**Review queue ownership.** A classification review queue is required (§11).
Who works it, and against what service level, is unresolved — and if the answer
is "the bid team, when they have time," the queue will not be worked.

---

## 11. Launch dependencies

These must exist before the product can go live in a real firm. They are not
features.

**1. Classification coverage.** Measured on the prototype corpus, nine of ten
sections defaulted to `restricted` because no one had ever classified them,
leaving the delivery lead able to see one section in ten. The product did not
work for its primary user. The security policy was correct; the coverage was
not.

This generalises: **permission-aware retrieval is only as good as its
classification coverage, and coverage is a data-governance problem rather than
an AI problem.** An archive of unlabelled documents is the normal state of an
enterprise content store. A classification review queue, with an owner and a
service level, is therefore a launch dependency rather than a later feature.

**2. Question taxonomy from the bid team.** What the team actually looks for
sits in their experience, not in process documentation. Capturing it requires
scheduled time with bid and proposal practitioners, and it is the input to the
held-out evaluation set. Without it there is no way to know whether retrieval
quality is adequate.

**3. Compliance position on client content.** Running proposal content — which
embeds client requirements and sometimes client-confidential material — through
a hosted model needs a documented position covering data residency, retention
and the terms under which content is processed.

**4. Identity integration.** In the prototype the role is a function argument.
In production it must come from the identity provider, with the entitlement
service as the source of truth. Role as user-selectable input is a security
hole, not a simplification.

**5. A defined path for wrong answers.** The system will produce grounded,
cited, incorrect answers — usually by retrieving a genuinely comparable bid
whose circumstances differ in a way that matters. Users need a way to flag this,
and the flags need to reach someone. Absent that, the first confidently wrong
answer in a live bid ends adoption.

---

## 12. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Classification never gets done | Product unusable for its primary user | Treat as launch dependency with named owner; measure coverage as a release gate |
| Over-restriction drives users back to asking colleagues | Silent failure — usage simply decays | Monitor withheld-notice frequency per user; a high rate indicates misclassification, not misuse |
| Grounded but wrong answers accepted uncritically | Weak bids submitted with false confidence | Mandatory citations; held-out evaluation set; feedback path per §11.5 |
| Commercial content leaks via the retrieval layer | Serious | Filter during retrieval, never post-generation; audit every retrieval; dual approval on grants |
| Scope expands into authoring before retrieval proves value | Neither capability ships | Phase line in §5 is a commitment, not a preference |

---

## 13. What the prototype establishes

The prototype in this repository is not the product. It establishes three things
that the product depends on:

1. **The mechanism works.** The same query, against the same index, returns
   different document sets to different roles, with entitlements applied during
   ranking rather than stripped from results afterwards.

2. **Permission filtering degrades answer quality invisibly.** Demonstrated and
   measured, not asserted. This is the finding that justifies naming withheld
   documents, and it would not have been visible without building it.

3. **Classification coverage is the binding constraint.** Also measured. It
   moves the review queue from a backlog item to a launch dependency, and it is
   the single most likely reason a deployment of this product would fail.
