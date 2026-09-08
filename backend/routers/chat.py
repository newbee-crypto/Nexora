import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agent.copilot import delete_session, get_session_history, run_agent_turn
from agent.copilot_langchain_prototype import run_langchain_agent_turn
from database import get_db

logger = logging.getLogger("crm.chat")

router = APIRouter(prefix="/chat", tags=["AI Copilot"])


class ChatRequest(BaseModel):
    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Session identifier. Generate once per conversation and reuse.",
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The marketer's message to the AI Copilot",
        example="Win back customers who haven't ordered in 45 days",
    )
    edited_template: str | None = Field(
        None,
        description="Manually edited message template to use when launching",
    )
    agent_framework: str = Field(
        "custom",
        description="Framework to use: 'custom' or 'langchain'",
    )


class StepCard(BaseModel):
    step: str
    data: dict


class ChatResponse(BaseModel):
    session_id: str
    steps: list[dict]
    final_message: str | None
    error: bool = False


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Run one turn of the AI Copilot agent loop."""
    logger.info(
        f"[chat] POST /chat session={payload.session_id[:8]} "
        f"message='{payload.message[:60]}'"
    )

    if payload.agent_framework == "langchain":
        result = await run_langchain_agent_turn(
            session_id=payload.session_id,
            user_message=payload.message,
            db=db,
            background_tasks=background_tasks,
            edited_template=payload.edited_template,
        )
    else:
        result = await run_agent_turn(
            session_id=payload.session_id,
            user_message=payload.message,
            db=db,
            background_tasks=background_tasks,
            edited_template=payload.edited_template,
        )

    return ChatResponse(
        session_id=result["session_id"],
        steps=result.get("steps", []),
        final_message=result.get("final_message"),
        error=result.get("error", False),
    )


@router.get("/{session_id}")
def get_chat_history(session_id: str):
    """Retrieve the full conversation history for a session."""
    history = get_session_history(session_id)
    if not history:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found or has no history",
        )
    return {
        "session_id": session_id,
        "message_count": len(history),
        "messages": history,
    }


@router.delete("/{session_id}")
def reset_chat_session(session_id: str):
    """Delete a session's conversation history to start fresh."""
    deleted = delete_session(session_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found",
        )
    return {
        "session_id": session_id,
        "status": "deleted",
        "message": "Session cleared. Start a new conversation.",
    }
