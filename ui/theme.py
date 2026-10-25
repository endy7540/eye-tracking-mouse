# -*- coding: utf-8 -*-
"""
theme.py — 데모 전체가 같이 쓰는 폰트·색상·이미지 + 메뉴·아이콘·커서용 테마

폰트: fonts/ 폴더(하위 폴더 ttf/, otf/ 포함) 안의 폰트 파일을 프로그램 시작 때 직접 불러옵니다.
     → 발표용 컴퓨터에 폰트가 설치돼 있지 않아도 똑같이 보입니다.
     제목용  = 배민 주아체 (Jua)         : 파일·폰트 이름에 "jua" 또는 "주아"가 들어간 폰트
     메뉴용  = 나눔스퀘어라운드 (Bold 계열) : 이름에 "nanumsquareround" 또는 "나눔스퀘어라운드"
     폰트 파일이 없으면 맑은 고딕으로 대신 표시하고, 콘솔에 안내를 출력합니다.
     fonts/ 폴더에 다른 폰트가 많이 들어 있어도(배민 폰트 모음 등) 위 두 가지만 골라서 불러옵니다.
     (전부 불러오면 수십 MB라 프로그램 시작이 느려짐)

크기 단위: 모든 글자 크기는 "픽셀"(setPixelSize)로 지정합니다. 버튼 크기도 픽셀이라
          글자와 버튼 비율이 컴퓨터마다 달라지지 않습니다.

색상은 두 종류입니다.
    1) 기본 색 (BG, INK, PANEL_BG, HIGHLIGHT, RED ...)
       캘리브레이션(두더지) 화면·상태 확인 창이 쓰는 갈색 계열 색. 테마와 상관없이 항상 그대로입니다.
       ※ 다른 담당자 파일(calibration/mole_calibration.py 등)도 이 이름을 쓰므로 이름·값을 바꾸지 마세요.
    2) 테마 색 (THEMES, 8종: 하늘·민트·라벤더·노을·체리·슬레이트·화이트·다크)
       메뉴창·메뉴 아이콘·스크롤 토글·커서·화상 키보드에 적용되는 색. 메뉴창 "설정" 화면의 바둑알로 바꿀 수 있고,
       기본은 "하늘(파랑)". 테마마다 카드·글자·강조·그림자 색을 따로 가짐 (아래 THEMES 위 설명 참고).
       지금 테마는 current()로 읽고, set_theme("mint")처럼 바꿉니다.
"""
from pathlib import Path

from PyQt5 import QtGui

BASE_DIR = Path(__file__).resolve().parent
ASSET_DIR = BASE_DIR / "assets"
FONT_DIR = BASE_DIR / "fonts"

# ── 기본 색 (테마와 무관 — 두더지 화면·키보드·상태 확인 창) ───────────────
BG = QtGui.QColor(236, 217, 191)              # 캘리브레이션 배경 (연한 갈색)
INK = QtGui.QColor(74, 52, 40)                # 기본 글자색 (진한 갈색)
INK_SOFT = QtGui.QColor(120, 95, 78)          # 보조 글자색
PANEL_BG = QtGui.QColor(255, 249, 240, 218)   # 키보드·상태 확인 창 배경 (반투명)
PANEL_EDGE = QtGui.QColor(150, 115, 85, 170)
BTN_BG = QtGui.QColor(255, 255, 255, 215)     # 버튼 기본
BTN_ON = QtGui.QColor(255, 214, 160, 235)     # 켜져 있는 토글 버튼
BTN_EDGE = QtGui.QColor(150, 115, 85)
HIGHLIGHT = QtGui.QColor(242, 130, 40)        # 하이라이트(시선이 올라간 버튼) 테두리 — 주황
GAUGE = QtGui.QColor(242, 130, 40)            # 응시 게이지
RED = QtGui.QColor(224, 88, 80)
YELLOW = QtGui.QColor(248, 196, 60)
GREEN = QtGui.QColor(70, 180, 110)

