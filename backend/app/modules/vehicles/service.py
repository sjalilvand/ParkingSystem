import json
from datetime import datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.vehicles.models import AccessPermit, Vehicle, VehicleRestriction
from app.shared.plate import normalize_plate


def _parse_hhmm(value) -> time | None:
    if value is None:
        return None
    if isinstance(value, time):
        return value
    try:
        parts = str(value).split(":")
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        return None


def permit_time_valid(permit, now: datetime) -> tuple[bool, str]:
    """بررسی بازه اعتبار مجوز — تابع خالص (قابل تست واحد)."""
    if permit.valid_from and now < permit.valid_from:
        return False, "PERMIT_NOT_STARTED"
    if permit.valid_until and now > permit.valid_until:
        return False, "PERMIT_EXPIRED"

    if permit.allowed_days:
        try:
            days = set(json.loads(permit.allowed_days)) if isinstance(permit.allowed_days, str) else set(permit.allowed_days)
        except Exception:
            days = None
        if days is not None and now.weekday() not in days:
            return False, "PERMIT_DAY_NOT_ALLOWED"

    from_t = _parse_hhmm(permit.allowed_from_time)
    to_t = _parse_hhmm(permit.allowed_until_time)
    if from_t and to_t:
        cur = now.time()
        if from_t <= to_t:
            if not (from_t <= cur <= to_t):
                return False, "PERMIT_TIME_NOT_ALLOWED"
        else:
            if not (cur >= from_t or cur <= to_t):
                return False, "PERMIT_TIME_NOT_ALLOWED"
    return True, "OK"


def permit_gate_allowed(permit, gate_id: str | None) -> bool:
    if not gate_id or not permit.allowed_gate_ids:
        return True
    try:
        ids = json.loads(permit.allowed_gate_ids) if isinstance(permit.allowed_gate_ids, str) else permit.allowed_gate_ids
        return gate_id in ids
    except Exception:
        return True


def permit_entries_available(permit) -> tuple[bool, str]:
    if permit.max_entries is None:
        return True, "OK"
    if permit.used_entries >= permit.max_entries:
        return False, "PERMIT_MAX_ENTRIES_REACHED"
    return True, "OK"


class VehicleService:
    @staticmethod
    async def get_by_plate(db: AsyncSession, plate_raw: str) -> Vehicle | None:
        normalized = normalize_plate(plate_raw)
        if not normalized:
            return None
        result = await db.execute(
            select(Vehicle)
            .where(Vehicle.plate_normalized == normalized)
            .order_by(Vehicle.created_at.asc())
            .limit(1)
        )
        return result.scalars().first()

    @staticmethod
    async def find_active_permit(db: AsyncSession, plate_normalized: str, gate_id: str | None, now: datetime) -> tuple[AccessPermit | None, str]:
        result = await db.execute(
            select(AccessPermit).where(
                AccessPermit.plate_normalized == plate_normalized,
                AccessPermit.status == "ACTIVE",
            ).order_by(AccessPermit.created_at.desc())
        )
        permits = result.scalars().all()

        for permit in permits:
            ok, _ = permit_time_valid(permit, now)
            if not ok:
                continue
            if not permit_gate_allowed(permit, gate_id):
                continue
            ok_entries, _ = permit_entries_available(permit)
            if not ok_entries:
                continue
            return permit, "OK"

        if permits:
            return None, "PERMIT_INVALID_NOW"
        return None, "PERMIT_NOT_FOUND"

    @staticmethod
    async def has_active_restriction(db: AsyncSession, plate_normalized: str, now: datetime) -> VehicleRestriction | None:
        result = await db.execute(
            select(VehicleRestriction).where(
                VehicleRestriction.plate_normalized == plate_normalized,
                VehicleRestriction.status == "ACTIVE",
            )
        )
        for r in result.scalars().all():
            if r.starts_at and now < r.starts_at:
                continue
            if r.ends_at and now > r.ends_at:
                continue
            return r
        return None