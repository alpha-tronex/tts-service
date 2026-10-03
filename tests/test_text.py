from app.text import MAX_CHUNK_CHARS, clean, split_for_speech


def test_clean_collapses_whitespace_and_keeps_the_words():
    assert clean("  Na nga   def?\n\tMaa ngi fi.  ") == "Na nga def? Maa ngi fi."


def test_clean_composes_accents_so_the_tokenizer_sees_one_character():
    assert clean("é") == "é"


def test_blank_text_has_nothing_to_say():
    assert split_for_speech("   ") == []


def test_splits_into_sentences_in_order():
    assert split_for_speech("I ni ce. I ka kɛnɛ wa? Tɔɔrɔ tɛ!") == ["I ni ce.", "I ka kɛnɛ wa?", "Tɔɔrɔ tɛ!"]


def test_a_short_phrase_is_one_chunk():
    assert split_for_speech("Jërëjëf") == ["Jërëjëf"]


def test_a_long_sentence_is_broken_between_words_under_the_limit():
    sentence = " ".join(["jàngalekat"] * 60)

    chunks = split_for_speech(sentence)

    assert len(chunks) > 1
    assert all(len(c) <= MAX_CHUNK_CHARS for c in chunks)
    assert " ".join(chunks) == sentence


def test_prefers_breaking_after_a_comma():
    first = "a" * 120 + ","
    chunks = split_for_speech(f"{first} " + "b " * 60)

    assert chunks[0] == first


def test_one_giant_word_is_still_cut_to_the_limit():
    chunks = split_for_speech("x" * (MAX_CHUNK_CHARS * 2 + 5))

    assert [len(c) for c in chunks] == [MAX_CHUNK_CHARS, MAX_CHUNK_CHARS, 5]
