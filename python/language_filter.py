import re

CJK_PATTERN = re.compile(
    r'['
    r'\u4e00-\u9fff'
    r'\u3400-\u4dbf'
    r'\uf900-\ufaff'
    r'\u3040-\u309f'
    r'\u30a0-\u30ff'
    r'\uac00-\ud7af'
    r'\u3000-\u303f'
    r'\uff00-\uffef'
    r']'
)


def contains_cjk(text: str) -> bool:
    return bool(CJK_PATTERN.search(text))


def cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    cjk_count = len(CJK_PATTERN.findall(text))
    return cjk_count / max(len(text), 1)


def strip_cjk(text: str) -> str:
    cleaned = CJK_PATTERN.sub('', text)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    cleaned = re.sub(r'([،,.!؟?])\s*\1+', r'\1', cleaned)
    return cleaned.strip()


def clean_response(
    text: str,
    regenerate_fn=None,
    max_retries: int = 1,
    bad_ratio_threshold: float = 0.15,
) -> str:
    if not contains_cjk(text):
        return text

    ratio = cjk_ratio(text)

    if regenerate_fn is None:
        return strip_cjk(text)

    if ratio < bad_ratio_threshold:
        return strip_cjk(text)

    current = text
    for attempt in range(max_retries):
        current = regenerate_fn()
        if not contains_cjk(current):
            return current

    cleaned = strip_cjk(current)
    if len(cleaned) < 3:
        return "معلش، حصل خلل في الرد. جرب تسأل تاني."
    return cleaned


if __name__ == "__main__":
    def fake_ollama_call():
        return "Hello 你好 how are you today?"

    tests = [
        "Hello 你好 how are you today?",
        "，！ ，、AI，，。、，。？",
        "أهلاً، أنا بخير الحمد لله!",
    ]
    for t in tests:
        print("before:", t)
        print("after: ", clean_response(t, regenerate_fn=fake_ollama_call, max_retries=1))
        print("---")