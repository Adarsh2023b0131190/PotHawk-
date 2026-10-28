import asyncio
import io
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime

import firebase_admin
import torch
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from firebase_admin import credentials, firestore
from groq import Groq
from PIL import Image, UnidentifiedImageError
from ultralytics import YOLO

try:
    import psutil
except ImportError:  # Optional; inference does not depend on psutil.
    psutil = None

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("pothawk")

MODEL_PATH = "runs/detect/pothawk_v1-3/weights/best.pt"
DEFAULT_IMAGE_SIZE = 416
DEFAULT_TORCH_THREADS = 2
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def read_positive_int_setting(name, default, *, minimum=1, maximum=None):
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} must be an integer; received {raw_value!r}") from exc
    if value < minimum or (maximum is not None and value > maximum):
        bounds = f"at least {minimum}" if maximum is None else f"between {minimum} and {maximum}"
        raise RuntimeError(f"{name} must be {bounds}; received {value}")
    return value


try:
    INFERENCE_SIZE = read_positive_int_setting(
        "POTHAWK_IMAGE_SIZE", DEFAULT_IMAGE_SIZE, minimum=320, maximum=1280
    )
    if INFERENCE_SIZE % 32 != 0:
        raise RuntimeError("POTHAWK_IMAGE_SIZE must be a multiple of 32 (320 through 1280)")
    TORCH_THREADS = read_positive_int_setting(
        "POTHAWK_TORCH_THREADS", DEFAULT_TORCH_THREADS, maximum=16
    )
except RuntimeError:
    logger.exception("Invalid PotHawk inference configuration")
    raise

model = None
db = None
groq_client = None
firebase_app = None
inference_lock = asyncio.Lock()


def process_rss_mb():
    if psutil is None:
        return None
    try:
        return round(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 1)
    except Exception:
        logger.exception("Unable to read process RSS")
        return None


def initialize_firebase():
    key_json = os.getenv("FIREBASE_KEY_JSON")
    if key_json:
        try:
            certificate = credentials.Certificate(json.loads(key_json))
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            raise RuntimeError("FIREBASE_KEY_JSON is present but is not a valid Firebase service account") from exc
    else:
        credential_path = "firebase-key.json"
        if not os.path.isfile(credential_path):
            raise RuntimeError(
                "Firebase credentials are missing: set FIREBASE_KEY_JSON or provide firebase-key.json"
            )
        certificate = credentials.Certificate(credential_path)

    try:
        app_instance = firebase_admin.get_app()
    except ValueError:
        app_instance = firebase_admin.initialize_app(certificate)
    return app_instance, firestore.client(app=app_instance)


def calculate_priority(box, image_width, image_height, confidence):
    x1, y1, x2, y2 = box
    box_area = (x2 - x1) * (y2 - y1)
    image_area = image_width * image_height
    area_ratio = box_area / image_area
    size_score = min(area_ratio * 50, 10)
    confidence_score = confidence * 10
    final_score = (size_score * 0.6) + (confidence_score * 0.4)
    return round(min(final_score, 10), 1)


def detect_potholes(image):
    started = time.perf_counter()
    try:
        if model is None:
            raise RuntimeError("YOLO model is not initialized; FastAPI lifespan startup did not complete")
        logger.info("report stage=yolo_predict start imgsz=%d device=cpu", INFERENCE_SIZE)
        results = model.predict(
            source=image,
            imgsz=INFERENCE_SIZE,
            device="cpu",
            verbose=False,
        )
        logger.info("report stage=yolo_predict returned seconds=%.3f", time.perf_counter() - started)
    except Exception:
        logger.exception("report stage=prediction failed seconds=%.3f rss_mb=%s", time.perf_counter() - started, process_rss_mb())
        raise

    prediction_seconds = time.perf_counter() - started
    model_timings = results[0].speed if results else {}
    postprocess_started = time.perf_counter()
    detections = []
    for result in results:
        img_h, img_w = result.orig_shape
        for box in result.boxes:
            xyxy = box.xyxy[0].tolist()
            confidence = box.conf[0].item()
            priority = calculate_priority(xyxy, img_w, img_h, confidence)
            detections.append({"confidence": round(confidence, 2), "priority": priority})
    postprocess_seconds = time.perf_counter() - postprocess_started
    logger.info(
        "report stage=prediction seconds=%.3f preprocess_ms=%.1f inference_ms=%.1f nms_postprocess_ms=%.1f detections=%d imgsz=%d; stage=box_postprocess seconds=%.3f rss_mb=%s",
        prediction_seconds,
        model_timings.get("preprocess", 0),
        model_timings.get("inference", 0),
        model_timings.get("postprocess", 0),
        len(detections),
        INFERENCE_SIZE,
        postprocess_seconds,
        process_rss_mb(),
    )
    return detections


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global model, db, groq_client, firebase_app

    torch.set_num_threads(TORCH_THREADS)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        # A dependency may have initialized the Torch interop pool already.
        pass

    startup_started = time.perf_counter()
    try:
        try:
            firebase_app, db = initialize_firebase()
        except Exception:
            logger.exception("Firebase initialization failed; check FIREBASE_KEY_JSON or firebase-key.json")
            raise

        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            logger.error("Groq initialization failed: GROQ_API_KEY is not configured")
            raise RuntimeError("Groq configuration is missing: set GROQ_API_KEY")
        try:
            groq_client = Groq(api_key=groq_api_key)
        except Exception:
            logger.exception("Groq client initialization failed")
            raise

        try:
            model = YOLO(MODEL_PATH)
        except Exception:
            logger.exception("YOLO model load failed path=%s", MODEL_PATH)
            raise

        logger.info(
            "PotHawk startup complete model=%s device=cpu precision=float32 imgsz=%d torch_threads=%d startup_seconds=%.3f rss_mb=%s",
            MODEL_PATH,
            INFERENCE_SIZE,
            TORCH_THREADS,
            time.perf_counter() - startup_started,
            process_rss_mb(),
        )
        yield
    finally:
        if groq_client is not None:
            try:
                close_client = getattr(groq_client, "close", None)
                if close_client is not None:
                    await run_in_threadpool(close_client)
            except Exception:
                logger.exception("Groq client cleanup failed")
            groq_client = None
        if db is not None:
            try:
                close_database = getattr(db, "close", None)
                if close_database is not None:
                    await run_in_threadpool(close_database)
            except Exception:
                logger.exception("Firestore client cleanup failed")
            db = None
        if firebase_app is not None:
            try:
                firebase_admin.delete_app(firebase_app)
            except Exception:
                logger.exception("Firebase app cleanup failed")
            firebase_app = None
        model = None
        logger.info("PotHawk resources cleaned up rss_mb=%s", process_rss_mb())


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"message": "PotHawk API is running"}


