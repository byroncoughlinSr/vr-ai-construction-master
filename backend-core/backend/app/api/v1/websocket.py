from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import HTMLResponse
import json
import asyncio
import logging
from typing import Dict, List, Set, Any
from datetime import datetime

from ...database import get_db
from sqlalchemy.orm import Session

router = APIRouter()
logger = logging.getLogger(__name__)

# Connection management
class ConnectionManager:
    """Manages WebSocket connections for real-time collaboration."""

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}  # room_id -> list of connections
        self.user_rooms: Dict[WebSocket, str] = {}  # connection -> room_id

    async def connect(self, websocket: WebSocket, room_id: str, user_id: str = None):
        """Connect a user to a room."""
        await websocket.accept()

        if room_id not in self.active_connections:
            self.active_connections[room_id] = []

        self.active_connections[room_id].append(websocket)
        self.user_rooms[websocket] = room_id

        # Notify others in the room
        await self.broadcast_to_room(
            room_id,
            {
                "type": "user_joined",
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat(),
                "message": f"User {user_id or 'Anonymous'} joined the room"
            },
            exclude=websocket
        )

        logger.info(f"User {user_id} connected to room {room_id}")

    async def disconnect(self, websocket: WebSocket, user_id: str = None):
        """Disconnect a user from their room."""
        room_id = self.user_rooms.get(websocket)

        if room_id and websocket in self.active_connections.get(room_id, []):
            self.active_connections[room_id].remove(websocket)

            # Clean up empty rooms
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]

            # Notify others in the room
            await self.broadcast_to_room(
                room_id,
                {
                    "type": "user_left",
                    "user_id": user_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "message": f"User {user_id or 'Anonymous'} left the room"
                }
            )

        if websocket in self.user_rooms:
            del self.user_rooms[websocket]

        logger.info(f"User {user_id} disconnected from room {room_id}")

    async def broadcast_to_room(self, room_id: str, message: dict, exclude: WebSocket = None):
        """Broadcast a message to all users in a room."""
        if room_id not in self.active_connections:
            return

        disconnected = []
        for connection in self.active_connections[room_id]:
            if connection == exclude:
                continue

            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send message to connection: {e}")
                disconnected.append(connection)

        # Clean up disconnected connections
        for connection in disconnected:
            await self.disconnect(connection)

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send a message to a specific user."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send personal message: {e}")
            await self.disconnect(websocket)

# Global connection manager
manager = ConnectionManager()

# Image generation progress tracking
image_generation_progress: Dict[str, Dict[str, Any]] = {}  # generation_id -> progress data
image_generation_completed: Dict[str, Dict[str, Any]] = {}  # generation_id -> completed result
progress_connections: Dict[str, List[WebSocket]] = {}  # generation_id -> list of connections


