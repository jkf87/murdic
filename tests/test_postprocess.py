from dictate.backend import filter_transcript


def test_drops_whisper_hallucinations_on_little_speech():
    assert filter_transcript("시청해 주셔서 감사합니다.", 1) == ""
    assert filter_transcript("감사합니다", 0) == ""
    assert filter_transcript("네 네 네 네", 5) == ""
    assert filter_transcript("ㅁ", 5) == ""


def test_keeps_real_thanks_when_speech_was_heard():
    assert filter_transcript("감사합니다.", 4) == "감사합니다."


def test_applies_murmur_term_corrections():
    assert filter_transcript("코덱스랑 클로드로 작업해요", 6) == "Codex랑 Claude로 작업해요"
