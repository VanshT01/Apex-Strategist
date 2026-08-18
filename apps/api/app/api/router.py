from fastapi import APIRouter

from app.api.routes import admin, catalog, health, race, simulations

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(catalog.router)
api_router.include_router(admin.router)
api_router.include_router(race.router)
api_router.include_router(simulations.router)
