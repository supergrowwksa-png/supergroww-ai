"""
Database Debug Utilities - CORRECTED VERSION
Save as: backend/app/interview/db_debug.py

FIXES:
1. Added InterviewStatus enum import
2. Fixed foreign key test to use existing interview
3. Fixed status queries to use enum instead of strings
"""

import asyncio
import logging
from datetime import datetime
from functools import wraps
from typing import Optional, Dict, Any

# Add to path
import sys
import os
current_file = os.path.abspath(__file__)
interview_dir = os.path.dirname(current_file)
app_dir = os.path.dirname(interview_dir)
backend_dir = os.path.dirname(app_dir)
sys.path.insert(0, backend_dir)

from database import (
    get_session,
    EvaluationScore,
    InterviewTranscript,
    Interview,
    Candidate,
    Job,
    InterviewStatus  
)
from logger import get_logger, log_exception

logger = get_logger("db_debug")


def log_db_operation(operation_name: str):
    """Decorator to log database operations with timing"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = datetime.utcnow()
            logger.info(f"🔵 Starting {operation_name}")
            try:
                result = await func(*args, **kwargs)
                duration = (datetime.utcnow() - start_time).total_seconds()
                logger.info(f"✅ {operation_name} succeeded in {duration:.2f}s")
                return result
            except Exception as e:
                duration = (datetime.utcnow() - start_time).total_seconds()
                logger.error(f"❌ {operation_name} failed after {duration:.2f}s: {e}")
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = datetime.utcnow()
            logger.info(f"🔵 Starting {operation_name}")
            try:
                result = func(*args, **kwargs)
                duration = (datetime.utcnow() - start_time).total_seconds()
                logger.info(f"✅ {operation_name} succeeded in {duration:.2f}s")
                return result
            except Exception as e:
                duration = (datetime.utcnow() - start_time).total_seconds()
                logger.error(f"❌ {operation_name} failed after {duration:.2f}s: {e}")
                raise
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


@log_db_operation("verify_database_connectivity")
async def verify_database_connectivity() -> bool:
    """
    Test database connection and table access
    
    Returns:
        bool: True if all tests pass, False otherwise
    """
    logger.info("Testing database connectivity...")
    
    db = next(get_session())
    all_tests_passed = True
    
    try:
        # Test 1 - Can we query evaluation_scores?
        logger.info("Test 1: Checking evaluation_scores table access...")
        try:
            count = db.query(EvaluationScore).count()
            logger.info(f"✅ evaluation_scores accessible. Current count: {count}")
        except Exception as e:
            logger.error(f"❌ Cannot access evaluation_scores: {e}")
            all_tests_passed = False
        
        # Test 2 - Can we query interview_transcripts?
        logger.info("Test 2: Checking interview_transcripts table access...")
        try:
            count = db.query(InterviewTranscript).count()
            logger.info(f"✅ interview_transcripts accessible. Current count: {count}")
        except Exception as e:
            logger.error(f"❌ Cannot access interview_transcripts: {e}")
            all_tests_passed = False
        
        # Test 3 - Can we query interviews?
        logger.info("Test 3: Checking interviews table access...")
        try:
            count = db.query(Interview).count()
            logger.info(f"✅ interviews accessible. Current count: {count}")
        except Exception as e:
            logger.error(f"❌ Cannot access interviews: {e}")
            all_tests_passed = False
        
        #Test 4 - Use existing interview ID for foreign key test
        logger.info("Test 4 - Testing INSERT permission on evaluation_scores...")
        try:
            # First, find an existing interview to use for the test
            existing_interview = db.query(Interview).first()
            
            if not existing_interview:
                logger.warning("⚠️ No interviews found - skipping INSERT test")
                logger.info("ℹ️ To test INSERT, create at least one interview first")
            else:
                test_interview_id = existing_interview.id
                logger.info(f"✅ Using existing interview ID: {test_interview_id}")
                
                # Now test the insert with a valid interview_id
                test_score = EvaluationScore(
                    interview_id=test_interview_id,
                    level=1,
                    category="TEST_CONNECTIVITY",
                    score_value=100.0,
                    max_score=100.0,
                    weight=1.0,
                    justification="Database connectivity test record",
                    evaluated_at=datetime.utcnow()
                )
                
                db.add(test_score)
                db.flush()  # Try to insert without committing
                
                test_id = test_score.id
                logger.info(f"✅ Test insert succeeded (not committed). Would have ID: {test_id}")
                
                db.rollback()  # Roll back the test insert
                logger.info("✅ Test rollback succeeded")
            
        except Exception as e:
            logger.error(f"❌ Cannot insert into evaluation_scores: {e}")
            all_tests_passed = False
            try:
                db.rollback()
            except:
                pass
        
        # Test 5 - Check recent activity
        logger.info("Test 5: Checking recent database activity...")
        try:
            recent_interviews = db.query(Interview).order_by(
                Interview.created_at.desc()
            ).limit(5).all()
            
            logger.info(f"✅ Found {len(recent_interviews)} recent interviews")
            
            for interview in recent_interviews:
                # Count scores for this interview
                score_count = db.query(EvaluationScore).filter(
                    EvaluationScore.interview_id == interview.id
                ).count()
                
                # Count transcripts for this interview
                transcript_count = db.query(InterviewTranscript).filter(
                    InterviewTranscript.interview_id == interview.id
                ).count()
                
                logger.info(
                    f"  Interview {interview.id}: "
                    f"{score_count} scores, {transcript_count} transcripts, "
                    f"status={interview.status}"
                )
        
        except Exception as e:
            logger.error(f"❌ Error checking recent activity: {e}")
            all_tests_passed = False
        
        if all_tests_passed:
            logger.info("✅ All database connectivity tests passed!")
        else:
            logger.warning("⚠️ Some database connectivity tests failed")
        
        return all_tests_passed
    
    except Exception as e:
        log_exception(logger, e, {"operation": "verify_database_connectivity"})
        return False
    
    finally:
        db.close()


@log_db_operation("get_database_summary")
def get_database_summary() -> Dict[str, Any]:
    """
    Get overall database summary statistics
    
    Returns:
        Dict containing database-wide statistics
    """
    db = next(get_session())
    
    try:
        total_interviews = db.query(Interview).count()
        total_candidates = db.query(Candidate).count()
        total_jobs = db.query(Job).count()
        total_scores = db.query(EvaluationScore).count()
        total_transcripts = db.query(InterviewTranscript).count()
        
        # Count by interview status using enum
        status_counts = {}
        for status in InterviewStatus:  # Iterate over enum values
            count = db.query(Interview).filter(
                Interview.status == status  # Compare enum to enum
            ).count()
            status_counts[status.value] = count  # Store with string key for JSON
        
        # Count scores by level
        scores_by_level = {
            "level_1": db.query(EvaluationScore).filter(EvaluationScore.level == 1).count(),
            "level_2": db.query(EvaluationScore).filter(EvaluationScore.level == 2).count(),
            "level_3": db.query(EvaluationScore).filter(EvaluationScore.level == 3).count()
        }
        
        # Recent activity
        recent_interviews = db.query(Interview).order_by(
            Interview.created_at.desc()
        ).limit(10).all()
        
        recent_activity = []
        for interview in recent_interviews:
            score_count = db.query(EvaluationScore).filter(
                EvaluationScore.interview_id == interview.id
            ).count()
            
            transcript_count = db.query(InterviewTranscript).filter(
                InterviewTranscript.interview_id == interview.id
            ).count()
            
            recent_activity.append({
                "interview_id": interview.id,
                "status": str(interview.status),
                "created_at": interview.created_at.isoformat() if interview.created_at else None,
                "scores": score_count,
                "transcripts": transcript_count
            })
        
        summary = {
            "totals": {
                "interviews": total_interviews,
                "candidates": total_candidates,
                "jobs": total_jobs,
                "scores": total_scores,
                "transcripts": total_transcripts
            },
            "interview_status": status_counts,
            "scores_by_level": scores_by_level,
            "recent_activity": recent_activity,
            "health_indicators": {
                "avg_scores_per_interview": round(total_scores / total_interviews, 2) if total_interviews > 0 else 0,
                "avg_transcripts_per_interview": round(total_transcripts / total_interviews, 2) if total_interviews > 0 else 0,
                "interviews_with_no_scores": db.query(Interview).outerjoin(EvaluationScore).filter(
                    EvaluationScore.id == None
                ).count(),
                "interviews_with_no_transcripts": db.query(Interview).outerjoin(InterviewTranscript).filter(
                    InterviewTranscript.id == None
                ).count()
            }
        }
        
        logger.info("Database summary retrieved", extra=summary)
        
        return summary
    
    except Exception as e:
        log_exception(logger, e, {"operation": "get_database_summary"})
        return {"error": str(e)}
    
    finally:
        db.close()


async def main():
    """Test the debug utilities"""
    logger.info("Starting database debug utilities test")
    
    # Test connectivity
    print("\n" + "="*60)
    print("DATABASE CONNECTIVITY TEST")
    print("="*60)
    connectivity_ok = await verify_database_connectivity()
    print(f"\nConnectivity test result: {'✅ PASS' if connectivity_ok else '❌ FAIL'}")
    
    # Get database summary
    print("\n" + "="*60)
    print("DATABASE SUMMARY")
    print("="*60)
    summary = get_database_summary()
    
    import json
    print(json.dumps(summary, indent=2))
    
    logger.info("Database debug test completed")


if __name__ == "__main__":
    asyncio.run(main())