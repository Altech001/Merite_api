"""
Real-time Notification Service

This module handles WebSocket connections and notification broadcasting.
It provides a centralized way to:
1. Manage WebSocket connections per user
2. Create and store notifications in the database
3. Broadcast notifications to connected clients in real-time
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional, Set
from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Notification, NotificationType


class ConnectionManager:
    """
    Manages WebSocket connections for real-time notifications.
    Uses a dictionary to store connections indexed by user_id for O(1) lookup.
    """
    
    def __init__(self):
        # Dict mapping user_id to a set of WebSocket connections
        # A user can have multiple connections (e.g., multiple browser tabs)
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, user_id: int):
        """Accept and register a new WebSocket connection for a user."""
        await websocket.accept()
        async with self._lock:
            if user_id not in self.active_connections:
                self.active_connections[user_id] = set()
            self.active_connections[user_id].add(websocket)
        print(f"[WS] User {user_id} connected. Total connections: {len(self.active_connections.get(user_id, set()))}")
    
    async def disconnect(self, websocket: WebSocket, user_id: int):
        """Remove a WebSocket connection for a user."""
        async with self._lock:
            if user_id in self.active_connections:
                self.active_connections[user_id].discard(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
        print(f"[WS] User {user_id} disconnected.")
    
    async def send_personal_message(self, message: dict, user_id: int):
        """Send a message to all connections of a specific user."""
        async with self._lock:
            connections = self.active_connections.get(user_id, set()).copy()
        
        disconnected = []
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"[WS] Error sending to user {user_id}: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected connections
        if disconnected:
            async with self._lock:
                for conn in disconnected:
                    if user_id in self.active_connections:
                        self.active_connections[user_id].discard(conn)
    
    async def broadcast(self, message: dict, user_ids: Optional[List[int]] = None):
        """
        Broadcast a message to multiple users.
        If user_ids is None, broadcast to all connected users.
        """
        async with self._lock:
            if user_ids is None:
                target_connections = [
                    (uid, conns.copy()) 
                    for uid, conns in self.active_connections.items()
                ]
            else:
                target_connections = [
                    (uid, self.active_connections.get(uid, set()).copy())
                    for uid in user_ids
                    if uid in self.active_connections
                ]
        
        for user_id, connections in target_connections:
            for connection in connections:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass
    
    def is_user_connected(self, user_id: int) -> bool:
        """Check if a user has any active connections."""
        return user_id in self.active_connections and len(self.active_connections[user_id]) > 0
    
    def get_connected_users_count(self) -> int:
        """Get the count of connected users."""
        return len(self.active_connections)


# Global connection manager instance
manager = ConnectionManager()


class NotificationService:
    """
    Service for creating and broadcasting notifications.
    This is designed to be used from any part of the application.
    """
    
    @staticmethod
    def create_notification(
        db: Session,
        user_id: int,
        notification_type: NotificationType,
        title: str,
        message: str,
        data: Optional[dict] = None
    ) -> Notification:
        """
        Create a notification in the database.
        
        Args:
            db: Database session
            user_id: Target user ID
            notification_type: Type of notification
            title: Notification title
            message: Notification message
            data: Optional additional data as dict (will be serialized to JSON)
        
        Returns:
            The created Notification object
        """
        notification = Notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            data=json.dumps(data) if data else None
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)
        return notification
    
    @staticmethod
    async def notify_user(
        db: Session,
        user_id: int,
        notification_type: NotificationType,
        title: str,
        message: str,
        data: Optional[dict] = None
    ) -> Notification:
        """
        Create a notification and send it via WebSocket if user is connected.
        
        This is the main method to use for sending notifications.
        It creates the notification in the database and broadcasts it in real-time.
        """
        # Create notification in database
        notification = NotificationService.create_notification(
            db=db,
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            data=data
        )
        
        # Prepare message for WebSocket
        ws_message = {
            "type": "notification",
            "data": {
                "id": notification.id,
                "notification_type": notification_type.value,
                "title": title,
                "message": message,
                "data": data,
                "is_read": False,
                "created_at": notification.created_at.isoformat()
            }
        }
        
        # Send via WebSocket if user is connected
        await manager.send_personal_message(ws_message, user_id)
        
        return notification
    
    @staticmethod
    def notify_user_sync(
        db: Session,
        user_id: int,
        notification_type: NotificationType,
        title: str,
        message: str,
        data: Optional[dict] = None
    ) -> Notification:
        """
        Synchronous version of notify_user.
        Creates the notification and schedules the WebSocket broadcast.
        Use this from synchronous endpoints.
        """
        # Create notification in database
        notification = NotificationService.create_notification(
            db=db,
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            data=data
        )
        
        # Schedule WebSocket broadcast
        ws_message = {
            "type": "notification",
            "data": {
                "id": notification.id,
                "notification_type": notification_type.value,
                "title": title,
                "message": message,
                "data": data,
                "is_read": False,
                "created_at": notification.created_at.isoformat()
            }
        }
        
        # Try to send via WebSocket (fire and forget)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(manager.send_personal_message(ws_message, user_id))
            else:
                loop.run_until_complete(manager.send_personal_message(ws_message, user_id))
        except RuntimeError:
            # No event loop running, create a new one
            try:
                asyncio.run(manager.send_personal_message(ws_message, user_id))
            except Exception:
                pass  # WebSocket delivery is best-effort
        except Exception:
            pass  # WebSocket delivery is best-effort
        
        return notification


# Convenience function for quick notifications
def send_notification(
    db: Session,
    user_id: int,
    notification_type: NotificationType,
    title: str,
    message: str,
    data: Optional[dict] = None
) -> Notification:
    """
    Convenience function to send a notification synchronously.
    Use this from any router endpoint.
    """
    return NotificationService.notify_user_sync(
        db=db,
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        message=message,
        data=data
    )
