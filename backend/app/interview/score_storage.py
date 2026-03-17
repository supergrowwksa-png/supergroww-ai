"""
Score Storage - Persisting Evaluation Scores to Database
"""

from database import get_session, EvaluationScore, Interview
from logger import get_logger, PerformanceLogger, log_exception
from datetime import datetime
from typing import List, Dict, Optional

logger = get_logger("score_storage")


async def store_answer_score(
    interview_id: int,
    topic: str,
    score_data: Dict,
    transcript_ids: Optional[List[int]] = None
) -> Optional[EvaluationScore]:
    """
    Store a per-answer evaluation score (Level 1).
    
    Args:
        interview_id: Interview ID
        topic: Topic/category being evaluated
        score_data: Dict with completeness, technical_depth, specificity, communication, justification
        transcript_ids: Optional list of transcript IDs as evidence
    
    Returns:
        Created EvaluationScore record or None on error
    """
    logger.info(
        "Storing answer evaluation score",
        extra={
            "interview_id": interview_id,
            "topic": topic
        }
    )
    
    db = next(get_session())
    
    try:
        with PerformanceLogger(logger, "store_answer_score", interview_id=interview_id):
            # Calculate average score from 4 dimensions (1-5 scale)
            avg_score = (
                score_data.get("completeness", 0) +
                score_data.get("technical_depth", 0) +
                score_data.get("specificity", 0) +
                score_data.get("communication", 0)
            ) / 4.0
            
            # Convert to 0-100 scale
            score_value = (avg_score / 5.0) * 100.0
            
            # Create record
            eval_score = EvaluationScore(
                interview_id=interview_id,
                level=1,  # Per-answer level
                category=topic,
                score_value=score_value,
                max_score=100.0,
                weight=1.0,
                justification=score_data.get("justification", ""),
                evidence_transcript_ids=transcript_ids or [],
                evaluated_at=datetime.utcnow()
            )
            
            db.add(eval_score)
            db.commit()
            db.refresh(eval_score)
            
            logger.info(
                "Answer score stored successfully",
                extra={
                    "interview_id": interview_id,
                    "score_id": eval_score.id,
                    "topic": topic,
                    "score_value": round(score_value, 2)
                }
            )
            
            return eval_score
    
    except Exception as e:
        db.rollback()
        log_exception(logger, e, {
            "operation": "store_answer_score",
            "interview_id": interview_id,
            "topic": topic
        })
        return None
    
    finally:
        db.close()


async def store_final_scores(
    interview_id: int,
    overall_score: float,
    recommendation: str,
    summary: str
) -> bool:
    """
    Store final interview results in the Interview table.
    
    Args:
        interview_id: Interview ID
        overall_score: Final score (0-100)
        recommendation: Hiring recommendation
        summary: AI-generated summary
    
    Returns:
        True if successful, False otherwise
    """
    logger.info(
        "Storing final interview scores",
        extra={
            "interview_id": interview_id,
            "overall_score": round(overall_score, 2),
            "recommendation": recommendation
        }
    )
    
    db = next(get_session())
    
    try:
        with PerformanceLogger(logger, "store_final_scores", interview_id=interview_id):
            # Update interview record
            interview = db.query(Interview).filter(
                Interview.id == interview_id
            ).first()
            
            if not interview:
                logger.error(
                    "Interview not found for final score update",
                    extra={"interview_id": interview_id}
                )
                return False
            
            interview.overall_score = overall_score
            interview.recommendation = recommendation
            interview.ai_summary = summary
            interview.ended_at = datetime.utcnow()
            
            # Calculate duration if started_at exists
            if interview.started_at:
                duration = (datetime.utcnow() - interview.started_at).total_seconds()
                interview.duration_seconds = int(duration)
            
            db.commit()
            
            logger.info(
                "Final scores stored successfully",
                extra={
                    "interview_id": interview_id,
                    "overall_score": round(overall_score, 2)
                }
            )
            
            return True
    
    except Exception as e:
        db.rollback()
        log_exception(logger, e, {
            "operation": "store_final_scores",
            "interview_id": interview_id
        })
        return False
    
    finally:
        db.close()

# Open backend/app/interview/score_storage.py

async def store_aggregated_scores(
    interview_id: int,
    topic_aggregates: Dict[str, Dict],
    overall_score: Optional[float] = None 
) -> bool:
    """
    Saves Level 2 (Topic) scores. Only saves Level 3 (Overall) if provided.
    """
    logger.info("Storing Level 2 scores", extra={"interview_id": interview_id,"num_topics": len(topic_aggregates),
            "overall_score": overall_score})
    
    db = next(get_session())
    
    try:
        with PerformanceLogger(logger, "store_aggregated_scores", interview_id=interview_id):
            
            # Save Level 2 Scores (Per Topic)
            for topic, data in topic_aggregates.items():
                topic_score = EvaluationScore(
                    interview_id=interview_id,
                    level=2,  # Level 2 = Topic
                    category=topic,
                    score_value=data.get("score", 0.0),
                    max_score=100.0,
                    weight=1.0,
                    justification=f"Aggregated from {data.get('num_answers', 0)} answers",
                    evaluated_at=datetime.utcnow()
                )
                db.add(topic_score)

            # 2. Save Level 3 Score (Overall) - ONLY IF VALID SCORE PROVIDED
            # This fixes the "0 score" and missing Level 2 issue
            if overall_score is not None and overall_score > 0:
                final_score_record = EvaluationScore(
                    interview_id=interview_id,
                    level=3,  # Level 3 = Overall
                    category="Overall Interview",
                    score_value=overall_score,
                    max_score=100.0,
                    weight=1.0,
                    justification="Final weighted score across all topics",
                    evaluated_at=datetime.utcnow()
                )
                db.add(final_score_record)
                logger.info("✅ Level 3 Score saved")
            
            db.commit()
            logger.info("✅ Level 2 scores committed to database")
            return True
            
    except Exception as e:
        db.rollback()
        log_exception(logger, e, {"operation": "store_aggregated_scores"})
        return False
    finally:
        db.close()