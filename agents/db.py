"""Shared Firestore client for all agents.

Single instantiation point — avoids 6 separate Client() calls across modules.
Returns None when Firestore is unavailable (local dev without credentials).
"""

try:
    from google.cloud import firestore
    db = firestore.Client()
except Exception:
    db = None
