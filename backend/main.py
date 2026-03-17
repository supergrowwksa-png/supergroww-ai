import os
import sys
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from livekit import api
from dotenv import load_dotenv

# Routers
from backend.app.api.endpoints.candidates import router as candidates_router
from backend.app.api.endpoints.interviews import router as interviews_router
from backend.app.api.endpoints.scorecards import router as scorecards_router

# Local imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from logger import get_logger, log_request, PerformanceLogger
from config import settings, validate_critical_settings, print_config_summary
from database import get_session, EvaluationScore, InterviewTranscript, Interview, Candidate, Job


logger = get_logger("api.main")

load_dotenv()

# Validate config on startup
validate_critical_settings()
print_config_summary()

app = FastAPI(title="Supegroww AI Interview Backend")

app.include_router(candidates_router)
app.include_router(interviews_router)
app.include_router(scorecards_router)


# ---------------------------------------------------
# Middleware
# ---------------------------------------------------

@app.middleware("http")
async def log_requests_middleware(request: Request, call_next):
    """Log all HTTP requests with timing"""
    start_time = time.time()

    response = await call_next(request)

    duration_ms = (time.time() - start_time) * 1000

    log_request(logger, request, duration_ms)

    return response


# ---------------------------------------------------
# Startup / Shutdown
# ---------------------------------------------------

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Supegroww Backend starting up")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Log Level: {settings.LOG_LEVEL}")
    logger.info(f"LiveKit URL: {settings.LIVEKIT_URL}")
    logger.info("⚠️  Make sure LiveKit agent is running: python backend/app/interview/agent.py dev")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Supegroww Backend shutting down")


# ---------------------------------------------------
# Request Models
# ---------------------------------------------------

class JoinRequest(BaseModel):
    candidate_name: str
    job_id: str
    interview_id: int


class StartInterviewRequest(BaseModel):
    candidate_name: str
    candidate_email: str
    resume_url: str
    job_title: str
    job_description: str
    skills: list[str] | None = []


# ---------------------------------------------------
# Join Interview (legacy endpoint)
# ---------------------------------------------------

@app.post("/api/join-interview")
async def join_interview(req: JoinRequest):

    logger.info(
        "Join request received",
        extra={
            "candidate_name": req.candidate_name,
            "job_id": req.job_id,
            "interview_id": req.interview_id
        }
    )

    with PerformanceLogger(logger, "generate_livekit_token"):

        room_name = f"interview-{req.job_id}-{req.candidate_name.replace(' ', '_')}-{req.interview_id}"

        token = api.AccessToken(
            settings.LIVEKIT_API_KEY,
            settings.LIVEKIT_API_SECRET
        ).with_identity(req.candidate_name) \
         .with_name(req.candidate_name) \
         .with_grants(api.VideoGrants(
             room_join=True,
             room=room_name,
             can_publish=True,
             can_subscribe=True
         ))

    logger.info(
        "✅ Token generated successfully",
        extra={
            "room_name": room_name,
            "candidate": req.candidate_name
        }
    )

    return {
        "token": token.to_jwt(),
        "room_name": room_name,
        "ws_url": settings.LIVEKIT_URL
    }


# ---------------------------------------------------
# Start Interview (MERN Backend Endpoint)
# ---------------------------------------------------

@app.post("/start-interview")
async def start_interview(req: StartInterviewRequest):

    logger.info(
        "Start interview request from MERN backend",
        extra={
            "candidate": req.candidate_name,
            "job_title": req.job_title
        }
    )

    with PerformanceLogger(logger, "generate_livekit_token_from_mern"):

        # ✅ Generate unique interview id
        interview_id = str(uuid.uuid4())

        # ✅ Simple and safe room name
        room_name = f"interview-{interview_id}"

        token = api.AccessToken(
            settings.LIVEKIT_API_KEY,
            settings.LIVEKIT_API_SECRET
        ).with_identity(req.candidate_name) \
         .with_name(req.candidate_name) \
         .with_grants(api.VideoGrants(
             room_join=True,
             room=room_name,
             can_publish=True,
             can_subscribe=True
         ))

    logger.info(
        "✅ Interview session created",
        extra={
            "room_name": room_name,
            "candidate": req.candidate_name,
            "interview_id": interview_id
        }
    )

    return {
        "token": token.to_jwt(),
        "room_name": room_name,
        "interview_id": interview_id,
        "ws_url": settings.LIVEKIT_URL
    }


# ---------------------------------------------------
# Debug Endpoints
# ---------------------------------------------------

@app.get("/api/debug/scores/{interview_id}")
async def get_interview_scores(interview_id: int):

    db = next(get_session())

    try:

        scores = db.query(EvaluationScore).filter(
            EvaluationScore.interview_id == interview_id
        ).all()

        return {
            "interview_id": interview_id,
            "total_scores": len(scores),
            "scores": [
                {
                    "id": s.id,
                    "level": s.level,
                    "category": s.category,
                    "score_value": s.score_value,
                    "created_at": s.evaluated_at.isoformat() if s.evaluated_at else None
                }
                for s in scores
            ]
        }

    finally:
        db.close()


@app.get("/api/debug/transcripts/{interview_id}")
async def get_interview_transcripts(interview_id: int):

    db = next(get_session())

    try:

        transcripts = db.query(InterviewTranscript).filter(
            InterviewTranscript.interview_id == interview_id
        ).order_by(InterviewTranscript.timestamp).all()

        return {
            "interview_id": interview_id,
            "total_transcripts": len(transcripts),
            "transcripts": [
                {
                    "id": t.id,
                    "speaker": t.speaker,
                    "message": t.message_text[:100] + "..." if len(t.message_text) > 100 else t.message_text,
                    "timestamp": t.timestamp.isoformat() if t.timestamp else None
                }
                for t in transcripts
            ]
        }

    finally:
        db.close()


@app.get("/api/debug/database-stats")
async def get_database_stats():

    db = next(get_session())

    try:

        return {
            "total_interviews": db.query(Interview).count(),
            "total_scores": db.query(EvaluationScore).count(),
            "total_transcripts": db.query(InterviewTranscript).count(),
            "scores_by_level": {
                "level_1": db.query(EvaluationScore).filter(EvaluationScore.level == 1).count(),
                "level_2": db.query(EvaluationScore).filter(EvaluationScore.level == 2).count(),
                "level_3": db.query(EvaluationScore).filter(EvaluationScore.level == 3).count(),
            }
        }

    finally:
        db.close()


# ---------------------------------------------------
# Health Check
# ---------------------------------------------------

@app.get("/")
def health_check():

    logger.debug("Health check called")

    return {
        "status": "Supergroww Backend Operational",
        "environment": settings.ENVIRONMENT.value,
        "livekit_configured": bool(settings.LIVEKIT_URL)
    }


# ---------------------------------------------------
# Agent Status Check
# ---------------------------------------------------

@app.get("/api/agent-status")
async def check_agent_status():

    try:

        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:60684/health",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:

                if response.status == 200:

                    logger.info("✅ Agent server is running")

                    return {
                        "agent_running": True,
                        "message": "LiveKit agent is running and healthy"
                    }

    except Exception as e:

        logger.warning(
            "Agent server not reachable",
            extra={"error": str(e)}
        )

        return {
            "agent_running": False,
            "message": "Agent server not reachable. Please start: python agent.py dev",
            "error": str(e)
        }


# ---------------------------------------------------
# Run Server
# ---------------------------------------------------

if __name__ == "__main__":

    import uvicorn

    logger.info("Starting Supergroww Backend via uvicorn")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )