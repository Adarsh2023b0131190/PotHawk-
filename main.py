from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from ultralytics import YOLO
from PIL import Image
import io
import json
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Firebase connect karo (local file ya environment variable dono se kaam kare)
firebase_key_json = os.getenv("FIREBASE_KEY_JSON")
if firebase_key_json:
    cred = credentials.Certificate(json.loads(firebase_key_json))
else:
    cred = credentials.Certificate("firebase-key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# YOLO model load karo
model = YOLO("runs/detect/pothawk_v1-3/weights/best.pt")
model.half()


def calculate_priority(box, image_width, image_height, confidence):
    x1, y1, x2, y2 = box
    box_area = (x2 - x1) * (y2 - y1)
    image_area = image_width * image_height
    area_ratio = box_area / image_area
    size_score = min(area_ratio * 50, 10)
    confidence_score = confidence * 10
    final_score = (size_score * 0.6) + (confidence_score * 0.4)
    return round(min(final_score, 10), 1)


@app.get("/")
def home():
    return {"message": "PotHawk API is running"}


@app.post("/report")
async def create_report(
    file: UploadFile = File(...),
    latitude: float = Form(...),
    longitude: float = Form(...)
):
    image_bytes = await file.read()
    image = Image.open(io.BytesIO(image_bytes))

    results = model(image,imgsz=320)

    detections = []
    for result in results:
        img_h, img_w = result.orig_shape
        for box in result.boxes:
            xyxy = box.xyxy[0].tolist()
            confidence = box.conf[0].item()
            priority = calculate_priority(xyxy, img_w, img_h, confidence)
            detections.append({
                "confidence": round(confidence, 2),
                "priority": priority
            })

    max_priority = max([d["priority"] for d in detections], default=0)

    report_data = {
        "filename": file.filename,
        "latitude": latitude,
        "longitude": longitude,
        "detections_count": len(detections),
        "detections": detections,
        "priority": max_priority,
        "status": "pending",
        "assigned_worker": None,
        "created_at": datetime.utcnow().isoformat()
    }

    doc_ref = db.collection("reports").add(report_data)

    return {
        "report_id": doc_ref[1].id,
        **report_data
    }


@app.post("/query")
async def natural_language_query(question: str = Form(...)):
    all_reports = [doc.to_dict() | {"id": doc.id} for doc in db.collection("reports").stream()]

    prompt = f"""
    You are a helpful assistant for a municipality dashboard. 
    Here is the list of pothole reports (JSON): {all_reports}

    User question: {question}

    Answer clearly and concisely based only on the data above.
    """

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )

    return {"answer": response.choices[0].message.content}