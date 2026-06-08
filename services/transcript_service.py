"""
ops_core.services.transcript_service
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

HTML transcript generation for tickets.
"""

from __future__ import annotations

import html
import logging
from datetime import timezone

import discord

log = logging.getLogger("red.ops_core.transcript")

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ticket Transcript - {ticket_id}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            background-color: #36393f;
            color: #dcddde;
            margin: 0;
            padding: 20px;
        }}
        .header {{
            background-color: #2f3136;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        .header h1 {{ margin: 0 0 10px 0; color: #ffffff; }}
        .meta {{ font-size: 0.9em; color: #b9bbbe; }}
        .message {{
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid #4f545c;
        }}
        .msg-header {{
            display: flex;
            align-items: baseline;
            margin-bottom: 5px;
        }}
        .author {{ font-weight: bold; color: #ffffff; margin-right: 10px; }}
        .timestamp {{ font-size: 0.8em; color: #72767d; }}
        .content {{ white-space: pre-wrap; }}
        .attachment {{ color: #00aff4; text-decoration: none; }}
        .attachment:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Ticket {ticket_id}</h1>
        <div class="meta">
            <div><strong>Type:</strong> {ticket_type}</div>
            <div><strong>Guild:</strong> {guild_name}</div>
            <div><strong>Channel:</strong> {channel_name}</div>
            <div><strong>Opened By:</strong> {opener_id}</div>
            <div><strong>Created:</strong> {created_at}</div>
            <div><strong>Closed:</strong> {closed_at}</div>
            <div><strong>Closed By:</strong> {closed_by}</div>
        </div>
    </div>
    <div class="messages">
{messages}
    </div>
</body>
</html>
"""


async def generate_transcript(
    channel_or_thread: discord.TextChannel | discord.Thread,
    ticket_data: dict,
) -> tuple[bytes | None, str | None]:
    """Fetch message history and generate an HTML transcript.

    Returns ``(html_bytes, error_message)``.
    """
    try:
        messages = [m async for m in channel_or_thread.history(limit=None, oldest_first=True)]
    except discord.Forbidden:
        return None, f"Missing permissions to read message history in {channel_or_thread.mention}."
    except discord.HTTPException as exc:
        return None, f"Discord API error reading history: {exc}"

    msg_html_list = []
    for msg in messages:
        # Escape all unsafe strings
        author_name = html.escape(str(msg.author.display_name))
        author_id = msg.author.id
        timestamp = msg.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Message content could have HTML-unsafe chars
        content = html.escape(msg.content)
        
        attachments_html = ""
        if msg.attachments:
            att_links = []
            for a in msg.attachments:
                safe_url = html.escape(a.url)
                safe_filename = html.escape(a.filename)
                att_links.append(f'<a class="attachment" href="{safe_url}" target="_blank">[{safe_filename}]</a>')
            attachments_html = "<br>" + " ".join(att_links)

        msg_html = (
            f'        <div class="message">\n'
            f'            <div class="msg-header">\n'
            f'                <span class="author">{author_name} ({author_id})</span>\n'
            f'                <span class="timestamp">{timestamp}</span>\n'
            f'            </div>\n'
            f'            <div class="content">{content}{attachments_html}</div>\n'
            f'        </div>'
        )
        msg_html_list.append(msg_html)

    # Prepare ticket metadata
    ticket_id = html.escape(str(ticket_data.get("ticket_id", "Unknown")))
    ticket_type = html.escape(str(ticket_data.get("ticket_type", "Unknown")))
    guild_name = html.escape(str(channel_or_thread.guild.name))
    channel_name = html.escape(str(channel_or_thread.name))
    opener_id = html.escape(str(ticket_data.get("user_id", "Unknown")))
    created_at = html.escape(str(ticket_data.get("created_at", "Unknown")))
    closed_at = html.escape(str(ticket_data.get("closed_at", "Unknown")))
    closed_by = html.escape(str(ticket_data.get("closed_by", "Unknown")))

    final_html = _HTML_TEMPLATE.format(
        ticket_id=ticket_id,
        ticket_type=ticket_type,
        guild_name=guild_name,
        channel_name=channel_name,
        opener_id=opener_id,
        created_at=created_at,
        closed_at=closed_at,
        closed_by=closed_by,
        messages="\n".join(msg_html_list)
    )

    return final_html.encode("utf-8"), None
