"""
Evaluation Agent - Real-Time Interview Scoring with Production Logging
======================================================================

This module implements the 3-level evaluation system with comprehensive
structured logging for monitoring, debugging, and quality assurance.

LOGGING FEATURES IMPLEMENTED:
1. Structured logging for each evaluation dimension
2. Performance metrics for LLM evaluation calls
3. Fallback mechanism logging
4. Score calculation transparency
5. Topic aggregation metrics
6. Final scorecard generation tracking
"""

import sys
import os

current_file = os.path.abspath(__file__)
interview_dir = os.path.dirname(current_file)
app_dir = os.path.dirname(interview_dir)
backend_dir = os.path.dirname(app_dir)

sys.path.insert(0, backend_dir)

import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from config import settings

# PROPER LOGGING SETUP (Following logger.py patterns)

from logger import (
    get_logger,
    PerformanceLogger,
    log_exception
)

# Create component logger
logger = get_logger("evaluation_agent")


# DATA STRUCTURES

@dataclass
class PerAnswerScore:
    """
    Level 1 - Scores for a single answer.
    
    Why these 4 dimensions:
    - Completeness - Did they address all parts of the question?
    - Technical Depth - Surface vs. expert understanding?
    - Specificity - Vague vs. concrete examples with numbers?
    - Communication - Clear vs. confused explanation?
    
    Each scored 1-5 -
    - 1: Very poor
    - 2: Below average
    - 3: Average
    - 4: Good
    - 5: Excellent
    """
    completeness: int  
    technical_depth: int  
    specificity: int  
    communication: int  
    justification: str
    needs_probing: bool  


@dataclass
class TopicScore:
    """
    Level 2 - Accumulated score for a topic.
    
    Example - "System Design" topic has 3 Q&A pairs.
    This aggregates their scores into one topic score.
    """
    topic: str
    score: float 
    weight: float 
    justification: str
    answer_scores: List[PerAnswerScore]


@dataclass
class FinalScorecard:
    """
    Level 3: Overall interview scorecard.
    
    Combines all topic scores with weights to produce final score.
    """
    overall_score: float  
    recommendation: str  
    topic_scores: List[TopicScore]
    summary: str
    strengths: List[str]
    weaknesses: List[str]


# EVALUATION AGENT

class EvaluationAgent:
    """
    Main evaluation engine with production-grade logging.
    
    Usage:
    ```python
    evaluator = EvaluationAgent()
    
    # Evaluate single answer
    score = await evaluator.evaluate_answer(
        question="Tell me about your Python experience",
        answer="I've worked with Python for 5 years..."
    )
    
    # Aggregate topic scores
    topic_score = evaluator.aggregate_topic_scores(
        "Python Expertise",
        [score1, score2, score3]
    )
    
    # Generate final scorecard
    scorecard = evaluator.generate_final_scorecard(
        topic_scores=[topic1, topic2, topic3],
        rubric={"Python": 0.4, "System Design": 0.6}
    )
    ```
    """
    
    def __init__(self):
        logger.info("Initializing EvaluationAgent")
        
        try:
            self.llm = ChatGroq(
                model=settings.GROQ_MODEL,
                api_key=settings.GROQ_API_KEY,
                temperature=0.2
            )
            
            # Metrics tracking
            self.evaluations_performed = 0
            self.fallback_count = 0
            
            logger.info(
                "EvaluationAgent initialized successfully",
                extra={
                    "model": settings.GROQ_MODEL,
                    "temperature": 0.2
                }
            )
        
        except Exception as e:
            log_exception(logger, e, {"operation": "initialize_evaluation_agent"})
            raise
    
    # LEVEL 1 - PER-ANSWER EVALUATION
    
    async def evaluate_answer(
        self,
        question: str,
        answer: str,
        topic: str = None
    ) -> PerAnswerScore:
        """
        Evaluate a single Q&A pair with comprehensive logging.
        
        Returns: PerAnswerScore with 4 dimensions + justification.
        """
        self.evaluations_performed += 1
        
        logger.info(
            "Starting answer evaluation",
            extra={
                "evaluation_number": self.evaluations_performed,
                "topic": topic,
                "question_length": len(question),
                "answer_length": len(answer),
                #"answer_word_count": len(answer.split())
            }
        )
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert technical interviewer evaluating a candidate's answer.

