"""APIهای مدیریتی تنظیمات/قوانین/گروه‌ها (موج ۵a) — مجوزها در لایه API (§۸)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.audit import write_audit
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_any_permission
from app.db.session import get_db
from app.modules.config_admin.models import (
    AppSetting, AppSettingHistory, BoxSetting, EntryExitRule,
    ReceiptTemplate, VehicleGroup,
)
from app.modules.identity.models import User

router = APIRouter(tags=["Config"])


def _perm_view(): return require_any_permission("settings.view", "rules.view", "groups.view")
def _perm_edit(): return require_any_permission("settings.edit", "rules.edit", "groups.edit")
def _perm_publish(): return require_any_permission("settings.publish", "rules.publish")


# ---------------- vehicle groups ----------------

class GroupBody(BaseModel):
    code: str | None = None
    title: str
    description: str | None = None
    membership_kind: str = "NONRESIDENT_YARD"
    is_active: bool = True
    sort_order: int = 0
    default_tariff_id: str | None = None


@router.get("/vehicle-groups")
async def list_groups(db: AsyncSession = Depends(get_db), user: User = Depends(_perm_view())):
    rows = (await db.execute(select(VehicleGroup).order_by(VehicleGroup.sort_order, VehicleGroup.code))).scalars().all()
    return [{"id": g.id, "code": g.code, "title": g.title, "description": g.description,
             "membership_kind": g.membership_kind, "is_active": g.is_active,
             "sort_order": g.sort_order, "default_tariff_id": g.default_tariff_id} for g in rows]


@router.post("/vehicle-groups")
async def create_group(body: GroupBody, db: AsyncSession = Depends(get_db), user: User = Depends(_perm_edit())):
    if not body.code:
        raise ConflictError("کد گروه الزامی است")
    if (await db.execute(select(VehicleGroup).where(VehicleGroup.code == body.code))).scalar_one_or_none():
        raise ConflictError("کد گروه تکراری است")
    g = VehicleGroup(**body.model_dump())
    db.add(g)
    if user:
        await write_audit(db, user_id=user.id, action="GROUP_CREATE", module="groups",
                          entity_type="vehicle_group", entity_id=g.id, new_values={"code": g.code})
    await db.commit()
    await db.refresh(g)
    return {"id": g.id, "code": g.code}


@router.patch("/vehicle-groups/{group_id}")
async def update_group(group_id: str, body: GroupBody, db: AsyncSession = Depends(get_db), user: User = Depends(_perm_edit())):
    g = await db.get(VehicleGroup, group_id)
    if not g:
        raise NotFoundError("گروه یافت نشد")
    for k, v in body.model_dump(exclude_unset=True, exclude={"code"}).items():
        setattr(g, k, v)
    if user:
        await write_audit(db, user_id=user.id, action="GROUP_UPDATE", module="groups",
                          entity_type="vehicle_group", entity_id=g.id)
    await db.commit()
    return {"success": True}


# ---------------- entry/exit rules ----------------

class RuleBody(BaseModel):
    name: str
    description: str | None = None
    direction: str = "ANY"
    priority: int = 100
    enabled: bool = True
    condition_mode: str = "ALL"
    conditions: list[dict] = Field(default_factory=list)
    actions: list[dict] = Field(default_factory=list)
    effective_from: datetime | None = None


@router.get("/rules")
async def list_rules(db: AsyncSession = Depends(get_db), user: User = Depends(require_any_permission("rules.view", "settings.view"))):
    rows = (await db.execute(select(EntryExitRule).order_by(EntryExitRule.priority))).scalars().all()
    return [{"id": r.id, "name": r.name, "description": r.description, "direction": r.direction,
             "priority": r.priority, "enabled": r.enabled, "condition_mode": r.condition_mode,
             "conditions": r.conditions, "actions": r.actions, "status": r.status,
             "effective_from": r.effective_from.isoformat() if r.effective_from else None} for r in rows]


@router.post("/rules")
async def create_rule(body: RuleBody, db: AsyncSession = Depends(get_db), user: User = Depends(require_any_permission("rules.edit", "settings.edit"))):
    r = EntryExitRule(**body.model_dump(), created_by=user.id if user else None)
    db.add(r)
    if user:
        await write_audit(db, user_id=user.id, action="RULE_CREATE", module="rules",
                          entity_type="entry_exit_rule", entity_id=r.id, new_values={"name": r.name})
    await db.commit()
    await db.refresh(r)
    return {"id": r.id, "status": r.status}


@router.patch("/rules/{rule_id}")
async def update_rule(rule_id: str, body: RuleBody, db: AsyncSession = Depends(get_db), user: User = Depends(require_any_permission("rules.edit", "settings.edit"))):
    r = await db.get(EntryExitRule, rule_id)
    if not r:
        raise NotFoundError("قانون یافت نشد")
    data = body.model_dump(exclude_unset=True)
    for k in ("name", "description", "direction", "priority", "enabled",
              "condition_mode", "conditions", "actions", "effective_from"):
        if k in data:
            setattr(r, k, data[k])
    if r.status == "ACTIVE":
        r.status = "DRAFT"  # هر ویرایش، بازگشت به پیش‌نویس تا انتشار مجدد (§۹)
    if user:
        await write_audit(db, user_id=user.id, action="RULE_UPDATE", module="rules",
                          entity_type="entry_exit_rule", entity_id=r.id)
    await db.commit()
    return {"success": True, "status": r.status}


@router.post("/rules/{rule_id}/publish")
async def publish_rule(rule_id: str, body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(_perm_publish())):
    r = await db.get(EntryExitRule, rule_id)
    if not r:
        raise NotFoundError("قانون یافت نشد")
    r.status = "ACTIVE"
    r.approved_by = user.id if user else None
    r.approved_at = datetime.now(timezone.utc)
    if user:
        await write_audit(db, user_id=user.id, action="RULE_PUBLISH", module="rules",
                          entity_type="entry_exit_rule", entity_id=r.id, reason=body.get("reason"))
    await db.commit()
    return {"success": True, "status": r.status}


@router.post("/rules/{rule_id}/disable")
async def disable_rule(rule_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(_perm_publish())):
    r = await db.get(EntryExitRule, rule_id)
    if not r:
        raise NotFoundError("قانون یافت نشد")
    r.status = "DISABLED"
    if user:
        await write_audit(db, user_id=user.id, action="RULE_DISABLE", module="rules",
                          entity_type="entry_exit_rule", entity_id=r.id)
    await db.commit()
    return {"success": True}


# ---------------- app settings (versioned) ----------------

DEFAULTS: dict[str, dict] = {
    "tariff_policy": {
        "free_minutes": 90, "hourly_amount": 250000, "daily_max_amount": 500000,
        "rounding": "HOUR_UP", "day_definition": "CALENDAR",
        "exit_grace_minutes": 20, "resident_discount_percent": 0,
        "_needs_decision": ["rounding", "day_definition", "resident_discount_percent"],
    },
    "violation_policy": {"default_penalty_amount": 1000000, "requires_image": True,
                         "_needs_decision": ["default_penalty_amount"]},
}


@router.get("/app-settings/{key}")
async def get_setting(key: str, db: AsyncSession = Depends(get_db), user: User = Depends(_perm_view())):
    row = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    base = DEFAULTS.get(key, {})
    if row is None:
        return {"key": key, "value": base, "is_default": True}
    return {"key": key, "value": row.value, "is_default": False,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None}


@router.put("/app-settings/{key}")
async def put_setting(key: str, body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(require_any_permission("settings.edit"))):
    row = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    old = row.value if row else None
    if row is None:
        row = AppSetting(key=key, value=body.get("value", {}), updated_by=user.id if user else None)
        db.add(row)
    else:
        row.value = body.get("value", {})
        row.updated_by = user.id if user else None
    db.add(AppSettingHistory(key=key, old_value=old, new_value=row.value,
                             changed_by=user.id if user else None,
                             reason=body.get("reason") or "MANUAL_EDIT"))
    if user:
        await write_audit(db, user_id=user.id, action="SETTING_UPDATE", module="settings",
                          entity_type="app_setting", entity_id=key,
                          new_values={"reason": body.get("reason")})
    await db.commit()
    return {"success": True}


@router.get("/app-settings/{key}/history")
async def setting_history(key: str, db: AsyncSession = Depends(get_db), user: User = Depends(_perm_view())):
    rows = (await db.execute(select(AppSettingHistory).where(AppSettingHistory.key == key)
                             .order_by(AppSettingHistory.changed_at.desc()).limit(50))).scalars().all()
    return [{"id": h.id, "old_value": h.old_value, "new_value": h.new_value,
             "reason": h.reason, "changed_at": h.changed_at.isoformat() if h.changed_at else None} for h in rows]


# ---------------- receipt templates & box settings ----------------

@router.get("/receipt-templates")
async def list_receipts(db: AsyncSession = Depends(get_db), user: User = Depends(_perm_view())):
    rows = (await db.execute(select(ReceiptTemplate))).scalars().all()
    return [{"id": t.id, "name": t.name, "is_active": t.is_active, "paper_width_mm": t.paper_width_mm,
             "sections": t.sections, "header_text": t.header_text, "footer_text": t.footer_text,
             "show_trial_badge": t.show_trial_badge} for t in rows]


@router.put("/receipt-templates/{tpl_id}")
async def put_receipt(tpl_id: str, body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(require_any_permission("settings.edit"))):
    t = await db.get(ReceiptTemplate, tpl_id)
    if not t:
        raise NotFoundError("قالب یافت نشد")
    for k in ("name", "is_active", "paper_width_mm", "sections", "header_text", "footer_text", "show_trial_badge"):
        if k in body:
            setattr(t, k, body[k])
    if user:
        await write_audit(db, user_id=user.id, action="RECEIPT_UPDATE", module="settings",
                          entity_type="receipt_template", entity_id=t.id)
    await db.commit()
    return {"success": True}


DEFAULT_SECTIONS = [
    {"key": "complex_name", "visible": True}, {"key": "receipt_id", "visible": True},
    {"key": "plate", "visible": True}, {"key": "entry_time", "visible": True},
    {"key": "parking_spot", "visible": True}, {"key": "tariff_summary", "visible": True},
    {"key": "trial_badge", "visible": True}, {"key": "qr", "visible": False},
    {"key": "guide_text", "visible": True},
]


@router.get("/box-settings/{side}")
async def get_box(side: str, db: AsyncSession = Depends(get_db), user: User = Depends(_perm_view())):
    row = (await db.execute(select(BoxSetting).where(BoxSetting.side == side))).scalar_one_or_none()
    if row is None:
        raise NotFoundError("تنظیمات باکس یافت نشد")
    return {"id": row.id, "side": row.side, "is_active": row.is_active, "buttons": row.buttons,
            "messages": row.messages, "font_scale": row.font_scale, "colors": row.colors}


@router.put("/box-settings/{side}")
async def put_box(side: str, body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(require_any_permission("settings.edit"))):
    row = (await db.execute(select(BoxSetting).where(BoxSetting.side == side))).scalar_one_or_none()
    if not row:
        raise NotFoundError("تنظیمات باکس یافت نشد")
    for k in ("is_active", "buttons", "messages", "font_scale", "colors"):
        if k in body:
            setattr(row, k, body[k])
    if user:
        await write_audit(db, user_id=user.id, action="BOX_SETTING_UPDATE", module="settings",
                          entity_type="box_setting", entity_id=side)
    await db.commit()
    return {"success": True}


@router.get("/receipts/render/{session_id}")
async def render_receipt(session_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """رندر قبض نشست بر اساس قالب فعال طراح (موج ۵f) — مقادیر از داده واقعی جلسه."""
    from app.modules.access_control.models import ParkingSession
    from app.modules.finance.models import Tariff
    from app.modules.parking.models import ParkingOccupancy, ParkingSpace

    sess = await db.get(ParkingSession, session_id)
    if not sess:
        raise NotFoundError("نشست یافت نشد")
    tpls = (await db.execute(select(ReceiptTemplate).where(ReceiptTemplate.is_active.is_(True)))).scalars().all()
    tpl = tpls[0] if tpls else None
    sections = (tpl.sections if tpl else None) or DEFAULT_SECTIONS
    spot_code = spot_zone = None
    if sess.entry_event_id:
        occ = (await db.execute(select(ParkingOccupancy).where(
            ParkingOccupancy.access_event_id == sess.entry_event_id))).scalars().first()
        if occ and occ.parking_space_id:
            sp = await db.get(ParkingSpace, occ.parking_space_id)
            if sp:
                spot_code, spot_zone = sp.code, sp.zone
    tariff_summary = None
    if sess.tariff_id:
        t = await db.get(Tariff, sess.tariff_id)
        if t:
            tariff_summary = f"{t.free_minutes} دقیقه رایگان — ساعتی {t.hourly_amount:,} ریال"
    data = {
        "receipt_id": f"RC-{sess.id[:8].upper()}",
        "plate": sess.plate_normalized,
        "entry_time": sess.entry_at.isoformat() if sess.entry_at else None,
        "exit_time": sess.exit_at.isoformat() if sess.exit_at else None,
        "duration_seconds": sess.duration_seconds,
        "parking_spot": (spot_code or "—") + (f" — {spot_zone}" if spot_zone else ""),
        "tariff_summary": tariff_summary or "بدون تعرفه فعال",
        "final_amount": sess.final_amount,
        "payment_status": sess.payment_status,
    }
    return {
        "template": {
            "name": tpl.name if tpl else "پیش‌فرض",
            "paper_width_mm": tpl.paper_width_mm if tpl else 80,
            "sections": sections,
            "header_text": tpl.header_text if tpl else "مجتمع مسکونی ارکیده",
            "footer_text": tpl.footer_text if tpl else "لطفاً پیش از خروج تسویه کنید.",
            "show_trial_badge": tpl.show_trial_badge if tpl else True,
        },
        "data": data,
    }
