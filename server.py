"""
سيرفر مزامنة مشاهدة يوتيوب + دردشة نصية + صور + رسائل صوتية بين عدة مستخدمين
يستخدم نفس أكواد الغرف اللي يستخدمها بوت تيليغرام (مجلد telegram_group_bot)
"""

import time
import uuid
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()

# حالة كل غرفة: الفيديو الحالي، هل شغال أو لأ، والوقت الحالي بالثواني
room_state: Dict[str, dict] = {}

# كل عميل متصل له معرّف فريد (client_id) داخل كل غرفة
room_clients: Dict[str, Dict[str, WebSocket]] = {}

# حدود تقريبية لحجم الملفات المرسلة بالدردشة (بايتات بعد ترميز base64)
MAX_IMAGE_SIZE = 3_500_000
MAX_VOICE_SIZE = 5_000_000


@app.get("/")
async def index():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")


async def broadcast(room_code: str, message: dict, exclude_id: str = None):
    clients = room_clients.get(room_code, {})
    dead = []
    for client_id, ws in clients.items():
        if client_id == exclude_id:
            continue
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(client_id)
    for client_id in dead:
        clients.pop(client_id, None)


@app.websocket("/ws/{room_code}")
async def websocket_endpoint(websocket: WebSocket, room_code: str):
    await websocket.accept()

    client_id = str(uuid.uuid4())
    room_clients.setdefault(room_code, {})[client_id] = websocket

    await websocket.send_json({"type": "welcome", "client_id": client_id})

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

            # --- مزامنة الفيديو ---
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
                    exclude_id=client_id,
                )

            # --- الدردشة النصية ---
            elif msg_type == "chat":
                await broadcast(room_code, {
                    "type": "chat",
                    "name": str(data.get("name", "مستخدم"))[:40],
                    "text": str(data.get("text", ""))[:2000],
                })

            # --- إرسال صورة/لقطة شاشة ---
            elif msg_type == "image":
                image_data = data.get("data", "")
                if len(image_data) > MAX_IMAGE_SIZE:
                    await websocket.send_json({
                        "type": "error", "message": "الصورة كبيرة جداً، جرب صورة أصغر.",
                    })
                else:
                    await broadcast(room_code, {
                        "type": "image",
                        "name": str(data.get("name", "مستخدم"))[:40],
                        "data": image_data,
                    })

            # --- إرسال رسالة صوتية ---
            elif msg_type == "voice":
                voice_data = data.get("data", "")
                if len(voice_data) > MAX_VOICE_SIZE:
                    await websocket.send_json({
                        "type": "error",
                        "message": "الرسالة الصوتية طويلة جداً، سجّل مقطع أقصر.",
                    })
                else:
                    await broadcast(room_code, {
                        "type": "voice",
                        "name": str(data.get("name", "مستخدم"))[:40],
                        "data": voice_data,
                    })

    except WebSocketDisconnect:
        room_clients.get(room_code, {}).pop(client_id, None)
        await broadcast(room_code, {
            "type": "viewers",
            "count": len(room_clients.get(room_code, {})),
        })
