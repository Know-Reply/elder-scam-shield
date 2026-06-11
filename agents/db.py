"""Shared Firestore client for all agents.

Single instantiation point — avoids 6 separate Client() calls across modules.
Returns None when Firestore is unavailable (local dev without credentials,
or the Firestore API not enabled in the project).

The database name comes from FIRESTORE_DATABASE (default: elder-shield, a
Native-mode database — the project's "(default)" database is Datastore
mode and unusable by the Firestore client).

Client construction succeeds even when the API is disabled, so a cheap
probe runs once at import: it fails fast (3 s) instead of letting every
call site hit multi-minute gRPC retry loops. Every consumer guards with
`if db is not None` and falls back to mock/demo data.
"""

import os

try:
    from google.cloud import firestore
    db = firestore.Client(database=os.environ.get("FIRESTORE_DATABASE", "elder-shield"))
    next(iter(db.collections(timeout=3.0)), None)
except Exception:
    db = None
