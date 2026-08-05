from fastapi import APIRouter

from app.api.v1.endpoints import analyze, career_conversation, health, tailor_resume

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(analyze.router, tags=["analyze"])
api_router.include_router(career_conversation.router, tags=["career-conversation"])
api_router.include_router(tailor_resume.router, tags=["tailor-resume"])