@router.websocket("/room/{room_id}")
async def room_websocket(
    websocket: WebSocket,
    room_id: str,
    user_id: str = None,
    token: str = None  # For authentication
):
    """
    WebSocket endpoint for real-time collaboration in project rooms.

    Supports real-time design updates, chat, and collaborative editing.
    """
    try:
        # Basic authentication check (extend this for production)
        if not user_id:
            await websocket.close(code=4001, reason="User ID required")
            return

        await manager.connect(websocket, room_id, user_id)

        while True:
            try:
                # Receive message from client
                data = await websocket.receive_json()

                # Process different message types
                message_type = data.get("type", "unknown")

                if message_type == "design_update":
                    # Broadcast design changes to all users in room
                    await manager.broadcast_to_room(
                        room_id,
                        {
                            "type": "design_update",
                            "user_id": user_id,
                            "timestamp": datetime.utcnow().isoformat(),
                            "data": data.get("data", {}),
                            "element_id": data.get("element_id"),
                            "action": data.get("action", "update")  # create, update, delete
                        },
                        exclude=websocket
                    )

                elif message_type == "cursor_position":
                    # Share cursor positions for collaborative editing
                    await manager.broadcast_to_room(
                        room_id,
                        {
                            "type": "cursor_update",
                            "user_id": user_id,
                            "timestamp": datetime.utcnow().isoformat(),
                            "position": data.get("position", {}),
                            "element_id": data.get("element_id")
                        },
                        exclude=websocket
                    )

                elif message_type == "chat_message":
                    # Handle chat messages
                    await manager.broadcast_to_room(
                        room_id,
                        {
                            "type": "chat_message",
                            "user_id": user_id,
                            "timestamp": datetime.utcnow().isoformat(),
                            "message": data.get("message", ""),
                            "message_type": data.get("message_type", "text")
                        }
                    )

                elif message_type == "ping":
                    # Respond to ping with pong
                    await manager.send_personal_message(
                        {
                            "type": "pong",
                            "timestamp": datetime.utcnow().isoformat()
                        },
                        websocket
                    )

                else:
                    # Unknown message type
                    await manager.send_personal_message(
                        {
                            "type": "error",
                            "message": f"Unknown message type: {message_type}",
                            "timestamp": datetime.utcnow().isoformat()
                        },
                        websocket
                    )

            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                await manager.send_personal_message(
                    {
                        "type": "error",
                        "message": "Invalid JSON format",
                        "timestamp": datetime.utcnow().isoformat()
                    },
                    websocket
                )
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await manager.send_personal_message(
                    {
                        "type": "error",
                        "message": "Internal server error",
                        "timestamp": datetime.utcnow().isoformat()
                    },
                    websocket
                )

    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    finally:
        await manager.disconnect(websocket, user_id)


@router.get("/room/{room_id}/status")
async def get_room_status(room_id: str):
    """Get the current status of a collaboration room."""
    connection_count = len(manager.active_connections.get(room_id, []))
    return {
        "room_id": room_id,
        "active_connections": connection_count,
        "status": "active" if connection_count > 0 else "empty",
        "last_activity": datetime.utcnow().isoformat()
    }


@router.get("/status")
async def get_websocket_status():
    """Get overall WebSocket service status."""
    total_rooms = len(manager.active_connections)
    total_connections = sum(len(connections) for connections in manager.active_connections.values())

    return {
        "service": "WebSocket Collaboration",
        "status": "healthy",
        "total_rooms": total_rooms,
        "total_connections": total_connections,
        "active_rooms": list(manager.active_connections.keys()),
        "features": [
            "real-time design collaboration",
            "cursor position sharing",
            "chat messaging",
            "live updates"
        ]
    }


