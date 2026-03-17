# previous code

"""
AI Interview Agent - State Machine Implementation with Production Logging

This module implements the interview orchestration using LangGraph with
comprehensive structured logging for monitoring and debugging.

LOGGING FEATURES IMPLEMENTED -
1. Structured logging with context (interview_id, candidate_name, phase)
2. Performance metrics for each node execution
3. Graph state transitions tracking
4. RAG retrieval metrics and quality logging
5. LLM invocation tracking with token usage
6. Error handling with detailed context
"""

import asyncio
from typing import TypedDict, Annotated, List, Dict, Optional
from datetime import datetime

import sys
import os

current_file = os.path.abspath(__file__)
interview_dir = os.path.dirname(current_file)
app_dir = os.path.dirname(interview_dir)
backend_dir = os.path.dirname(app_dir)

sys.path.insert(0, backend_dir)

from config import settings

from app.interview.score_storage import store_answer_score

from database import (
    get_session,
    Interview,
    Candidate,
    Job,
    EvaluationScore,
    semantic_search_resume
)
from app.websocket_handler import send_evaluation_score

from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

# PROPER LOGGING SETUP (Following logger.py patterns)

from logger import (
    get_logger,
    ContextLogger,
    PerformanceLogger,
    log_exception
)

from app.interview.score_storage import store_final_scores, store_aggregated_scores
# Create component logger
logger = get_logger("ai_agent")


# STATE DEFINITION
class InterviewState(TypedDict):
    """
    The state that flows through the interview graph.
    
    Why: LangGraph requires a TypedDict to define what data passes between nodes.
    This state is updated as we move through the interview.
    
    Fields explained:
    - interview_id: Database ID to store results
    - candidate_name: For personalization
    - job_description: Context for generating questions
    - resume_context: RAG-retrieved chunks about current topic
    - topics_covered: Track what we've asked about
    - current_topic: Active topic being discussed
    - conversation_history: Full chat history for LLM context
    - evaluation_scores: Real-time scoring accumulation
    - interview_plan: List of topics to cover
    - questions_asked: Counter for pacing
    - interview_phase: Current node in state machine
    - last_user_response: Most recent candidate answer
    - probing_depth: How many follow-ups on current topic (prevent infinite loops)
    """
    
    interview_id: int
    candidate_id: int  # ← ADD THIS
    candidate_name: str
    job_id: int  # ← ADD THIS
    job_description: str
    
    # Job configuration
    evaluation_rubric: Optional[Dict[str, float]]  # ← ADD THIS
    
    # Context management
    resume_context: Optional[str]
    topics_covered: List[str]
    current_topic: Optional[str]
    questions_in_current_topic: int
    
    # Conversation
    conversation_history: List[Dict]
    last_user_response: Optional[str]
    
    # Evaluation
    evaluation_scores: Dict[str, float]
    
    # Flow control
    interview_plan: List[str]
    questions_asked: int
    max_questions: int
    interview_phase: str
    probing_depth: int
    max_probing_depth: int
    topic_context_cache: Dict[str, Optional[str]] 
    current_prompt_params: dict  # ADD THIS
    generation_type: str

async def calibration_node(state: InterviewState) -> InterviewState:
    """
    Node A: Pre-interview checks with logging.
    
    Why: Before starting, we need to verify:
    - Audio/video quality is acceptable
    - Candidate identity matches expected
    - System is ready to record
    """
    ctx_logger = ContextLogger(
        logger=logger,
        interview_id=state["interview_id"],
        candidate_name=state["candidate_name"],
        phase="calibration"
    )
    
    ctx_logger.info("Starting calibration phase")
    
    with PerformanceLogger(logger, "calibration_node", interview_id=state["interview_id"]):
        state["interview_phase"] = "calibration_complete"
        state["conversation_history"] = []
        state["topics_covered"] = []
        state["evaluation_scores"] = {}
        state["questions_asked"] = 0
        state["probing_depth"] = 0
        state["questions_in_current_topic"] = 0 
        state["topic_context_cache"] = {}  
    
    ctx_logger.info("Calibration phase completed successfully")
    
    return state


