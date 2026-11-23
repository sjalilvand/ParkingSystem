from types import SimpleNamespace

import numpy as np
import pytest

from app.modules.plate_ocr import engine


@pytest.fixture
def reader(monkeypatch):
    instance = engine.PlateReader()
    caps = engine.capabilities()
    monkeypatch.setattr(engine, "capabilities", lambda *_: {**caps, "hezar": True, "onnx_plate_detector": False})
    monkeypatch.setattr(instance, "_get_crnn", lambda: None)
    monkeypatch.setattr(instance, "_detect", lambda _: [((65, 35, 215, 70), None)])
    return instance


def test_persian_plate_includes_province_from_wider_crop(reader, monkeypatch):
    def read(crop):
        if crop.shape[1] <= 150:
            return "۱۳ب۱۱۱", 0.98
        return "۱۳ب۱۱۱۱۰", 0.93

    monkeypatch.setattr(reader, "_get_persian", lambda: SimpleNamespace(read=read))

    def unexpected_fallback(*args, **kwargs):
        pytest.fail("The complete Hezar result should skip the EasyOCR fallback")

    monkeypatch.setattr(reader, "_ocr_crop", unexpected_fallback)
    image = np.full((120, 300, 3), 210, dtype=np.uint8)
    result = reader.read_image(image, want_annotated=False)
    assert result["best"]["system"] == "13B111IR10"
    assert result["best"]["confidence"] == 0.93
    assert result["engine"]["ocr"] == "hezar"


@pytest.mark.parametrize("text, confidence", [("13ب111", 0.99), ("13ب11110", 0.65)])
def test_uncertain_persian_read_falls_back(reader, monkeypatch, text, confidence):
    monkeypatch.setattr(
        reader, "_get_persian", lambda: SimpleNamespace(read=lambda _: (text, confidence))
    )
    monkeypatch.setattr(reader, "_ocr_crop", lambda *_: [("22س34511", 0.85, "easyocr")])
    monkeypatch.setattr(reader, "_province_candidates", lambda *_: [])
    image = np.full((120, 300, 3), 210, dtype=np.uint8)
    result = reader.read_image(image, want_annotated=False)
    assert result["best"]["raw"] == "22س34511"
    assert result["engine"]["ocr"] == "easyocr"


def test_learned_detector_recovers_tilted_plate(reader, monkeypatch):
    caps = engine.capabilities()
    monkeypatch.setattr(engine, "capabilities", lambda *_: {
        **caps, "hezar": True, "onnx_plate_detector": True,
    })
    monkeypatch.setattr(reader, "_detect", lambda _: [])
    monkeypatch.setattr(reader, "_detect_plate_boxes", lambda _: [(10, 10, 110, 70)])
    monkeypatch.setattr(engine, "warp_plate", lambda _: np.zeros((20, 80, 3), dtype=np.uint8))

    def read(crop):
        return ("۱۳ب۱۱۱۱۰", 0.93) if not crop.any() else ("۱۳ب۱۱۱", 0.98)

    monkeypatch.setattr(reader, "_get_persian", lambda: SimpleNamespace(read=read))
    image = np.full((120, 300, 3), 210, dtype=np.uint8)
    result = reader.read_image(image, want_annotated=False)
    assert result["best"]["system"] == "13B111IR10"
    assert result["best"]["method"] == "onnx-yolov9+hezar"
    assert result["engine"]["detector"] == "onnx-yolov9"


def test_wide_crop_retries_with_border(reader, monkeypatch):
    def read(crop):
        return ("۱۳ب۱۱۱۱۰", 0.94) if crop.shape[1] > 300 else ("۱۳ب۱۱۱", 0.98)

    monkeypatch.setattr(reader, "_get_persian", lambda: SimpleNamespace(read=read))
    image = np.full((60, 300, 3), 210, dtype=np.uint8)
    result = reader.read_image(image, want_annotated=False)
    assert result["best"]["system"] == "13B111IR10"
    assert result["best"]["box"] == [0, 0, 300, 60]