# HTML page for testing WebSocket connections (development only)
@router.get("/test/{room_id}", response_class=HTMLResponse)
async def websocket_test_page(room_id: str):
    """Simple HTML page for testing WebSocket connections."""
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>WebSocket Test - Room {room_id}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            #messages {{ border: 1px solid #ccc; height: 300px; overflow-y: scroll; padding: 10px; margin: 10px 0; }}
            input[type="text"] {{ width: 300px; padding: 5px; }}
            button {{ padding: 5px 10px; margin: 5px; }}
        </style>
    </head>
    <body>
        <h1>WebSocket Test - Room {room_id}</h1>
        <div id="status">Connecting...</div>
        <div id="messages"></div>
        <input type="text" id="messageInput" placeholder="Enter message">
        <button onclick="sendMessage()">Send Message</button>
        <button onclick="sendDesignUpdate()">Send Design Update</button>

        <script>
            const ws = new WebSocket('ws://localhost:8000/api/v1/ws/room/{room_id}?user_id=test_user');
            const messages = document.getElementById('messages');
            const status = document.getElementById('status');

            ws.onopen = function(event) {{
                status.textContent = 'Connected to room {room_id}';
                addMessage('Connected to WebSocket');
            }};

            ws.onmessage = function(event) {{
                const data = JSON.parse(event.data);
                addMessage('Received: ' + JSON.stringify(data, null, 2));
            }};

            ws.onclose = function(event) {{
                status.textContent = 'Disconnected';
                addMessage('Disconnected from WebSocket');
            }};

            ws.onerror = function(error) {{
                status.textContent = 'Error: ' + error;
                addMessage('WebSocket error: ' + error);
            }};

            function addMessage(message) {{
                const div = document.createElement('div');
                div.textContent = new Date().toLocaleTimeString() + ' - ' + message;
                messages.appendChild(div);
                messages.scrollTop = messages.scrollHeight;
            }}

            function sendMessage() {{
                const input = document.getElementById('messageInput');
                if (input.value) {{
                    ws.send(JSON.stringify({{
                        type: 'chat_message',
                        message: input.value
                    }}));
                    input.value = '';
                }}
            }}

            function sendDesignUpdate() {{
                ws.send(JSON.stringify({{
                    type: 'design_update',
                    action: 'update',
                    element_id: 'wall_001',
                    data: {{
                        position: {{ x: 10, y: 0, z: 5 }},
                        dimensions: {{ width: 8, height: 3, depth: 0.2 }}
                    }}
                }}));
            }}

            // Enter key support
            document.getElementById('messageInput').addEventListener('keypress', function(e) {{
                if (e.key === 'Enter') {{
                    sendMessage();
                }}
            }});
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.get("/image-progress/test/{generation_id}", response_class=HTMLResponse)
async def image_progress_test_page(generation_id: str):
    """Simple HTML page for testing image generation progress WebSocket."""
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Image Generation Progress Test - {generation_id}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            #messages {{ border: 1px solid #ccc; height: 300px; overflow-y: scroll; padding: 10px; margin: 10px 0; }}
            #progressBar {{ width: 100%; height: 20px; background-color: #f0f0f0; border: 1px solid #ccc; margin: 10px 0; }}
            #progressFill {{ height: 100%; background-color: #4CAF50; width: 0%; transition: width 0.3s; }}
            #percentage {{ text-align: center; margin-top: 5px; }}
            button {{ padding: 10px 15px; margin: 5px; cursor: pointer; }}
            .status {{ padding: 10px; margin: 10px 0; border-radius: 5px; }}
            .status.generating {{ background-color: #e3f2fd; border: 1px solid #2196F3; }}
            .status.completed {{ background-color: #e8f5e8; border: 1px solid #4CAF50; }}
            .status.failed {{ background-color: #ffebee; border: 1px solid #f44336; }}
        </style>
    </head>
    <body>
        <h1>Image Generation Progress Test</h1>
        <p><strong>Generation ID:</strong> {generation_id}</p>

        <div id="status" class="status">Connecting to progress WebSocket...</div>

        <div>
            <strong>Progress:</strong>
            <div id="progressBar">
                <div id="progressFill"></div>
            </div>
            <div id="percentage">0%</div>
        </div>

        <div>
            <button onclick="startGeneration()">Start Image Generation</button>
            <button onclick="clearMessages()">Clear Messages</button>
        </div>

        <div id="messages"></div>

        <script>
            let ws = null;
            const messages = document.getElementById('messages');
            const status = document.getElementById('status');
            const progressBar = document.getElementById('progressFill');
            const percentage = document.getElementById('percentage');
            let currentGenerationId = '{generation_id}';

            function connectWebSocket(genId) {{
                // Close existing connection if any
                if (ws) {{
                    ws.close();
                }}

                currentGenerationId = genId;
                ws = new WebSocket(`ws://localhost:8000/api/v1/ws/image-progress/${{genId}}`);

                ws.onopen = function(event) {{
                    status.textContent = `Connected to progress WebSocket for ${{genId}}`;
                    status.className = 'status';
                    addMessage(`✅ Connected to WebSocket for generation ${{genId}}`);
                }};

                ws.onmessage = function(event) {{
                    const data = JSON.parse(event.data);
                    addMessage('Received: ' + JSON.stringify(data, null, 2));

                    if (data.type === 'progress') {{
                        updateProgress(data.step, data.total_steps, data.percentage);
                        status.textContent = `Generating image... Step ${{data.step}}/${{data.total_steps}} (${{data.percentage}}%)`;
                        status.className = 'status generating';
                    }} else if (data.type === 'completed') {{
                        updateProgress(data.result.metadata.steps, data.result.metadata.steps, 100);
                        status.textContent = 'Image generation completed!';
                        status.className = 'status completed';
                        if (data.result.images && data.result.images[0]) {{
                            addMessage(`✅ Image available at: ${{data.result.images[0].image_url}}`);
                        }}
                    }} else if (data.type === 'error') {{
                        status.textContent = `Generation failed: ${{data.error}}`;
                        status.className = 'status failed';
                    }}
                }};

                ws.onclose = function(event) {{
                    status.textContent = 'WebSocket disconnected';
                    addMessage('Disconnected from WebSocket');
                }};

                ws.onerror = function(error) {{
                    status.textContent = 'WebSocket error';
                    status.className = 'status failed';
                    addMessage('❌ WebSocket error: ' + error);
                }};
            }}

            // Connect to initial generation ID from URL
            connectWebSocket(currentGenerationId);

            function updateProgress(step, totalSteps, percent) {{
                progressBar.style.width = percent + '%';
                percentage.textContent = percent + '%';
            }}

            function addMessage(message) {{
                const div = document.createElement('div');
                div.textContent = new Date().toLocaleTimeString() + ' - ' + message;
                messages.appendChild(div);
                messages.scrollTop = messages.scrollHeight;
            }}

            function clearMessages() {{
                messages.innerHTML = '';
            }}

            async function startGeneration() {{
                try {{
                    addMessage('🚀 Starting image generation...');
                    
                    const response = await fetch('/api/v1/image/generate', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json'
                        }},
                        body: JSON.stringify({{
                            prompt: 'modern kitchen with island',
                            width: 512,
                            height: 512,
                            num_inference_steps: 10,
                            guidance_scale: 7.5
                        }})
                    }});

                    if (response.ok) {{
                        const result = await response.json();
                        addMessage('✅ Generation started with ID: ' + result.generation_id);
                        
                        // Auto-connect to the new generation's WebSocket
                        addMessage('🔌 Reconnecting to new generation WebSocket...');
                        connectWebSocket(result.generation_id);
                    }} else {{
                        const errorText = await response.text();
                        addMessage('❌ Failed to start generation: ' + response.status + ' - ' + errorText);
                    }}
                }} catch (error) {{
                    addMessage('❌ Error starting generation: ' + error.message);
                }}
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.websocket("/image-progress/{generation_id}")
async def image_progress_websocket(websocket: WebSocket, generation_id: str):
    """
    WebSocket endpoint for real-time image generation progress updates.

    Clients connect to this endpoint using the generation_id returned by the image generation API.
    """
    await websocket.accept()

    # Add connection to progress tracking
    if generation_id not in progress_connections:
        progress_connections[generation_id] = []
    progress_connections[generation_id].append(websocket)

    # Send connection confirmation immediately
    try:
        await websocket.send_json({
            "type": "connected",
            "generation_id": generation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Connected to progress WebSocket"
        })
    except Exception as e:
        logger.error(f"Failed to send connection confirmation: {e}")

    # If generation already completed before client connected, send result immediately and close
    if generation_id in image_generation_completed:
        logger.info(f"Generation {generation_id} already completed — sending result to late client")
        try:
            await websocket.send_json({
                "type": "completed",
                **image_generation_completed[generation_id]
            })
        except Exception as e:
            logger.error(f"Failed to send late-connect completion: {e}")
        finally:
            if generation_id in progress_connections and websocket in progress_connections[generation_id]:
                progress_connections[generation_id].remove(websocket)
            await websocket.close()
        return

    # Send current progress if generation is still in progress
    if generation_id in image_generation_progress:
        try:
            await websocket.send_json({
                "type": "progress",
                **image_generation_progress[generation_id]
            })
        except Exception as e:
            logger.error(f"Failed to send initial progress: {e}")

    logger.info(f"Client connected to image progress WebSocket for generation {generation_id}")

    try:
        while True:
            # Keep connection alive and wait for client messages (ping/pong) with timeout
            try:
                # Wait for message with 30 second timeout
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                # Send ping if no message received
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error in WebSocket loop: {e}")
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Clean up connection
        if generation_id in progress_connections and websocket in progress_connections[generation_id]:
            progress_connections[generation_id].remove(websocket)
            if not progress_connections[generation_id]:
                del progress_connections[generation_id]
        logger.info(f"Client disconnected from image progress WebSocket for generation {generation_id}")


async def send_image_progress_update(generation_id: str, progress_data: Dict[str, Any]):
    """
    Send progress update to all clients connected to a specific generation.
    """
    if generation_id not in progress_connections:
        return

    # Update stored progress
    image_generation_progress[generation_id] = progress_data

    # Send to all connected clients
    disconnected = []
    for websocket in progress_connections[generation_id]:
        try:
            await websocket.send_json({
                "type": "progress",
                **progress_data
            })
        except Exception as e:
            logger.error(f"Failed to send progress update: {e}")
            disconnected.append(websocket)

    # Clean up disconnected clients
    for websocket in disconnected:
        if websocket in progress_connections[generation_id]:
            progress_connections[generation_id].remove(websocket)


async def complete_image_generation(generation_id: str, result: Dict[str, Any]):
    """
    Mark image generation as complete and send final result to clients.
    Stores the result so late-connecting clients can still receive it.
    """
    completion_data = {
        "generation_id": generation_id,
        "status": "completed",
        "result": result,
        "timestamp": datetime.utcnow().isoformat()
    }

    # Persist result for any clients that connect after completion
    image_generation_completed[generation_id] = completion_data

    # Send to any already-connected clients
    if generation_id in progress_connections:
        disconnected = []
        for websocket in progress_connections[generation_id]:
            try:
                await websocket.send_json({
                    "type": "completed",
                    **completion_data
                })
            except Exception as e:
                logger.error(f"Failed to send completion message: {e}")
                disconnected.append(websocket)

        for websocket in disconnected:
            if websocket in progress_connections[generation_id]:
                progress_connections[generation_id].remove(websocket)

    # Clean up in-progress tracking
    if generation_id in image_generation_progress:
        del image_generation_progress[generation_id]


async def fail_image_generation(generation_id: str, error: str):
    """
    Mark image generation as failed and send error to clients.
    """
    if generation_id in progress_connections:
        error_data = {
            "generation_id": generation_id,
            "status": "failed",
            "error": error,
            "timestamp": datetime.utcnow().isoformat()
        }

        for websocket in progress_connections[generation_id]:
            try:
                await websocket.send_json({
                    "type": "error",
                    **error_data
                })
            except Exception as e:
                logger.error(f"Failed to send error message: {e}")

        # Clean up progress data on failure
        if generation_id in image_generation_progress:
            del image_generation_progress[generation_id]


@router.get("/image-progress/{generation_id}/status")
async def get_image_generation_status(generation_id: str):
    """Get the current status of an image generation."""
    if generation_id in image_generation_progress:
        return {
            "generation_id": generation_id,
            "status": "in_progress",
            "progress": image_generation_progress[generation_id],
            "connections": len(progress_connections.get(generation_id, []))
        }
    else:
        return {
            "generation_id": generation_id,
            "status": "not_found",
            "message": "Generation not found or completed"
        }
