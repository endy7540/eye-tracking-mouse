# -*- coding: utf-8 -*-
"""
hangul.py — 화상 키보드용 한글 조합기 (두벌식) + 자동완성용 자모 분해

Qt와 무관한 순수 파이썬 파일이라 화면 없이도 테스트할 수 있습니다.

키보드는 사용자가 누른 키를 "자모 한 글자씩" 리스트로만 저장하고(예: ㄷ ㅏ ㄹ ㄱ),
화면에 보여줄 때마다 compose_jamo()로 처음부터 다시 조합합니다(→ "닭").
이렇게 하면 지우기(⌫)는 "마지막 자모 하나 빼기"만 하면 되고(→ ㄷ ㅏ ㄹ = "달"),
조합 상태를 따로 관리하다 꼬이는 문제가 생기지 않습니다.
"""

CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"                 # 초성 19개 (유니코드 순서)
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"             # 중성 21개
JONG = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ",
        "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]   # 종성 28개(없음 포함)

# 모음 두 개가 합쳐지는 경우 (ㅗ+ㅏ=ㅘ 등)
VOWEL_COMB = {("ㅗ", "ㅏ"): "ㅘ", ("ㅗ", "ㅐ"): "ㅙ", ("ㅗ", "ㅣ"): "ㅚ", ("ㅜ", "ㅓ"): "ㅝ",
              ("ㅜ", "ㅔ"): "ㅞ", ("ㅜ", "ㅣ"): "ㅟ", ("ㅡ", "ㅣ"): "ㅢ"}
# 받침 두 개가 합쳐지는 경우 (ㄹ+ㄱ=ㄺ 등)
JONG_COMB = {("ㄱ", "ㅅ"): "ㄳ", ("ㄴ", "ㅈ"): "ㄵ", ("ㄴ", "ㅎ"): "ㄶ", ("ㄹ", "ㄱ"): "ㄺ",
             ("ㄹ", "ㅁ"): "ㄻ", ("ㄹ", "ㅂ"): "ㄼ", ("ㄹ", "ㅅ"): "ㄽ", ("ㄹ", "ㅌ"): "ㄾ",
             ("ㄹ", "ㅍ"): "ㄿ", ("ㄹ", "ㅎ"): "ㅀ", ("ㅂ", "ㅅ"): "ㅄ"}
VOWEL_SPLIT = {v: k for k, v in VOWEL_COMB.items()}
JONG_SPLIT = {v: k for k, v in JONG_COMB.items()}


def is_consonant(ch):
    return ch in CHO


def is_vowel(ch):
    return ch in JUNG


def is_jamo(ch):
    return is_consonant(ch) or is_vowel(ch)


def _syllable(cho, jung, jong):
    """초성/중성/종성 → 완성형 한 글자. 일부만 있으면 그 자모를 그대로 반환."""
    if cho and jung:
        return chr(0xAC00 + (CHO.index(cho) * 21 + JUNG.index(jung)) * 28 + JONG.index(jong or ""))
    return cho or jung or ""


def compose_jamo(keys):
    """두벌식 자모 입력 순서 → 조합된 문자열. 예: ['ㄷ','ㅏ','ㄹ','ㄱ','ㅇ','ㅣ'] → '닭이'"""
    out = []
    cho = jung = jong = None

    def flush():
        nonlocal cho, jung, jong
        if cho or jung:
            out.append(_syllable(cho, jung, jong))
        cho = jung = jong = None

    for k in keys:
        if is_consonant(k):
            if cho and jung:                                  # 받침 자리
                if jong is None:
                    if k in JONG:                             # ㄸ ㅃ ㅉ은 받침이 될 수 없음
                        jong = k
                    else:
                        flush()
                        cho = k
                else:
                    comb = JONG_COMB.get((jong, k))
                    if comb:
                        jong = comb
                    else:
                        flush()
                        cho = k
            else:                                             # 새 글자의 초성으로 시작
                flush()
                cho = k
        elif is_vowel(k):
            if jong:                                          # 받침이 다음 글자 초성으로 넘어감 (갑+ㅣ → 가비)
                if jong in JONG_SPLIT:
                    first, second = JONG_SPLIT[jong]
                    jong = first
                    flush()
                    cho = second
                else:
                    moved = jong
                    jong = None
                    flush()
                    cho = moved
                jung = k
            elif jung:
                comb = VOWEL_COMB.get((jung, k))
                if comb:
                    jung = comb
                else:
                    flush()
                    jung = k
            else:
                jung = k                                      # 초성 뒤 중성 (또는 모음 단독 시작)
        else:
            flush()
            out.append(k)                                     # 한글이 아닌 글자는 그대로
    flush()
    return "".join(out)


def to_keystrokes(text):
    """완성된 글자 → 그 글자를 두벌식으로 칠 때의 자모 순서. 자동완성 비교/입력에 사용.
    예: '닭' → ['ㄷ','ㅏ','ㄹ','ㄱ'],  '과' → ['ㄱ','ㅗ','ㅏ']"""
    keys = []
    for ch in text:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            cho, rest = divmod(code, 21 * 28)
            jung, jong = divmod(rest, 28)
            keys.append(CHO[cho])
            keys.extend(VOWEL_SPLIT.get(JUNG[jung], (JUNG[jung],)))
            if jong:
                keys.extend(JONG_SPLIT.get(JONG[jong], (JONG[jong],)))
        elif ch in VOWEL_SPLIT:
            keys.extend(VOWEL_SPLIT[ch])
        elif ch in JONG_SPLIT:
            keys.extend(JONG_SPLIT[ch])
        else:
            keys.append(ch)
    return keys
