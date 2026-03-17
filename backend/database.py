"""
Database Models for Supegroww AI Interview Platform with Production Logging

This module defines the database schema using SQLAlchemy ORM with
comprehensive logging for database operations, migrations, and queries.

LOGGING FEATURES IMPLEMENTED -
1. Connection pool monitoring and metrics
2. Query performance tracking
3. Transaction logging with context
4. RAG embedding generation metrics
5. Vector search performance logging
6. Database initialization and migration tracking
7. Session lifecycle management
"""

from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    create_engine, 
    Column, 
    Integer, 
    String, 
    Text, 
    DateTime, 
    Float, 
    Boolean,
    ForeignKey,
    JSON,
    Enum as SQLEnum,
    event
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from langchain_community.embeddings import HuggingFaceEmbeddings
from backend.config import settings
from pgvector.sqlalchemy import Vector  
import enum
import os

from backend.logger import (
    get_logger,
    PerformanceLogger,
    log_exception
)

# Create component logger
logger = get_logger("database")

Base = declarative_base()

# Enums for interview status
class InterviewStatus(enum.Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"

class CheatingFlag(enum.Enum):
    GAZE_DEVIATION = "gaze_deviation"
    TAB_SWITCH = "tab_switch"
    MULTIPLE_VOICES = "multiple_voices"
    SUSPICIOUS_TYPING = "suspicious_typing"
    FULLSCREEN_EXIT = "fullscreen_exit"

# USER MANAGEMENT

class User(Base):
    """
    Represents recruiters and administrators.
    
    Why: We need to track who created jobs and interviews.
    In production, this would integrate with Auth0 or similar.
    """
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    company_name = Column(String(255))
    role = Column(String(50), default='recruiter') 
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    jobs = relationship("Job", back_populates="created_by_user")
    interviews = relationship("Interview", back_populates="created_by_user")

# JOB POSTINGS

class Job(Base):
    """
    Represents an open position.
    
    Why: Each interview is tied to a specific job. The job description
    is used in RAG to generate relevant questions.
    """
    __tablename__ = 'jobs'
    
    id = Column(Integer, primary_key=True)
    job_id = Column(String(100), unique=True, nullable=False, index=True) 
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)  
    requirements = Column(JSON)  
    
    # Interview configuration
    interview_duration_minutes = Column(Integer, default=30)
    topics_to_cover = Column(JSON)  
    evaluation_rubric = Column(JSON)  
    
    # Metadata
    created_by = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    created_by_user = relationship("User", back_populates="jobs")
    candidates = relationship("Candidate", back_populates="job")
    interviews = relationship("Interview", back_populates="job")

# CANDIDATES

class Candidate(Base):
    """
    Stores candidate information and resume.
    
    Why - We need to persist candidate data even before the interview.
    The resume is parsed and embedded for RAG retrieval.
    """
    __tablename__ = 'candidates'
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    phone = Column(String(50))
    
    # Resume data
    resume_text = Column(Text)  
    resume_url = Column(String(500))  
    resume_parsed_data = Column(JSON)  
    
    # Application tracking
    job_id = Column(Integer, ForeignKey('jobs.id'))
    ats_candidate_id = Column(String(100))  
    source = Column(String(100))  
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    job = relationship("Job", back_populates="candidates")
    resume_embeddings = relationship("ResumeEmbedding", back_populates="candidate")
    interviews = relationship("Interview", back_populates="candidate")

# RESUME EMBEDDINGS (for RAG)

class ResumeEmbedding(Base):
    """
    Stores vector embeddings of resume chunks for similarity search.
    
    Why - To implement RAG, we need to -
    1. Split resume into semantic chunks
    2. Embed each chunk using OpenAI/Cohere
    3. Store in pgvector for fast retrieval
    4. During interview, retrieve relevant chunks based on current topic
    """
    __tablename__ = 'resume_embeddings'
    
    id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id'), nullable=False)
    
    # Text chunk
    chunk_text = Column(Text, nullable=False)
    chunk_metadata = Column(JSON)  
    
    # Vector embedding (1536 dimensions for OpenAI text-embedding-3-small)
    embedding = Column(Vector(settings.EMBEDDING_DIMENSION))  
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    candidate = relationship("Candidate", back_populates="resume_embeddings")

# INTERVIEWS

