"""
API Schemas (Pydantic Models) with Production Logging
=====================================================

This file defines Pydantic models for request/response validation with
comprehensive logging for validation errors and data quality monitoring.

LOGGING FEATURES IMPLEMENTED:
1. Request validation logging with context
2. Data quality metrics tracking
3. Validation error categorization
4. Field-level validation logging
5. Schema usage statistics
6. Custom validator logging
"""

from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

# PROPER LOGGING SETUP (Following logger.py patterns)

from backend.logger import get_logger

# Create component logger
logger = get_logger("api.models")

# ENUMS

class InterviewStatusEnum(str, Enum):
    """Valid interview statuses"""
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class RecommendationEnum(str, Enum):
    """Interview outcome recommendations"""
    STRONG_HIRE = "strong_hire"
    HIRE = "hire"
    MAYBE = "maybe"
    NO_HIRE = "no_hire"

# BASE MODEL WITH LOGGING

class LoggedBaseModel(BaseModel):
    """
    Base model with automatic validation logging.
    
    Why: Centralizes logging for all Pydantic models.
    """
    
    def __init__(self, **data):
        """Initialize with validation logging"""
        model_name = self.__class__.__name__
        
        logger.debug(
            f"Validating {model_name}",
            extra={
                "model": model_name,
                "field_count": len(data)
            }
        )
        
        try:
            super().__init__(**data)
            
            logger.debug(
                f"{model_name} validated successfully",
                extra={
                    "model": model_name,
                    "fields": list(data.keys())
                }
            )
        
        except Exception as e:
            logger.warning(
                f"{model_name} validation failed",
                extra={
                    "model": model_name,
                    "error": str(e),
                    "provided_fields": list(data.keys())
                }
            )
            raise

# REQUEST SCHEMAS (What API accepts)

class CreateCandidateRequest(LoggedBaseModel):
    """
    Request to create a new candidate.
    
    Why: When a candidate applies or is imported from ATS.
    """
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=50)
    resume_text: Optional[str] = None
    resume_url: Optional[str] = None
    job_id: int
    ats_candidate_id: Optional[str] = None
    source: str = Field(default="manual", max_length=100)
    
    @validator('name')
    def validate_name(cls, v):
        """Validate candidate name"""
        if not v.strip():
            logger.warning("Empty candidate name provided")
            raise ValueError("Name cannot be empty")
        
        logger.debug(
            "Candidate name validated",
            extra={"name_length": len(v)}
        )
        return v.strip()
    
    @validator('resume_text')
    def validate_resume_text(cls, v):
        """Validate resume text quality"""
        if v and len(v.strip()) < 50:
            logger.warning(
                "Resume text too short",
                extra={"length": len(v.strip())}
            )
        
        if v:
            logger.debug(
                "Resume text validated",
                extra={
                    "length": len(v),
                    "word_count": len(v.split())
                }
            )
        
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "name": "Alice Johnson",
                "email": "alice@example.com",
                "phone": "+1-555-0123",
                "job_id": 1,
                "source": "lever"
            }
        }


class CreateJobRequest(LoggedBaseModel):
    """
    Request to create a new job posting.
    
    Why: HR team creates a job before scheduling interviews.
    """
    job_id: str = Field(..., max_length=100, description="External ATS job ID")
    title: str = Field(..., max_length=255)
    description: str = Field(..., min_length=10)
    requirements: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Skills, experience level, etc."
    )
    interview_duration_minutes: int = Field(default=30, ge=10, le=120)
    topics_to_cover: Optional[List[str]] = Field(
        default=["Technical Background", "Problem Solving", "Team Collaboration"],
        description="Topics to cover in interview"
    )
    evaluation_rubric: Optional[Dict[str, float]] = Field(
        default=None,
        description="Scoring weights for topics"
    )
    
    @validator('topics_to_cover')
    def validate_topics(cls, v):
        """Ensure at least one topic with logging"""
        if not v or len(v) == 0:
            logger.error("No topics specified for interview")
            raise ValueError("Must specify at least one topic to cover")
        
        logger.debug(
            "Topics validated",
            extra={
                "num_topics": len(v),
                "topics": v
            }
        )
        
        return v
    
    @validator('evaluation_rubric')
    def validate_rubric(cls, v):
        """Validate scoring weights"""
        if v:
            total_weight = sum(v.values())
            
            logger.debug(
                "Evaluation rubric validated",
                extra={
                    "num_categories": len(v),
                    "total_weight": round(total_weight, 3)
                }
            )
            
            if abs(total_weight - 1.0) > 0.01:
                logger.warning(
                    "Rubric weights don't sum to 1.0",
                    extra={"total_weight": total_weight}
                )
        
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "job_id": "backend-eng-2025",
                "title": "Senior Backend Engineer",
                "description": "We are looking for an experienced backend engineer...",
                "requirements": {
                    "skills": ["Python", "FastAPI", "PostgreSQL"],
                    "experience": "5+ years"
                },
                "interview_duration_minutes": 45,
                "topics_to_cover": [
                    "System Design",
                    "Python Expertise",
                    "Database Design",
                    "Leadership"
                ],
                "evaluation_rubric": {
                    "System Design": 0.3,
                    "Python Expertise": 0.25,
                    "Database Design": 0.25,
                    "Leadership": 0.2
                }
            }
        }


