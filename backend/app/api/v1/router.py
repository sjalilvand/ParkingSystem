from fastapi import APIRouter

from app.api.v1 import auth
from app.api.v1.users import roles_router, router as users_router
from app.modules.access_control.router import router as gate_router
from app.modules.base_data.router import router as base_data_router
from app.modules.notifications.router import router as notifications_router
from app.modules.ops.router import router as ops_router
from app.modules.parking.cad_router import router as cad_router
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
api_router.include_router(roles_router)
api_router.include_router(complexes_router)
api_router.include_router(residents_router)
api_router.include_router(vehicles_router)
api_router.include_router(permits_router)
api_router.include_router(parking_router)
api_router.include_router(devices_router)
api_router.include_router(gate_router)
api_router.include_router(violations_router)
api_router.include_router(finance_router)
api_router.include_router(reports_router)
api_router.include_router(files_router)
api_router.include_router(base_data_router)
api_router.include_router(cad_router)
api_router.include_router(notifications_router)
api_router.include_router(ops_router)


@api_router.get("/ping", tags=["System"])
async def ping():
    return {"message": "pong"}