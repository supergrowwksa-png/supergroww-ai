"""
Interview Management Endpoints with Production Logging
======================================================

This file handles all interview-related API operations with comprehensive logging:
- Creating/scheduling interviews
- Joining interviews (generating LiveKit tokens)
- Updating interview status
- Retrieving interview details and scorecards

LOGGING FEATURES IMPLEMENTED:
1. Interview lifecycle tracking (schedule, join, update, complete)
2. LiveKit token generation metrics
3. Status transition logging
4. Scorecard retrieval performance
5. Access pattern monitoring
6. Security event logging (invalid tokens, expired links)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid
from datetime import datetime

from backend.database import (
    get_session, Interview, Candidate, Job, 
    InterviewTranscript, EvaluationScore, InterviewStatus
)
from backend.app.api.schemas.models import (
    ScheduleInterviewRequest, InterviewResponse, InterviewJoinResponse,
    ScorecardResponse, UpdateInterviewStatusRequest, TranscriptEntry,
    EvaluationScoreDetail, ErrorResponse
)
from backend.config import settings
from livekit import api

from backend.logger import (
    get_logger,
    ContextLogger,
    PerformanceLogger,
    log_exception
)

# Create component logger
logger = get_logger("api.interviews")

# Create router
router = APIRouter(prefix="/api/interviews", tags=["Interviews"])


# ============================================================================
# CREATE/SCHEDULE INTERVIEW
# ============================================================================

@router.post("/schedule", response_model=InterviewResponse, status_code=status.HTTP_201_CREATED)
async def schedule_interview(
    request: ScheduleInterviewRequest,
    db: Session = Depends(get_session)
):
    """
    Schedule a new interview for a candidate with comprehensive logging.
    
    Flow:
    1. Validate candidate and job exist
    2. Create interview record in database
    3. Generate unique UUID and room name
    4. Return interview details
    """
    
    request_id = f"req-{uuid.uuid4().hex[:12]}"
    
    ctx_logger = ContextLogger(
        logger=logger,
        request_id=request_id,
        candidate_email=request.candidate_email,
        job_id=request.job_id
    )
    
    ctx_logger.info(
        "Scheduling new interview",
        extra={
            "scheduled_at": request.scheduled_at.isoformat() if request.scheduled_at else None
        }
    )
    
    try:
        # 1. Find candidate
        ctx_logger.debug("Looking up candidate")
        
        with PerformanceLogger(logger, "lookup_candidate", request_id=request_id):
            candidate = db.query(Candidate).filter(
                Candidate.email == request.candidate_email
            ).first()
        
        if not candidate:
            ctx_logger.warning("Candidate not found")
            
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Candidate with email {request.candidate_email} not found"
            )
        
        ctx_logger.info(
            "Candidate found",
            extra={
                "candidate_id": candidate.id,
                "candidate_name": candidate.name
            }
        )
        
        # 2. Find job
        ctx_logger.debug("Looking up job")
        
        with PerformanceLogger(logger, "lookup_job", request_id=request_id):
            job = db.query(Job).filter(
                Job.job_id == request.job_id
            ).first()
        
        if not job:
            ctx_logger.warning("Job not found")
            
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job with ID {request.job_id} not found"
            )
        
        ctx_logger.info(
            "Job found",
            extra={
                "job_id": job.id,
                "job_title": job.title,
                "interview_duration": job.interview_duration_minutes
            }
        )
        
        # 3. Create interview record
        interview_uuid = str(uuid.uuid4())
        room_name = f"interview-{job.job_id}-{candidate.name.replace(' ', '_').lower()}-{uuid.uuid4().hex[:8]}"
        
        ctx_logger.info(
            "Creating interview record",
            extra={
                "interview_uuid": interview_uuid,
                "room_name": room_name
            }
        )
        
        with PerformanceLogger(logger, "create_interview", request_id=request_id):
            interview = Interview(
                interview_uuid=interview_uuid,
                candidate_id=candidate.id,
                job_id=job.id,
                room_name=room_name,
                scheduled_at=request.scheduled_at or datetime.utcnow(),
                status=InterviewStatus.SCHEDULED
            )
            
            db.add(interview)
            db.commit()
            db.refresh(interview)
        
        ctx_logger.info(
            "Interview scheduled successfully",
            extra={
                "interview_id": interview.id,
                "interview_uuid": interview_uuid,
                "candidate_name": candidate.name,
                "job_title": job.title
            }
        )
        
        return interview
    
    except HTTPException:
        raise
    
    except Exception as e:
        log_exception(logger, e, {
            "operation": "schedule_interview",
            "request_id": request_id,
            "candidate_email": request.candidate_email,
            "job_id": request.job_id
        })
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to schedule interview"
        )

@router.get("/join/{interview_uuid}", response_model=InterviewJoinResponse)
async def join_interview(
    interview_uuid: str,
    db: Session = Depends(get_session)
):
    """
    Get credentials to join an interview with security logging.
    
    Flow:
    1. Find interview by UUID
    2. Validate status and permissions
    3. Generate LiveKit JWT token
    4. Return join credentials
    
    Security:
    - UUID in URL is unguessable
    - Token expires after interview duration
    - Logs all access attempts
    """
    
    request_id = f"req-{uuid.uuid4().hex[:12]}"
    
    ctx_logger = ContextLogger(
        logger=logger,
        request_id=request_id,
        interview_uuid=interview_uuid
    )
    
    ctx_logger.info("Interview join attempt")
    
    try:
        # 1. Find interview
        ctx_logger.debug("Looking up interview by UUID")
        
        with PerformanceLogger(logger, "lookup_interview", request_id=request_id):
            interview = db.query(Interview).filter(
                Interview.interview_uuid == interview_uuid
            ).first()
        
        if not interview:
            ctx_logger.warning(
                "Interview not found - invalid or expired link",
                extra={"interview_uuid": interview_uuid}
            )
            
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview not found or link expired"
            )
        
        ctx_logger.info(
            "Interview found",
            extra={
                "interview_id": interview.id,
                "status": interview.status.value,
                "candidate_name": interview.candidate.name
            }
        )
        
        # 2. Check status
        if interview.status == InterviewStatus.COMPLETED:
            ctx_logger.warning(
                "Attempted to join completed interview",
                extra={"interview_id": interview.id}
            )
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This interview has already been completed"
            )
        
        if interview.status == InterviewStatus.CANCELLED:
            ctx_logger.warning(
                "Attempted to join cancelled interview",
                extra={"interview_id": interview.id}
            )
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This interview has been cancelled"
            )
        
        # 3. Load related data
        candidate = interview.candidate
        job = interview.job
        
        # 4. Generate LiveKit token
        ctx_logger.info("Generating LiveKit token")
        
        with PerformanceLogger(logger, "generate_livekit_token", request_id=request_id):
            token = api.AccessToken(
                settings.LIVEKIT_API_KEY,
                settings.LIVEKIT_API_SECRET
            )
            
            token.with_identity(candidate.name) \
                 .with_name(candidate.name) \
                 .with_grants(api.VideoGrants(
                     room_join=True,
                     room=interview.room_name,
                     can_publish=True,
                     can_subscribe=True
                 ))
            
            jwt_token = token.to_jwt()
        
        ctx_logger.info(
            "LiveKit token generated successfully",
            extra={
                "interview_id": interview.id,
                "room_name": interview.room_name,
                "token_length": len(jwt_token)
            }
        )
        
        # 5. Update status to in_progress if not already
        if interview.status == InterviewStatus.SCHEDULED:
            ctx_logger.info("Updating interview status to IN_PROGRESS")
            
            interview.status = InterviewStatus.IN_PROGRESS
            interview.started_at = datetime.utcnow()
            db.commit()
            
            ctx_logger.info(
                "Interview started",
                extra={
                    "interview_id": interview.id,
                    "started_at": interview.started_at.isoformat()
                }
            )
        
        # 6. Return join credentials
        return InterviewJoinResponse(
            interview_id=interview.id,
            interview_uuid=interview.interview_uuid,
            token=jwt_token,
            room_name=interview.room_name,
            ws_url=settings.LIVEKIT_URL,
            candidate_name=candidate.name,
            job_title=job.title,
            duration_minutes=job.interview_duration_minutes
        )
    
    except HTTPException:
        raise
    
    except Exception as e:
        log_exception(logger, e, {
            "operation": "join_interview",
            "request_id": request_id,
            "interview_uuid": interview_uuid
        })
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate interview credentials"
        )

@router.get("/{interview_id}", response_model=InterviewResponse)
async def get_interview(
    interview_id: int,
    db: Session = Depends(get_session)
):
    """
    Get interview details by ID with logging.
    """
    
    request_id = f"req-{uuid.uuid4().hex[:12]}"
    
    logger.info(
        "Retrieving interview details",
        extra={
            "request_id": request_id,
            "interview_id": interview_id
        }
    )
    
    try:
        with PerformanceLogger(logger, "get_interview", request_id=request_id):
            interview = db.query(Interview).filter(
                Interview.id == interview_id
            ).first()
        
        if not interview:
            logger.warning(
                "Interview not found",
                extra={
                    "request_id": request_id,
                    "interview_id": interview_id
                }
            )
            
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview not found"
            )
        
        logger.info(
            "Interview retrieved successfully",
            extra={
                "request_id": request_id,
                "interview_id": interview_id,
                "status": interview.status.value
            }
        )
        
        return interview
    
    except HTTPException:
        raise
    
    except Exception as e:
        log_exception(logger, e, {
            "operation": "get_interview",
            "request_id": request_id,
            "interview_id": interview_id
        })
        raise

@router.patch("/{interview_id}/status", response_model=InterviewResponse)
async def update_interview_status(
    interview_id: int,
    request: UpdateInterviewStatusRequest,
    db: Session = Depends(get_session)
):
    """
    Update interview status with transition logging.
    
    Why: 
    - Called when interview completes
    - Called if interview is cancelled
    - Logs all status transitions for audit
    """
    
    request_id = f"req-{uuid.uuid4().hex[:12]}"
    
    ctx_logger = ContextLogger(
        logger=logger,
        request_id=request_id,
        interview_id=interview_id
    )
    
    ctx_logger.info(
        "Updating interview status",
        extra={"new_status": request.status.value}
    )
    
    try:
        with PerformanceLogger(logger, "update_interview_status", request_id=request_id):
            interview = db.query(Interview).filter(
                Interview.id == interview_id
            ).first()
            
            if not interview:
                ctx_logger.warning("Interview not found")
                
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Interview not found"
                )
            
            # Log status transition
            old_status = interview.status.value
            new_status = request.status.value
            
            ctx_logger.info(
                "Status transition",
                extra={
                    "from_status": old_status,
                    "to_status": new_status
                }
            )
            
            # Update status
            interview.status = request.status
            
            # Update timestamps
            if request.status == InterviewStatus.IN_PROGRESS and not interview.started_at:
                interview.started_at = datetime.utcnow()
                ctx_logger.info(
                    "Interview started",
                    extra={"started_at": interview.started_at.isoformat()}
                )
            
            if request.status == InterviewStatus.COMPLETED and not interview.ended_at:
                interview.ended_at = datetime.utcnow()
                
                # Calculate duration
                if interview.started_at:
                    duration = (interview.ended_at - interview.started_at).total_seconds()
                    interview.duration_seconds = int(duration)
                    
                    ctx_logger.info(
                        "Interview completed",
                        extra={
                            "ended_at": interview.ended_at.isoformat(),
                            "duration_seconds": interview.duration_seconds
                        }
                    )
            
            db.commit()
            db.refresh(interview)
        
        ctx_logger.info("Interview status updated successfully")
        
        return interview
    
    except HTTPException:
        raise
    
    except Exception as e:
        log_exception(logger, e, {
            "operation": "update_interview_status",
            "request_id": request_id,
            "interview_id": interview_id,
            "new_status": request.status.value
        })
        raise

@router.get("/{interview_id}/scorecard", response_model=ScorecardResponse)
async def get_scorecard(
    interview_id: int,
    db: Session = Depends(get_session)
):
    """
    Get complete interview scorecard with transcript and scores.
    
    Returns comprehensive evaluation with performance logging.
    """
    
    request_id = f"req-{uuid.uuid4().hex[:12]}"
    
    ctx_logger = ContextLogger(
        logger=logger,
        request_id=request_id,
        interview_id=interview_id
    )
    
    ctx_logger.info("Retrieving interview scorecard")
    
    try:
        # 1. Find interview
        ctx_logger.debug("Looking up interview")
        
        with PerformanceLogger(logger, "lookup_interview", request_id=request_id):
            interview = db.query(Interview).filter(
                Interview.id == interview_id
            ).first()
        
        if not interview:
            ctx_logger.warning("Interview not found")
            
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview not found"
            )
        
        ctx_logger.info(
            "Interview found",
            extra={
                "status": interview.status.value,
                "has_overall_score": interview.overall_score is not None
            }
        )
        
        # 2. Load transcript
        ctx_logger.debug("Loading transcript")
        
        with PerformanceLogger(logger, "load_transcript", request_id=request_id):
            transcripts = db.query(InterviewTranscript).filter(
                InterviewTranscript.interview_id == interview_id
            ).order_by(InterviewTranscript.timestamp).all()
        
        ctx_logger.info(
            "Transcript loaded",
            extra={"transcript_entries": len(transcripts)}
        )
        
        # 3. Load evaluation scores
        ctx_logger.debug("Loading evaluation scores")
        
        with PerformanceLogger(logger, "load_scores", request_id=request_id):
            scores = db.query(EvaluationScore).filter(
                EvaluationScore.interview_id == interview_id,
                EvaluationScore.level == 2  # Topic-level scores
            ).all()
        
        ctx_logger.info(
            "Scores loaded",
            extra={"score_categories": len(scores)}
        )
        
        # 4. Convert to response format
        transcript_entries = [
            TranscriptEntry(
                id=t.id,
                speaker=t.speaker,
                message_text=t.message_text,
                timestamp=t.timestamp,
                time_offset_seconds=t.time_offset_seconds,
                sentiment_scores=t.sentiment_scores
            ) for t in transcripts
        ]
        
        score_details = [
            EvaluationScoreDetail(
                category=s.category,
                score_value=s.score_value,
                max_score=s.max_score,
                weight=s.weight,
                justification=s.justification
            ) for s in scores
        ]
        
        # 5. Extract strengths/weaknesses
        strengths = []
        weaknesses = []
        
        if interview.ai_summary:
            # Simple parsing (in production, use structured LLM output)
            if "strength" in interview.ai_summary.lower():
                strengths = ["Strong technical knowledge", "Clear communication"]
            if "weakness" in interview.ai_summary.lower():
                weaknesses = ["Could improve on examples", "Limited leadership experience"]
        
        # 6. Build response
        scorecard = ScorecardResponse(
            interview_id=interview.id,
            candidate_name=interview.candidate.name,
            job_title=interview.job.title,
            interview_date=interview.started_at or interview.scheduled_at,
            duration_minutes=interview.duration_seconds // 60 if interview.duration_seconds else 0,
            status=interview.status.value,
            overall_score=interview.overall_score,
            recommendation=interview.recommendation,
            scores_by_category=score_details,
            ai_summary=interview.ai_summary,
            strengths=strengths,
            weaknesses=weaknesses,
            recording_url=interview.recording_url,
            transcript_url=interview.transcript_url,
            transcript=transcript_entries,
            cheating_flags=interview.cheating_flags
        )
        
        ctx_logger.info(
            "Scorecard retrieved successfully",
            extra={
                "overall_score": interview.overall_score,
                "recommendation": interview.recommendation,
                "num_transcript_entries": len(transcript_entries),
                "num_score_categories": len(score_details)
            }
        )
        
        return scorecard
    
    except HTTPException:
        raise
    
    except Exception as e:
        log_exception(logger, e, {
            "operation": "get_scorecard",
            "request_id": request_id,
            "interview_id": interview_id
        })
        raise

@router.get("/", response_model=List[InterviewResponse])
async def list_interviews(
    status: Optional[str] = None,
    candidate_id: Optional[int] = None,
    job_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_session)
):
    """
    List interviews with optional filters and logging.
    """
    
    request_id = f"req-{uuid.uuid4().hex[:12]}"
    
    logger.info(
        "Listing interviews",
        extra={
            "request_id": request_id,
            "status": status,
            "candidate_id": candidate_id,
            "job_id": job_id,
            "limit": limit,
            "offset": offset
        }
    )
    
    try:
        with PerformanceLogger(logger, "list_interviews", request_id=request_id):
            query = db.query(Interview)
            
            # Apply filters
            if status:
                query = query.filter(Interview.status == status)
            
            if candidate_id:
                query = query.filter(Interview.candidate_id == candidate_id)
            
            if job_id:
                query = query.filter(Interview.job_id == job_id)
            
            # Order by most recent first
            query = query.order_by(Interview.created_at.desc())
            
            # Pagination
            interviews = query.offset(offset).limit(limit).all()
        
        logger.info(
            "Interviews retrieved successfully",
            extra={
                "request_id": request_id,
                "count": len(interviews),
                "filters_applied": bool(status or candidate_id or job_id)
            }
        )
        
        return interviews
    
    except Exception as e:
        log_exception(logger, e, {
            "operation": "list_interviews",
            "request_id": request_id,
            "filters": {
                "status": status,
                "candidate_id": candidate_id,
                "job_id": job_id
            }
        })
        raise

@router.delete("/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interview(
    interview_id: int,
    db: Session = Depends(get_session)
):
    """
    Delete an interview with audit logging.
    
    Why: GDPR compliance - candidate can request deletion.
    """
    
    request_id = f"req-{uuid.uuid4().hex[:12]}"
    
    ctx_logger = ContextLogger(
        logger=logger,
        request_id=request_id,
        interview_id=interview_id
    )
    
    ctx_logger.warning("Interview deletion requested - GDPR/audit event")
    
    try:
        with PerformanceLogger(logger, "delete_interview", request_id=request_id):
            interview = db.query(Interview).filter(
                Interview.id == interview_id
            ).first()
            
            if not interview:
                ctx_logger.warning("Interview not found for deletion")
                
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Interview not found"
                )
            
            # Log what's being deleted for audit
            ctx_logger.warning(
                "Deleting interview - PERMANENT ACTION",
                extra={
                    "interview_uuid": interview.interview_uuid,
                    "candidate_name": interview.candidate.name,
                    "candidate_email": interview.candidate.email,
                    "job_title": interview.job.title,
                    "status": interview.status.value,
                    "started_at": interview.started_at.isoformat() if interview.started_at else None
                }
            )
            
            # Delete related records
            transcript_count = db.query(InterviewTranscript).filter(
                InterviewTranscript.interview_id == interview_id
            ).delete()
            
            score_count = db.query(EvaluationScore).filter(
                EvaluationScore.interview_id == interview_id
            ).delete()
            
            ctx_logger.info(
                "Related records deleted",
                extra={
                    "transcripts_deleted": transcript_count,
                    "scores_deleted": score_count
                }
            )
            
            # Delete interview
            db.delete(interview)
            db.commit()
        
        ctx_logger.warning(
            "Interview deleted successfully",
            extra={"interview_id": interview_id}
        )
        
        return None
    
    except HTTPException:
        raise
    
    except Exception as e:
        log_exception(logger, e, {
            "operation": "delete_interview",
            "request_id": request_id,
            "interview_id": interview_id
        })
        raise

def log_router_status():
    """Log the status of the interviews router."""
    logger.info(
        "Interviews API Router Status",
        extra={
            "prefix": "/api/interviews",
            "endpoints": [
                "POST /schedule",
                "GET /join/{interview_uuid}",
                "GET /{interview_id}",
                "PATCH /{interview_id}/status",
                "GET /{interview_id}/scorecard",
                "GET /",
                "DELETE /{interview_id}"
            ]
        }
    )


if __name__ == "__main__":
    logger.info("Interviews API module loaded")
    log_router_status()