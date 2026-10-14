# ============================================================
#  BID INTELLIGENCE ASSISTANT
#  Permission-aware RAG over enterprise proposal documents.
#
#  The point of this system: the same query returns different
#  answers depending on who is asking. Entitlements are applied
#  during retrieval, not stripped from results afterwards.
#
#  Pipeline:  load -> parse metadata -> embed -> search
#             -> filter by role -> generate grounded answer
# ============================================================

import os
import numpy as np
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from anthropic import Anthropic

# API key is read from .env (never hardcoded, never committed —
# .env is in .gitignore)
load_dotenv()
client = Anthropic()


# ------------------------------------------------------------
#  1. ENTITLEMENT MODEL
# ------------------------------------------------------------
# Each role maps to the sensitivity tiers it may see.
# PM decision: this is deliberately a flat list, not a numeric
# level. Real entitlements are rarely a clean hierarchy —
# "finance can see pricing but not loss reviews" breaks a
# simple <= comparison. A list scales to that; a number doesn't.
ROLES = {
    "Bid Partner":   ["public", "internal", "confidential", "restricted"],
    "Delivery Lead": ["public", "internal", "confidential"],
}


# ------------------------------------------------------------
#  2. DOCUMENT PARSING
# ------------------------------------------------------------
def parse_document(text):
    """
    Split a document into metadata header and body.

    Expected file shape:
        Title: ...
        Client: ...
        Sensitivity: RESTRICTED      <- optional
        <blank line>
        ...body text...
    """
    # partition splits on the FIRST blank line only, so blank
    # lines inside the body don't break the parse
    header, _, body = text.partition("\n\n")
# - parses the metadata from the header
    meta = {}
    for line in header.split("\n"):
        if ":" in line:
            # split on the first colon only — values can contain colons
            key, value = line.split(":", 1)
            meta[key.strip().lower()] = value.strip()

    meta["content"] = body.strip()

    # FAIL CLOSED: a missing Sensitivity label is an absence of
    # information, not evidence the document is safe. Default to
    # the most restrictive tier.
    # PM consequence: untagged documents become Partner-only and
    # effectively invisible to everyone else — so this design
    # requires a classification review queue to be operable.
    meta["sensitivity"] = meta.get("sensitivity", "restricted").lower()

    return meta

# - loads the documents from the folder
def load_documents(folder="docs"):
    """Read every file in the folder, parsed, in filename order."""
    documents = []
    for filename in sorted(os.listdir(folder)):
        with open(os.path.join(folder, filename)) as f:
            doc = parse_document(f.read())
            doc["filename"] = filename   # needed for citations
            documents.append(doc)
    return documents
# loads the documents from the folder
docs = load_documents()
print(f"Loaded {len(docs)} documents")


#  - counts the number of documents at each sensitivity level
def sensitivity_counts(docs):
    """Count the number of documents at each sensitivity level."""
    counts = {}
    for doc in docs:
        counts[doc["sensitivity"]] = counts.get(doc["sensitivity"], 0) + 1
    return counts

print(sensitivity_counts(docs))



# ------------------------------------------------------------
#  3. EMBEDDING
# ------------------------------------------------------------
# bge-base-en-v1.5 runs locally — no API cost, no data leaving
# the machine. 768 dimensions.
# PM decision: a larger model scores marginally better on
# retrieval benchmarks but costs more memory and latency per
# query. For a 2,800-section corpus this is the right trade.
model = SentenceTransformer("BAAI/bge-base-en-v1.5")

# Embedding BODY ONLY, not the header.
# Finding worth recording: when headers were included, header
# text like "Security Architecture / security_compliance" was
# inflating relevance for keyword-adjacent queries. Ranking
# changed once removed. Metadata in the embedded text is a
# retrieval-quality lever, not a neutral choice.
texts = [d["content"] for d in docs]
embeddings = model.encode(texts)

# docs, texts and embeddings are PARALLEL ARRAYS.
# Index i refers to the same document in all three. Everything
# below depends on that alignment holding.
print(f"Embedded {len(embeddings)} documents, {len(embeddings[0])} dimensions")


