from ultralytics import YOLO

# Apna trained model load karo
model = YOLO("runs/detect/pothawk_v1-3/weights/best.pt")

# Validation images pe test karo
results = model("pothole_data-1/valid/images", save=True)

print("Done! Results saved in runs/detect/predict folder")