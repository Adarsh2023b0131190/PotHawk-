from ultralytics import YOLO

# Ek chhota pretrained model load karo (pehli baar chalane pe auto-download hoga)
model = YOLO("yolov8n.pt")

# Ek sample image pe test karo
results = model("https://ultralytics.com/images/bus.jpg")

# Detection ka result screen pe dikhao
results[0].show()