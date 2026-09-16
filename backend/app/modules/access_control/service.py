from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.access_control.models import AccessEvent, ParkingSession, PlateRecognitionEvent
from app.modules.devices.models import Gate
from app.modules.vehicles.models import Vehicle
from app.modules.vehicles.service import VehicleService
from app.parking_helpers import find_assigned_space, vehicle_unit_info
from app.realtime.manager import manager
from app.shared.plate import normalize_plate

try:
    from app.modules.finance.service import close_session_amounts
except ImportError:
    close_session_amounts = None


class GateDecisionService:

    @staticmethod
    def barrier_action_for(decision: str) -> str:
        if decision in ("ALLOW", "ALLOW_WITH_WARNING", "OFFLINE_ALLOW"):
            return "OPEN"
        return "KEEP_CLOSED"

    @staticmethod
    def build_response(event, gate, vehicle, unit_info, parking, warnings) -> dict:
        return {
            "access_event_id": event.id,
            "decision": event.decision,
            "decision_reason": event.decision_reason,
            "plate": {"raw": None, "normalized": event.plate_normalized},
            "vehicle": ({"id": vehicle.id, "type": vehicle.vehicle_type, "color": vehicle.color} if vehicle else None),
            "unit": unit_info,
            "parking": parking,
            "warnings": warnings,
            "barrier_action": GateDecisionService.barrier_action_for(event.decision),
            "gate": {"id": gate.id, "code": gate.code, "name": gate.name},
            "issued_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    async def process_plate_event(
        db: AsyncSession,
        *,
        gate_code: str,
        direction: str,
        plate_raw: str,
        source_event_id: str,
        device_id: str | None = None,
        captured_at: datetime | None = None,
        confidence: float | None = None,
        raw_payload: dict | None = None,
        is_manual: bool = False,
        operator_id: str | None = None,
        offline_created: bool = False,
        idempotency_key: str | None = None,
        client_decision: str | None = None,
        dry_run: bool = False,
    ) -> dict:
        now = datetime.now(timezone.utc)
        gate = (await db.execute(select(Gate).where(Gate.code == gate_code))).scalar_one_or_none()
        if gate is None:
            raise ValueError(f"GATE_NOT_FOUND:{gate_code}")

        key = idempotency_key or f"{gate.code}:{source_event_id}"

        existing = (await db.execute(
            select(AccessEvent).where(AccessEvent.idempotency_key == key)
        )).scalar_one_or_none()
        if existing:
            vehicle = await db.get(Vehicle, existing.vehicle_id) if existing.vehicle_id else None
            unit_info = await vehicle_unit_info(db, vehicle) if vehicle else None
            resp = GateDecisionService.build_response(existing, gate, vehicle, unit_info, None, ["DUPLICATE_EVENT"])
            resp["duplicate"] = True
            return resp

        normalized = normalize_plate(plate_raw)
        warnings: list[str] = []

        pre = PlateRecognitionEvent(
            gate_id=gate.id, device_id=device_id, direction=direction,
            plate_raw=plate_raw, plate_normalized=normalized, confidence=confidence,
            captured_at=captured_at or now, received_at=now,
            source_event_id=source_event_id, raw_payload=raw_payload,
        )
        if not dry_run:
            db.add(pre)
            await db.flush()

        vehicle = await VehicleService.get_by_plate(db, plate_raw) if normalized else None
        decision = None
        reason = None
        permit = None
        parking_info = None
        create_new_session = True
        closed_session_info = None

        if not normalized:
            decision, reason = "UNKNOWN_PLATE", "PLATE_NOT_READABLE"
        elif vehicle is None:
            decision, reason = "UNKNOWN_PLATE", "VEHICLE_NOT_REGISTERED"
        elif not vehicle.is_active:
            decision, reason = "DENY", "VEHICLE_INACTIVE"
        else:
            restriction = await VehicleService.has_active_restriction(db, normalized, now)
            if restriction:
                decision, reason = "DENY", "PLATE_RESTRICTED"
            elif direction == "OUT":
                session = (await db.execute(
                    select(ParkingSession).where(
                        ParkingSession.plate_normalized == normalized,
                        ParkingSession.status == "OPEN",
                    ).order_by(ParkingSession.entry_at.desc())
                )).scalars().first()
                if session:
                    session.exit_at = now
                    session.duration_seconds = max(0, int((now - session.entry_at).total_seconds()))
                    if close_session_amounts:
                        amounts = await close_session_amounts(db, session)
                        warnings.extend(amounts.get("warnings", []))
                    session.status = "CLOSED"
                    session.payment_status = "FREE" if session.final_amount == 0 else "UNPAID"
                    decision, reason = "ALLOW", "EXIT_SESSION_CLOSED"
                    closed_session_info = {
                        "id": session.id,
                        "duration_seconds": session.duration_seconds,
                        "base_amount": session.base_amount,
                        "final_amount": session.final_amount,
                        "payment_status": session.payment_status,
                    }
                else:
                    decision, reason = "ALLOW_WITH_WARNING", "NO_OPEN_SESSION_FOR_EXIT"
                    warnings.append("NO_OPEN_SESSION_FOR_EXIT")
            else:
                permit, permit_reason = await VehicleService.find_active_permit(db, normalized, gate.id, now)
                if permit is None:
                    if permit_reason == "PERMIT_NOT_FOUND":
                        decision, reason = "UNKNOWN_PLATE", "NO_ACTIVE_PERMIT"
                    else:
                        decision, reason = "REQUIRE_OPERATOR_APPROVAL", permit_reason
                else:
                    open_session = (await db.execute(
                        select(ParkingSession).where(
                            ParkingSession.plate_normalized == normalized,
                            ParkingSession.status == "OPEN",
                        )
                    )).scalars().first()
                    if open_session:
                        warnings.append("SESSION_ALREADY_OPEN")
                        decision, reason = "ALLOW_WITH_WARNING", "DUPLICATE_ENTRY_SESSION_OPEN"
                        create_new_session = False
                    else:
                        decision, reason = "ALLOW", "VALID_PERMIT"
                    permit.used_entries += 1

        if is_manual:
            event_type = "MANUAL_ENTRY" if direction == "IN" else "MANUAL_EXIT"
        else:
            event_type = "ENTRY" if direction == "IN" else "EXIT"
        if decision in ("DENY", "UNKNOWN_PLATE"):
            event_type = "DENIED_ENTRY" if direction == "IN" else "DENIED_EXIT"

        event = AccessEvent(
            plate_recognition_event_id=None if dry_run else pre.id,
            gate_id=gate.id,
            vehicle_id=vehicle.id if vehicle else None,
            plate_normalized=normalized,
            event_type=event_type,
            event_time=captured_at or now,
            permit_id=permit.id if permit else None,
            decision=decision,
            decision_reason=reason,
            operator_id=operator_id,
            is_manual=is_manual,
            offline_created=offline_created,
            idempotency_key=key,
            synced_at=now if offline_created else None,
        )
        if not dry_run:
            db.add(event)
            await db.flush()

            if direction == "IN" and decision in ("ALLOW", "ALLOW_WITH_WARNING") and create_new_session:
                from app.modules.parking.models import ParkingOccupancy
                session = ParkingSession(
                    vehicle_id=vehicle.id if vehicle else None,
                    plate_normalized=normalized,
                    entry_event_id=event.id,
                    entry_at=captured_at or now,
                    status="OPEN",
                )
                db.add(session)
                await db.flush()
                space = await find_assigned_space(db, vehicle)
                db.add(ParkingOccupancy(
                    parking_space_id=space.id if space else None,
                    vehicle_id=vehicle.id if vehicle else None,
                    access_event_id=event.id,
                    occupied_at=captured_at or now,
                    source="OFFLINE_SYNC" if offline_created else "GATE",
                ))
                if space:
                    space.status = "OCCUPIED"
                    parking_info = {"id": space.id, "code": space.code, "zone": space.zone}

            if direction == "OUT" and decision in ("ALLOW", "ALLOW_WITH_WARNING") and vehicle:
                from app.modules.parking.models import ParkingOccupancy, ParkingSpace
                occ = (await db.execute(
                    select(ParkingOccupancy).where(
                        ParkingOccupancy.vehicle_id == vehicle.id,
                        ParkingOccupancy.status == "OCCUPIED",
                    ).order_by(ParkingOccupancy.occupied_at.desc())
                )).scalars().first()
                if occ:
                    occ.vacated_at = now
                    occ.status = "VACATED"
                    if occ.parking_space_id:
                        space = await db.get(ParkingSpace, occ.parking_space_id)
                        if space:
                            space.status = "FREE"

            await db.commit()
            await db.refresh(event)

        unit_info = await vehicle_unit_info(db, vehicle) if vehicle else None
        if parking_info is None and vehicle and direction == "IN":
            space = await find_assigned_space(db, vehicle)
            if space:
                parking_info = {"id": space.id, "code": space.code, "zone": space.zone}

        response = GateDecisionService.build_response(event, gate, vehicle, unit_info, parking_info, warnings)
        response["plate"]["raw"] = plate_raw
        if confidence is not None:
            response["plate"]["confidence"] = confidence
        response["event_type"] = event_type
        if closed_session_info:
            response["session"] = closed_session_info

        if not dry_run:
            ws_data = {"plate": normalized, "gate_id": gate.id, "gate_code": gate.code,
                       "decision": decision, "access_event_id": event.id}
            try:
                await manager.broadcast("plate.detected", ws_data)
                if decision in ("ALLOW", "ALLOW_WITH_WARNING"):
                    await manager.broadcast("access.allowed", ws_data)
                    await manager.broadcast("vehicle.entered" if direction == "IN" else "vehicle.exited", ws_data)
                else:
                    await manager.broadcast("access.denied", ws_data)
            except Exception:
                pass

        if client_decision and client_decision != decision:
            response["needs_review"] = True
            response["warnings"].append("OFFLINE_DECISION_MISMATCH")

        return response