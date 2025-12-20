"""
Real-time Notifications Router

This module provides:
1. WebSocket endpoint for real-time notifications
2. REST endpoints for managing notifications
3. Pagination with cursor-based and offset-based indexing

WebSocket Connection Flow:
1. Client connects to /notifications/ws?token=<JWT_TOKEN>
2. Server authenticates and accepts the connection
3. Server sends real-time notifications as they occur
4. Client can send ping messages to keep connection alive
5. On disconnect, connection is cleaned up

REST Endpoints:
- GET /notifications/ - List all notifications with pagination
- GET /notifications/unread - Get unread count
- PUT /notifications/{id}/read - Mark single notification as read
- PUT /notifications/read-all - Mark all notifications as read
- DELETE /notifications/{id} - Delete a notification
"""

import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from app.database import get_db
from app.models import User, Notification, NotificationType
from app.schemas import (
    NotificationResponse, NotificationListResponse, 
    NotificationUpdateRequest, NotificationBulkUpdateRequest, MessageResponse
)
from app.utils import get_current_user_with_api_key, verify_token
from app.notification_service import manager

router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ==================== Helper Functions ====================

def get_user_from_token(token: str, db: Session) -> Optional[User]:
    """Validate JWT token and return user."""
    payload = verify_token(token)
    if not payload:
        return None
    
    user_id = payload.get("user_id")
    if not user_id:
        return None
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        return None
    
    return user


# ==================== WebSocket Endpoint ====================

@router.websocket("/ws")
async def websocket_notifications(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time notifications.
    
    Connect with: ws://host/notifications/ws?token=YOUR_JWT_TOKEN
    
    Messages received:
    - {"type": "notification", "data": {...}} - New notification
    - {"type": "pong", "data": {}} - Response to ping
    
    Messages to send:
    - {"type": "ping"} - Keep-alive ping
    - {"type": "subscribe"} - Subscribe to notifications (auto on connect)
    """
    # Authenticate user
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return
    
    user = get_user_from_token(token, db)
    if not user:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return
    
    # Connect user
    await manager.connect(websocket, user.id)
    
    try:
        # Send initial connection success message
        await websocket.send_json({
            "type": "connected",
            "data": {
                "user_id": user.id,
                "message": "Successfully connected to notification service"
            }
        })
        
        # Send unread count on connect
        unread_count = db.query(Notification).filter(
            Notification.user_id == user.id,
            Notification.is_read == False
        ).count()
        
        await websocket.send_json({
            "type": "unread_count",
            "data": {"count": unread_count}
        })
        
        # Listen for messages from client
        while True:
            try:
                data = await websocket.receive_json()
                message_type = data.get("type", "")
                
                if message_type == "ping":
                    await websocket.send_json({"type": "pong", "data": {}})
                
                elif message_type == "subscribe":
                    # Already subscribed on connect, just acknowledge
                    await websocket.send_json({
                        "type": "subscribed",
                        "data": {"message": "Subscribed to notifications"}
                    })
                
                elif message_type == "get_unread_count":
                    # Refresh unread count
                    unread_count = db.query(Notification).filter(
                        Notification.user_id == user.id,
                        Notification.is_read == False
                    ).count()
                    await websocket.send_json({
                        "type": "unread_count",
                        "data": {"count": unread_count}
                    })
                
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "data": {"message": "Invalid JSON message"}
                })
    
    except WebSocketDisconnect:
        await manager.disconnect(websocket, user.id)
    except Exception as e:
        print(f"[WS] Error for user {user.id}: {e}")
        await manager.disconnect(websocket, user.id)


# ==================== REST Endpoints ====================

@router.get("/", response_model=NotificationListResponse)
def get_notifications(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    notification_type: Optional[NotificationType] = Query(None, description="Filter by type"),
    is_read: Optional[bool] = Query(None, description="Filter by read status"),
    after_id: Optional[int] = Query(None, description="Cursor: get notifications after this ID (for infinite scroll)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Get all notifications for the current user with pagination.
    
    Supports two pagination strategies:
    1. Offset-based: Use `page` and `page_size` for traditional pagination
    2. Cursor-based: Use `after_id` for infinite scroll (more efficient for large datasets)
    
    Indexes used:
    - user_id index for fast user filtering
    - created_at index for efficient ordering
    - is_read index for read/unread filtering
    - Composite filtering on notification_type
    """
    # Base query with user filter (uses user_id index)
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    
    # Apply filters (uses respective indexes)
    if notification_type:
        query = query.filter(Notification.notification_type == notification_type)
    
    if is_read is not None:
        query = query.filter(Notification.is_read == is_read)
    
    # Cursor-based pagination (more efficient for large datasets)
    if after_id:
        query = query.filter(Notification.id < after_id)
    
    # Get total count for pagination info
    total_count = query.count()
    
    # Get unread count
    unread_query = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    )
    if notification_type:
        unread_query = unread_query.filter(Notification.notification_type == notification_type)
    unread_count = unread_query.count()
    
    # Order by ID descending (uses primary key index, correlates with created_at)
    query = query.order_by(desc(Notification.id))
    
    # Apply offset-based pagination if not using cursor
    if not after_id:
        offset = (page - 1) * page_size
        query = query.offset(offset)
    
    # Limit results
    notifications = query.limit(page_size).all()
    
    return NotificationListResponse(
        notifications=notifications,
        total_count=total_count,
        unread_count=unread_count,
        page=page,
        page_size=page_size
    )


@router.get("/unread-count")
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Get the count of unread notifications.
    Uses is_read and user_id indexes for efficient counting.
    """
    count = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).count()
    
    return {"unread_count": count}


@router.get("/{notification_id}", response_model=NotificationResponse)
def get_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    """Get a single notification by ID."""
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id
    ).first()
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    return notification


@router.put("/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    """Mark a single notification as read."""
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id
    ).first()
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    
    return notification


@router.put("/read-all", response_model=MessageResponse)
def mark_all_notifications_read(
    request: Optional[NotificationBulkUpdateRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Mark multiple notifications as read.
    
    If notification_ids is provided, only those notifications are updated.
    If notification_ids is None or not provided, all unread notifications are marked as read.
    """
    query = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    )
    
    if request and request.notification_ids:
        query = query.filter(Notification.id.in_(request.notification_ids))
    
    count = query.update({"is_read": True}, synchronize_session=False)
    db.commit()
    
    return MessageResponse(
        message=f"Marked {count} notifications as read",
        success=True
    )


@router.delete("/{notification_id}", response_model=MessageResponse)
def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    """Delete a single notification."""
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id
    ).first()
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    db.delete(notification)
    db.commit()
    
    return MessageResponse(
        message="Notification deleted successfully",
        success=True
    )


@router.delete("/", response_model=MessageResponse)
def delete_all_notifications(
    only_read: bool = Query(True, description="If true, only delete read notifications"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_with_api_key)
):
    """
    Delete multiple notifications.
    By default, only deletes read notifications.
    Set only_read=false to delete all notifications.
    """
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    
    if only_read:
        query = query.filter(Notification.is_read == True)
    
    count = query.delete(synchronize_session=False)
    db.commit()
    
    return MessageResponse(
        message=f"Deleted {count} notifications",
        success=True
    )
