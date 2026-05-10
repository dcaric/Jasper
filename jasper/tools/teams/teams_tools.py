import html
from datetime import datetime

import requests

from ...utility.config import get_setting, log_event


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


def _clean_html(value):
    if not value:
        return ""
    text = value.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    text = html.unescape(text)
    return " ".join(text.split())


def _as_list(raw_value):
    if not raw_value:
        return []
    return [item.strip() for item in str(raw_value).split(",") if item.strip()]


def _build_headers():
    token = get_setting("TEAMS_ACCESS_TOKEN")
    if not token:
        return None, "Error: Please set TEAMS_ACCESS_TOKEN in .env."
    return {"Authorization": f"Bearer {token}"}, None


def _graph_get(path, params=None):
    headers, err = _build_headers()
    if err:
        return None, err

    try:
        response = requests.get(f"{GRAPH_BASE_URL}{path}", headers=headers, params=params, timeout=25)
        if response.status_code >= 400:
            detail = response.text[:400]
            log_event("TEAMS", f"Graph GET failed {path}: {response.status_code} {detail}")
            return None, f"Teams Graph error ({response.status_code}): {detail}"
        return response.json(), None
    except Exception as exc:
        log_event("TEAMS", f"Graph GET exception {path}: {exc}")
        return None, f"Teams request failed: {str(exc)}"


def _matches_filters(message, sender=None, subject=None, body=None, date_from=None, date_to=None):
    sender_value = (message.get("sender") or "").lower()
    subject_value = (message.get("subject") or "").lower()
    body_value = (message.get("body") or "").lower()

    def contains(needle, haystack):
        return not needle or needle.lower() in haystack

    if not contains(sender, sender_value):
        return False
    if not contains(subject, subject_value):
        return False
    if body and body.lower() not in body_value:
        return False

    received = message.get("received_raw")
    if received:
        try:
            received_dt = datetime.fromisoformat(received.replace("Z", "+00:00"))
            if date_from and received_dt < date_from.astimezone(received_dt.tzinfo):
                return False
            if date_to and received_dt > date_to.astimezone(received_dt.tzinfo):
                return False
        except Exception:
            pass

    return True


def _normalize_chat_message(message, container_name, container_type):
    body = _clean_html((((message or {}).get("body") or {}).get("content")) or "")
    sender_info = (((message or {}).get("from") or {}).get("user") or {})
    sender_name = sender_info.get("displayName") or "Unknown sender"
    created = message.get("createdDateTime") or message.get("lastModifiedDateTime") or "Unknown date"
    short_body = body[:1000]
    preview = short_body[:120] or "Teams message"
    subject = f"{container_name}: {preview}"

    return {
        "id": message.get("id"),
        "message_id": message.get("id"),
        "subject": subject,
        "sender": sender_name,
        "received": created,
        "received_raw": created,
        "body": short_body,
        "web_url": message.get("webUrl"),
        "source": "teams",
        "container_type": container_type,
        "container_name": container_name,
    }


def _search_chats(limit, per_chat_limit):
    chat_data, err = _graph_get("/me/chats", params={"$top": limit})
    if err:
        return None, err

    results = []
    for chat_item in chat_data.get("value", []):
        chat_id = chat_item.get("id")
        if not chat_id:
            continue
        topic = chat_item.get("topic") or f"Chat {chat_id[:8]}"
        msg_data, msg_err = _graph_get(f"/chats/{chat_id}/messages", params={"$top": per_chat_limit})
        if msg_err:
            log_event("TEAMS", f"Skipping chat {chat_id}: {msg_err}")
            continue
        for message in msg_data.get("value", []):
            results.append(_normalize_chat_message(message, topic, "chat"))
    return results, None


def _search_channels(per_channel_limit):
    team_ids = _as_list(get_setting("TEAMS_TEAM_IDS"))
    if not team_ids:
        return [], None

    results = []
    for team_id in team_ids:
        team_data, team_err = _graph_get(f"/teams/{team_id}")
        team_name = team_id
        if not team_err and team_data:
            team_name = team_data.get("displayName") or team_name

        channel_data, channel_err = _graph_get(f"/teams/{team_id}/channels", params={"$top": 25})
        if channel_err:
            log_event("TEAMS", f"Skipping team {team_id}: {channel_err}")
            continue

        channel_filter_ids = set(_as_list(get_setting(f"TEAMS_CHANNEL_IDS_{team_id.replace('-', '_').upper()}")))

        for channel in channel_data.get("value", []):
            channel_id = channel.get("id")
            if not channel_id:
                continue
            if channel_filter_ids and channel_id not in channel_filter_ids:
                continue

            channel_name = channel.get("displayName") or channel_id
            msg_data, msg_err = _graph_get(
                f"/teams/{team_id}/channels/{channel_id}/messages",
                params={"$top": per_channel_limit},
            )
            if msg_err:
                log_event("TEAMS", f"Skipping channel {channel_id}: {msg_err}")
                continue

            for message in msg_data.get("value", []):
                container = f"{team_name} / {channel_name}"
                results.append(_normalize_chat_message(message, container, "channel"))

    return results, None


def find_messages(sender_name=None, subject_text=None, body_text=None, limit=10, date_from=None, date_to=None):
    """
    Read-only Teams search.
    Phase 1 searches:
    - User chats via /me/chats
    - Optional configured channels via TEAMS_TEAM_IDS
    """
    safe_limit = max(1, min(int(limit), 50))
    chat_limit = max(1, min(int(get_setting("TEAMS_CHAT_LIMIT", 10)), 25))
    per_chat_limit = max(safe_limit, min(int(get_setting("TEAMS_MESSAGES_PER_CHAT", 20)), 50))
    per_channel_limit = max(safe_limit, min(int(get_setting("TEAMS_MESSAGES_PER_CHANNEL", 20)), 50))

    chat_results, chat_err = _search_chats(chat_limit, per_chat_limit)
    if chat_err:
        return chat_err

    channel_results, channel_err = _search_channels(per_channel_limit)
    if channel_err:
        log_event("TEAMS", f"Channel search warning: {channel_err}")

    combined = (chat_results or []) + (channel_results or [])
    filtered = [
        item for item in combined
        if _matches_filters(
            item,
            sender=sender_name,
            subject=subject_text,
            body=body_text,
            date_from=date_from,
            date_to=date_to,
        )
    ]

    filtered.sort(key=lambda item: item.get("received_raw", ""), reverse=True)
    return filtered[:safe_limit]
