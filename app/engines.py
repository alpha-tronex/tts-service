"""The voice models. torch/transformers are imported lazily so the web layer
and its tests run without them."""
import os
from typing import Protocol

import numpy as np

# One model per language, chosen in v2 Week 9 (see README "Models").
DEFAULT_MODELS = {
    "wo": "bilalfaye/speecht5_tts-wolof-v0.2",  # SpeechT5, MIT
    "bm": "facebook/mms-tts-bam",  # VITS (Meta MMS), CC-BY-NC 4.0
}
SPEECHT5_VOCODER = "microsoft/speecht5_hifigan"
SPEAKER_DATASET = "Matthijs/cmu-arctic-xvectors"
SPEAKER_INDEX = 7306  # the voice the Wolof model card uses


class Engine(Protocol):
    sample_rate: int

    def synthesize(self, text: str) -> np.ndarray:
        """One chunk of text to mono float samples in [-1, 1]."""
        ...


class VitsEngine:
    """Meta MMS-TTS (VITS). Small and fast on CPU."""

    def __init__(self, model_id: str):
        import torch
        from transformers import AutoTokenizer, VitsModel

        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(model_id)
        self._model = VitsModel.from_pretrained(model_id).eval()
        self.sample_rate = int(self._model.config.sampling_rate)

    def synthesize(self, text: str) -> np.ndarray:
        torch = self._torch
        inputs = self._tokenizer(text, return_tensors="pt")
        if inputs["input_ids"].shape[-1] == 0:
            return np.zeros(0, dtype=np.float32)
        torch.manual_seed(0)  # VITS is stochastic; same text, same audio
        with torch.no_grad():
            waveform = self._model(**inputs).waveform
        return waveform.squeeze().cpu().numpy().astype(np.float32)


class SpeechT5Engine:
    """SpeechT5 fine-tuned for Wolof, with the HiFi-GAN vocoder."""

    def __init__(self, model_id: str):
        import torch
        from transformers import SpeechT5ForTextToSpeech, SpeechT5HifiGan, SpeechT5Processor

        self._torch = torch
        self._processor = SpeechT5Processor.from_pretrained(model_id)
        self._model = SpeechT5ForTextToSpeech.from_pretrained(model_id).eval()
        self._vocoder = SpeechT5HifiGan.from_pretrained(SPEECHT5_VOCODER).eval()
        self._speaker = load_speaker_embedding(torch)
        self.sample_rate = 16000

    def synthesize(self, text: str) -> np.ndarray:
        torch = self._torch
        inputs = self._processor(
            text=text,
            return_tensors="pt",
            truncation=True,
            max_length=self._model.config.max_text_positions,
        )
        with torch.no_grad():
            speech = self._model.generate_speech(inputs["input_ids"], self._speaker, vocoder=self._vocoder)
        return speech.cpu().numpy().astype(np.float32)


def load_speaker_embedding(torch):
    """The x-vector that gives SpeechT5 its voice. Cached on disk after the
    first download so restarts don't need the dataset again."""
    cache = os.path.join(os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface")), "speaker.npy")
    if os.path.exists(cache):
        return torch.tensor(np.load(cache)).unsqueeze(0)

    vector = _download_speaker_vector()
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    np.save(cache, vector)
    return torch.tensor(vector).unsqueeze(0)


def _download_speaker_vector() -> np.ndarray:
    """Tries the dataset loader first, then the dataset's Parquet export
    (newer `datasets` releases no longer run dataset loading scripts)."""
    try:
        from datasets import load_dataset

        dataset = load_dataset(SPEAKER_DATASET, split="validation", trust_remote_code=True)
        return np.asarray(dataset[SPEAKER_INDEX]["xvector"], dtype=np.float32)
    except Exception:
        import pyarrow.parquet as pq
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(
            SPEAKER_DATASET,
            "default/validation/0000.parquet",
            repo_type="dataset",
            revision="refs/convert/parquet",
        )
        column = pq.read_table(path, columns=["xvector"]).column("xvector")
        return np.asarray(column[SPEAKER_INDEX].as_py(), dtype=np.float32)


def load_engines() -> dict[str, Engine]:
    """Loads both models once, at startup. Model IDs can be overridden with
    TTS_MODEL_WO / TTS_MODEL_BM to try another checkpoint of the same family."""
    import torch

    torch.set_num_threads(int(os.environ.get("TTS_THREADS", "2")))
    return {
        "wo": SpeechT5Engine(os.environ.get("TTS_MODEL_WO", DEFAULT_MODELS["wo"])),
        "bm": VitsEngine(os.environ.get("TTS_MODEL_BM", DEFAULT_MODELS["bm"])),
    }
