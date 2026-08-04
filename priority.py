from ultralytics import YOLO

def calculate_priority(box, image_width, image_height, confidence):
    x1, y1, x2, y2 = box
    box_area = (x2 - x1) * (y2 - y1)
    image_area = image_width * image_height
    area_ratio = box_area / image_area
    size_score = min(area_ratio * 50, 10)
    confidence_score = confidence * 10
    final_score = (size_score * 0.6) + (confidence_score * 0.4)
    return round(min(final_score, 10), 1)


def test_priority_on_image(image_path):
    model = YOLO("runs/detect/pothawk_v1-3/weights/best.pt")
    results = model(image_path)

    for result in results:
        img_h, img_w = result.orig_shape
        for box in result.boxes:
            xyxy = box.xyxy[0].tolist()
            confidence = box.conf[0].item()
            priority = calculate_priority(xyxy, img_w, img_h, confidence)
            print(f"Pothole detected — Confidence: {confidence:.2f}, Priority Score: {priority}/10")


if __name__ == "__main__":
    test_priority_on_image("pothole_data-1/valid/images/file-20221017-15-drdtr5_jpg.rf.1099dd810c11a756373f36d779021dd3.jpg")