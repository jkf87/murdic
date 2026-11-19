"""User-facing error text: never empty, always names the exception type."""


def describe(error, prefix=""):
    """`prefix: message (ExceptionType)`; falls back to the type when the message is empty
    (e.g. a bare AssertionError from a library)."""
    kind = type(error).__name__
    text = str(error).strip()
    if text and getattr(error, "user_facing", False):
        pass   # murdic's own errors already carry the cause and its type
    elif text and kind not in text:
        text = f"{text} ({kind})"
    elif not text:
        text = kind
    return f"{prefix}: {text}" if prefix else text
