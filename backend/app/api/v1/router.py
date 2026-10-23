"""Aggregate router for API v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import auth, health, organizations, intelligence, performance, jobs

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(intelligence.router)
api_router.include_router(performance.router)
api_router.include_router(jobs.router)