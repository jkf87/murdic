"""Conservative local editing of a single dictated utterance."""
import re

FILLER = re.compile(r"(?<!\w)(?:어+|으?음+|아+)(?!\w)[\s,，.…]*")
REPEAT = re.compile(r"(?<!\S)([^\s,.!?]+(?: [^\s,.!?]+){0,3}?)(?:[,，]? \1)+(?=[\s,.!?]|$)", re.I)
# Keep shared context in common slot corrections ("내일 세 시, 아니 네 시").
CLOCK = r"(?:[0-9]+|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열(?:한|두)?) ?시"
SLOTS = (
    r"[월화수목금토일]요일",
    rf"(?:오전|오후|저녁|아침) {CLOCK}",
    CLOCK,
)
CORRECTION = re.compile(r"(?<!\w)(?:아니[, ]+그게\s*아니라|그게\s*아니라|다시\s*말할게요)(?!\w)[\s,，.…]*")


def correct_restart(text):
    for slot in SLOTS:
        text = re.sub(rf"(?<!\w)(?:{slot})(?:에|로)?[,，]?\s+아니[,，]?\s+"
                      rf"(?:그게\s*아니라[,，]?\s+)?(?={slot})", "", text)
    parts = CORRECTION.split(text)
    kept = parts[0]
    for replacement in parts[1:]:
        if not replacement.strip():
            continue
        # Keep previous complete sentences. In the interrupted clause, keep a
        # leading topic when the speaker supplies only a replacement value.
        before = kept.rstrip(" ,，….!?")
        end = max(before.rfind(mark) for mark in ".!?")
        prefix, fragment = before[:end + 1], before[end + 1:].strip()
        topic = re.match(r"^(.{1,45}?(?:은|는))\s+\S", fragment)
        new_topic = re.match(r"^\S+(?:은|는)\s", replacement)
        kept = " ".join(x for x in (prefix, topic[1] if topic and not new_topic else "", replacement) if x)
    return kept


def clean(text):
    text = correct_restart(" ".join(text.split()))
    text = FILLER.sub("", text).strip(" ,，")
    text = re.sub(r"\s+([,.!?])", r"\1", text)
    text = re.sub(r"([,!?])(?=[가-힣A-Za-z])", r"\1 ", text)
    # Separate the bound noun 수 in common ability expressions.
    text = re.sub(r"([할갈볼될올줄쓸])\s*수\s*(있|없)", r"\1 수 \2", text)
    while True:
        reduced = REPEAT.sub(r"\1", text)
        if reduced == text:
            break
        text = reduced
    text = text.strip().rstrip(",，").strip()
    if not re.search(r"\w", text):
        return ""
    if text[-1].isalnum():
        text += "?" if re.search(r"(?:까요|습니까|인가요)$", text) else "."
    return text
