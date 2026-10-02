from datetime import datetime, timezone


def offline_decide(snapshot: dict | None, plate_normalized: str | None,
                   direction: str, locally_inside: bool) -> dict:
    """تصمیم آفلاین بر اساس آخرین Snapshot (سیاست بخش ۱۷-۴ سند)."""
    if snapshot is None:
        return {"decision": "OFFLINE_REQUIRE_REVIEW", "decision_reason": "NO_LOCAL_SNAPSHOT", "barrier_action": "KEEP_CLOSED"}

    allowed = {p["plate"]: p for p in snapshot.get("allowed_plates", [])}
    restricted = {p["plate"] for p in snapshot.get("restricted_plates", [])}

    if plate_normalized is None:
        return {"decision": "OFFLINE_REQUIRE_REVIEW", "decision_reason": "PLATE_NOT_READABLE", "barrier_action": "KEEP_CLOSED"}

    if plate_normalized in restricted:
        return {"decision": "OFFLINE_REQUIRE_REVIEW", "decision_reason": "PLATE_RESTRICTED", "barrier_action": "KEEP_CLOSED"}

    if direction == "OUT":
        if locally_inside or plate_normalized in allowed:
            return {"decision": "OFFLINE_ALLOW", "decision_reason": "OFFLINE_EXIT_OK", "barrier_action": "OPEN"}
        return {"decision": "OFFLINE_REQUIRE_REVIEW", "decision_reason": "NO_LOCAL_ENTRY_RECORD", "barrier_action": "KEEP_CLOSED"}

    permit = allowed.get(plate_normalized)
    if permit is None:
        return {"decision": "OFFLINE_REQUIRE_REVIEW", "decision_reason": "PLATE_NOT_IN_SNAPSHOT", "barrier_action": "KEEP_CLOSED"}

    vu = permit.get("valid_until")
    if vu:
        try:
            if datetime.fromisoformat(vu) < datetime.now(timezone.utc):
                return {"decision": "OFFLINE_REQUIRE_REVIEW", "decision_reason": "PERMIT_EXPIRED", "barrier_action": "KEEP_CLOSED"}
        except Exception:
            pass

    # F22 (§۴/§ح): سقف ورود مجوز در حالت آفلاین هم رعایت شود (محافظه‌کارانه:
    # سقف پرشده => نیاز به بررسی، نه عبور قطعی)
    max_entries = permit.get("max_entries")
    used_entries = permit.get("used_entries") or 0
    if max_entries is not None and used_entries >= max_entries:
        return {"decision": "OFFLINE_REQUIRE_REVIEW", "decision_reason": "PERMIT_MAX_ENTRIES_REACHED", "barrier_action": "KEEP_CLOSED"}

    return {"decision": "OFFLINE_ALLOW", "decision_reason": "PLATE_IN_LOCAL_SNAPSHOT", "barrier_action": "OPEN"}