class Interview(Base):
    """
    Represents a single interview session.
    
    Why - Central record that ties together -
    - Candidate
    - Job
    - LiveKit room
    - Transcript
    - Scores
    - Recording
    """
    __tablename__ = 'interviews'
    
    id = Column(Integer, primary_key=True)
    interview_uuid = Column(String(100), unique=True, nullable=False, index=True)
    
    # Relationships
    candidate_id = Column(Integer, ForeignKey('candidates.id'), nullable=False)
    job_id = Column(Integer, ForeignKey('jobs.id'), nullable=False)
    created_by = Column(Integer, ForeignKey('users.id'))
    
    # LiveKit data
    room_name = Column(String(255), nullable=False)
    livekit_room_sid = Column(String(100))  
    
    # Scheduling
    scheduled_at = Column(DateTime)
    started_at = Column(DateTime)
    ended_at = Column(DateTime)
    duration_seconds = Column(Integer)
    
    # Status tracking
    status = Column(SQLEnum(InterviewStatus), default=InterviewStatus.SCHEDULED)
    
    # Recording
    recording_url = Column(String(500))  
    transcript_url = Column(String(500))  
    
    # Anti-cheating flags
    cheating_flags = Column(JSON)  
    
    # Final evaluation
    overall_score = Column(Float)  
    recommendation = Column(String(50)) 
    ai_summary = Column(Text)  
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    candidate = relationship("Candidate", back_populates="interviews")
    job = relationship("Job", back_populates="interviews")
    created_by_user = relationship("User", back_populates="interviews")
    transcripts = relationship("InterviewTranscript", back_populates="interview")
    scores = relationship("EvaluationScore", back_populates="interview")

# REAL-TIME TRANSCRIPT

class InterviewTranscript(Base):
    """
    Stores each turn in the conversation.
    
    Why: 
    - Enables replay functionality
    - Provides data for evaluation
    - Helps with debugging
    - Required for GDPR "Right to Explanation"
    """
    __tablename__ = 'interview_transcripts'
    
    id = Column(Integer, primary_key=True)
    interview_id = Column(Integer, ForeignKey('interviews.id'), nullable=False)
    
    # Speaker identification
    speaker = Column(String(50), nullable=False)  
    
    # Message content
    message_text = Column(Text, nullable=False)
    
    # Timing
    timestamp = Column(DateTime, default=lambda: datetime.utcnow())
    time_offset_seconds = Column(Float)  
    
    # Audio analysis (optional, from Hume AI)
    sentiment_scores = Column(JSON)  
    
    # Relationships
    interview = relationship("Interview", back_populates="transcripts")

# EVALUATION SCORES

class EvaluationScore(Base):
    """
    Stores hierarchical scoring data.
    
    Why - The evaluation system has 3 levels:
    Level 1 - Real-time per-answer scoring (completeness, depth, etc.)
    Level 2 - Topic-based accumulated scores (System Design: 85/100)
    Level 3 - Final weighted scorecard
    """
    __tablename__ = 'evaluation_scores'
    
    id = Column(Integer, primary_key=True)
    interview_id = Column(Integer, ForeignKey('interviews.id'), nullable=False)
    
    # Scoring hierarchy
    level = Column(Integer, nullable=False)  
    category = Column(String(100))  
    
    # Scores
    score_value = Column(Float, nullable=False)  
    max_score = Column(Float, default=100)
    weight = Column(Float)  
    
    # Evidence
    justification = Column(Text)  
    evidence_transcript_ids = Column(JSON)  
    
    # Timing
    evaluated_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    interview = relationship("Interview", back_populates="scores")

# DATABASE CONNECTION WITH LOGGING

def init_db():
    """
    Initialize database connection and create tables with comprehensive logging.
    
    Why - This should be called on application startup.
    It creates all tables if they don't exist.
    """
    logger.info("Initializing database connection")
    
    try:
        with PerformanceLogger(logger, "database_initialization"):
            # Create engine with connection pooling
            engine = create_engine(
                settings.DATABASE_URL,
                echo=False,  # Disable SQLAlchemy's built-in logging (we have our own)
                pool_pre_ping=True,  # Verify connections before use
                pool_size=settings.DATABASE_POOL_SIZE,
                max_overflow=settings.DATABASE_MAX_OVERFLOW
            )
            
            logger.info(
                "Database engine created",
                extra={
                    "pool_size": settings.DATABASE_POOL_SIZE,
                    "max_overflow": settings.DATABASE_MAX_OVERFLOW,
                    "pool_pre_ping": True
                }
            )
            
            # Set up connection pool event listeners for monitoring
            @event.listens_for(engine, "connect")
            def receive_connect(dbapi_conn, connection_record):
                logger.debug("New database connection established")
            
            @event.listens_for(engine, "checkout")
            def receive_checkout(dbapi_conn, connection_record, connection_proxy):
                logger.debug("Connection checked out from pool")
            
            @event.listens_for(engine, "checkin")
            def receive_checkin(dbapi_conn, connection_record):
                logger.debug("Connection checked back into pool")
            
            # Enable pgvector extension
            with engine.connect() as conn:
                try:
                    logger.info("Enabling pgvector extension")
                    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    conn.commit()
                    logger.info("pgvector extension enabled successfully")
                except Exception as e:
                    log_exception(logger, e, {"operation": "enable_pgvector"})
                    logger.warning("Could not create vector extension - proceeding anyway")
            
            # Create all tables
            logger.info("Creating database tables")
            Base.metadata.create_all(engine)
            
            # Log table creation success
            table_names = [table.name for table in Base.metadata.sorted_tables]
            logger.info(
                "Database tables created successfully",
                extra={
                    "num_tables": len(table_names),
                    "tables": table_names
                }
            )
        
        logger.info("Database initialization completed successfully")
        return engine
    
    except Exception as e:
        log_exception(logger, e, {"operation": "init_db"})
        raise


