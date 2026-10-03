"""Joining model output and encoding it as MP3."""
import lameenc
import numpy as np

PAUSE_SECONDS = 0.25
MP3_BITRATE_KBPS = 48  # plenty for 16 kHz mono speech; keeps responses small


def join(chunks: list[np.ndarray], sample_rate: int, pause_seconds: float = PAUSE_SECONDS) -> np.ndarray:
    """Concatenates chunks with a short pause between sentences."""
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    pause = np.zeros(int(sample_rate * pause_seconds), dtype=np.float32)
    pieces: list[np.ndarray] = []
    for i, chunk in enumerate(chunks):
        if i:
            pieces.append(pause)
        pieces.append(np.asarray(chunk, dtype=np.float32).reshape(-1))
    return np.concatenate(pieces)


def to_pcm16(samples: np.ndarray) -> bytes:
    """Float samples in [-1, 1] to 16-bit PCM, scaled down only if they would clip."""
    samples = np.nan_to_num(np.asarray(samples, dtype=np.float32).reshape(-1))
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak > 1.0:
        samples = samples / peak
    return (samples * 32767.0).astype("<i2").tobytes()


def encode_mp3(samples: np.ndarray, sample_rate: int) -> bytes:
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(MP3_BITRATE_KBPS)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(1)
    encoder.set_quality(5)
    encoder.silence()
    return bytes(encoder.encode(to_pcm16(samples)) + encoder.flush())
