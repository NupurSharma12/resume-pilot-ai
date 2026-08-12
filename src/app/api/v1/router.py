from fastapi import APIRouter

from app.api.v1.endpoints import (
    analyze,
    career_conversation,
    health,
    job_preparation_history,
    tailoring_suggestions,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(analyze.router, tags=["analyze"])
api_router.include_router(career_conversation.router, tags=["career-conversation"])
api_router.include_router(tailoring_suggestions.router, tags=["tailoring-suggestions"])
api_router.include_router(job_preparation_history.router, tags=["job-preparation-history"])
