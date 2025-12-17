from datetime import datetime
from typing import Dict, List, Optional

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # Key = restaurant_id, Value = list of WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # Track which restaurant each websocket belongs to (for cleanup)
        self.websocket_to_restaurant: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, restaurant_id: str, user_id: Optional[str] = None):
        """Connect a client to a specific restaurant's room"""
        await websocket.accept()
        
        # Create restaurant room if it doesn't exist
        if restaurant_id not in self.active_connections:
            self.active_connections[restaurant_id] = []
        
        # Add connection to the restaurant's room
        self.active_connections[restaurant_id].append(websocket)
        self.websocket_to_restaurant[websocket] = restaurant_id
        
        print(f"Client connected to restaurant {restaurant_id}. Total connections: {len(self.active_connections[restaurant_id])}")
        
        # Send confirmation message
        await websocket.send_json({
            "type": "connection_established",
            "restaurant_id": restaurant_id,
            "message": f"Connected to restaurant {restaurant_id}",
            "timestamp": datetime.now().isoformat()
        })

    def disconnect(self, websocket: WebSocket):
        """Remove a client connection"""
        restaurant_id = self.websocket_to_restaurant.get(websocket)
        
        if restaurant_id and restaurant_id in self.active_connections:
            if websocket in self.active_connections[restaurant_id]:
                self.active_connections[restaurant_id].remove(websocket)
                print(f"Client disconnected from restaurant {restaurant_id}. Remaining: {len(self.active_connections[restaurant_id])}")
            
            # Clean up empty restaurant rooms
            if len(self.active_connections[restaurant_id]) == 0:
                del self.active_connections[restaurant_id]
        
        if websocket in self.websocket_to_restaurant:
            del self.websocket_to_restaurant[websocket]

    async def broadcast_to_restaurant(self, restaurant_id: str, message: dict):
        """Send message to ALL clients connected to a specific restaurant"""
        if restaurant_id not in self.active_connections:
            print(f"No active connections for restaurant {restaurant_id}")
            return
        
        # Get all connections for this restaurant
        connections = self.active_connections[restaurant_id].copy()
        disconnected = []
        
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"Error sending to client: {e}")
                disconnected.append(connection)
        
        # Clean up dead connections
        for connection in disconnected:
            self.disconnect(connection)

    async def send_to_specific_client(self, websocket: WebSocket, message: dict):
        """Send message to a specific client"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            print(f"Error sending to specific client: {e}")
            self.disconnect(websocket)

    def get_restaurant_connection_count(self, restaurant_id: str) -> int:
        """Get number of active connections for a restaurant"""
        return len(self.active_connections.get(restaurant_id, []))

    def get_all_active_restaurants(self) -> List[str]:
        """Get list of all restaurants with active connections"""
        return list(self.active_connections.keys())
    
manager = ConnectionManager()

def get_connection_manager() -> ConnectionManager:
    """Dependency that returns the ConnectionManager singleton"""
    return manager