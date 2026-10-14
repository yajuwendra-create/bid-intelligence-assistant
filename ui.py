# ============================================================
#  BID INTELLIGENCE — UI
#  Thin Streamlit front end over app.py.
#
#  Deliberately thin: all retrieval, filtering and generation
#  logic lives in app.py. This file only draws widgets and
#  passes their values through. If the UI needs business logic
#  to work, the logic is in the wrong place.
# ============================================================

import streamlit as st

# Importing from app.py runs everything at its top level —
# loading documents and computing embeddings. That happens once
# when Streamlit starts the script, which is what we want: the
# model load is the slow part (~5s) and shouldn't repeat.
from app import answer, ROLES


st.title("Bid Intelligence")

# Role selector. Options come from ROLES itself rather than a
# hardcoded list, so adding a role in app.py automatically
# appears here — one source of truth for the entitlement model.
role = st.selectbox("Viewing as", list(ROLES.keys()))

query = st.text_input("Query")

# Streamlit re-runs the whole script on every interaction, so
# st.button() is True only on the run triggered by the click.
# Everything inside this block runs once per search — which is
# why the expensive API call sits here and not at module level.
if st.button("Search"):

    # Same function the command line uses. The UI knows nothing
    # about embeddings, sensitivity tiers or thresholds — it
    # passes a role and a query and renders what comes back.
    text, withheld = answer(query, role=role)

    st.write(text)

    # The withheld notice is the product's honesty mechanism:
    # it tells the user that relevant material exists which
    # their clearance doesn't cover, so they can request access
    # rather than assuming this was the best answer available.
    if withheld:
        st.warning(f"{len(withheld)} document(s) withheld at your clearance")