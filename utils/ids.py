"""
ops_core.utils.ids
~~~~~~~~~~~~~~~~~~

Deterministic ID generation for operational records.
"""

from ..constants import APPROVAL_ID_PREFIX


def next_approval_id(existing_requests: dict) -> str:
    """Return the next sequential approval request ID.

    Scans existing request keys (e.g. ``APPROVAL-000003``) and returns
    the next one in sequence.  If no requests exist, starts at
    ``APPROVAL-000001``.

    Parameters
    ----------
    existing_requests:
        The current ``approval_requests`` dict from guild Config.

    Returns
    -------
    str
        A string like ``APPROVAL-000042``.
    """
    if not existing_requests:
        return f"{APPROVAL_ID_PREFIX}-000001"

    max_num = 0
    for key in existing_requests:
        # key format: "APPROVAL-000001"
        try:
            num = int(key.split("-", 1)[1])
            if num > max_num:
                max_num = num
        except (IndexError, ValueError):
            continue

    return f"{APPROVAL_ID_PREFIX}-{max_num + 1:06d}"
