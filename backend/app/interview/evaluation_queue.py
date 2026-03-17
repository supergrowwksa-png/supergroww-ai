"""
Enhanced Async Evaluation Queue - Background Score Processing
==============================================================

COMPLETE IMPLEMENTATION with:
✅ Non-blocking evaluation
✅ Automatic topic aggregation
✅ Graceful shutdown
✅ Error recovery
✅ Performance monitoring

STEP-BY-STEP GUIDE:
-------------------

STEP 1: Queue receives evaluation task (non-blocking)
STEP 2: Background worker processes evaluation
STEP 3: Store Level 1 score in database
STEP 4: Auto-check if topic is complete
STEP 5: Auto-aggregate Level 2 score if topic complete
STEP 6: Continue until interview ends
STEP 7: Calculate and store Level 3 (overall) score

"""

import asyncio
from typing import Dict, Optional, List
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict

from backend.logger import get_logger, PerformanceLogger, log_exception

logger = get_logger("evaluation_queue_enhanced")


@dataclass
class EvaluationTask:
    """A pending evaluation task"""
    interview_id: int
    question: str
    answer: str
    topic: str
    timestamp: datetime
    transcript_ids: List[int] = field(default_factory=list)


@dataclass
class QueueStats:
    """Statistics for monitoring queue health"""
    total_processed: int = 0
    total_failed: int = 0
    avg_processing_time_ms: float = 0.0
    queue_size: int = 0
    last_processed_at: Optional[datetime] = None