class ScheduleInterviewRequest(LoggedBaseModel):
    """
    Request to schedule/create a new interview.
    
    Why: After candidate applies, recruiter schedules interview.
    """
    candidate_email: str
    job_id: str
    scheduled_at: Optional[datetime] = None
    
    @validator('scheduled_at')
    def validate_scheduled_time(cls, v):
        """Ensure scheduled time is in future"""
        if v and v < datetime.utcnow():
            logger.warning(
                "Interview scheduled in the past",
                extra={"scheduled_at": v.isoformat()}
            )
        
        if v:
            logger.debug(
                "Interview time validated",
                extra={"scheduled_at": v.isoformat()}
            )
        
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "candidate_email": "alice@example.com",
                "job_id": "backend-eng-2025",
                "scheduled_at": "2025-01-15T10:00:00Z"
            }
        }


class UpdateInterviewStatusRequest(LoggedBaseModel):
    """
    Request to update interview status.
    
    Why: When interview starts, ends, or is cancelled.
    """
    status: InterviewStatusEnum
    
    class Config:
        schema_extra = {
            "example": {
                "status": "in_progress"
            }
        }

# RESPONSE SCHEMAS (What API returns)

class CandidateResponse(BaseModel):
    """Response containing candidate data"""
    id: int
    name: str
    email: str
    phone: Optional[str]
    job_id: int
    created_at: datetime
    
    class Config:
        orm_mode = True


class JobResponse(BaseModel):
    """Response containing job data"""
    id: int
    job_id: str
    title: str
    description: str
    requirements: Optional[Dict[str, Any]]
    interview_duration_minutes: int
    topics_to_cover: Optional[List[str]]
    is_active: bool
    created_at: datetime
    
    class Config:
        orm_mode = True


class InterviewResponse(BaseModel):
    """Response containing interview data"""
    id: int
    interview_uuid: str
    candidate_id: int
    job_id: int
    room_name: str
    scheduled_at: Optional[datetime]
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    status: str
    duration_seconds: Optional[int]
    overall_score: Optional[float]
    recommendation: Optional[str]
    created_at: datetime
    
    class Config:
        orm_mode = True


class InterviewJoinResponse(BaseModel):
    """Response for joining an interview"""
    interview_id: int
    interview_uuid: str
    token: str
    room_name: str
    ws_url: str
    candidate_name: str
    job_title: str
    duration_minutes: int
    
    class Config:
        schema_extra = {
            "example": {
                "interview_id": 123,
                "interview_uuid": "550e8400-e29b-41d4-a716-446655440000",
                "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "room_name": "interview-backend-eng-2025-alice_johnson",
                "ws_url": "wss://your-livekit.cloud",
                "candidate_name": "Alice Johnson",
                "job_title": "Senior Backend Engineer",
                "duration_minutes": 45
            }
        }


class TranscriptEntry(BaseModel):
    """Single conversation turn"""
    id: int
    speaker: str
    message_text: str
    timestamp: datetime
    time_offset_seconds: float
    sentiment_scores: Optional[Dict[str, float]]
    
    class Config:
        orm_mode = True


class EvaluationScoreDetail(BaseModel):
    """Detailed score for a category"""
    category: str
    score_value: float
    max_score: float
    weight: Optional[float]
    justification: Optional[str]
    
    class Config:
        orm_mode = True


class ScorecardResponse(BaseModel):
    """Complete interview scorecard"""
    interview_id: int
    candidate_name: str
    job_title: str
    interview_date: datetime
    duration_minutes: int
    status: str
    
    # Scoring
    overall_score: Optional[float]
    recommendation: Optional[str]
    scores_by_category: List[EvaluationScoreDetail]
    
    # Summary
    ai_summary: Optional[str]
    strengths: List[str]
    weaknesses: List[str]
    
    # Recording & Transcript
    recording_url: Optional[str]
    transcript_url: Optional[str]
    transcript: List[TranscriptEntry]
    
    # Anti-cheating flags
    cheating_flags: Optional[List[Dict[str, Any]]]
    
    class Config:
        schema_extra = {
            "example": {
                "interview_id": 123,
                "candidate_name": "Alice Johnson",
                "job_title": "Senior Backend Engineer",
                "interview_date": "2025-01-15T10:00:00Z",
                "duration_minutes": 43,
                "status": "completed",
                "overall_score": 82.5,
                "recommendation": "hire",
                "scores_by_category": [
                    {
                        "category": "System Design",
                        "score_value": 85,
                        "max_score": 100,
                        "weight": 0.3,
                        "justification": "Candidate demonstrated strong understanding..."
                    }
                ],
                "ai_summary": "Alice showed excellent technical knowledge...",
                "strengths": [
                    "Deep understanding of distributed systems",
                    "Clear communication"
                ],
                "weaknesses": [
                    "Limited experience with Kubernetes",
                    "Could improve on behavioral examples"
                ],
                "recording_url": "https://s3.amazonaws.com/recordings/123.mp4",
                "transcript": [],
                "cheating_flags": []
            }
        }


