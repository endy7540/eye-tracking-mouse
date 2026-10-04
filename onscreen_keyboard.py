# -*- coding: utf-8 -*-
"""
onscreen_keyboard.py — 메뉴 "키보드 열기"로 뜨는 화상 키보드

일반 키보드보다 키가 크고 간격이 넓어서 시선으로 고르기 쉽게 만들었습니다.
    - 모든 키는 GazeButton이라 마우스 클릭 또는 1초 응시로 입력됩니다.
      글자키·지우기·띄어쓰기는 계속 바라보고 있으면 반복 입력됩니다 (같은 글자 연속 입력용).
    - 한/영 전환, Shift(쌍자음 ㄲㄸㅃㅆㅉ, ㅒㅖ / 영어 대문자) 지원
    - 자동완성: 지금 입력 중인 단어로 시작하는 단어를 위쪽에 3개까지 보여주고, 누르면 그 단어로 완성
    - 오른쪽 위 X 버튼으로 닫기

입력한 글자는 키보드 위쪽 입력창에 보여집니다 (데모용 — 다른 프로그램으로 보내지는 않음).
한글 조합은 hangul.py가 담당합니다. 키보드는 누른 자모를 순서대로 저장만 하고(self.tokens),
보여줄 때마다 hangul.compose_jamo()로 조합합니다. 그래서 지우기는 "마지막 자모 하나 빼기"입니다.
"""
import html

from PyQt5 import QtWidgets, QtCore, QtGui

import theme
from gaze_widgets import GazeButton, CloseButton, setup_floating_window
from hangul import compose_jamo, to_keystrokes
from menu_bar import paint_panel_background

KEY_DWELL_SEC = 1.0        # 글자키는 메뉴 버튼(1.2초)보다 조금 빠르게
GAP = 12                   # 키 사이 간격 (일반 키보드보다 넓게)

KO_ROWS = ["ㅂㅈㄷㄱㅅㅛㅕㅑㅐㅔ", "ㅁㄴㅇㄹㅎㅗㅓㅏㅣ", "ㅋㅌㅊㅍㅠㅜㅡ"]
EN_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
KO_SHIFT = {"ㅂ": "ㅃ", "ㅈ": "ㅉ", "ㄷ": "ㄸ", "ㄱ": "ㄲ", "ㅅ": "ㅆ", "ㅐ": "ㅒ", "ㅔ": "ㅖ"}

# 자동완성 단어 목록 (데모용 — 자주 쓰는 말 위주)
KO_WORDS = ["안녕하세요", "안녕히 계세요", "감사합니다", "고맙습니다", "괜찮아요", "네", "아니요",
            "도와주세요", "물 주세요", "화장실 가고 싶어요", "배고파요", "졸려요", "아파요", "추워요",
            "더워요", "사랑해요", "보고 싶어요", "잠깐만요", "좋아요", "싫어요", "반가워요",
            "잘 부탁드립니다", "시선 추적", "졸업 작품", "두더지", "물개", "캘리브레이션", "키보드"]
EN_WORDS = ["hello", "help", "thank you", "thanks", "yes", "no", "water", "please", "sorry",
            "okay", "good", "great", "eye tracking", "keyboard", "demo"]


