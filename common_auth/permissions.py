"""App access permission checks backed by Firestore app_access documents."""

from __future__ import annotations

from common_auth import firebase_init
from common_auth.users import get_user


def can_access_app(uid: str, app_id: str) -> bool:
    """Return True if the user may access the given app.

    Rules:
    - If the user's role is 'admin', access is always granted.
    - Otherwise, an app_access/{uid}_{app_id} doc with allowed == True must exist.
    - If the user doc doesn't exist at all, access is denied.
    """
    user = get_user(uid)
    if user is None:
        return False
    if user.get("role") == "admin":
        return True

    db = firebase_init.get_firestore()
    doc_id = f"{uid}_{app_id}"
    doc = db.collection("app_access").document(doc_id).get()
    if not doc.exists:
        return False
    return bool(doc.to_dict().get("allowed", False))
