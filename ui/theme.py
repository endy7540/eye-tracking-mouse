# -*- coding: utf-8 -*-
"""
theme.py — 데모 전체가 같이 쓰는 폰트·색상·이미지

폰트: fonts/ 폴더 안의 .ttf/.otf 파일을 프로그램 시작 때 직접 불러옵니다.
     → 발표용 컴퓨터에 폰트가 설치돼 있지 않아도 똑같이 보입니다.
     제목용  = 배민 주아체 (Jua)         : 이름에 "jua" 또는 "주아"가 들어간 폰트
     메뉴용  = 나눔스퀘어라운드 (Bold 계열) : 이름에 "nanumsquareround" 또는 "나눔스퀘어라운드"
     폰트 파일이 없으면 맑은 고딕으로 대신 표시하고, 콘솔에 안내를 출력합니다.

크기 단위: 모든 글자 크기는 "픽셀"(setPixelSize)로 지정합니다. 버튼 크기도 픽셀이라
          글자와 버튼 비율이 컴퓨터마다 달라지지 않습니다.
"""
from pathlib import Path

from PyQt5 import QtGui

BASE_DIR = Path(__file__).resolve().parent
ASSET_DIR = BASE_DIR / "assets"
FONT_DIR = BASE_DIR / "fonts"

# ── 색상 ────────────────────────────────────────────────────────────────
BG = QtGui.QColor(236, 217, 191)              # 캘리브레이션 배경 (연한 갈색)
INK = QtGui.QColor(74, 52, 40)                # 기본 글자색 (진한 갈색)
INK_SOFT = QtGui.QColor(120, 95, 78)          # 보조 글자색
PANEL_BG = QtGui.QColor(255, 249, 240, 218)   # 메뉴판·키보드 배경 (반투명)
PANEL_EDGE = QtGui.QColor(150, 115, 85, 170)
BTN_BG = QtGui.QColor(255, 255, 255, 215)     # 버튼 기본
BTN_ON = QtGui.QColor(255, 214, 160, 235)     # 켜져 있는 토글 버튼
BTN_EDGE = QtGui.QColor(150, 115, 85)
HIGHLIGHT = QtGui.QColor(242, 130, 40)        # 하이라이트(시선이 올라간 버튼) 테두리 — 주황
GAUGE = QtGui.QColor(242, 130, 40)            # 응시 게이지
RED = QtGui.QColor(224, 88, 80)
YELLOW = QtGui.QColor(248, 196, 60)
GREEN = QtGui.QColor(70, 180, 110)

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


def load_fonts():
    """fonts/ 폴더의 폰트를 등록하고 제목용·메뉴용 폰트 이름을 정한다. (QApplication 생성 후 호출)"""
    global TITLE_FAMILY, UI_FAMILY
    families = []
    if FONT_DIR.exists():
        for f in sorted(FONT_DIR.iterdir()):
            if f.suffix.lower() in (".ttf", ".otf"):
                fid = QtGui.QFontDatabase.addApplicationFont(str(f))
                if fid != -1:
                    families += QtGui.QFontDatabase.applicationFontFamilies(fid)

    title = [n for n in families if "jua" in n.lower() or "주아" in n]
    ui = sorted(families, key=_ui_score, reverse=True)
    TITLE_FAMILY = title[0] if title else FALLBACK_FAMILY
    UI_FAMILY = ui[0] if ui and _ui_score(ui[0]) > 0 else FALLBACK_FAMILY

    print(f"[폰트] 제목: {TITLE_FAMILY} / 메뉴: {UI_FAMILY}")
    if TITLE_FAMILY == FALLBACK_FAMILY or UI_FAMILY == FALLBACK_FAMILY:
        print("[폰트] fonts/ 폴더에 배민 주아체·나눔스퀘어라운드 파일을 넣으면 그 폰트로 바뀝니다.")


def title_font(px):
    f = QtGui.QFont(TITLE_FAMILY)
    f.setPixelSize(int(px))
    return f


def ui_font(px, bold=True):
    f = QtGui.QFont(UI_FAMILY)
    f.setPixelSize(int(px))
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