class OnScreenKeyboard(QtWidgets.QWidget):
    close_requested = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        setup_floating_window(self)
        self.tokens = []           # 입력한 자모/글자를 순서대로 저장 (조합은 보여줄 때 함)
        self.korean = True
        self.shift = False

        area = QtWidgets.QApplication.primaryScreen().availableGeometry()
        k = int(max(56, min(84, (area.width() * 0.62 - 9 * GAP) / 10)))   # 키 한 칸 크기
        self.k = k

        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(22, 14, 16, 20)
        v.setSpacing(GAP)

        # 머리줄: 제목 + 지금 언어 + 오른쪽 위 X
        head = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("화상 키보드")
        title.setFont(theme.title_font(30))
        title.setStyleSheet("color: #4A3428; background: transparent;")
        self.lang_label = QtWidgets.QLabel("")
        self.lang_label.setFont(theme.ui_font(17))
        self.lang_label.setStyleSheet("color: #78604E; background: transparent;")
        self.close_btn = CloseButton()
        self.close_btn.clicked.connect(lambda: self.close_requested.emit())
        head.addWidget(title)
        head.addSpacing(12)
        head.addWidget(self.lang_label, 0, QtCore.Qt.AlignBottom)
        head.addStretch(1)
        head.addWidget(self.close_btn, 0, QtCore.Qt.AlignTop)
        v.addLayout(head)

        # 입력창
        self.display = QtWidgets.QLabel()
        self.display.setTextFormat(QtCore.Qt.RichText)
        self.display.setFont(theme.ui_font(30, bold=False))
        self.display.setFixedHeight(66)
        self.display.setStyleSheet("QLabel { background-color: rgba(255, 255, 255, 235);"
                                   " border: 2px solid rgba(150, 115, 85, 170); border-radius: 14px;"
                                   " padding: 4px 16px; color: #4A3428; }")
        v.addWidget(self.display)

        # 자동완성 후보 3칸
        sug = QtWidgets.QHBoxLayout()
        sug.setSpacing(GAP)
        self.sugg_btns = []
        for i in range(3):
            b = GazeButton("", font_px=24)
            b.setFixedHeight(58)
            b.clicked.connect(lambda _=False, i=i: self._choose(i))
            sug.addWidget(b, 1)
            self.sugg_btns.append(b)
        v.addLayout(sug)

        # 글자키 3줄 (위치는 고정, 한/영·Shift에 따라 글자만 바뀜)
        self.letter_btns = []      # (버튼, 줄 번호, 칸 번호)
        for r in range(3):
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(GAP)
            row.addStretch(1)
            if r == 2:
                self.shift_btn = self._key("Shift", self._toggle_shift, int(k * 1.5 + GAP / 2),
                                           font_px=20, repeat=False)
                row.addWidget(self.shift_btn)
            for c in range(len(KO_ROWS[r])):
                b = self._key("", None, k, font_px=30, repeat=True)
                b.clicked.connect(lambda _=False, b=b: self._type(b.text()))
                self.letter_btns.append((b, r, c))
                row.addWidget(b)
            if r == 2:
                row.addWidget(self._key("지우기", self._backspace, int(k * 1.5 + GAP / 2),
                                        font_px=20, repeat=True))
            row.addStretch(1)
            v.addLayout(row)

        # 맨 아랫줄: 한/영 · 띄어쓰기 · 전체 지우기
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(GAP)
        row.addStretch(1)
        row.addWidget(self._key("한/영", self._toggle_lang, 2 * k + GAP, font_px=22, repeat=False))
        row.addWidget(self._key("띄어쓰기", lambda: self._type(" "), 5 * k + 4 * GAP, font_px=22,
                                repeat=True))
        row.addWidget(self._key("전체 지우기", self._clear, 3 * k + 2 * GAP, font_px=20, repeat=False))
        row.addStretch(1)
        v.addLayout(row)

        self._relabel()
        self._refresh()
        self.adjustSize()

    def _key(self, text, slot, width, font_px, repeat):
        b = GazeButton(text, font_px=font_px, repeatable=repeat,
                       dwell_sec=KEY_DWELL_SEC if repeat else 1.2, radius=14)
        b.setFixedSize(width, self.k)
        if slot is not None:
            b.clicked.connect(slot)
        return b

    # ── 키 동작 ───────────────────────────────────────────────────
    def _type(self, ch):
        if ch:
            self.tokens.append(ch)
        if self.shift:                      # Shift는 한 글자만 적용되고 풀림
            self.shift = False
            self._relabel()
        self._refresh()

    def _backspace(self):
        if self.tokens:
            self.tokens.pop()
        self._refresh()

    def _clear(self):
        self.tokens.clear()
        self._refresh()

    def _toggle_lang(self):
        self.korean = not self.korean
        self.shift = False
        self._relabel()
        self._refresh()

    def _toggle_shift(self):
        self.shift = not self.shift
        self._relabel()

    def _relabel(self):
        """한/영, Shift 상태에 맞게 글자키 표시를 바꿈."""
        rows = KO_ROWS if self.korean else EN_ROWS
        for b, r, c in self.letter_btns:
            ch = rows[r][c]
            if self.shift:
                ch = KO_SHIFT.get(ch, ch) if self.korean else ch.upper()
            b.setText(ch)
        self.shift_btn.set_on(self.shift)
        self.lang_label.setText("한글 입력 중" if self.korean else "영문 입력 중")

    # ── 자동완성 ─────────────────────────────────────────────────
    def _current_word(self):
        """마지막 띄어쓰기 뒤에 입력 중인 자모/글자들."""
        cur = []
        for t in reversed(self.tokens):
            if t == " ":
                break
            cur.append(t)
        return cur[::-1]

    def _suggestions(self):
        cur = [t.lower() for t in self._current_word()]
        if not cur:
            return []
        words = KO_WORDS + EN_WORDS if self.korean else EN_WORDS + KO_WORDS
        out = []
        for w in words:
            keys = [k.lower() for k in to_keystrokes(w)]   # 단어를 자모 단위로 풀어서 비교 ('안' → ㅇㅏㄴ 이면 '아니요'도 후보)
            if len(keys) > len(cur) and keys[:len(cur)] == cur:
                out.append(w)
            if len(out) == 3:
                break
        return out

    def _choose(self, i):
        word = self.sugg_btns[i].text()
        if not word:
            return
        n = len(self._current_word())
        self.tokens = self.tokens[:len(self.tokens) - n] + to_keystrokes(word) + [" "]
        self._refresh()

    # ── 화면 갱신 ────────────────────────────────────────────────
    def _refresh(self):
        text = compose_jamo(self.tokens)
        shown = text[-30:]                                   # 너무 길면 뒷부분만
        caret = '<span style="color:#F28228;">|</span>'
        if shown:
            body = html.escape(shown).replace(" ", "&nbsp;")
        else:
            body = '<span style="color:#B09A88;">여기에 입력한 글자가 보여요</span>'
        self.display.setText(body + caret)

        sugg = self._suggestions()
        for i, b in enumerate(self.sugg_btns):
            b.setText(sugg[i] if i < len(sugg) else "")
            b.setEnabled(i < len(sugg))

    def paintEvent(self, event):
        paint_panel_background(self)