# ── 테마 색 (메뉴창·메뉴 아이콘·스크롤 토글·커서·화상 키보드) ─────────────────
#   key: 설정 파일에 저장되는 이름 / name: 메뉴에 보이는 이름
#   테마마다 아래 색을 가짐 (theme.current()["card"]처럼 꺼내 씀, 색은 QColor)
#     main   대표색 (메뉴 아이콘 바탕)          deep   글자·아이콘 색
#     light  아이콘 뒤 동그라미 바탕            accent 켜짐 스위치·"윙크하면 선택" 표시·강조
#     on     accent 위 글자색                   main_ink  main 위 글자·아이콘(≡) 색
#     ring   하이라이트 테두리                  gauge  응시 게이지
#     card   카드 바탕                          chip   상태 알약·스크롤 토글(꺼짐) 바탕
#     panel  메뉴창·키보드 배경 (반투명)        border 카드 테두리      edge  메뉴창 테두리
#     off    꺼짐 스위치                        trail  시선 잔상
#     stone / stone_side  바둑알 윗면 / 옆면(두께)
#     shadow 그림자 세기 (화이트는 흰 바탕끼리 구별되게 진하게)   dark  다크 테마 여부
WHITE_ = (255, 255, 255)


def _color_theme(key, name, main, deep, light):
    """색깔 테마 (하늘·민트 …): 흰 카드 + 대표색."""
    return {"key": key, "name": name, "main": main, "deep": deep, "light": light,
            "accent": main, "on": WHITE_, "main_ink": WHITE_, "ring": deep, "gauge": main,
            "card": (255, 255, 255, 205), "chip": (255, 255, 255, 235), "panel": main + (77,),
            "border": main + (115,), "edge": main + (242,), "off": (160, 166, 176), "trail": main,
            "stone": main, "stone_side": deep, "shadow": 0.35, "dark": False}


THEMES = [
    _color_theme("sky", "하늘", (59, 142, 234), (24, 84, 168), (220, 235, 255)),
    _color_theme("mint", "민트", (32, 178, 150), (14, 112, 95), (214, 245, 237)),
    _color_theme("lavender", "라벤더", (138, 106, 228), (88, 60, 175), (236, 229, 255)),
    _color_theme("sunset", "노을", (238, 118, 88), (176, 68, 42), (255, 228, 218)),
    _color_theme("cherry", "체리", (226, 92, 146), (160, 40, 96), (255, 225, 238)),
    _color_theme("slate", "슬레이트", (96, 114, 140), (46, 60, 82), (226, 232, 241)),
    # 화이트: 흰 메뉴창·흰 카드 → 그림자를 진하게 해서 칸을 구별. 커서는 흰 바둑알
    {"key": "white", "name": "화이트", "main": (246, 247, 250), "deep": (40, 44, 54), "light": (236, 239, 244),
     "accent": (58, 64, 78), "on": WHITE_, "main_ink": (40, 44, 54), "ring": (58, 64, 78), "gauge": (58, 64, 78),
     "card": (255, 255, 255, 252), "chip": (255, 255, 255, 255), "panel": (250, 251, 253, 215),
     "border": (204, 209, 218, 255), "edge": (186, 192, 204, 255), "off": (170, 176, 186), "trail": (150, 156, 170),
     "stone": (246, 246, 246), "stone_side": (176, 180, 188), "shadow": 1.0, "dark": False},
    # 다크: 어두운 카드 + 밝은 글자. 커서는 검은 바둑알 (어두운 화면에서도 보이게 얇은 밝은 테두리)
    {"key": "black", "name": "다크", "main": (30, 32, 38), "deep": (236, 239, 245), "light": (58, 62, 74),
     "accent": (232, 235, 242), "on": (26, 28, 34), "main_ink": (236, 239, 245), "ring": (232, 235, 242),
     "gauge": (232, 235, 242), "card": (40, 43, 51, 240), "chip": (56, 60, 72, 255), "panel": (20, 22, 27, 205),
     "border": (78, 84, 98, 255), "edge": (92, 98, 114, 255), "off": (80, 86, 100), "trail": (120, 126, 140),
     "stone": (44, 46, 52), "stone_side": (8, 8, 10), "shadow": 0.6, "dark": True},
]
DEFAULT_THEME = "sky"
_THEME_BY_KEY = {t["key"]: t for t in THEMES}
_current_key = DEFAULT_THEME


def set_theme(key):
    """테마 바꾸기. 모르는 이름이면 기본(하늘)으로. 화면을 다시 그리는 건 부르는 쪽(main.py)이 함."""
    global _current_key
    _current_key = key if key in _THEME_BY_KEY else DEFAULT_THEME


def current_key():
    return _current_key


def current():
    """지금 테마의 색들 (QColor). 예: theme.current()["main"]"""
    return theme_colors(_current_key)


