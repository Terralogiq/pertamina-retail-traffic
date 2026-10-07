"""STUB from `.4.7`: GET /api/traffic/latest returns [] so the map view (`.4.2`) can start in parallel.

`.4.3` replaces this file with the real router (latest, series, pattern).
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/traffic/latest")
def traffic_latest():
    return []
