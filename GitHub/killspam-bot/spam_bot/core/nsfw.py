"""Local NSFW image check via NudeNet (ONNX, CPU, MIT-licensed).

No cloud Vision call here: an ambiguous result returns None so the caller can
ask a human admin instead. ponytail: tune thresholds/classes against real data.
"""
import logging

_detector = None

# NudeNet v3 classes that signal explicit nudity.
_EXPOSED = (
    "FEMALE_BREAST_EXPOSED", "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED", "BUTTOCKS_EXPOSED", "ANUS_EXPOSED",
)
_HIGH = 0.6  # >= this on an exposed class -> explicit
_LOW = 0.4   # < this -> clean; between -> ambiguous (admin review)


def _get():
    global _detector
    if _detector is None:
        from nudenet import NudeDetector
        _detector = NudeDetector()  # lazy: only pay the load if a photo is checked
    return _detector


def check(image_bytes: bytes):
    """True = explicit, False = clean, None = ambiguous / check failed."""
    try:
        dets = _get().detect(image_bytes)
    except Exception as e:
        logging.error(f"NudeNet check failed: {e}")
        return None
    score = max((d["score"] for d in dets if d["class"] in _EXPOSED), default=0.0)
    if score >= _HIGH:
        return True
    if score < _LOW:
        return False
    return None