@app.post("/report")
async def create_report(
    file: UploadFile = File(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
):
    request_started = time.perf_counter()
    try:
        stage_started = time.perf_counter()
        image_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
        read_seconds = time.perf_counter() - stage_started
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Uploaded image is empty")
        if len(image_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Uploaded image exceeds the 20 MB limit")

        stage_started = time.perf_counter()
        try:
            with Image.open(io.BytesIO(image_bytes)) as uploaded_image:
                uploaded_image.load()
                image = uploaded_image.convert("RGB")
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            logger.warning("report stage=image_decode failed seconds=%.3f", time.perf_counter() - stage_started)
            raise HTTPException(status_code=415, detail="Uploaded file is not a supported image") from exc
        decode_seconds = time.perf_counter() - stage_started
        logger.info(
            "report stage=upload_decode bytes=%d read_seconds=%.3f decode_seconds=%.3f image_size=%s",
            len(image_bytes), read_seconds, decode_seconds, image.size
        )

        lock_started = time.perf_counter()
        logger.info("report stage=inference_lock waiting elapsed_seconds=%.3f", lock_started - request_started)
        async with inference_lock:
            logger.info(
                "report stage=inference_lock acquired lock_wait_seconds=%.3f",
                time.perf_counter() - lock_started,
            )
            prediction_started = time.perf_counter()
            detections = await run_in_threadpool(detect_potholes, image)
            inference_seconds = time.perf_counter() - prediction_started

        max_priority = max((detection["priority"] for detection in detections), default=0)
        report_data = {
            "filename": file.filename,
            "latitude": latitude,
            "longitude": longitude,
            "detections_count": len(detections),
            "detections": detections,
            "priority": max_priority,
            "status": "pending",
            "assigned_worker": None,
            "created_at": datetime.utcnow().isoformat(),
        }

        firestore_started = time.perf_counter()
        try:
            doc_ref = await run_in_threadpool(lambda: db.collection("reports").add(report_data))
        except Exception:
            logger.exception("report stage=firestore_write failed seconds=%.3f", time.perf_counter() - firestore_started)
            raise
        firestore_seconds = time.perf_counter() - firestore_started
        logger.info(
            "report stage=firestore_write saved seconds=%.3f report_id=%s",
            firestore_seconds,
            doc_ref[1].id,
        )
        logger.info(
            "report complete inference_seconds=%.3f firestore_write_seconds=%.3f total_seconds=%.3f rss_mb=%s",
            inference_seconds, firestore_seconds, time.perf_counter() - request_started, process_rss_mb()
        )
        return {"report_id": doc_ref[1].id, **report_data}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("report failed total_seconds=%.3f rss_mb=%s", time.perf_counter() - request_started, process_rss_mb())
        raise HTTPException(status_code=503, detail="Report processing is temporarily unavailable") from exc
    finally:
        await file.close()


@app.post("/query")
async def natural_language_query(question: str = Form(...)):
    request_started = time.perf_counter()
    try:
        firestore_started = time.perf_counter()
        try:
            all_reports = await run_in_threadpool(
                lambda: [doc.to_dict() | {"id": doc.id} for doc in db.collection("reports").stream()]
            )
        except Exception:
            logger.exception("query stage=firestore_read failed seconds=%.3f", time.perf_counter() - firestore_started)
            raise
        firestore_seconds = time.perf_counter() - firestore_started

        prompt = f"""
        You are a helpful assistant for a municipality dashboard.
        Here is the list of pothole reports (JSON): {all_reports}

        User question: {question}

        Answer clearly and concisely based only on the data above.
        """

        groq_started = time.perf_counter()
        try:
            response = await run_in_threadpool(
                lambda: groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                )
            )
        except Exception:
            logger.exception("query stage=groq_request failed seconds=%.3f", time.perf_counter() - groq_started)
            raise
        groq_seconds = time.perf_counter() - groq_started
        logger.info(
            "query complete reports=%d firestore_read_seconds=%.3f groq_seconds=%.3f total_seconds=%.3f rss_mb=%s",
            len(all_reports), firestore_seconds, groq_seconds, time.perf_counter() - request_started, process_rss_mb()
        )
        return {"answer": response.choices[0].message.content}
    except Exception as exc:
        logger.exception("query failed total_seconds=%.3f rss_mb=%s", time.perf_counter() - request_started, process_rss_mb())
        raise HTTPException(status_code=503, detail="Query service is temporarily unavailable") from exc
