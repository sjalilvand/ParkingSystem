"""موتور قوانین ورود/خروج (موج ۵a) — ساختار معتبر، عملیات ازپیش‌تعریف‌شده.
هیچ eval/SQL دلخواه وجود ندارد. قوانین فقط می‌توانند تشدید کنند یا برای
پلاک ناشناسِ متقاضی محوطه مسیر کنترل‌شده باز کنند؛ محدودیت/غیرفعال را
نمی‌شکنند و بازکردن راهبند فقط از مسیر تصمیم ALLOW سرور می‌گذرد."""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.access_control.models import ParkingSession
from app.modules.config_admin.models import EntryExitRule, VehicleGroup
from app.modules.finance.models import Charge
from app.modules.violations.models import Violation

CONDITION_FIELDS = {
    "membership_kind", "is_resident", "has_valid_permit", "yard_full",
    "covered_free_count", "has_open_session", "has_debt",
    "confirmed_violations_count", "driver_request", "time_window", "gate_code",
    "plate_in",
}
ACTIONS = {
    "show_message", "require_driver_selection", "refer_to_guard", "deny",
    "allow_with_warning", "notify_field_op", "issue_receipt", "request_payment",
}
SOFTEN_PROTECTED_REASONS = {"PLATE_RESTRICTED", "VEHICLE_INACTIVE"}


async def build_context(db: AsyncSession, *, direction, gate, plate_raw, normalized,
                        vehicle, permit, driver_request, now) -> dict:
    from app.capacity import count_confirmed_occupancy, yard_capacity_decision
    from app.modules.parking.models import ParkingSpace

    ctx: dict = {
        "direction": direction, "gate_code": gate.code if gate else None,
        "plate_normalized": normalized, "driver_request": driver_request,
        "is_resident": bool(vehicle is not None and vehicle.unit_id),
        "has_valid_permit": permit is not None,
        "now": now.isoformat(),
    }
    membership = None
    if vehicle is not None and getattr(vehicle, "vehicle_group_id", None):
        g = await db.get(VehicleGroup, vehicle.vehicle_group_id)
        if g is not None:
            membership = g.membership_kind
    ctx["membership_kind"] = membership

    declared = getattr(settings, "YARD_CAPACITY_TOTAL", None)
    if declared and declared > 0:
        confirmed = await count_confirmed_occupancy(db)
        ok, _ = yard_capacity_decision(declared, confirmed)
        ctx["yard_full"] = not ok
        ctx["yard_free"] = max(0, declared - confirmed)
    else:
        ctx["yard_full"] = False
        ctx["yard_free"] = None

    free_spaces = await db.scalar(select(func.count()).select_from(ParkingSpace)
                                  .where(ParkingSpace.status == "FREE", ParkingSpace.is_active.is_(True)))
    ctx["covered_free_count"] = int(free_spaces or 0)

    open_sess = await db.scalar(select(func.count()).select_from(ParkingSession)
                                .where(ParkingSession.plate_normalized == normalized,
                                       ParkingSession.status == "OPEN")) if normalized else 0
    ctx["has_open_session"] = bool(open_sess)

    if normalized:
        sess_ids = (await db.execute(select(ParkingSession.id).where(
            ParkingSession.plate_normalized == normalized))).scalars().all()
        debt = 0
        if sess_ids:
            rows = (await db.execute(select(Charge).where(
                Charge.parking_session_id.in_(sess_ids), Charge.status == "UNPAID"))).scalars().all()
            debt = sum(max(0, c.amount - (c.paid_amount or 0)) for c in rows)
        ctx["has_debt"] = debt > 0
        ctx["debt_amount"] = debt
        confirmed_v = await db.scalar(select(func.count()).select_from(Violation).where(
            Violation.plate_normalized == normalized, Violation.status == "CONFIRMED"))
        ctx["confirmed_violations_count"] = int(confirmed_v or 0)
    else:
        ctx["has_debt"] = False
        ctx["debt_amount"] = 0
        ctx["confirmed_violations_count"] = 0
    return ctx