async def context_loading_node(state: InterviewState) -> InterviewState:
    """
    Node B - Load interview context with RAG metrics logging.
    
    Why - Before starting, the AI needs to know:
    - What job is this for?
    - What topics should we cover?
    - What does the candidate's resume say?
    """
    ctx_logger = ContextLogger(
        logger=logger,
        interview_id=state["interview_id"],
        phase="context_loading"
    )
    
    ctx_logger.info("Loading interview context")
    
    with PerformanceLogger(logger, "context_loading_node", interview_id=state["interview_id"]):
        
        num_topics = len(state["interview_plan"])
        topics = state['interview_plan']

        print(f"\n[DEBUG] Number of Topics: {num_topics}")
        print(f"[DEBUG] Topics List: {topics}\n")

        ctx_logger.info(
        "Interview context loaded successfully",
        # extra={
        #     "num_topics": len(state["interview_plan"]),
        #     "topics": state["interview_plan"]
        # }
        )

        # PRE-FETCH RAG CONTEXT FOR ALL TOPICS
        topic_context_cache = {}
        candidate_id = state.get("candidate_id")

        if candidate_id:
            db = next(get_session())
            try:
                for topic in state["interview_plan"]:
                    relevant_chunks = semantic_search_resume(
                        db=db,
                        candidate_id=candidate_id,
                        query=topic,
                        top_k=3
                    )
                    if relevant_chunks:
                        topic_context_cache[topic] = "\n\n".join(relevant_chunks)
                    else:
                        topic_context_cache[topic] = None
                    
                    ctx_logger.info(f"Pre-fetched RAG for topic: {topic}, chunks found: {len(relevant_chunks) if relevant_chunks else 0}")
            except Exception as e:
                log_exception(logger, e, {"operation": "pre_fetch_rag", "interview_id": state["interview_id"]})
            finally:
                db.close()

        state["topic_context_cache"] = topic_context_cache
    
    return state


async def topic_selection_node(state: InterviewState) -> InterviewState:
    """
    Node D - Select the next topic with RAG retrieval logging.
    
    UPDATED: Now uses REAL RAG to retrieve resume context!
    """
    ctx_logger = ContextLogger(
        logger=logger,
        interview_id=state["interview_id"],
        phase="topic_selection"
    )
    
    ctx_logger.info("Selecting next topic")

    if state.get("current_topic") and state["current_topic"] not in state["topics_covered"]:
        state["topics_covered"].append(state["current_topic"])
        logger.info(f" Marked topic as covered: {state['current_topic']}")
    
    # Find uncovered topics
    remaining_topics = [
        topic for topic in state["interview_plan"] 
        if topic not in state["topics_covered"]
    ]
    
    if not remaining_topics:
        state["interview_phase"] = "all_topics_complete"
        return state
    
    # Select next topic
    next_topic = remaining_topics[0]

    state["current_topic"] = next_topic
    state["probing_depth"] = 0
    state["questions_in_current_topic"] = 0
    
    ctx_logger.info(
        f"Selected topic: {next_topic}",
        extra={
            "remaining_topics": len(remaining_topics),
            "total_topics": len(state["interview_plan"])
        }
    )
    
    # LOOK UP PRE-FETCHED CONTEXT FROM CACHE (no DB call needed)
    try:
        cache = state.get("topic_context_cache", {})
        cached_context = cache.get(next_topic)  
        state["resume_context"] = cached_context
        
        if cached_context:
            ctx_logger.info(
                "RAG context loaded from cache (no DB call)",
                extra={"topic": next_topic, "context_length": len(cached_context)}
            )
        else:
            ctx_logger.warning(f"No cached context found for topic: {next_topic}")

    except Exception as e:
        log_exception(logger, e, {"operation": "cache_lookup", "topic": next_topic})
        state["resume_context"] = None
    
    state["interview_phase"] = "ready_to_question"
    
    return state

async def question_generation_node(state: InterviewState) -> InterviewState:
    """
    Node E - Generate contextual question with LLM metrics.
    
    Uses:
    - Job description
    - Current topic
    - RAG-retrieved resume context
    - Conversation history
    """
    ctx_logger = ContextLogger(
        logger=logger,
        interview_id=state["interview_id"],
        phase="question_generation",
        current_topic=state.get("current_topic")
    )
    
    ctx_logger.info("Generating interview question")

    inter_cond = state["interview_phase"]
    current_topic=state.get("current_topic")

    print(f"\n[DEBUG] condition of interview : {inter_cond}")
    print(f"\n[DEBUG] current_topic : {current_topic}")

    try:
        with PerformanceLogger(logger, "generate_question", interview_id=state["interview_id"]):
            llm = ChatGroq(
                model=settings.GROQ_MODEL,
                api_key=settings.GROQ_API_KEY,
                temperature=0.7
            )
            
            # Build context-aware prompt
            resume_context_str = f"\n\nRelevant from resume:\n{state['resume_context']}" if state.get('resume_context') else ""
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", """You are Supegroww, an AI interviewer.

