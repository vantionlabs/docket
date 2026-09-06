"""Shared teardown for the integration lane.

These tests run against a real database that is not reset between runs, so
each one cleans up after itself. Deleting the org cascades everything that
hangs off it; deleting the user clears what is still user-scoped.
"""

from sqlalchemy import select

from app.db.models import Membership, Organization


def _purge(db, user) -> None:
    """Remove a test user and every org they own."""
    org_ids = [
        m.org_id for m in db.scalars(select(Membership).where(Membership.user_id == user.id))
    ]
    db.delete(user)
    db.commit()
    for org_id in org_ids:
        org = db.get(Organization, org_id)
        if org is not None:
            db.delete(org)
    db.commit()