def get_session():
    """
    Get a database session with logging.
    
    Why: This is used in FastAPI with dependency injection.
    Each API request gets a fresh session that's automatically closed.
    """
    logger.debug("Creating new database session")
    
    try:
        engine = create_engine(settings.DATABASE_URL)
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()
        
        try:
            yield db
        finally:
            logger.debug("Closing database session")
            db.close()
    
    except Exception as e:
        log_exception(logger, e, {"operation": "get_session"})
        raise

def get_embedding_function():
    """Get embedding function with provider logging."""
    logger.info(
        "Initializing embedding function",
        extra={
            "provider": settings.EMBEDDING_PROVIDER,
            "model": settings.EMBEDDING_MODEL,
            "dimension": settings.EMBEDDING_DIMENSION
        }
    )
    
    try:
        if settings.EMBEDDING_PROVIDER == "openai":
            from langchain_openai import OpenAIEmbeddings
            
            embed_func = OpenAIEmbeddings(
                model=settings.EMBEDDING_MODEL, 
                api_key=settings.OPENAI_API_KEY
            )
            
            logger.info("OpenAI embedding function initialized")
            return embed_func
        else:
            # Use Local HuggingFace Embeddings (Free, runs on CPU/GPU)
            embed_func = HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)
            
            logger.info("HuggingFace embedding function initialized")
            return embed_func
    
    except Exception as e:
        log_exception(logger, e, {
            "operation": "get_embedding_function",
            "provider": settings.EMBEDDING_PROVIDER
        })
        raise

from langchain_text_splitters import RecursiveCharacterTextSplitter

def create_candidate_with_resume(db, name: str, email: str, resume_text: str, job_id: int):
    """
    Creates a candidate and embeds their resume with comprehensive logging.
    
    Args:
        db: Database session
        name: Candidate name
        email: Candidate email
        resume_text: Full resume text
        job_id: Associated job ID
    
    Returns:
        Candidate: Created candidate object
    """
    logger.info(
        "Creating candidate with resume embeddings",
        extra={
            "candidate_name": name,
            "candidate_email": email,
            "resume_length": len(resume_text),
            "job_id": job_id
        }
    )
    
    try:
        # 1. Create Candidate record
        with PerformanceLogger(logger, "create_candidate_record"):
            candidate = Candidate(
                name=name,
                email=email,
                resume_text=resume_text,
                job_id=job_id,
                created_at=datetime.utcnow()
            )
            db.add(candidate)
            db.commit()
            db.refresh(candidate)
        
        logger.info(
            "Candidate record created",
            extra={"candidate_id": candidate.id}
        )
        
        # 2. Chunk the resume
        logger.debug("Chunking resume text")
        logger.debug("Chunking resume text using RecursiveSplitter")

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=600,       # Group ~600 characters together
            chunk_overlap=100,    # Overlap slightly so context isn't lost at the edges
            separators=["\n\n", "\n", " ", ""] # Try double enter, then single enter, then space
        )

        chunks = text_splitter.split_text(resume_text)
        
        logger.info(
            "Resume chunked",
            extra={
                "candidate_id": candidate.id,
                "num_chunks": len(chunks),
                "avg_chunk_length": sum(len(c) for c in chunks) / len(chunks) if chunks else 0
            }
        )
        
        # 3. Generate Embeddings
        embed_func = get_embedding_function()
        
        try:
            logger.info(
                "Generating embeddings",
                extra={
                    "candidate_id": candidate.id,
                    "num_chunks": len(chunks),
                    "provider": settings.EMBEDDING_PROVIDER
                }
            )
            
            with PerformanceLogger(logger, "generate_embeddings", candidate_id=candidate.id):
                # Batch embed all chunks
                embeddings_list = embed_func.embed_documents(chunks)
            
            logger.info(
                "Embeddings generated successfully",
                extra={
                    "candidate_id": candidate.id,
                    "num_embeddings": len(embeddings_list)
                }
            )
            
            # Store embeddings in database
            with PerformanceLogger(logger, "store_embeddings", candidate_id=candidate.id):
                for i, text_chunk in enumerate(chunks):
                    resume_embedding = ResumeEmbedding(
                        candidate_id=candidate.id,
                        chunk_text=text_chunk,
                        chunk_metadata={"chunk_index": i},
                        embedding=embeddings_list[i]
                    )
                    db.add(resume_embedding)
                
                db.commit()
            
            logger.info(
                "Resume embeddings stored successfully",
                extra={
                    "candidate_id": candidate.id,
                    "candidate_name": name,
                    "num_embeddings": len(chunks),
                    "provider": settings.EMBEDDING_PROVIDER
                }
            )
        
        except Exception as e:
            log_exception(logger, e, {
                "operation": "generate_resume_embeddings",
                "candidate_id": candidate.id,
                "num_chunks": len(chunks)
            })
            
            logger.warning(
                "Continuing without embeddings due to error",
                extra={"candidate_id": candidate.id}
            )
        
        return candidate
    
    except Exception as e:
        log_exception(logger, e, {
            "operation": "create_candidate_with_resume",
            "candidate_name": name,
            "candidate_email": email
        })
        raise