class ListResponse(BaseModel):
    """Generic paginated list response"""
    total: int
    page: int
    page_size: int
    items: List[Any]
    
    class Config:
        schema_extra = {
            "example": {
                "total": 150,
                "page": 1,
                "page_size": 20,
                "items": []
            }
        }

# WEBHOOK SCHEMAS (For ATS Integration)

class LeverWebhookPayload(LoggedBaseModel):
    """Webhook payload from Lever ATS"""
    event: str
    candidateId: str
    opportunityId: str
    stage: Optional[str]
    posting: Optional[Dict[str, Any]]
    
    class Config:
        schema_extra = {
            "example": {
                "event": "candidate_stage_change",
                "candidateId": "abc123",
                "opportunityId": "def456",
                "stage": "assessment",
                "posting": {
                    "id": "backend-eng-2025",
                    "text": "Senior Backend Engineer"
                }
            }
        }


class GreenhouseWebhookPayload(LoggedBaseModel):
    """Webhook payload from Greenhouse ATS"""
    action: str
    payload: Dict[str, Any]
    
    class Config:
        schema_extra = {
            "example": {
                "action": "application_updated",
                "payload": {
                    "application": {
                        "id": 123456,
                        "candidate_id": 789,
                        "current_stage": {
                            "name": "Technical Screen"
                        }
                    }
                }
            }
        }

# WEBSOCKET SCHEMAS

class WebSocketMessage(BaseModel):
    """Generic WebSocket message format"""
    type: str
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        schema_extra = {
            "example": {
                "type": "transcript_chunk",
                "data": {
                    "speaker": "candidate",
                    "text": "I have 5 years of experience with Python..."
                },
                "timestamp": "2025-01-15T10:05:32Z"
            }
        }


class InterviewStatusUpdate(BaseModel):
    """WebSocket message for interview status changes"""
    interview_id: int
    status: str
    timestamp: datetime
    
    class Config:
        schema_extra = {
            "example": {
                "interview_id": 123,
                "status": "in_progress",
                "timestamp": "2025-01-15T10:00:00Z"
            }
        }

# ERROR RESPONSE

class ErrorResponse(BaseModel):
    """Standard error response"""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None
    
    class Config:
        schema_extra = {
            "example": {
                "error": "Candidate not found",
                "detail": "No candidate with email alice@example.com exists",
                "code": "CANDIDATE_NOT_FOUND"
            }
        }

# MODEL USAGE TRACKING

_model_usage_stats = {}


def log_model_usage(model_name: str, operation: str = "validation"):
    """Track model usage statistics"""
    key = f"{model_name}:{operation}"
    
    if key not in _model_usage_stats:
        _model_usage_stats[key] = 0
    
    _model_usage_stats[key] += 1
    
    # Log periodically
    if _model_usage_stats[key] % 100 == 0:
        logger.info(
            "Model usage milestone",
            extra={
                "model": model_name,
                "operation": operation,
                "count": _model_usage_stats[key]
            }
        )


def get_model_usage_stats() -> dict:
    """Get model usage statistics"""
    logger.debug(
        "Model usage statistics requested",
        extra={"stats": _model_usage_stats}
    )
    
    return _model_usage_stats.copy()

# MODULE-LEVEL STATUS

def log_models_status():
    """Log status of all defined models"""
    models = [
        "CreateCandidateRequest",
        "CreateJobRequest",
        "ScheduleInterviewRequest",
        "UpdateInterviewStatusRequest",
        "CandidateResponse",
        "JobResponse",
        "InterviewResponse",
        "InterviewJoinResponse",
        "ScorecardResponse",
        "TranscriptEntry",
        "EvaluationScoreDetail"
    ]
    
    logger.info(
        "API Models Status",
        extra={
            "total_models": len(models),
            "request_models": 4,
            "response_models": 7,
            "webhook_models": 2
        }
    )


if __name__ == "__main__":
    logger.info("API models module loaded")
    log_models_status()
    
    # Example: Test validation logging
    try:
        logger.info("Testing candidate request validation")
        
        candidate = CreateCandidateRequest(
            name="Test User",
            email="test@example.com",
            job_id=1
        )
        
        logger.info("Test validation successful")
    
    except Exception as e:
        logger.error(
            "Test validation failed",
            extra={"error": str(e)},
            exc_info=True
        )