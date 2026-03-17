"""
WebSocket Handler for Real-Time Interview Updates with Production Logging
=========================================================================

This enables real-time communication with the recruiter dashboard with
comprehensive logging for connection management and message delivery.

LOGGING FEATURES IMPLEMENTED:
1. Connection lifecycle tracking (connect, disconnect, errors)
2. Message broadcast performance metrics
3. Active connection monitoring
4. Dead connection detection and cleanup logging
5. Message type and payload tracking
6. WebSocket error categorization
7. Heartbeat monitoring
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
from typing import Dict, List, Set
import json
import asyncio
from datetime import datetime

from database import get_session, Interview
from config import settings

# ============================================================================
# PROPER LOGGING SETUP (Following logger.py patterns)
# ============================================================================

from logger import (
    get_logger,
    ContextLogger,
    PerformanceLogger,
    log_exception
)

# Create component logger
logger = get_logger("websocket_handler")

router = APIRouter()


# CONNECTION MANAGER WITH LOGGING

class ConnectionManager:
    """
    Manages active WebSocket connections with comprehensive logging.
    
    Why:
    - Track which recruiters are watching which interviews
    - Broadcast updates to all connected clients
    - Handle disconnections gracefully
    - Monitor connection health
    
    Pattern: Singleton - only one manager instance
    """
    
    def __init__(self):
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        self.lock = asyncio.Lock()
        
        # Metrics tracking
        self.total_connections = 0
        self.total_disconnections = 0
        self.total_messages_sent = 0
        self.failed_messages = 0
        
        logger.info("ConnectionManager initialized")
    
    async def connect(self, websocket: WebSocket, interview_id: int):
        """
        Accept a new WebSocket connection with logging.
        
        Flow:
        1. Accept WebSocket handshake
        2. Add to active connections for this interview
        3. Log connection details
        """
        try:
            await websocket.accept()
            
            async with self.lock:
                if interview_id not in self.active_connections:
                    self.active_connections[interview_id] = set()
                
                self.active_connections[interview_id].add(websocket)
                self.total_connections += 1
            
            connection_count = len(self.active_connections.get(interview_id, []))
            
            logger.info(
                "WebSocket connected",
                extra={
                    "interview_id": interview_id,
                    "connections_for_interview": connection_count,
                    "total_active_interviews": len(self.active_connections),
                    "total_connections_ever": self.total_connections
                }
            )
        
        except Exception as e:
            log_exception(logger, e, {
                "operation": "websocket_connect",
                "interview_id": interview_id
            })
            raise
    
    async def disconnect(self, websocket: WebSocket, interview_id: int):
        """
        Remove a WebSocket connection with logging.
        
        Called when:
        - Recruiter closes browser tab
        - Connection times out
        - Error occurs
        """
        try:
            async with self.lock:
                if interview_id in self.active_connections:
                    self.active_connections[interview_id].discard(websocket)
                    self.total_disconnections += 1
                    
                    # Clean up empty interview entries
                    if len(self.active_connections[interview_id]) == 0:
                        del self.active_connections[interview_id]
                        logger.info(
                            "Last connection closed for interview",
                            extra={"interview_id": interview_id}
                        )
            
            logger.info(
                "WebSocket disconnected",
                extra={
                    "interview_id": interview_id,
                    "remaining_connections": len(self.active_connections.get(interview_id, [])),
                    "total_disconnections": self.total_disconnections
                }
            )
        
        except Exception as e:
            log_exception(logger, e, {
                "operation": "websocket_disconnect",
                "interview_id": interview_id
            })
    
    async def broadcast(self, interview_id: int, message: dict):
        """
        Send message to all connected clients watching this interview.
        
        Why broadcast:
        - Multiple recruiters might watch same interview
        - Updates should reach everyone
        - Track delivery success/failure
        
        Args:
            interview_id: Which interview the update is for
            message: JSON-serializable dict to send
        """
        logger.debug(
            "Broadcasting message",
            extra={
                "interview_id": interview_id,
                "message_type": message.get("type"),
                "message_size": len(json.dumps(message))
            }
        )
        
        try:
            with PerformanceLogger(logger, "broadcast_message", interview_id=interview_id):
                async with self.lock:
                    connections = self.active_connections.get(interview_id, set()).copy()
                
                if not connections:
                    logger.debug(
                        "No active connections for interview",
                        extra={"interview_id": interview_id}
                    )
                    return
                
                dead_connections = []
                successful_sends = 0
                
                for connection in connections:
                    try:
                        await connection.send_json(message)
                        successful_sends += 1
                        self.total_messages_sent += 1
                    except Exception as e:
                        logger.warning(
                            "Failed to send message to connection",
                            extra={
                                "interview_id": interview_id,
                                "error": str(e)
                            }
                        )
                        dead_connections.append(connection)
                        self.failed_messages += 1
                
                # Clean up dead connections
                if dead_connections:
                    async with self.lock:
                        if interview_id in self.active_connections:
                            for conn in dead_connections:
                                self.active_connections[interview_id].discard(conn)
                    
                    logger.warning(
                        "Removed dead connections",
                        extra={
                            "interview_id": interview_id,
                            "dead_connections": len(dead_connections)
                        }
                    )
                
                logger.debug(
                    "Broadcast completed",
                    extra={
                        "interview_id": interview_id,
                        "successful_sends": successful_sends,
                        "failed_sends": len(dead_connections),
                        "message_type": message.get("type")
                    }
                )
        
        except Exception as e:
            log_exception(logger, e, {
                "operation": "broadcast_message",
                "interview_id": interview_id,
                "message_type": message.get("type")
            })
    
    def get_metrics(self) -> dict:
        """
        Get connection manager metrics for monitoring.
        
        Returns:
            dict: Metrics about WebSocket connections
        """
        metrics = {
            "active_interviews": len(self.active_connections),
            "total_active_connections": sum(len(conns) for conns in self.active_connections.values()),
            "total_connections_ever": self.total_connections,
            "total_disconnections": self.total_disconnections,
            "total_messages_sent": self.total_messages_sent,
            "failed_messages": self.failed_messages,
            "message_success_rate": ((self.total_messages_sent - self.failed_messages) / self.total_messages_sent * 100)
                                    if self.total_messages_sent > 0 else 0
        }
        
        logger.debug("Connection manager metrics retrieved", extra=metrics)
        
        return metrics


# Global connection manager
manager = ConnectionManager()

# WEBSOCKET ENDPOINT WITH LOGGING

@router.websocket("/ws/interviews/{interview_id}")
async def interview_websocket(
    websocket: WebSocket,
    interview_id: int,
    db: Session = Depends(get_session)
):
    """
    WebSocket endpoint for real-time interview updates with comprehensive logging.
    
    Usage (JavaScript):
    ```javascript
    const ws = new WebSocket('ws://localhost:8000/ws/interviews/123');
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.type === 'status_update') {
            console.log('Status:', data.status);
        }
        
        if (data.type === 'transcript_chunk') {
            appendTranscript(data.speaker, data.text);
        }
        
        if (data.type === 'evaluation_score') {
            updateScore(data.category, data.score);
        }
    };
    ```
    
    Message types sent to client:
    1. connected - Initial connection confirmation
    2. status_update - Interview status changed
    3. transcript_chunk - New conversation turn
    4. evaluation_score - Score computed for answer
    5. error - Something went wrong
    6. echo - Debug echo back
    """
    
    ctx_logger = ContextLogger(
        logger=logger,
        interview_id=interview_id
    )
    
    ctx_logger.info("New WebSocket connection attempt")
    
    try:
        # 1. Validate interview exists
        ctx_logger.debug("Validating interview exists")
        
        interview = db.query(Interview).filter(
            Interview.id == interview_id
        ).first()
        
        if not interview:
            ctx_logger.warning("Interview not found, rejecting connection")
            await websocket.close(code=1008, reason="Interview not found")
            return
        
        ctx_logger.info(
            "Interview found",
            extra={
                "candidate_name": interview.candidate.name,
                "job_title": interview.job.title,
                "status": interview.status.value
            }
        )
        
        # 2. Accept connection
        await manager.connect(websocket, interview_id)
        
        # 3. Send initial status
        initial_message = {
            "type": "connected",
            "interview_id": interview_id,
            "status": interview.status.value,
            "candidate_name": interview.candidate.name,
            "job_title": interview.job.title,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await websocket.send_json(initial_message)
        
        ctx_logger.info("Initial status sent to client")
        
        # 4. Keep connection alive and listen for messages
        message_count = 0
        
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                message_count += 1
                
                ctx_logger.debug(
                    "Received message from client",
                    extra={
                        "message_count": message_count,
                        "message_length": len(data)
                    }
                )
                
                # Echo back (for debugging/ping)
                await websocket.send_json({
                    "type": "echo",
                    "message": data,
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            except WebSocketDisconnect:
                ctx_logger.info(
                    "Client disconnected normally",
                    extra={"messages_received": message_count}
                )
                break
            
            except Exception as e:
                log_exception(logger, e, {
                    "interview_id": interview_id,
                    "operation": "websocket_receive",
                    "messages_received": message_count
                })
                break
    
    except WebSocketDisconnect:
        ctx_logger.info("Client disconnected during handshake")
    
    except Exception as e:
        log_exception(logger, e, {
            "interview_id": interview_id,
            "operation": "interview_websocket"
        })
    
    finally:
        # Always clean up connection
        await manager.disconnect(websocket, interview_id)
        ctx_logger.info("WebSocket connection cleaned up")


# HELPER FUNCTIONS WITH LOGGING

async def send_status_update(interview_id: int, status: str):
    """
    Send interview status update to all connected clients.
    
    Called by:
    - livekit_handler.py when interview starts/ends
    - API endpoint when status is updated
    """
    logger.info(
        "Sending status update",
        extra={
            "interview_id": interview_id,
            "status": status
        }
    )
    
    try:
        await manager.broadcast(interview_id, {
            "type": "status_update",
            "status": status,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    except Exception as e:
        log_exception(logger, e, {
            "operation": "send_status_update",
            "interview_id": interview_id,
            "status": status
        })


async def send_transcript_chunk(
    interview_id: int,
    speaker: str,
    text: str,
    time_offset: float
):
    """
    Send new transcript chunk to all connected clients.
    
    Called by:
    - livekit_handler.py every time candidate or AI speaks
    """
    logger.debug(
        "Sending transcript chunk",
        extra={
            "interview_id": interview_id,
            "speaker": speaker,
            "text_length": len(text),
            "time_offset_seconds": round(time_offset, 2)
        }
    )
    
    try:
        await manager.broadcast(interview_id, {
            "type": "transcript_chunk",
            "speaker": speaker,
            "text": text,
            "time_offset_seconds": time_offset,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    except Exception as e:
        log_exception(logger, e, {
            "operation": "send_transcript_chunk",
            "interview_id": interview_id,
            "speaker": speaker
        })


async def send_evaluation_score(
    interview_id: int,
    scores: dict,
    time_offset: float
):
    """
    Send evaluation score update to all connected clients.
    
    Called by:
    - evaluation_agent.py after scoring each answer
    
    Args:
        interview_id: Interview ID
        scores: Dict of score dimensions
        time_offset: Time offset in seconds
    """
    logger.info(
        "Sending evaluation scores",
        extra={
            "interview_id": interview_id,
            "num_dimensions": len(scores),
            "time_offset_seconds": round(time_offset, 2)
        }
    )
    
    try:
        await manager.broadcast(interview_id, {
            "type": "evaluation_score",
            "scores": scores,
            "time_offset_seconds": time_offset,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    except Exception as e:
        log_exception(logger, e, {
            "operation": "send_evaluation_score",
            "interview_id": interview_id
        })


async def send_error(interview_id: int, error_message: str):
    """
    Send error notification to all connected clients.
    
    Called by:
    - Any component when error occurs during interview
    """
    logger.error(
        "Sending error notification",
        extra={
            "interview_id": interview_id,
            "error_message": error_message
        }
    )
    
    try:
        await manager.broadcast(interview_id, {
            "type": "error",
            "error": error_message,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    except Exception as e:
        log_exception(logger, e, {
            "operation": "send_error",
            "interview_id": interview_id
        })


# HEARTBEAT WITH LOGGING

async def start_heartbeat(interview_id: int):
    """
    Send periodic ping to keep connection alive with logging.
    
    Why:
    - Some proxies/load balancers close idle WebSockets
    - Sending ping every 30s prevents timeout
    - Also detects dead connections
    
    Run as background task:
    ```python
    asyncio.create_task(start_heartbeat(123))
    ```
    """
    logger.info(
        "Starting heartbeat for interview",
        extra={"interview_id": interview_id}
    )
    
    ping_count = 0
    
    try:
        while True:
            await asyncio.sleep(30)
            
            # Check if interview still has connections
            if interview_id not in manager.active_connections:
                logger.info(
                    "Stopping heartbeat - no active connections",
                    extra={
                        "interview_id": interview_id,
                        "total_pings_sent": ping_count
                    }
                )
                break
            
            ping_count += 1
            
            await manager.broadcast(interview_id, {
                "type": "ping",
                "ping_count": ping_count,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            if ping_count % 10 == 0:
                logger.debug(
                    "Heartbeat status",
                    extra={
                        "interview_id": interview_id,
                        "pings_sent": ping_count
                    }
                )
    
    except Exception as e:
        log_exception(logger, e, {
            "operation": "heartbeat",
            "interview_id": interview_id,
            "pings_sent": ping_count
        })


def get_websocket_metrics() -> dict:
    """
    Get WebSocket metrics for monitoring.
    
    Returns:
        dict: WebSocket connection and message metrics
    """
    logger.info("Retrieving WebSocket metrics")
    return manager.get_metrics()


def log_websocket_status():
    """Log current WebSocket handler status."""
    metrics = get_websocket_metrics()
    
    logger.info(
        "WebSocket Handler Status",
        extra=metrics
    )


# ============================================================================
# MODULE-LEVEL TESTING
# ============================================================================

if __name__ == "__main__":
    logger.info("WebSocket handler module loaded")
    logger.info("Use this module in FastAPI with: app.include_router(router)")
    
    # Log initial metrics
    log_websocket_status()