Rate the answer on 4 dimensions (1-5 scale):

1. COMPLETENESS (1-5)
   - 1: Ignored the question entirely
   - 2: Addressed only one aspect
   - 3: Addressed most aspects
   - 4: Fully answered all parts
   - 5: Exceeded expectations with additional insights

2. TECHNICAL DEPTH (1-5)
   - 1: Fundamentally misunderstands concept
   - 2: Surface-level knowledge only
   - 3: Solid understanding of basics
   - 4: Deep understanding with examples
   - 5: Expert-level with trade-offs and edge cases

3. SPECIFICITY (1-5)
   - 1: Completely vague, no examples
   - 2: Generic statements only
   - 3: Some specific details
   - 4: Concrete examples with numbers
   - 5: Detailed metrics, architectures, and outcomes

4. COMMUNICATION (1-5)
   - 1: Incoherent or impossible to follow
   - 2: Confusing with many digressions
   - 3: Understandable but could be clearer
   - 4: Clear and well-structured
   - 5: Exceptionally clear with excellent framing

Also determine: Does this answer need probing follow-up?
- True if answer is vague, incomplete, or shallow
- False if answer is detailed and satisfactory

Output ONLY valid JSON:
{{
    "completeness": <1-5>,
    "technical_depth": <1-5>,
    "specificity": <1-5>,
    "communication": <1-5>,
    "justification": "<2-3 sentences explaining scores with specific examples>",
    "needs_probing": <true/false>
}}"""),
            
            ("human", """Question: {question}

Candidate's Answer: {answer}

