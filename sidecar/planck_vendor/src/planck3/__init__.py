"""
Planck 3.0: a "System One" SGS policy for web retrieval.

The model never writes free text. It picks typed actions from a closed
vocabulary (see actions.py) and scores candidates; deterministic tools
(web.py, candidates.py) do search / fetch / extract, and a local store
(store.py) holds everything learned. Plan: SETUP_092026_planck3.md.
"""