# ------------------------------------------------------------
#  4. PERMISSION-AWARE RETRIEVAL  <- the differentiating feature
# ------------------------------------------------------------
def search(query, role, top_k=3):
    """
    Rank all documents by semantic similarity, then split the
    ranking into what this role may see and what it may not.

    Returns (hits, withheld) — both lists of (filename, score).

    Why two lists: withheld documents are NAMED, not silently
    dropped. A user who can see that a restricted pricing
    document exists knows to request access. Silent filtering
    teaches users the archive is empty and they stop asking.
    """
    allowed = ROLES[role]

    query_vec = model.encode(query)
    scores = model.similarity(query_vec, embeddings)[0]
       # EVERY index, best score first. No slice here — the filter
    # must run over the full ranking, or a user whose best 3
    # matches are all restricted gets nothing instead of their
    # best permitted ones.
    ranked = list(np.argsort(-scores))

    visible = [i for i in ranked if docs[i]["sensitivity"] in allowed][:top_k]
    hits = [(docs[i]["filename"], float(scores[i])) for i in visible]

    # Relative threshold: only name a withheld document if it
    # would have made the top_k on relevance alone. Anything
    # scoring below the weakest result we actually returned
    # wasn't going to be shown regardless of clearance, so
    # naming it is noise — and noise trains users to ignore the
    # withheld notice entirely.
    #
    # Self-calibrating per query, so it survives a change of
    # embedding model. A fixed number would not.
    #
    # No visible results at all -> cutoff 0.0 -> name everything.
    # A user cleared for nothing still needs to know the archive
    # isn't empty.

    cutoff = hits[-1][1] if hits else 0.0

    blocked = [i for i in ranked
               if docs[i]["sensitivity"] not in allowed
               and scores[i] >= cutoff][:top_k]
    withheld = [(docs[i]["filename"], float(scores[i])) for i in blocked]

    return hits, withheld

# ------------------------------------------------------------
#  5. GROUNDED GENERATION
# ------------------------------------------------------------
def answer(query, role, top_k=3):
    """
    Retrieve within the role's entitlements, then generate an
    answer grounded only in those extracts.

    The LLM never sees a document the role isn't entitled to.
    Filtering happens before the prompt is built, not after the
    answer comes back — post-filtering would mean restricted
    content had already influenced the wording.
    """
    hits, withheld = search(query, role=role, top_k=top_k)

    # Build the context block the model is allowed to use.
    # Filenames go in as tags so citations are verifiable.
    context = ""
    for filename, score in hits:
        doc = next(d for d in docs if d["filename"] == filename)
        context += f"[{filename}]\n{doc['content']}\n\n"

    # Three instructions doing three jobs:
    #   "ONLY"        - forbids outside knowledge
    #   "Cite"        - makes every claim traceable
    #   "say so"      - gives the model a legitimate way to fail
    #                   instead of inventing an answer
    prompt = f"""Answer the question using ONLY the proposal extracts below.
Cite the source filename in square brackets after each claim.
If the extracts do not contain the answer, say so.

EXTRACTS:
{context}

QUESTION: {query}"""

    # Haiku, not Sonnet. This task is summarisation over supplied
    # context — no reasoning the smaller model can't do. At
    # thousands of queries a month the cost difference is the
    # difference between viable and not.
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )

    # Returning withheld alongside the answer so the UI can show
    # "2 documents withheld at your clearance"
    return response.content[0].text, withheld


# ------------------------------------------------------------
#  6. PERMISSION TEST
# ------------------------------------------------------------
# A query aimed straight at the restricted tier. The two roles
# must return different document sets or the feature isn't real.
q = "commercial model and pricing"

hits, withheld = search(q, role="Delivery Lead")
print("\nDL  hits:", [f for f, s in hits])
print("DL  held:", [f for f, s in withheld])

hits, withheld = search(q, role="Bid Partner")
print("BP  hits:", [f for f, s in hits])
print("BP  held:", [f for f, s in withheld])

