from ultralytics import YOLO

def main():
    model = YOLO("yolov8n.pt")

    model.train(
        data="pothole_data-1/data.yaml",
        epochs=25,
        imgsz=640,
        batch=16,
        device=0,
        name="pothawk_v1"
    )

if __name__ == "__main__":
    main()
