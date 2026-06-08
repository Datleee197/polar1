"""
ops_core.constants
~~~~~~~~~~~~~~~~~~

Central constants for the ops_core cog.
All default config values, version info, and namespace prefixes live here.
"""

# ---------------------------------------------------------------------------
# Cog metadata
# ---------------------------------------------------------------------------
COG_NAME = "OpsCore"
COG_VERSION = "0.3.0"
COG_IDENTIFIER = 2738100538  # Unique Red Config identifier (random stable int)

# ---------------------------------------------------------------------------
# Custom-ID namespace prefix  (used by persistent views in later stages)
# ---------------------------------------------------------------------------
CUSTOM_ID_PREFIX = "ops_core"

# ---------------------------------------------------------------------------
# Approval Queue constants
# ---------------------------------------------------------------------------
APPROVAL_ID_PREFIX = "APPROVAL"

# ---------------------------------------------------------------------------
# Ticket System constants
# ---------------------------------------------------------------------------
TICKET_ID_PREFIX = "TICKET"

TICKET_TYPES = {
    "report":  {"label": "Report Violation", "emoji": "\U0001f6a8", "staff": "mod_role_ids"},
    "bug":     {"label": "Report System Bug", "emoji": "\U0001f41b", "staff": "dev_role_ids"},
    "appeal":  {"label": "Appeal", "emoji": "\u2696\ufe0f", "staff": "mod_role_ids"},
    "other":   {"label": "Other", "emoji": "\U0001f4ac", "staff": "staff_role_ids"},
}

# ---------------------------------------------------------------------------
# Embed colours
# ---------------------------------------------------------------------------
COLOUR_PRIMARY = 0x5865F2   # Discord blurple
COLOUR_PENDING = 0xFEE75C   # Yellow
COLOUR_APPROVED = 0x57F287  # Green
COLOUR_DENIED = 0xED4245    # Red
COLOUR_TICKET_OPEN = 0x5865F2 # Blurple
COLOUR_TICKET_CLOSED = 0x95A5A6 # Grey

# ---------------------------------------------------------------------------
# Default guild configuration schema
# ---------------------------------------------------------------------------
DEFAULT_GUILD = {
    # Channel IDs
    "support_channel_id": None,
    "ticket_archive_channel_id": None,
    "approval_review_channel_id": None,
    "admin_log_channel_id": None,

    # Quarantine
    "quarantine_role_id": None,

    # Staff / role groups
    "staff_role_ids": [],
    "dev_role_ids": [],
    "mod_role_ids": [],

    # Approval role options  (key -> role_id mapping set by admin)
    "approval_role_options": {},

    # Panel message IDs  (so the bot can find its own panels after restart)
    "panel_messages": {
        "support_panel": None,
        "approval_panel": None,
        "admin_panel": None,
    },

    # Active runtime data  (keyed by ID strings)
    "active_tickets": {},
    "approval_requests": {},
    "quarantine_cases": {},
}