Evaluate:""")
        ])
        
        chain = prompt | self.llm
        
        try:
            logger.debug("Invoking LLM for answer evaluation")
            
            with PerformanceLogger(logger, "llm_evaluation_call"):
                response = await chain.ainvoke({
                    "question": question,
                    "answer": answer
                })
            
            logger.debug(
                "LLM evaluation response received",
                extra={"response_length": len(response.content)}
            )
            
            # Parse JSON response
            import json
            data = json.loads(
                response.content.strip()
                .replace("```json", "")
                .replace("```", "")
            )
            
            result = PerAnswerScore(
                completeness=data["completeness"],
                technical_depth=data["technical_depth"],
                specificity=data["specificity"],
                communication=data["communication"],
                justification=data["justification"],
                needs_probing=data["needs_probing"]
            )
            
            logger.info(
                "Answer evaluation completed successfully",
                extra={
                    "completeness": result.completeness,
                    "technical_depth": result.technical_depth,
                    "specificity": result.specificity,
                    "communication": result.communication,
                    "needs_probing": result.needs_probing,
                    "average_score": (result.completeness + result.technical_depth + 
                                     result.specificity + result.communication) / 4
                }
            )
            
            return result
        
        except Exception as e:
            self.fallback_count += 1
            
            log_exception(logger, e, {
                "operation": "evaluate_answer",
                "topic": topic,
                "fallback_count": self.fallback_count
            })

            if answer is None:
                answer = ""
            
            # Fallback scoring based on answer length
            word_count = len(answer)
            
            fallback_score = PerAnswerScore(
                completeness=3 if word_count > 30 else 2,
                technical_depth=3,
                specificity=3 if word_count > 50 else 2,
                communication=3,
                justification="Automatic fallback score due to evaluation error",
                needs_probing=word_count < 50
            )
            
            logger.warning(
                "Using fallback evaluation",
                extra={
                    "word_count": word_count,
                    "fallback_completeness": fallback_score.completeness,
                    "fallback_specificity": fallback_score.specificity,
                    "needs_probing": fallback_score.needs_probing
                }
            )
            
            return fallback_score
    
    # LEVEL 2 - TOPIC AGGREGATION
    
    def aggregate_topic_scores(
        self,
        topic: str,
        answer_scores: List[PerAnswerScore],
        weight: float = 1.0
    ) -> TopicScore:
        """
        Aggregate multiple answer scores into one topic score.
        
        Method:
        1. Average each dimension across all answers
        2. Take weighted average of dimensions
        3. Scale to 0-100
        
        Dimension weights:
        - Technical Depth: 40% (most important)
        - Completeness: 30%
        - Specificity: 20%
        - Communication: 10%
        """
        logger.info(
            "Starting topic score aggregation",
            extra={
                "topic": topic,
                "num_answers": len(answer_scores),
                "weight": weight
            }
        )
        
        if not answer_scores:
            logger.warning(
                "No answer scores provided for topic",
                extra={"topic": topic}
            )
            
            return TopicScore(
                topic=topic,
                score=0.0,
                weight=weight,
                justification="No answers recorded for this topic",
                answer_scores=[]
            )
        
        with PerformanceLogger(logger, "aggregate_topic_scores", topic=topic):
            # Average each dimension
            avg_completeness = sum(s.completeness for s in answer_scores) / len(answer_scores)
            avg_depth = sum(s.technical_depth for s in answer_scores) / len(answer_scores)
            avg_specificity = sum(s.specificity for s in answer_scores) / len(answer_scores)
            avg_communication = sum(s.communication for s in answer_scores) / len(answer_scores)
            
            logger.debug(
                "Dimension averages calculated",
                extra={
                    "topic": topic,
                    "avg_completeness": round(avg_completeness, 2),
                    "avg_depth": round(avg_depth, 2),
                    "avg_specificity": round(avg_specificity, 2),
                    "avg_communication": round(avg_communication, 2)
                }
            )
            
            # Weighted average (scale 1-5 to 0-100)
            raw_score = (
                avg_depth * 0.4 +
                avg_completeness * 0.3 +
                avg_specificity * 0.2 +
                avg_communication * 0.1
            )
            
            # Scale to 0-100
            final_score = ((raw_score - 1) / 4) * 100
            
            # Generate justification
            justification = self._generate_topic_justification(
                topic, answer_scores, final_score
            )
        
        result = TopicScore(
            topic=topic,
            score=final_score,
            weight=weight,
            justification=justification,
            answer_scores=answer_scores
        )
        
        logger.info(
            "Topic score aggregation completed",
            extra={
                "topic": topic,
                "final_score": round(final_score, 2),
                "num_answers_aggregated": len(answer_scores)
            }
        )
        
        return result
    
    def _generate_topic_justification(
        self,
        topic: str,
        answer_scores: List[PerAnswerScore],
        score: float
    ) -> str:
        """
        Generate human-readable justification for topic score.
        
        Why:
        - GDPR compliance (right to explanation)
        - Helps recruiter understand the score
        - Points to specific transcript moments
        """
        logger.debug(
            "Generating topic justification",
            extra={"topic": topic, "score": round(score, 2)}
        )
        
        # Find strongest and weakest dimensions
        dims = {
            "technical depth": sum(s.technical_depth for s in answer_scores) / len(answer_scores),
            "completeness": sum(s.completeness for s in answer_scores) / len(answer_scores),
            "specificity": sum(s.specificity for s in answer_scores) / len(answer_scores),
            "communication": sum(s.communication for s in answer_scores) / len(answer_scores)
        }
        
        strongest = max(dims.items(), key=lambda x: x[1])
        weakest = min(dims.items(), key=lambda x: x[1])
        
        justification = (
            f"{topic} score: {score:.1f}/100. "
            f"Strongest in {strongest[0]} ({strongest[1]:.1f}/5). "
            f"Needs improvement in {weakest[0]} ({weakest[1]:.1f}/5). "
            f"Based on {len(answer_scores)} Q&A pairs."
        )
        
        logger.debug(
            "Topic justification generated",
            extra={
                "topic": topic,
                "strongest_dimension": strongest[0],
                "weakest_dimension": weakest[0]
            }
        )
        
        return justification
    
    # LEVEL 3 - FINAL SCORECARD
    
    def generate_final_scorecard(
        self,
        topic_scores: List[TopicScore],
        rubric: Dict[str, float] = None
    ) -> FinalScorecard:
        """
        Generate final weighted scorecard with comprehensive logging.
        
        Args:
            topic_scores: List of topic scores
            rubric: Dict mapping topic -> weight (should sum to 1.0)
        
        Returns:
            FinalScorecard with overall score and recommendation
        
        Recommendation thresholds:
        - 90-100: strong_hire
        - 75-89: hire
        - 60-74: maybe
        - <60: no_hire
        """
        logger.info(
            "Starting final scorecard generation",
            extra={
                "num_topics": len(topic_scores),
                "has_rubric": rubric is not None
            }
        )
        
        if not topic_scores:
            logger.warning("No topic scores provided for final scorecard")
            
            return FinalScorecard(
                overall_score=0.0,
                recommendation="no_hire",
                topic_scores=[],
                summary="No evaluation data available",
                strengths=[],
                weaknesses=[]
            )
        
        with PerformanceLogger(logger, "generate_final_scorecard"):
            # Calculate weighted average
            total_score = 0.0
            total_weight = 0.0
            
            for topic_score in topic_scores:
                weight = rubric.get(topic_score.topic, 1.0 / len(topic_scores)) if rubric else 1.0 / len(topic_scores)
                total_score += topic_score.score * weight
                total_weight += weight
                
                logger.debug(
                    "Processing topic score",
                    extra={
                        "topic": topic_score.topic,
                        "score": round(topic_score.score, 2),
                        "weight": round(weight, 3)
                    }
                )
            
            overall_score = total_score / total_weight if total_weight > 0 else 0
            
            # Determine recommendation
            if overall_score >= 90:
                recommendation = "strong_hire"
            elif overall_score >= 75:
                recommendation = "hire"
            elif overall_score >= 60:
                recommendation = "maybe"
            else:
                recommendation = "no_hire"
            
            logger.info(
                "Overall score calculated",
                extra={
                    "overall_score": round(overall_score, 2),
                    "recommendation": recommendation,
                    "total_weight": round(total_weight, 3)
                }
            )
            
            # Extract strengths and weaknesses
            strengths, weaknesses = self._extract_strengths_weaknesses(topic_scores)
            
            # Generate summary
            summary = self._generate_summary(overall_score, recommendation, topic_scores)
        
        result = FinalScorecard(
            overall_score=overall_score,
            recommendation=recommendation,
            topic_scores=topic_scores,
            summary=summary,
            strengths=strengths,
            weaknesses=weaknesses
        )
        
        logger.info(
            "Final scorecard generated successfully",
            extra={
                "overall_score": round(overall_score, 2),
                "recommendation": recommendation,
                "num_strengths": len(strengths),
                "num_weaknesses": len(weaknesses)
            }
        )
        
        return result
    
    def _extract_strengths_weaknesses(
        self,
        topic_scores: List[TopicScore]
    ) -> Tuple[List[str], List[str]]:
        """
        Identify top strengths and weaknesses.
        
        Method:
        - Strengths: Topics scored >= 80
        - Weaknesses: Topics scored < 65
        """
        logger.debug("Extracting strengths and weaknesses")
        
        strengths = []
        weaknesses = []
        
        for topic_score in sorted(topic_scores, key=lambda x: x.score, reverse=True):
            if topic_score.score >= 80:
                strengths.append(f"Strong {topic_score.topic.lower()} skills ({topic_score.score:.0f}/100)")
            elif topic_score.score < 65:
                weaknesses.append(f"Limited {topic_score.topic.lower()} experience ({topic_score.score:.0f}/100)")
        
        logger.debug(
            "Strengths and weaknesses extracted",
            extra={
                "num_strengths": len(strengths),
                "num_weaknesses": len(weaknesses)
            }
        )
        
        return strengths[:3], weaknesses[:2]
    
    def _generate_summary(
        self,
        overall_score: float,
        recommendation: str,
        topic_scores: List[TopicScore]
    ) -> str:
        """
        Generate 2-3 sentence summary.
        """
        logger.debug(
            "Generating scorecard summary",
            extra={
                "overall_score": round(overall_score, 2),
                "recommendation": recommendation
            }
        )
        
        best_topic = max(topic_scores, key=lambda x: x.score)
        worst_topic = min(topic_scores, key=lambda x: x.score)
        
        if recommendation == "strong_hire":
            summary = (
                f"Exceptional candidate with overall score of {overall_score:.1f}/100. "
                f"Particularly strong in {best_topic.topic} ({best_topic.score:.0f}/100). "
                f"Recommend immediate hire."
            )
        elif recommendation == "hire":
            summary = (
                f"Solid candidate with overall score of {overall_score:.1f}/100. "
                f"Demonstrated good skills across {len(topic_scores)} areas, especially {best_topic.topic}. "
                f"Recommend hire with standard onboarding."
            )
        elif recommendation == "maybe":
            summary = (
                f"Borderline candidate with overall score of {overall_score:.1f}/100. "
                f"Strong in {best_topic.topic} but needs development in {worst_topic.topic}. "
                f"Recommend further discussion or additional interview."
            )
        else:
            summary = (
                f"Not recommended with overall score of {overall_score:.1f}/100. "
                f"Skills did not meet requirements, particularly in {worst_topic.topic} ({worst_topic.score:.0f}/100)."
            )
        
        logger.debug("Summary generated successfully")
        
        return summary
    
    def get_metrics(self) -> dict:
        """
        Get evaluation metrics for monitoring.
        
        Returns:
            dict: Metrics about evaluation performance
        """
        metrics = {
            "evaluations_performed": self.evaluations_performed,
            "fallback_count": self.fallback_count,
            "fallback_rate": (self.fallback_count / self.evaluations_performed * 100) 
                            if self.evaluations_performed > 0 else 0
        }
        
        logger.debug("Evaluation metrics retrieved", extra=metrics)
        
        return metrics


# Global instance
_evaluator = None

def get_evaluator() -> EvaluationAgent:
    """Get singleton evaluator instance."""
    global _evaluator
    if _evaluator is None:
        logger.info("Creating singleton EvaluationAgent instance")
        _evaluator = EvaluationAgent()
    return _evaluator


async def quick_evaluate(question: str, answer: str) -> PerAnswerScore:
    """Quick evaluation helper with logging."""
    logger.info("Quick evaluation requested")
    evaluator = get_evaluator()
    return await evaluator.evaluate_answer(question, answer)

# MODULE-LEVEL TESTING

async def test_evaluator():
    """Test the evaluation agent with logging"""
    logger.info("Starting evaluation agent test")
    
    evaluator = EvaluationAgent()
    
    # Test 1 - Evaluate a good answer
    logger.info("Test 1: Evaluating high-quality answer")
    score1 = await evaluator.evaluate_answer(
        question="Tell me about your Python experience",
        answer="I have 5 years of Python experience building scalable microservices. At my last company, I led the migration from a monolith to microservices, reducing deployment time by 70%. I'm particularly experienced with FastAPI, having built 15+ production APIs handling 10M+ requests per day."
    )
    logger.info(f"Test 1 result: {score1}")
    
    # Test 2 - Evaluate a weak answer
    logger.info("Test 2: Evaluating low-quality answer")
    score2 = await evaluator.evaluate_answer(
        question="Describe your experience with databases",
        answer="I have used databases before. They are important for storing data."
    )
    logger.info(f"Test 2 result: {score2}")
    
    # Test 3 - Topic aggregation
    logger.info("Test 3: Testing topic aggregation")
    topic_score = evaluator.aggregate_topic_scores(
        topic="Python Programming",
        answer_scores=[score1, score2]
    )
    logger.info(f"Test 3 result: {topic_score}")
    
    # Test 4 - Final scorecard
    logger.info("Test 4: Testing final scorecard generation")
    scorecard = evaluator.generate_final_scorecard(
        topic_scores=[topic_score],
        rubric={"Python Programming": 1.0}
    )
    logger.info(f"Test 4 result: {scorecard}")
    
    # Get metrics
    metrics = evaluator.get_metrics()
    logger.info("Evaluation agent test completed", extra=metrics)


if __name__ == "__main__":
    asyncio.run(test_evaluator())