class EvaluationQueueEnhanced:
    """
    Production-ready background evaluation queue.
    
    Key Features:
    - Non-blocking evaluation submission
    - Automatic topic aggregation
    - Graceful shutdown handling
    - Performance monitoring
    - Error recovery
    
    Usage:
    ------
    # Initialize
    queue = EvaluationQueueEnhanced()
    await queue.start()
    
    # Queue evaluation (non-blocking - returns immediately)
    await queue.queue_evaluation(
        interview_id=123,
        question="What is Python?",
        answer="Python is a programming language...",
        topic="Python Basics"
    )
    
    # Graceful shutdown (waits for pending tasks)
    await queue.stop()
    """
    
    def __init__(self, num_workers: int = 2):
        """
        Initialize the evaluation queue.
        
        Args:
            num_workers: Number of background workers (default: 2)
        """
        self.queue: asyncio.Queue = asyncio.Queue()
        self.num_workers = num_workers
        self.workers: List[asyncio.Task] = []
        self.running = False
        
        # Track questions per topic for auto-aggregation
        self.topic_question_count: Dict[tuple, int] = defaultdict(int)
        # (interview_id, topic) -> count
        
        # Performance monitoring
        self.stats = QueueStats()
        
        # Lazy-load evaluator (only when needed)
        self._evaluator = None
        
        logger.info(
            "EvaluationQueueEnhanced initialized",
            extra={"num_workers": num_workers}
        )
    
    @property
    def evaluator(self):
        """Lazy-load evaluator to avoid import cycles"""
        if self._evaluator is None:
            from evaluation_agent import get_evaluator
            self._evaluator = get_evaluator()
            logger.info("Evaluator loaded")
        return self._evaluator
    
    async def start(self):
        """
        Start background evaluation workers.
        
        STEP 1: Call this when agent initializes
        """
        if self.running:
            logger.warning("Workers already running")
            return
        
        self.running = True
        
        # Start multiple workers for parallel processing
        for i in range(self.num_workers):
            worker = asyncio.create_task(
                self._worker(worker_id=i),
                name=f"eval-worker-{i}"
            )
            self.workers.append(worker)
        
        logger.info(
            f" Started {self.num_workers} evaluation workers",
            extra={"num_workers": self.num_workers}
        )
    
    async def stop(self, timeout: float = 30.0):
        """
        Stop workers gracefully, waiting for pending tasks.
        
        STEP 7: Call this when interview ends
        
        Args:
            timeout: Maximum seconds to wait for pending tasks
        """
        if not self.running:
            logger.warning("Workers not running")
            return
        
        logger.info(
            " Stopping evaluation workers",
            extra={
                "pending_tasks": self.queue.qsize(),
                "timeout_seconds": timeout
            }
        )
        
        self.running = False
        
        try:
            # Wait for queue to empty (with timeout)
            await asyncio.wait_for(
                self.queue.join(),
                timeout=timeout
            )
            logger.info(" All pending evaluations completed")
        
        except asyncio.TimeoutError:
            remaining = self.queue.qsize()
            logger.warning(
                f" Timeout reached with {remaining} tasks remaining",
                extra={"remaining_tasks": remaining}
            )
        
        # Cancel workers
        for worker in self.workers:
            worker.cancel()
        
        # Wait for workers to finish
        await asyncio.gather(*self.workers, return_exceptions=True)
        
        logger.info(
            "Evaluation workers stopped",
            extra={
                "total_processed": self.stats.total_processed,
                "total_failed": self.stats.total_failed
            }
        )
    
    async def queue_evaluation(
        self,
        interview_id: int,
        question: str,
        answer: str,
        topic: str,
        transcript_ids: Optional[List[int]] = None
    ):
        """
        Queue an evaluation task (non-blocking - returns immediately).
        
        STEP 2: Call this after candidate responds
        
        Args:
            interview_id: Interview database ID
            question: The question that was asked
            answer: Candidate's response
            topic: Topic category (e.g., "Python", "System Design")
            transcript_ids: Optional transcript IDs for evidence
        """
        if not self.running:
            logger.error("Cannot queue - workers not running")
            return
        
        task = EvaluationTask(
            interview_id=interview_id,
            question=question,
            answer=answer,
            topic=topic,
            timestamp=datetime.utcnow(),
            transcript_ids=transcript_ids or []
        )
        
        # Non-blocking - Add to queue and return immediately
        await self.queue.put(task)
        
        # Update stats
        self.stats.queue_size = self.queue.qsize()
        
        logger.info(
            "Evaluation queued (non-blocking)",
            extra={
                "interview_id": interview_id,
                "topic": topic,
                "queue_size": self.stats.queue_size,
                "answer_preview": answer[:50] + "..." if len(answer) > 50 else answer
            }
        )
    
    async def _worker(self, worker_id: int):
        """
        Background worker that processes evaluation queue.
        
        This runs continuously in the background.
        """
        logger.info(f"🔄 Worker {worker_id} started")
        
        while self.running:
            try:
                # Wait for task with timeout (allows checking running flag)
                task = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=1.0
                )
                
                # STEP 3 - Process the evaluation
                await self._process_evaluation(task, worker_id)
                
                # Mark task as done
                self.queue.task_done()
            
            except asyncio.TimeoutError:
                # No tasks, continue loop
                continue
            
            except Exception as e:
                log_exception(logger, e, {
                    "worker_id": worker_id,
                    "operation": "worker_loop"
                })
                await asyncio.sleep(1)  # Avoid tight loop on errors
        
        logger.info(f"Worker {worker_id} stopped")
    
    async def _process_evaluation(self, task: EvaluationTask, worker_id: int):
        """
        Process a single evaluation task.
        
        STEP 3-6: Evaluate, store, check aggregation
        """
        start_time = datetime.utcnow()
        
        logger.info(
            f"Worker {worker_id} processing",
            extra={
                "interview_id": task.interview_id,
                "topic": task.topic
            }
        )
        
        try:
            with PerformanceLogger(
                logger,
                "background_evaluation",
                interview_id=task.interview_id
            ):
                # STEP 3 - Evaluate answer (calls LLM)
                score = await self.evaluator.evaluate_answer(
                    question=task.question,
                    answer=task.answer,
                    topic=task.topic
                )
                
                # STEP 4 - Store Level 1 score
                await self._store_score(task, score)
                
                # STEP 5 - Check if topic is complete and aggregate
                await self._check_and_aggregate(task)
                
                # Update stats
                duration = (datetime.utcnow() - start_time).total_seconds() * 1000
                self._update_stats(duration, success=True)
                
                logger.info(
                    f"Worker {worker_id} completed evaluation",
                    extra={
                        "interview_id": task.interview_id,
                        "topic": task.topic,
                        "duration_ms": round(duration, 2)
                    }
                )
        
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            self._update_stats(duration, success=False)
            
            log_exception(logger, e, {
                "operation": "process_evaluation",
                "worker_id": worker_id,
                "interview_id": task.interview_id,
                "topic": task.topic
            })
    
    async def _store_score(self, task: EvaluationTask, score):
        """Store Level 1 (per-answer) score in database"""
        from score_storage import store_answer_score
        
        score_data = {
            "completeness": score.completeness,
            "technical_depth": score.technical_depth,
            "specificity": score.specificity,
            "communication": score.communication,
            "justification": score.justification
        }
        
        stored = await store_answer_score(
            interview_id=task.interview_id,
            topic=task.topic,
            score_data=score_data,
            transcript_ids=task.transcript_ids
        )
        
        if stored:
            logger.info(
                "Level 1 score stored",
                extra={
                    "interview_id": task.interview_id,
                    "score_id": stored.id,
                    "score_value": round(stored.score_value, 2)
                }
            )
        else:
            logger.error(
                "Failed to store Level 1 score",
                extra={
                    "interview_id": task.interview_id,
                    "topic": task.topic
                }
            )
    
    async def _check_and_aggregate(self, task: EvaluationTask):
        """
        Check if topic is complete and aggregate Level 2 score.
        
        STEP 5: Auto-aggregate when topic has enough answers
        """
        from database import get_session, EvaluationScore
        from score_storage import store_aggregated_scores
        
        # Track question count for this topic
        key = (task.interview_id, task.topic)
        self.topic_question_count[key] += 1
        
        # Get scores from database
        db = next(get_session())
        try:
            topic_scores = db.query(EvaluationScore).filter(
                EvaluationScore.interview_id == task.interview_id,
                EvaluationScore.level == 1,
                EvaluationScore.category == task.topic
            ).all()
            
            num_scores = len(topic_scores)
            
            # Check if topic is complete (2 questions per topic by default)
            QUESTIONS_PER_TOPIC = 2
            
            if num_scores >= QUESTIONS_PER_TOPIC:
                logger.info(
                    f"Topic '{task.topic}' complete - aggregating",
                    extra={
                        "interview_id": task.interview_id,
                        "topic": task.topic,
                        "num_answers": num_scores
                    }
                )
                
                # Calculate average score
                avg_score = sum(s.score_value for s in topic_scores) / num_scores
                
                # Check if Level 2 score already exists
                existing_l2 = db.query(EvaluationScore).filter(
                    EvaluationScore.interview_id == task.interview_id,
                    EvaluationScore.level == 2,
                    EvaluationScore.category == task.topic
                ).first()
                
                if not existing_l2:
                    # Store Level 2 score
                    topic_agg_data = {
                        task.topic: {
                            "score": avg_score,
                            "num_answers": num_scores
                        }
                    }
                    
                    await store_aggregated_scores(
                        interview_id=task.interview_id,
                        topic_aggregates=topic_agg_data,
                        overall_score=None  # Don't calculate overall yet
                    )
                    
                    logger.info(
                        f"Level 2 score stored for '{task.topic}'",
                        extra={
                            "interview_id": task.interview_id,
                            "topic": task.topic,
                            "avg_score": round(avg_score, 2)
                        }
                    )
                else:
                    logger.info(
                        f"ℹ️ Level 2 score already exists for '{task.topic}'",
                        extra={"interview_id": task.interview_id}
                    )
        
        finally:
            db.close()
    
    async def finalize_interview(self, interview_id: int):
        """
        Calculate and store final Level 3 (overall) score.
        
        STEP 8: Call this when interview ends
        
        Args:
            interview_id: Interview database ID
        """
        logger.info(
            "🏁 Finalizing interview scores",
            extra={"interview_id": interview_id}
        )
        
        # Wait for all pending tasks for this interview
        await self.queue.join()
        
        from database import get_session, EvaluationScore
        from score_storage import store_aggregated_scores, store_final_scores
        
        db = next(get_session())
        try:
            # Get all Level 2 scores
            level2_scores = db.query(EvaluationScore).filter(
                EvaluationScore.interview_id == interview_id,
                EvaluationScore.level == 2
            ).all()
            
            if not level2_scores:
                logger.warning(
                    "No Level 2 scores found - cannot finalize",
                    extra={"interview_id": interview_id}
                )
                return
            
            # Calculate overall score (simple average for now)
            overall_score = sum(s.score_value for s in level2_scores) / len(level2_scores)
            
            # Generate recommendation
            if overall_score >= 80:
                recommendation = "Strong Hire"
            elif overall_score >= 65:
                recommendation = "Hire"
            elif overall_score >= 50:
                recommendation = "Maybe"
            else:
                recommendation = "No Hire"
            
            # Generate summary
            summary = f"Candidate scored {overall_score:.1f}/100 across {len(level2_scores)} topics. "
            summary += f"Recommendation: {recommendation}."
            
            # Store Level 3 score
            await store_aggregated_scores(
                interview_id=interview_id,
                topic_aggregates={},  # Already stored
                overall_score=overall_score
            )
            
            # Store final results in Interview table
            await store_final_scores(
                interview_id=interview_id,
                overall_score=overall_score,
                recommendation=recommendation,
                summary=summary
            )
            
            logger.info(
                "Interview finalized",
                extra={
                    "interview_id": interview_id,
                    "overall_score": round(overall_score, 2),
                    "recommendation": recommendation
                }
            )
        
        finally:
            db.close()
    
    def _update_stats(self, duration_ms: float, success: bool):
        """Update performance statistics"""
        if success:
            self.stats.total_processed += 1
        else:
            self.stats.total_failed += 1
        
        # Update rolling average
        total = self.stats.total_processed + self.stats.total_failed
        self.stats.avg_processing_time_ms = (
            (self.stats.avg_processing_time_ms * (total - 1) + duration_ms) / total
        )
        
        self.stats.last_processed_at = datetime.utcnow()
        self.stats.queue_size = self.queue.qsize()
    
    def get_stats(self) -> Dict:
        """Get queue statistics for monitoring"""
        return {
            "total_processed": self.stats.total_processed,
            "total_failed": self.stats.total_failed,
            "avg_processing_time_ms": round(self.stats.avg_processing_time_ms, 2),
            "queue_size": self.stats.queue_size,
            "success_rate": (
                self.stats.total_processed / 
                (self.stats.total_processed + self.stats.total_failed)
                if self.stats.total_processed + self.stats.total_failed > 0
                else 0
            ),
            "last_processed_at": (
                self.stats.last_processed_at.isoformat()
                if self.stats.last_processed_at else None
            )
        }


# Global singleton instance
_global_queue: Optional[EvaluationQueueEnhanced] = None


def get_evaluation_queue() -> EvaluationQueueEnhanced:
    """
    Get or create the global evaluation queue.
    
    Usage:
    ------
    from evaluation_queue_enhanced import get_evaluation_queue
    
    queue = get_evaluation_queue()
    await queue.start()
    """
    global _global_queue
    
    if _global_queue is None:
        _global_queue = EvaluationQueueEnhanced(num_workers=2)
        logger.info("Created global evaluation queue")
    
    return _global_queue


# Convenience function for quick access
async def queue_evaluation(
    interview_id: int,
    question: str,
    answer: str,
    topic: str,
    transcript_ids: Optional[List[int]] = None
):
    """
    Convenience function to queue evaluation.
    
    This is a shortcut for:
        queue = get_evaluation_queue()
        await queue.queue_evaluation(...)
    """
    queue = get_evaluation_queue()
    await queue.queue_evaluation(
        interview_id=interview_id,
        question=question,
        answer=answer,
        topic=topic,
        transcript_ids=transcript_ids
    )