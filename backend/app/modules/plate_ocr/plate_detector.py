"""CPU plate detector used when classical localization yields no reliable read."""
import os
from pathlib import Path

MODEL = "yolo-v9-t-640-license-plate-end2end"


def load_plate_detector():
    from onnxruntime import SessionOptions
    from open_image_models import create_detector
    from open_image_models.detection.core.hub import download_model

    cache_root = os.getenv("EASYOCR_MODULE_PATH") or os.getenv("MODULE_PATH")
    root = Path(cache_root) if cache_root else Path.home() / ".EasyOCR"
    weights = download_model(MODEL, save_directory=root / "plate-detector")
    options = SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    return create_detector(
        weights, backend="yolo_v9", class_labels=["License Plate"], conf_thresh=0.35,
        providers=["CPUExecutionProvider"], sess_options=options,
    )