def theme_colors(key):
    """테마 key → 색 묶음 (색은 QColor, "shadow"는 숫자, "dark"는 참/거짓, "key"·"name"은 글자)."""
    t = _THEME_BY_KEY.get(key, _THEME_BY_KEY[DEFAULT_THEME])
    out = {}
    for k, v in t.items():
        out[k] = QtGui.QColor(*v) if isinstance(v, tuple) else v
    return out


def css(color, alpha=None):
    """QColor → 스타일시트 글자 "rgba(r, g, b, a)" (QLabel 글자색·배경색을 테마에 맞출 때 씀)."""
    a = color.alpha() if alpha is None else int(255 * max(0.0, min(1.0, alpha)))
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {a})"


def with_alpha(color, alpha):
    """색은 그대로, 투명도만 바꾼 새 QColor (alpha: 0.0 = 완전 투명 ~ 1.0 = 불투명)."""
    c = QtGui.QColor(color)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


# ── 폰트 ────────────────────────────────────────────────────────────────
FALLBACK_FAMILY = "Malgun Gothic"
TITLE_FAMILY = FALLBACK_FAMILY
UI_FAMILY = FALLBACK_FAMILY


def _ui_score(name):
    """나눔스퀘어라운드 중에서도 굵은 버전을 우선 고르기 위한 점수."""
    low = name.lower().replace(" ", "")
    if "nanumsquareround" not in low and "나눔스퀘어라운드" not in low:
        return 0
    if "extrabold" in low or low.endswith("eb"):
        return 3
    if "bold" in low or low.endswith("b"):
        return 2
    if "light" in low or low.endswith("l"):
        return 0.5
    return 1


def _wanted_font_files():
    """fonts/ 아래(하위 폴더 포함)에서 주아체·나눔스퀘어라운드 파일만 고름. 같은 이름이면 .ttf를 우선."""
    if not FONT_DIR.exists():
        return []
    picked = {}
    for f in sorted(FONT_DIR.rglob("*")):
        if f.suffix.lower() not in (".ttf", ".otf"):
            continue
        low = f.stem.lower().replace(" ", "").replace("_", "").replace("-", "")
        if not ("jua" in low or "주아" in low or "nanumsquareround" in low or "나눔스퀘어라운드" in low):
            continue
        key = low.replace("ttf", "").replace("otf", "")
        if key not in picked or f.suffix.lower() == ".ttf":
            picked[key] = f
    return list(picked.values())


def load_fonts():
    """fonts/ 폴더의 폰트를 등록하고 제목용·메뉴용 폰트 이름을 정한다. (QApplication 생성 후 호출)"""
    global TITLE_FAMILY, UI_FAMILY
    families = []
    for f in _wanted_font_files():
        fid = QtGui.QFontDatabase.addApplicationFont(str(f))
        if fid != -1:
            families += QtGui.QFontDatabase.applicationFontFamilies(fid)

    title = [n for n in families if "jua" in n.lower() or "주아" in n]
    ui = sorted(families, key=_ui_score, reverse=True)
    TITLE_FAMILY = title[0] if title else FALLBACK_FAMILY
    UI_FAMILY = ui[0] if ui and _ui_score(ui[0]) > 0 else FALLBACK_FAMILY

    print(f"[폰트] 제목: {TITLE_FAMILY} / 메뉴: {UI_FAMILY}")
    if TITLE_FAMILY == FALLBACK_FAMILY or UI_FAMILY == FALLBACK_FAMILY:
        print("[폰트] ui/fonts/ 폴더에 배민 주아체·나눔스퀘어라운드 파일을 넣으면 그 폰트로 바뀝니다.")


def title_font(px):
    f = QtGui.QFont(TITLE_FAMILY)
    f.setPixelSize(max(1, int(px)))
    return f


def ui_font(px, bold=True):
    f = QtGui.QFont(UI_FAMILY)
    f.setPixelSize(max(1, int(px)))
    f.setBold(bold)
    return f


# ── 이미지 ──────────────────────────────────────────────────────────────
_PIX_CACHE = {}


def pixmap(name):
    """assets/ 폴더의 이미지를 한 번만 읽어서 재사용."""
    if name not in _PIX_CACHE:
        pm = QtGui.QPixmap(str(ASSET_DIR / name))
        if pm.isNull():
            print(f"[이미지] assets/{name} 을(를) 찾을 수 없습니다.")
        _PIX_CACHE[name] = pm
    return _PIX_CACHE[name]
