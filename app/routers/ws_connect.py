import json
from typing import Annotated
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.models.models import User
from app.services.auth_service import get_current_active_user
from app.services.ws_service import ConnectionManager, get_connection_manager


router = APIRouter(tags=["ws_connect"])

@router.websocket("/ws/orders/{restaurant_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    restaurant_id: int,
    manager: ConnectionManager = Depends(get_connection_manager)
):
    """
    WebSocket endpoint for real-time order updates
    Each client connects with their restaurant_id
    """
    await manager.connect(websocket, restaurant_id)
    
    try:
        while True:
            # Keep connection alive and listen for client messages
            data = await websocket.receive_text()
            
            # Optional: Handle client messages (like heartbeat, acknowledgments)
            try:
                message = json.loads(data)
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print(f"Client disconnected from restaurant {restaurant_id}")