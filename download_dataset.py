from roboflow import Roboflow

rf = Roboflow(api_key="XFld89ta8gdEZiA8eoLk")
project = rf.workspace("adarsh-maurya-pompz").project("pothole_data-tjba5-svldu")
version = project.version(1)
dataset = version.download("yolov8")