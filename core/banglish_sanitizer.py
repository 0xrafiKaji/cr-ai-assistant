import re

BENGALI_WORD_MAP = {
    "উপস্থিত": "uposthit",
    "অনুরোধ": "onurodh",
    "অনুরোধে": "onurodhe",
    "নোটিশ": "notice",
    "পরীক্ষা": "exam",
    "ক্লাস": "class",
    "ছুটি": "chuti",
    "রুটিন": "routine",
    "বিশ্ববিদ্যালয়": "university",
    "বিভাগ": "department",
    "শিক্ষক": "teacher",
    "তারিখ": "date",
    "সময়": "time",
    "রুম": "room",
    "বিষয়": "subject",
    "জরুরী": "urgent",
    "সকল": "shokol",
    "ছাত্র": "student",
    "ছাত্রী": "student",
    "ছাত্রছাত্রী": "students",
    "শিক্ষার্থী": "students",
    "শিক্ষার্থীরা": "students",
    "সবাই": "sobai",
    "সবাইকে": "sobaike",
    "জানাচ্ছে": "janacche",
    "জানানো": "janano",
    "যাচ্ছে": "jacche",
    "হচ্ছে": "hocche",
    "হবে": "hobe",
    "আছে": "ache",
    "ধন্যবাদ": "dhonnobad",
    "ফিস": "fees",
    "ফি": "fee",
    "কার্ড": "card",
    "এডমিট": "admit",
    "সেকশন": "section",
    "ব্যাচ": "batch",
    "শনিবার": "Saturday",
    "রবিবার": "Sunday",
    "সোমবার": "Monday",
    "মঙ্গলবার": "Tuesday",
    "বুধবার": "Wednesday",
    "বৃহস্পতিবার": "Thursday",
    "শুক্রবার": "Friday",
}

BENGALI_CHAR_MAP = {
    'অ': 'o', 'আ': 'a', 'ই': 'i', 'ঈ': 'i', 'উ': 'u', 'ঊ': 'u', 'ঋ': 'ri',
    'এ': 'e', 'ঐ': 'oi', 'ও': 'o', 'ঔ': 'ou',
    'ক': 'k', 'খ': 'kh', 'গ': 'g', 'ঘ': 'gh', 'ঙ': 'ng',
    'চ': 'ch', 'ছ': 'chh', 'জ': 'j', 'ঝ': 'jh', 'ঞ': 'n',
    'ট': 't', 'ঠ': 'th', 'ড': 'd', 'ঢ': 'dh', 'ণ': 'n',
    'ত': 't', 'থ': 'th', 'দ': 'd', 'ধ': 'dh', 'ন': 'n',
    'প': 'p', 'ফ': 'f', 'ব': 'b', 'ভ': 'bh', 'ম': 'm',
    'য': 'z', 'র': 'r', 'ল': 'l', 'শ': 'sh', 'ষ': 'sh', 'স': 's', 'হ': 'h',
    'ড়': 'r', 'ঢ়': 'rh', 'য়': 'y', 'ৎ': 't',
    'ং': 'ng', 'ঃ': 'h', 'ঁ': 'n',
    'া': 'a', 'ি': 'i', 'ী': 'i', 'ু': 'u', 'ূ': 'u', 'ৃ': 'ri',
    'ে': 'e', 'ৈ': 'oi', 'ো': 'o', 'ৌ': 'ou', '্': '',
    '০': '0', '১': '1', '২': '2', '৩': '3', '৪': '4',
    '৫': '5', '৬': '6', '৭': '7', '৮': '8', '৯': '9',
    '।': '.'
}

def sanitize_to_banglish(text: str) -> str:
    """
    Guarantees zero Bengali Unicode characters in output text.
    Transliterates any accidental Bengali Unicode words or letters into clean Banglish.
    Protects Linux terminals from font glitching / broken square boxes.
    """
    if not text or not any('\u0980' <= c <= '\u09FF' for c in text):
        return text

    # 1. Whole word replacements
    for bn, en in BENGALI_WORD_MAP.items():
        text = text.replace(bn, en)

    # 2. Character-level phonetic transliteration for any remaining Unicode characters
    res = []
    for c in text:
        if '\u0980' <= c <= '\u09FF':
            res.append(BENGALI_CHAR_MAP.get(c, ''))
        else:
            res.append(c)

    cleaned = ''.join(res)
    # Remove repeated spaces if any
    cleaned = re.sub(r' +', ' ', cleaned)
    return cleaned