Generate ONE concise, specific question about: {topic}

Context:
- Job: {job_description}
- Questions asked so far: {questions_count}{resume_context}

Requirements:
1. Make it conversational (not interrogative)
2. Reference their resume if relevant context is provided
3. Ask for specific examples with outcomes
4. Keep it under 2 sentences

Example good questions:
- "I see you worked with Python. Can you walk me through a challenging bug you fixed?"
- "Tell me about a time you had to make a technical trade-off decision."

Just output the question, nothing else."""),
                ("human", "Generate a question about {topic}.")
            ])
            
            chain = prompt | llm
            
            ctx_logger.debug(
                "Invoking LLM for question generation",
                extra={
                    "has_resume_context": bool(state.get('resume_context')),
                    #"resume_context_length": len(state.get('resume_context', ''))
                }
            )
            
            question = await chain.ainvoke({
                "topic": state["current_topic"],
                "job_description": state["job_description"][:200],
                "questions_count": state["questions_asked"],
                "resume_context": resume_context_str
            })
        
        # Add to conversation history
        state["conversation_history"].append({
            "role": "assistant",
            "content": question.content,
            "timestamp": datetime.utcnow().isoformat(),
            "topic": state["current_topic"]
        })
        
        state["questions_asked"] += 1
        state["interview_phase"] = "awaiting_response"

        no_questions_asked = state["questions_asked"]
        print(f"no of questions asked : {no_questions_asked}")
        
        ctx_logger.info(
            "Question generated successfully",
            extra={
                "question_number": state["questions_asked"],
                "question_length": len(question.content),
                "preview": question.content[:80]
            }
        )
    
    except Exception as e:
        log_exception(logger, e, {
            "interview_id": state["interview_id"],
            "phase": "question_generation",
            "topic": state.get("current_topic")
        })
        
        # Fallback question
        fallback_question = f"Tell me about your experience with {state['current_topic']}."
        state["conversation_history"].append({
            "role": "assistant",
            "content": fallback_question,
            "timestamp": datetime.utcnow().isoformat()
        })
        state["questions_asked"] += 1
        state["interview_phase"] = "awaiting_response"

        no_questions = state["questions_asked"]

        print(f"\n[DEBUG] number of questions asked : {no_questions}")
        
        ctx_logger.warning("Using fallback question due to LLM error")
    
    return state

async def evaluation_node(state: InterviewState) -> InterviewState:
    """
    Node F - Evaluate candidate's response.
    
    COMPLETELY NON-BLOCKING: 
    - Evaluation happens in background via queue
    - Level 2 aggregation happens in background
    - This node ONLY updates state machine - NO database I/O
    - Next question is asked IMMEDIATELY
    """
    ctx_logger = ContextLogger(
        logger=logger,
        interview_id=state["interview_id"],
        phase="evaluation",
        current_topic=state.get("current_topic")
    )
    
    # Save to state (for state machine tracking only)
    if state["current_topic"] not in state["evaluation_scores"]:
        state["evaluation_scores"][state["current_topic"]] = []

    dummy_score = {
        "completeness": 3,
        "technical_depth": 3,
        "specificity": 3,
        "communication": 3,
        "overall": 60.0
    }

    state["evaluation_scores"][state["current_topic"]].append(dummy_score)
    
    # Increment counter
    if state["probing_depth"] == 0:
        state["questions_in_current_topic"] += 1
    
    # Decision logic
    QUESTIONS_PER_TOPIC = 2
    
    # Simple state machine logic - NO database operations
    if state["questions_in_current_topic"] < QUESTIONS_PER_TOPIC:
        state["interview_phase"] = "stay_on_topic"
        state["probing_depth"] = 0
        ctx_logger.info("Moving to next question in topic")
    
    else:
        # Topic complete - mark it
        if state["current_topic"] and state["current_topic"] not in state["topics_covered"]:
            state["topics_covered"].append(state["current_topic"])
        
        ctx_logger.info(
            f"Topic '{state['current_topic']}' complete - Level 2 will aggregate in background",
            extra={
                "interview_id": state["interview_id"],
                "topic": state["current_topic"],
                "questions_answered": state["questions_in_current_topic"]
            }
        )
        
        state["interview_phase"] = "topic_complete"
        state["probing_depth"] = 0
        state["questions_in_current_topic"] = 0
    
    return state

async def probing_node(state: InterviewState) -> InterviewState:
    """
    Node G - Ask follow-up question to get more detail.
    
    Called when evaluation determines answer was too shallow.
    """
    ctx_logger = ContextLogger(
        logger=logger,
        interview_id=state["interview_id"],
        phase="probing",
        current_topic=state.get("current_topic")
    )
    
    ctx_logger.info(
        "Generating probing follow-up question",
        extra={"probing_depth": state["probing_depth"]}
    )
    
    try:
        with PerformanceLogger(logger, "generate_probing_question", interview_id=state["interview_id"]):
            llm = ChatGroq(
                model=settings.GROQ_MODEL,
                api_key=settings.GROQ_API_KEY,
                temperature=0.7
            )
            
            last_answer = state.get("last_user_response", "")
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", """You are Supegroww. The candidate's answer was too brief or vague.