def semantic_search_resume(db, candidate_id: int, query: str, top_k: int = 3):
    """
    Search candidate's resume using vector similarity with performance logging.
    
    Args:
        db: Database session
        candidate_id: Candidate ID
        query: Search query
        top_k: Number of results to return
    
    Returns:
        List[str]: Top-k matching resume chunks
    """
    logger.info(
        "Performing semantic resume search",
        extra={
            "candidate_id": candidate_id,
            "query": query[:100],
            "top_k": top_k
        }
    )
    
    try:
        with PerformanceLogger(logger, "semantic_search", candidate_id=candidate_id):
            # 1. Embed the query
            logger.debug("Embedding search query")
            embed_func = get_embedding_function()
            query_embedding = embed_func.embed_query(query)
            
            logger.debug(
                "Query embedded",
                extra={
                    "embedding_dimension": len(query_embedding),
                    "provider": settings.EMBEDDING_PROVIDER
                }
            )
            
            # 2. Vector similarity search (pgvector)
            logger.debug("Executing vector similarity search")
            results = db.query(ResumeEmbedding).filter(
                ResumeEmbedding.candidate_id == candidate_id
            ).order_by(
                ResumeEmbedding.embedding.cosine_distance(query_embedding)
            ).limit(top_k).all()
        
        result_texts = [r.chunk_text for r in results]
        
        logger.info(
            "Semantic search completed",
            extra={
                "candidate_id": candidate_id,
                "results_found": len(results),
                "avg_result_length": sum(len(r) for r in result_texts) / len(result_texts) if result_texts else 0
            }
        )
        
        return result_texts
    
    except Exception as e:
        log_exception(logger, e, {
            "operation": "semantic_search_resume",
            "candidate_id": candidate_id,
            "query": query[:100]
        })
        
        # Return empty list on error
        logger.warning("Returning empty results due to error")
        return []

def get_database_stats():
    """
    Get database statistics for monitoring.
    
    Returns:
        dict: Database metrics
    """
    logger.info("Retrieving database statistics")
    
    try:
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.connect() as conn:
            # Get table row counts
            stats = {}
            
            for table in Base.metadata.sorted_tables:
                try:
                    result = conn.execute(f"SELECT COUNT(*) FROM {table.name}")
                    count = result.scalar()
                    stats[table.name] = count
                except Exception as e:
                    logger.warning(
                        f"Could not get count for table {table.name}",
                        extra={"error": str(e)}
                    )
                    stats[table.name] = None
        
        # Get connection pool stats
        pool_stats = {
            "pool_size": engine.pool.size(),
            "checked_in": engine.pool.checkedin(),
            "overflow": engine.pool.overflow(),
            "checked_out": engine.pool.checkedout()
        }
        
        stats["_pool_stats"] = pool_stats
        
        logger.info("Database statistics retrieved", extra=stats)
        
        return stats
    
    except Exception as e:
        log_exception(logger, e, {"operation": "get_database_stats"})
        return {}

if __name__ == "__main__":
    logger.info("Starting database module test")
    
    try:
        logger.info("Initializing database")
        init_db()
        
        logger.info("Getting database statistics")
        stats = get_database_stats()
        
        logger.info(
            "Database test completed successfully",
            extra={"stats": stats}
        )
    
    except Exception as e:
        log_exception(logger, e, {"operation": "database_test"})
        logger.error("Database test failed")