"""
فلترة أساسية للمحتوى النصي بدردشة الموقع (Watch Party).
نفس منطق ملف moderation.py الموجود بمجلد البوت، لكن نسخة مستقلة
لأن هذا المشروع يُنشر بشكل منفصل (سيرفر ثاني).
"""

import re

_FLAGGED_WORDS = {
    "porn", "pornhub", "xvideos", "xnxx", "nude", "naked", "sex video",
    "onlyfans",
    "سكس", "بورن", "اباحي", "إباحي", "اباحية", "إباحية", "عاري", "عارية",
    "نيك", "منيوك", "طيز", "كس", "زب", "قحبة", "شرموطة", "خنيث",
}


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return text


def contains_flagged_content(text: str) -> bool:
    if not text:
        return False
    normalized = _normalize(text)
    words = set(normalized.split())
    for flagged in _FLAGGED_WORDS:
        if " " in flagged:
            if flagged in normalized:
                return True
        elif flagged in words:
            return True
    return False