Generate ONE follow-up question to get more specific details.

Strategies:
- Ask for concrete numbers/metrics
- Request specific examples
- Probe for outcomes/results
- Ask about challenges faced

Keep it conversational and under 2 sentences.

Example good follow-ups:
- "Can you give me a specific example with numbers?"
- "What was the outcome of that decision?"
- "Walk me through the technical challenges you faced."

Just output the question."""),
                ("human", """Topic: {topic}

Their answer: {answer}

Generate a follow-up question:""")
            ])
            
            chain = prompt | llm
            
            follow_up = await chain.ainvoke({
                "topic": state["current_topic"],
                "answer": last_answer
            })
        
        # Add to conversation history
        state["conversation_history"].append({
            "role": "assistant",
            "content": follow_up.content,
            "timestamp": datetime.utcnow().isoformat(),
            "is_probing": True
        })
        
        state["probing_depth"] += 1
        state["interview_phase"] = "awaiting_response"
        
        ctx_logger.info(
            "Probing question generated",
            extra={
                "probing_depth": state["probing_depth"],
                "question_preview": follow_up.content[:80]
            }
        )
    
    except Exception as e:
        log_exception(logger, e, {
            "interview_id": state["interview_id"],
            "phase": "probing"
        })
        
        # Fallback
        state["topics_covered"].append(state["current_topic"])
        state["interview_phase"] = "topic_complete"
        
        ctx_logger.warning("Probing question generation failed, moving to next topic")
    
    return state

async def conclusion_node(state: InterviewState) -> InterviewState:
    """
    Node H - Wrap up the interview with final summary.
    
    Called when all topics are covered or max questions reached.
    """
    ctx_logger = ContextLogger(
        logger=logger,
        interview_id=state["interview_id"],
        phase="conclusion"
    )
    
    ctx_logger.info(
        "Generating interview conclusion",
        extra={
            "topics_covered": len(state["topics_covered"]),
            "questions_asked": state["questions_asked"]
        }
    )

    state["interview_phase"] = "complete"

    return state

def should_continue_interview(state: InterviewState) -> str:
    """
    Decides whether to continue asking questions or conclude.
    """
    logger.info(
        "Checking if interview should continue",
        extra={
            "topics_covered": state["topics_covered"],
            "interview_plan": state["interview_plan"],
            "questions_asked": state["questions_asked"],
            "max_questions": state["max_questions"],
            "current_phase": state["interview_phase"]
        }
    )
    
    # 1. Check if we have run out of topics
    if not state["interview_plan"]:
        logger.info("No interview plan. Concluding.")
        return "conclude"
    
    if len(state["topics_covered"]) >= len(state["interview_plan"]):
        logger.info(
            "All topics covered. Concluding.",
            extra={
                "topics_covered_count": len(state["topics_covered"]),
                "total_topics": len(state["interview_plan"])
            }
        )
        return "conclude"

    # 2. Check explicit flag from topic_selection_node
    if state["interview_phase"] == "all_topics_complete":
        logger.info("Phase indicates all topics complete. Concluding.")
        return "conclude"
    
    # 3. Safety Net: Max questions
    if state["questions_asked"] >= state["max_questions"]:
        logger.warning(
            "Max questions reached. Concluding.",
            extra={
                "questions_asked": state["questions_asked"],
                "max_questions": state["max_questions"]
            }
        )
        return "conclude"
    
    logger.info("Interview continues")
    return "continue"

def should_probe_or_continue(state: InterviewState) -> str:
    """
    Decides whether to probe deeper or move to next topic.
    
    Called after evaluation_node.
    """
    logger.debug(
        "Checking if probing is needed",
        extra={
            "interview_phase": state["interview_phase"],
            "probing_depth": state["probing_depth"],
            "max_probing_depth": state["max_probing_depth"]
        }
    )
    
    if state["interview_phase"] == "needs_probing":
        logger.info("Probing follow-up required")
        return "probe"
    
    elif state["interview_phase"] == "stay_on_topic":
        return "continue_topic"

    else:
        logger.info("Moving to next topic")
        return "next_topic"


# BUILD THE STATE GRAPH
from langgraph.graph import StateGraph, END, START  

def route_start(state: InterviewState) -> str:
    """Decides if we are STARTING or RESUMING the interview."""
    phase = state.get("interview_phase", "not_started")
    
    # If we are waiting for an answer, we must EVALUATE it first.
    if phase == "awaiting_response" and state.get("last_user_response"):
        return "evaluation"
    
    # Otherwise, start from the beginning.
    return "calibration"

def create_interview_graph():
    """
    Constructs the interview state machine using LangGraph.
    
    Flow:
    START → Calibration → Context Loading → Introduction → 
    Topic Selection → Question Generation → [Wait for response] →
    Evaluation → (Probe OR Next Topic) → Topic Selection → ... → Conclusion → END
    """
    logger.info("Creating interview state graph")
    
    # Initialize graph
    workflow = StateGraph(InterviewState)
    
    # Add nodes
    workflow.add_node("calibration", calibration_node)
    workflow.add_node("context_loading", context_loading_node)
    workflow.add_node("topic_selection", topic_selection_node)
    workflow.add_node("question_generation", question_generation_node)
    workflow.add_node("evaluation", evaluation_node)
    workflow.add_node("probing", probing_node)
    workflow.add_node("conclusion", conclusion_node)
    
    workflow.add_conditional_edges(
        START,
        route_start,
        {
            "calibration": "calibration",
            "evaluation": "evaluation"
        }
    )
    
    # Linear progression at start
    workflow.add_edge("calibration", "context_loading")
    workflow.add_edge("context_loading", "topic_selection")
    
    # Conditional: continue or conclude?
    workflow.add_conditional_edges(
        "topic_selection",
        should_continue_interview,
        {
            "continue": "question_generation",
            "conclude": "conclusion"
        }
    )
    
    # After question generation, we wait for user response (handled externally)
    # Then evaluation is called
    workflow.add_edge("question_generation", END) 
    
    # 3. Same for probing questions
    workflow.add_edge("probing", END)
    
    # Conditional - probe or next topic?
    workflow.add_conditional_edges(
        "evaluation",
        should_probe_or_continue,
        {
            "probe": "probing",
            "continue_topic": "question_generation",
            "next_topic": "topic_selection"
        }
    )
    
    # End at conclusion
    workflow.add_edge("conclusion", END)
    
    logger.info("Interview state graph created successfully")
    
    return workflow.compile()


# USAGE WRAPPER

class InterviewAgent:
    """
    Wrapper class for easy interaction with the state graph.
    
    Why: The raw graph is complex. This provides a clean interface with logging.
    """
    
    def __init__(self, interview_id: int, candidate_id: int, job_id: int):
        logger.info(
            "Initializing InterviewAgent",
            extra={
                "interview_id": interview_id,
                "candidate_id": candidate_id,
                "job_id": job_id
            }
        )

        # 1. Get database session
        db = next(get_session())
        
        try:
            # 2. Fetch job from database
            logger.info("Fetching job from database", extra={"job_id": job_id})
            
            job = db.query(Job).filter(Job.id == job_id).first()
            
            if not job:
                logger.error("Job not found", extra={"job_id": job_id})
                raise ValueError(f"Job with ID {job_id} not found")
            
            job_description = job.description
            topics_to_cover = job.topics_to_cover or []
            evaluation_rubric = job.evaluation_rubric or {}
            
            logger.info(
                "Job loaded successfully",
                extra={
                    "job_id": job_id,
                    "job_title": job.title,
                    "num_topics": len(topics_to_cover)
                }
            )
            
            # 3. Fetch candidate name
            logger.info("Fetching candidate from database", extra={"candidate_id": candidate_id})
            
            candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
            
            if not candidate:
                logger.error("Candidate not found", extra={"candidate_id": candidate_id})
                raise ValueError(f"Candidate with ID {candidate_id} not found")
            
            candidate_name = candidate.name
            
            logger.info(
                "Candidate loaded successfully",
                extra={
                    "candidate_id": candidate_id,
                    "candidate_name": candidate_name
                }
            )
            
        finally:
            db.close()
        
        self.graph = create_interview_graph()

        db = next(get_session())
        interview = db.query(Interview).get(interview_id)
        
        # Load previous scores/topics if they exist
        existing_topics_covered = []
        existing_scores = {}
        
        if interview.scores:
            for s in interview.scores:
                if s.level == 1: # Rebuild Level 1 cache
                    if s.category not in existing_scores:
                        existing_scores[s.category] = []
                    # Add dummy dict or reconstruct from DB columns
                    existing_scores[s.category].append({
                        "completeness": 3, # Approximate since we didn't save raw dims
                        "overall": s.score_value
                    })
                
                # Rebuild topics covered
                if s.category not in existing_topics_covered:
                    existing_topics_covered.append(s.category)
        
        db.close()
        
        # Initialize state
        self.state: InterviewState = {
            "interview_id": interview_id,
            "candidate_id": candidate_id,
            "candidate_name": candidate_name,
            "job_description": job_description,
            "job_id": job_id,
            "evaluation_rubric": evaluation_rubric,
            "resume_context": None,
            "topics_covered": existing_topics_covered,
            "current_topic": None,
            "questions_in_current_topic": 0,
            "conversation_history": [],
            "last_user_response": None,
            "evaluation_scores":existing_scores,
            "interview_plan": topics_to_cover,
            "questions_asked": 0,
            "max_questions": 4,
            "interview_phase": "not_started",
            "probing_depth": 0,
            "max_probing_depth": 2
        }
        
        logger.info("InterviewAgent initialized successfully")
    
    async def start_interview(self) -> str:
        """
        Run the initial nodes and return the introduction.
        
        Returns:
            The AI's introduction text (to be spoken via TTS)
        """
        logger.info(
            "Starting interview",
            extra={"interview_id": self.state["interview_id"]}
        )
        
        try:
            with PerformanceLogger(logger, "start_interview", interview_id=self.state["interview_id"]):
                # Run: calibration → context_loading → introduction
                result = await self.graph.ainvoke(self.state)
                self.state = result
            
            logger.info(
                "Interview started successfully",
                extra={
                    "interview_id": self.state["interview_id"],
                    #"intro_length": len(intro)
                }
            )
            
            return f"Interview initialized for {self.state['candidate_name']}. Ready to begin."
        
        except Exception as e:
            log_exception(logger, e, {
                "interview_id": self.state["interview_id"],
                "operation": "start_interview"
            })
            raise
    
    async def process_response(self, response_text: str) -> str:
        """
        Process the answer, run the graph, SAVE TO DB, and return next question.
        """
        logger.info(
            "Processing user response",
            extra={
                "interview_id": self.state["interview_id"],
                "current_phase": self.state["interview_phase"],
                "current_topic": self.state.get("current_topic"),
                "questions_in_current_topic": self.state.get("questions_in_current_topic", 0)
            }
        )
        
        # 1. Update State with User's Answer
        self.state["conversation_history"].append({
            "role": "user",
            "content": response_text,
            "timestamp": datetime.utcnow().isoformat()
        })
        self.state["last_user_response"] = response_text
        
        # 2. Set phase to trigger evaluation
        self.state["interview_phase"] = "awaiting_response"
        
        # 3. Run the Graph
        logger.debug(f"[BEFORE GRAPH] Phase: {self.state['interview_phase']}")
        result = await self.graph.ainvoke(self.state)
        self.state = result
        logger.debug(f"[AFTER GRAPH] Phase: {self.state['interview_phase']}")
        
        # 4. Check if interview completed
        if self.state["interview_phase"] == "complete":
            logger.info("Interview completed during graph execution")
            return "Thank you for your time. The interview is now complete."
        
        # 5. Get the Next AI Message (The Question)
        ai_message = next(
            (msg["content"] for msg in reversed(self.state["conversation_history"])
            if msg["role"] == "assistant"),
            None
        )
        
        if not ai_message:
            logger.error("No AI message found in conversation history")
            return "I apologize, there was an issue generating the next question."
        
        logger.info(
            "Next question ready",
            extra={
                "phase_after_processing": self.state["interview_phase"],
                "question_preview": ai_message[:100]
            }
        )
        
        return ai_message
    
    def get_current_question(self) -> str:
        """Get the most recent question asked."""
        for msg in reversed(self.state["conversation_history"]):
            if msg["role"] == "assistant":
                return msg["content"]
        return ""
    
    def get_context(self) -> dict:
        """Get current interview context for evaluation."""
        return {
            "topic": self.state.get("current_topic"),
            "job_description": self.state["job_description"],
            "resume_context": self.state.get("resume_context")
        }
    
    def is_complete(self) -> bool:
        """Check if interview is finished."""
        is_done = self.state["interview_phase"] == "complete"
        
        if is_done:
            logger.info(
                "Interview marked as complete",
                extra={"interview_id": self.state["interview_id"]}
            )
        
        return is_done
    
    async def end_interview(self):
        """
        Handle any final cleanup when the interview terminates.
        """
        logger.info(
            "Ending interview in state machine",
            extra={"interview_id": self.state["interview_id"]}
        )
        self.state["interview_phase"] = "complete"

    def get_evaluation_summary(self) -> Dict:
        """Get the full evaluation data for storage."""
        logger.info(
            "Generating evaluation summary",
            extra={"interview_id": self.state["interview_id"]}
        )
        
        # Calculate topic-level scores
        topic_aggregates = {}
        
        for topic, answer_scores in self.state["evaluation_scores"].items():
            if answer_scores:
                # Average the 'overall' score (if exists) or calculate from dimensions
                scores_list = []
                for score in answer_scores:
                    if "overall" in score:
                        scores_list.append(score["overall"])
                    else:
                        # Calculate from dimensions
                        avg = (score["completeness"] + score["technical_depth"] + 
                               score["specificity"] + score["communication"]) / 4
                        scores_list.append(avg)
                
                avg_overall = sum(scores_list) / len(scores_list) if scores_list else 0
                
                topic_aggregates[topic] = {
                    "score": avg_overall,
                    "num_answers": len(answer_scores),
                    "scores": answer_scores
                }
        
        summary = {
            "topics_covered": self.state["topics_covered"],
            "evaluation_scores": self.state["evaluation_scores"],
            "topic_aggregates": topic_aggregates,  
            "questions_asked": self.state["questions_asked"],
            "conversation_history": self.state["conversation_history"]
        }
        
        logger.info(
            "Evaluation summary generated",
            extra={
                "interview_id": self.state["interview_id"],
                "topics_evaluated": len(topic_aggregates),
                "total_questions": self.state["questions_asked"]
            }
        )
        
        return summary


async def test_agent():
    """Test the agent locally with logging"""
    logger.info("Starting AI agent test")
    
    agent = InterviewAgent(
        interview_id=1,
        candidate_id=1, 
        job_id=789    
    )
    
    # Start interview
    intro = await agent.start_interview()
    print(f"AI: {intro}\n")
    
    # Simulate responses
    # Simulate responses (50 distinct answers to cover a full interview flow)
    responses = [
        # PHASE 1: Introduction & Background 
        "Yes, I am ready to begin the interview!",
        "I am a Senior Software Engineer with 5 years of experience specializing in Python backend development and cloud architecture.",
        "Currently, I work at TechSolutions where I lead the migration of legacy monoliths to microservices.",
        "I have a strong background in building scalable REST APIs using FastAPI and Django.",
        "I also have experience managing AWS infrastructure and setting up CI/CD pipelines.",
        
        # PHASE 2: Python Technical Questions 
        "The main difference between a list and a tuple is that lists are mutable while tuples are immutable.",
        "A decorator in Python is a design pattern that allows you to modify the behavior of a function or class without changing its source code.",
        "The Global Interpreter Lock (GIL) is a mutex that allows only one thread to hold the control of the Python interpreter at a time.",
        "I use generators when handling large datasets because they yield items one by one and save memory compared to lists.",
        "List comprehensions provide a concise way to create lists. They are generally faster than normal for-loops.",
        "Method overriding occurs when a child class provides a specific implementation of a method that is already defined in its parent class.",
        "I prefer using 'pytest' for testing because of its simple syntax and powerful fixture system.",
        "To manage dependencies, I use tools like Poetry or pip-tools to ensure reproducible builds.",
        "Deep copy creates a new object and recursively copies the objects found in the original, whereas shallow copy constructs a new compound object and inserts references into it.",
        "Context managers, used with the 'with' statement, ensure that resources like file streams are properly managed and closed.",
        "Lambda functions are small anonymous functions defined with the lambda keyword, usually used for short, simple operations.",
        "Docstrings are important for documenting code, explaining what a function does, its arguments, and return values.",
        "I handle asynchronous programming in Python using the 'asyncio' library and 'async/await' syntax.",
        "The difference between 'is' and '==' is that 'is' checks for identity (memory address), while '==' checks for equality (value).",
        "Python's garbage collection uses reference counting and a cyclic garbage collector to manage memory.",

        # PHASE 3: Database & SQL 
        "I primarily use PostgreSQL for relational data and Redis for caching.",
        "ACID stands for Atomicity, Consistency, Isolation, and Durability, which are key properties of database transactions.",
        "An INNER JOIN returns records that have matching values in both tables.",
        "A LEFT JOIN returns all records from the left table, and the matched records from the right table.",
        "Indexing improves the speed of data retrieval operations on a database table but can slow down writes.",
        "Normalization is the process of organizing data to reduce redundancy and improve data integrity.",
        "I optimize slow SQL queries by analyzing the execution plan using 'EXPLAIN ANALYZE'.",
        "NoSQL databases like MongoDB are better for unstructured data or when schema flexibility is required.",
        "Database sharding involves splitting a large database into smaller, faster, and more easily managed parts called data shards.",
        "Connection pooling significantly improves performance by reusing active database connections instead of creating new ones for every request.",

        #PHASE 4: System Design & Architecture 
        "Horizontal scaling means adding more machines to the resource pool, whereas vertical scaling means adding more power to an existing machine.",
        "I use Docker to containerize applications, ensuring they run consistently across different environments.",
        "Kubernetes is my tool of choice for orchestrating container deployment, scaling, and management.",
        "A Load Balancer distributes incoming network traffic across multiple servers to ensure no single server bears too much load.",
        "For caching strategies, I typically implement 'Cache-Aside' or 'Write-Through' depending on the read/write ratio.",
        "The CAP theorem states that a distributed system can only deliver two of three guarantees: Consistency, Availability, and Partition Tolerance.",
        "Microservices architecture allows teams to develop, deploy, and scale services independently.",
        "I use message queues like RabbitMQ or Kafka to handle asynchronous communication between services.",
        "API Gateway acts as a single entry point for defined backends and handles cross-cutting concerns like authentication and rate limiting.",
        "REST is an architectural style that uses standard HTTP methods, while GraphQL allows clients to request exactly the data they need.",

        # PHASE 5: Behavioral & Soft Skills
        "I once missed a deadline due to scope creep. I learned to communicate potential delays early and negotiate feature priorities.",
        "I resolve conflicts within the team by listening to all perspectives and focusing on the technical data rather than personal opinions.",
        "One of my biggest challenges was debugging a memory leak in production. I used profiling tools to isolate the issue and fix it.",
        "I prioritize tasks based on their impact on the business and their urgency.",
        "I stay updated with the latest technology trends by reading tech blogs, following newsletters, and attending conferences.",
        "I believe in the importance of code reviews not just for catching bugs, but for knowledge sharing among the team.",
        "I mentored a junior developer by pair programming with them and helping them understand design patterns.",
        "I thrive in agile environments where we iterate quickly and gather feedback often.",
        "When dealing with a difficult stakeholder, I ensure I understand their core needs and explain technical constraints in simple terms.",
        
        # PHASE 6: Closing 
        "Do you have any questions about the team culture or the company's future roadmap?",
        "Thank you for this opportunity. I really enjoyed our discussion and look forward to the next steps."
    ]
    
    for user_response in responses:
        if agent.is_complete():
            break
        
        print(f"Candidate: {user_response}\n")
        ai_response = await agent.process_response(user_response, {})
        print(f"AI: {ai_response}\n")
    
    print("\n=== Evaluation Summary ===")
    print(agent.get_evaluation_summary())
    
    logger.info("AI agent test completed")


if __name__ == "__main__":
    asyncio.run(test_agent())