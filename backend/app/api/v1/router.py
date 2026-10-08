from fastapi import APIRouter, Depends

from app.core.permissions import require_any_permission

from app.api.v1 import auth
from app.api.v1.roles import router as roles_v2_router
from app.api.v1.users import roles_router, router as users_router
from app.modules.access_control.router import router as gate_router
from app.modules.base_data.router import router as base_data_router
from app.modules.notifications.router import router as notifications_router
from app.modules.ops.router import router as ops_router
from app.modules.simulator.router import router as simulator_router
from app.modules.parking.cad_router import router as cad_router
from app.modules.config_admin.router import router as config_router
from app.modules.scenario.router import router as scenario_router
from app.modules.camera.router import router as camera_router
from app.modules.complexes.router import router as complexes_router
from app.modules.devices.router import router as devices_router
from app.modules.files.router import router as files_router
from app.modules.finance.router import router as finance_router
from app.modules.parking.router import router as parking_router
from app.modules.permits.router import router as permits_router
from app.modules.reports.router import router as reports_router
from app.modules.residents.router import router as residents_router
from app.modules.vehicles.router import router as vehicles_router
from app.modules.violations.router import router as violations_router

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users_router)
api_router.include_router(roles_v2_router)
api_router.include_router(roles_router)
api_router.include_router(complexes_router, dependencies=[Depends(require_any_permission("structure.create", "structure.delete", "structure.edit", "structure.view"))])
api_router.include_router(residents_router, dependencies=[Depends(require_any_permission("structure.create", "structure.delete", "structure.edit", "structure.view"))])
api_router.include_router(vehicles_router, dependencies=[Depends(require_any_permission("gate.manual_access", "vehicles.create", "vehicles.delete", "vehicles.edit", "vehicles.export", "vehicles.sensitive", "vehicles.view"))])
api_router.include_router(permits_router, dependencies=[Depends(require_any_permission("gate.manual_access", "permits.approve", "permits.create", "permits.delete", "permits.edit", "permits.reject", "permits.view"))])
api_router.include_router(parking_router)
api_router.include_router(devices_router, dependencies=[Depends(require_any_permission("field.approve", "field.create", "field.delete", "field.edit", "field.reject", "field.view"))])
api_router.include_router(gate_router)
api_router.include_router(violations_router)
api_router.include_router(finance_router)
api_router.include_router(reports_router, dependencies=[Depends(require_any_permission("access_events.create", "access_events.edit", "access_events.export", "access_events.sensitive", "access_events.view", "dashboard.view", "reports.export", "reports.view"))])
api_router.include_router(files_router)
api_router.include_router(base_data_router, dependencies=[Depends(require_any_permission("base_data.create", "base_data.delete", "base_data.edit", "base_data.view"))])
api_router.include_router(cad_router)
api_router.include_router(notifications_router)
api_router.include_router(ops_router, dependencies=[Depends(require_any_permission("ops.create", "ops.edit", "ops.view"))])
api_router.include_router(simulator_router, dependencies=[Depends(require_any_permission("simulator.create", "simulator.view"))])


api_router.include_router(config_router)
api_router.include_router(scenario_router)
api_router.include_router(camera_router)
@api_router.get("/ping", tags=["System"])
async def ping():
    return {"message": "pong"}