def _match_condition(cond: dict, ctx: dict) -> bool:
    field, op = cond.get("field"), cond.get("op")
    if field not in CONDITION_FIELDS or field not in ctx:
        return False
    val = ctx[field]
    target = cond.get("value")
    try:
        if op == "true":
            return bool(val) is True
        if op == "false":
            return bool(val) is False
        if op == "eq":
            return val == target
        if op == "ne":
            return val != target
        if op == "in":
            return val in (target or [])
        if op == "not_in":
            return val not in (target or [])
        if op == "gte":
            return val is not None and val >= target
        if op == "lte":
            return val is not None and val <= target
        if op == "time_window":
            cur = datetime.now(timezone.utc).time()
            f_t = datetime.strptime(target["from"], "%H:%M").time()
            t_t = datetime.strptime(target["to"], "%H:%M").time()
            return (f_t <= cur <= t_t) if f_t <= t_t else (cur >= f_t or cur <= t_t)
    except Exception:
        return False
    return False


def _apply_action(act: dict, overrides: dict, warnings: list) -> None:
    a, p = act.get("action"), act.get("params") or {}
    if a not in ACTIONS:
        warnings.append(f"UNKNOWN_ACTION:{a}")
        return
    if a == "show_message":
        overrides["message"] = str(p.get("text", ""))
    elif a == "require_driver_selection":
        overrides["require_driver_selection"] = True
    elif a == "refer_to_guard":
        overrides["decision"] = "REQUIRE_OPERATOR_APPROVAL"
        overrides["reason"] = p.get("reason", "RULE_REFER_GUARD")
    elif a == "deny":
        overrides["decision"] = "DENY"
        overrides["reason"] = p.get("reason", "RULE_DENY")
    elif a == "allow_with_warning":
        overrides["decision"] = "ALLOW_WITH_WARNING"
        overrides["reason"] = p.get("reason", "RULE_ALLOW")
    elif a == "notify_field_op":
        overrides["notify_field_op"] = True
    elif a == "issue_receipt":
        overrides["issue_receipt"] = True
    elif a == "request_payment":
        overrides["request_payment"] = True


async def apply_rules_for_event(db: AsyncSession, *, direction, gate, plate_raw, normalized,
                                vehicle, permit, decision, reason, warnings,
                                driver_request, now) -> tuple[dict, dict | None]:
    rules = (await db.execute(
        select(EntryExitRule)
        .where(EntryExitRule.status == "ACTIVE", EntryExitRule.enabled.is_(True),
               EntryExitRule.direction.in_([direction, "ANY"]))
        .order_by(EntryExitRule.priority.asc())
    )).scalars().all()
    if not rules:
        return {}, None

    ctx = await build_context(db, direction=direction, gate=gate, plate_raw=plate_raw,
                              normalized=normalized, vehicle=vehicle, permit=permit,
                              driver_request=driver_request, now=now)

    for r in rules:
        if r.effective_from and now < r.effective_from:
            continue
        conds = r.conditions or []
        results = [_match_condition(c, ctx) for c in conds]
        matched = all(results) if (r.condition_mode or "ALL").upper() == "ALL" else any(results)
        if not matched:
            continue
        trace = {"rule_id": r.id, "rule_name": r.name, "conditions": conds,
                 "condition_results": results, "actions": r.actions, "context": ctx}
        overrides: dict = {"warnings": []}
        soften_blocked = reason in SOFTEN_PROTECTED_REASONS
        for act in (r.actions or []):
            a = act.get("action")
            if soften_blocked and a in ("allow_with_warning", "refer_to_guard"):
                overrides["warnings"].append("RULE_SOFTEN_BLOCKED")
                continue
            _apply_action(act, overrides, overrides["warnings"])
            # هرگز از DENY/REQUIRE به ALLOW نرو (فقط مسیر مخالف مجاز است)
            if (a == "allow_with_warning"
                    and decision in ("DENY", "REQUIRE_OPERATOR_APPROVAL")
                    and reason not in ("UNKNOWN_PLATE", "NO_ACTIVE_PERMIT")):
                overrides.pop("decision", None)
                overrides.pop("reason", None)
                overrides["warnings"].append("RULE_SOFTEN_BLOCKED")
        return overrides, trace
    return {}, None
