"""
سيرفر بسيط لمزامنة مشاهدة فيديوهات يوتيوب بين عدة مستخدمين (Watch Party)
يستخدم نفس أكواد الغرف اللي يستخدمها بوت تيليغرام (مجلد telegram_group_bot)
"""

import time
from typing import Dict, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()

# حالة كل غرفة: الفيديو الحالي، هل شغال أو لأ، والوقت الحالي بالثواني
room_state: Dict[str, dict] = {}
room_clients: Dict[str, Set[WebSocket]] = {}


@app.get("/")
async def index():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")


async def broadcast(room_code: str, message: dict, exclude: WebSocket = None):
    clients = room_clients.get(room_code, set())
    dead = []
    for ws in clients:
        if ws is exclude:
            continue
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


@app.websocket("/ws/{room_code}")
async def websocket_endpoint(websocket: WebSocket, room_code: str):
    await websocket.accept()
    room_clients.setdefault(room_code, set()).add(websocket)

    # لو فيه فيديو محمّل مسبقاً بهذي الغرفة، نرسل حالته للمستخدم الجديد
    if room_code in room_state:
        state = room_state[room_code]
        current_time = state["current_time"]
        if state["is_playing"]:
            current_time += time.time() - state["updated_at"]
        await websocket.send_json({
            "type": "sync",
            "video_id": state["video_id"],
            "is_playing": state["is_playing"],
            "current_time": current_time,
        })

    await broadcast(room_code, {
        "type": "viewers",
        "count": len(room_clients[room_code]),
    })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "load_video":
                room_state[room_code] = {
                    "video_id": data["video_id"],
                    "is_playing": True,
                    "current_time": 0,
                    "updated_at": time.time(),
                }
                await broadcast(room_code, {
                    "type": "load_video",
                    "video_id": data["video_id"],
                })

            elif msg_type in ("play", "pause", "seek"):
                if room_code in room_state:
                    state = room_state[room_code]
                    state["current_time"] = data.get("current_time", state["current_time"])
                    state["is_playing"] = (msg_type != "pause")
                    state["updated_at"] = time.time()

                await broadcast(
                    room_code,
                    {"type": msg_type, "current_time": data.get("current_time", 0)},
                    exclude=websocket,
                )

    except WebSocketDisconnect:
        room_clients.get(room_code, set()).discard(websocket)
        await broadcast(room_code, {
            "type": "viewers",
            "count": len(room_clients.get(room_code, set())),
        })
