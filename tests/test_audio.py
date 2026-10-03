import numpy as np

from app.audio import PAUSE_SECONDS, encode_mp3, join, to_pcm16


def test_join_puts_a_pause_between_sentences_but_not_at_the_ends():
    a = np.ones(100, dtype=np.float32)
    b = np.ones(50, dtype=np.float32)

    joined = join([a, b], sample_rate=1000)

    pause = int(1000 * PAUSE_SECONDS)
    assert len(joined) == 100 + pause + 50
    assert joined[0] == 1 and joined[-1] == 1
    assert not joined[100 : 100 + pause].any()


def test_join_of_nothing_is_empty():
    assert join([], 16000).size == 0


def test_pcm_is_16_bit_little_endian():
    pcm = to_pcm16(np.array([0.0, 1.0, -1.0], dtype=np.float32))

    assert np.frombuffer(pcm, dtype="<i2").tolist() == [0, 32767, -32767]


def test_loud_output_is_scaled_down_instead_of_clipping():
    pcm = np.frombuffer(to_pcm16(np.array([2.0, -4.0], dtype=np.float32)), dtype="<i2")

    assert pcm.tolist() == [16383, -32767]


def test_nan_from_a_model_becomes_silence_not_a_crash():
    pcm = np.frombuffer(to_pcm16(np.array([np.nan, 0.5], dtype=np.float32)), dtype="<i2")

    assert pcm[0] == 0


def test_encodes_a_real_mp3():
    second_of_tone = np.sin(np.linspace(0, 2 * np.pi * 220, 16000)).astype(np.float32)

    mp3 = encode_mp3(second_of_tone, 16000)

    assert len(mp3) > 1000
    # MP3 frame sync: 11 set bits.
    assert mp3[0] == 0xFF and mp3[1] & 0xE0 == 0xE0
