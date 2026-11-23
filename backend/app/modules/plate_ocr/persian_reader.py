"""Optional CRNN recognizer trained specifically on cropped Iranian plates."""
from itertools import groupby
import os
from pathlib import Path

MODEL_ID = "hezarai/crnn-fa-license-plate-recognition-v2"
MODEL_REVISION = "8f629aec2b5fb091e034317cb472dadd29640289"
MODEL_FILES = ["model.pt", "model_config.yaml", "preprocessor/image_processor_config.yaml"]


class PersianPlateRecognizer:
    def __init__(self):
        from hezar.models import Model
        from huggingface_hub import snapshot_download
        from huggingface_hub.errors import LocalEntryNotFoundError

        # Share the existing persistent model cache used by the Docker installation.
        cache_root = (os.getenv("EASYOCR_MODULE_PATH") or os.getenv("MODULE_PATH")
                      or str(Path.home() / ".EasyOCR"))
        download_options = dict(
            revision=MODEL_REVISION,
            allow_patterns=MODEL_FILES,
            cache_dir=str(Path(cache_root) / "hezar"),
            token=False,
        )
        try:
            model_path = Path(snapshot_download(MODEL_ID, local_files_only=True, **download_options))
            if not all((model_path / filename).is_file() for filename in MODEL_FILES):
                raise LocalEntryNotFoundError("Incomplete Persian OCR model cache")
        except LocalEntryNotFoundError:
            model_path = Path(snapshot_download(MODEL_ID, **download_options))
        self.model = Model.load(str(model_path), load_locally=True, device="cpu").eval()

    def read(self, crop) -> tuple[str, float]:
        import torch
        from hezar.utils import reverse_string_digits

        with torch.inference_mode():
            inputs = self.model.preprocess(crop)
            log_probs = self.model(**inputs)["logits"][:, 0]
            values, labels = log_probs.exp().max(dim=1)

        # Collapse CTC repeats before dropping blanks so adjacent identical
        # digits separated by a blank survive. Blank scores do not count.
        chars = []
        scores = []
        for label, run in groupby(zip(labels.tolist(), values.tolist()), key=lambda item: item[0]):
            if label == self.model.config.blank_id:
                continue
            char = self.model.config.id2label[label]
            chars.append(char)
            if char.strip():
                scores.append(max(score for _, score in run))

        text = "".join(chars)
        if self.model.config.reverse_output_digits:
            text = reverse_string_digits(text)
        return text, min(scores, default=0.0)
