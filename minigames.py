# -*- coding: utf-8 -*-
"""
minigames.py — 눈동자 마우스 시연용 "시선 미니게임 모음" (단독 실행 파일 1개)

이 파일 하나로 돌아갑니다. 프로젝트의 다른 .py 파일을 불러오지 않아요.
(그림·글꼴은 프로젝트의 ui/assets, ui/fonts 폴더에 있으면 그걸 쓰고, 없으면 직접 그린 그림·기본 글꼴로 대신합니다)

실행
    python minigames.py                 전체화면 (ESC 로 종료)
    python minigames.py --windowed      창 모드 (테스트용)
    python minigames.py --mute          효과음 끄기
    python minigames.py --hide-cursor   윈도우 마우스 커서를 숨김 (시선 점만 보이게)

게임 6개 (모두 "클릭 없이 바라보기만"으로 진행. 인정 시간: 대부분 0.1초, 숫자 0.3초, 다른 그림 0.35초)
    1. 두더지 잡기      튀어나온 두더지를 바라보면 잡힘
    2. 반짝이 잡기      나타났다 사라지는 별을 바라봐서 터뜨림
    3. 숫자 순서 찍기   1번부터 순서대로 숫자를 바라봄
    4. 따라잡기         움직이는 공을 바라보고 있는 동안 점수
    5. 다른 그림 찾기   비슷한 그림 중 하나만 다른 것을 찾음
    6. 폭탄 피하기      별은 터뜨리고 폭탄은 바라보지 않기

화면 조작 (전부 바라보기: 메뉴 버튼은 실수로 눌리지 않게 0.5초, 나가기는 0.8초)
    가운데 카드        바라보면 그 게임 시작
    양옆 화살표        게임 고르기
    카드 위 "게임방법"   게임 설명 보기
    키보드             ← → 고르기 / Enter·Space 시작 / H 게임방법 / R 다시 하기 / ESC 뒤로·종료
    마우스             버튼을 클릭하면 바로 눌림 (테스트용)

시선(눈동자 마우스)과 연결하는 법 — 두 프로그램은 별개로 실행되고, 시선 좌표만 UDP 로 주고받습니다
    눈동자 마우스(main.py)의 _on_gaze(x, y, t) 함수 맨 위에 아래 3줄을 넣으면
    게임이 그 좌표를 시선으로 씁니다 (x, y 는 화면 전체 좌표):

        import socket
        _GS = getattr(self, "_gs", None) or socket.socket(socket.AF_INET, socket.SOCK_DGRAM); self._gs = _GS
        _GS.sendto(f"{x:.0f},{y:.0f}".encode(), ("127.0.0.1", 47321))

    시선이 들어오지 않으면(0.3초 이상 소식 없음) 자동으로 마우스 커서 위치를 시선처럼 씁니다.
    포트를 바꾸려면 --gaze-port 번호, 끄려면 --gaze-port 0

구성: 위쪽은 화면과 상관없는 게임 규칙(Qt 없이 테스트 가능), 아래쪽이 PyQt5 화면입니다.
"""
import argparse
import colorsys
import math
import random
import socket
import struct
import sys
import tempfile
import time
import wave
from pathlib import Path

# ════════════════════════════════════════════════════════════════
#  1. 설정 (숫자를 바꾸면 느낌이 바뀝니다)
# ════════════════════════════════════════════════════════════════
GAME_DWELL = 0.10        # 게임 중: 이만큼만 바라봐도 인정
LIFE_SCALE = 1.4         # 별·두더지가 머무는 시간 배수 (1.0 = 예전 속도, 클수록 느긋 — --life 로 바꿈)
BOMB_DWELL = 0.20        # 폭탄은 스쳐 보는 것만으로 터지지 않게 조금 더 길게
NUMBER_DWELL = 0.30      # 숫자 순서 찍기: 훑어보다 스치는 것과 구분하려고 조금 더 길게
ODD_DWELL = 0.35         # 다른 그림 찾기: 정답으로 인정하는 시간
WRONG_DWELL = 0.90       # 다른 그림 찾기: 엉뚱한 그림을 이만큼 "오래" 봐야 감점 (훑어보는 건 봐줌)
MENU_DWELL = 0.50        # 메뉴 버튼 (카드, 화살표, 게임방법, 다시하기 …)
EXIT_DWELL = 0.80        # 게임 중 "나가기" 버튼
GRACE = 0.06             # 시선이 잠깐(이 시간 이하) 튀어도 바라보던 걸 이어서 셈
ROUND_SEC = 40.0         # 한 판 시간 (따라잡기는 30초)
INTRO_SEC = 1.0          # "준비~ 시작!" 시간
RESULT_ARM_SEC = 0.8     # 결과 화면에서 버튼이 눌리기 시작하는 시간
EFFECT_LIFE = 1.0
GAZE_PORT = 47321
GAZE_FRESH = 0.30        # 시선 소식이 이보다 오래되면 마우스를 씀
CALIB_PORT = 47322       # 맞힌 별·두더지 위치를 눈동자 마우스(자동 보정)에 알려주는 UDP 포트

# 두더지 그림(800x800) 안의 위치 비율 (프로젝트의 mole.png 기준)
MOLE_NOSE_Y = 0.52       # 코 — 이 지점이 목표 위치
MOLE_BOTTOM_Y = 0.92     # 구멍 아래쪽
HOLE_MID_Y = 0.79        # 구멍 입구 가운데
RISE_DEPTH = 0.72
HAMMER_PIVOT_Y = 0.922
POP_SEC, SINK_SEC, HIT_SEC, HIT_AT = 0.2, 0.25, 0.5, 0.4


def lerp(a, b, k):
    return a + (b - a) * max(0.0, min(1.0, k))


# ════════════════════════════════════════════════════════════════
#  2. 공통 부품 (바라보기 판정, 버튼 위치)
# ════════════════════════════════════════════════════════════════
class Dwell:
    """한 번에 하나의 대상을 바라본 시간을 잰다. step() 이 True 를 돌려주는 순간이 "인정"."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.key, self.t0, self.seen, self.progress = None, 0.0, 0.0, 0.0

    def step(self, key, now, need):
        if key is None:
            if self.key is not None and now - self.seen > GRACE:
                self.reset()
            return False
        if key != self.key:
            self.key, self.t0 = key, now
        self.seen = now
        self.progress = min(1.0, (now - self.t0) / need) if need > 0 else 1.0
        if self.progress >= 1.0:
            self.reset()
            return True
        return False


class Btn:
    """화면 속 버튼. shape: 'rect'(x0,y0,x1,y1) 또는 'circle'(cx,cy,r)."""

    def __init__(self, key, shape, geom, need):
        self.key, self.shape, self.geom, self.need = key, shape, geom, need

    def contains(self, x, y, pad=0.0):
        if self.shape == "circle":
            cx, cy, r = self.geom
            return math.hypot(x - cx, y - cy) <= r + pad
        x0, y0, x1, y1 = self.geom
        return x0 - pad <= x <= x1 + pad and y0 - pad <= y <= y1 + pad


def layout(w, h):
    """메뉴·결과 화면의 버튼 위치. 전부 화면 높이(h)에 비례."""
    L = {}
    cw, ch = min(h * 0.46, w * 0.30), h * 0.66
    cx, cy = w / 2, h * 0.54
    L["card"] = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
    bw, bh = h * 0.22, h * 0.065
    top = L["card"][1] - h * 0.02
    L["howto"] = (cx - bw / 2, top - bh, cx + bw / 2, top)
    ar, gap = h * 0.06, h * 0.13
    L["prev"] = (cx - cw / 2 - gap, cy, ar)
    L["next"] = (cx + cw / 2 + gap, cy, ar)
    L["close"] = (cx - h * 0.14, h * 0.80, cx + h * 0.14, h * 0.80 + h * 0.08)
    ew, eh = h * 0.20, h * 0.062
    L["exit"] = (w - w * 0.02 - ew, h * 0.03, w - w * 0.02, h * 0.03 + eh)
    rw, rh = h * 0.30, h * 0.085
    L["retry"] = (cx - h * 0.02 - rw, h * 0.78, cx - h * 0.02, h * 0.78 + rh)
    L["tomenu"] = (cx + h * 0.02, h * 0.78, cx + h * 0.02 + rw, h * 0.78 + rh)
    L["card_size"] = (cw, ch)
    return L


# ════════════════════════════════════════════════════════════════
#  3. 게임 규칙 (화면과 무관 — 시간과 시선 좌표만 받아서 계산)
#     모든 게임이 같은 모양: start(now) / update(now, ptr) / pop_events() 와
#     score, state('intro'|'play'|'result'), time_left(now), effects, ring 을 가짐
# ════════════════════════════════════════════════════════════════
class MiniGame:
    kind = ""
    title = ""
    tagline = ""
    howto = []
    accent = (242, 130, 40)
    round_sec = ROUND_SEC

    def __init__(self, w, h, rng=None):
        self.rng = rng or random.Random()
        self.dwell = Dwell()
        self.set_size(w, h)
        self.start(0.0)

    def set_size(self, w, h):
        self.w, self.h = w, h
        self.area = (w * 0.05, h * 0.15, w * 0.95, h * 0.95)       # 게임이 펼쳐지는 영역 (위쪽은 점수판)

    # ── 진행 ──
    def start(self, now):
        self.state, self.t_state, self.t0 = "intro", now, now
        self.score = self.combo = self.max_combo = self.hits = self.misses = 0
        self.penalty = 0.0
        self.effects, self.events, self.ring = [], [], None
        self.samples = []                      # 보정에 쓸 "여기를 보고 있었다" 기록 (x, y, 시각)
        self.flash_t = -10.0
        self.dwell.reset()
        self.reset_game()

    def reset_game(self):
        pass

    def begin(self, now):
        pass

    def step(self, now, ptr):
        raise NotImplementedError

    def hud_extra(self, now):
        return ""

    def result_line(self):
        return f"성공 {self.hits}번 · 최대 콤보 {self.max_combo}"

    def elapsed(self, now):
        return max(0.0, now - self.t0) if self.state == "play" else 0.0

    def time_left(self, now):
        if self.state == "intro":
            return self.round_sec
        if self.state == "result":
            return 0.0
        return max(0.0, self.round_sec - self.elapsed(now) - self.penalty)

    def progress(self, now):
        return max(0.0, min(1.0, self.elapsed(now) / self.round_sec))

    def update(self, now, ptr):
        self.effects = [e for e in self.effects if now - e["t"] < EFFECT_LIFE]
        if self.state == "intro":
            if now - self.t_state >= INTRO_SEC:
                self.state, self.t0 = "play", now
                self.begin(now)
            return
        if self.state != "play":
            return
        if self.time_left(now) <= 0:
            self.state, self.t_state, self.ring = "result", now, None
            self.dwell.reset()
            self.events.append("end")
            return
        self.step(now, ptr)

    def pop_events(self):
        ev, self.events = self.events, []
        return ev

    def pop_samples(self):
        s, self.samples = self.samples, []
        return s

    # ── 점수·효과 도우미 ──
    def gain(self, base=10):
        self.combo += 1
        self.max_combo = max(self.max_combo, self.combo)
        self.hits += 1
        pts = base + 5 * min(self.combo - 1, 5)
        self.score += pts
        return pts

    def lose_combo(self):
        self.combo = 0

    def popup(self, x, y, text, now, color=(248, 196, 60)):
        self.effects.append({"kind": "popup", "x": x, "y": y, "t": now, "text": text, "color": color})

    def burst(self, x, y, now, good=True):
        self.effects.append({"kind": "burst", "x": x, "y": y, "t": now, "good": good})

    def rand_pos(self, r):
        x0, y0, x1, y1 = self.area
        return self.rng.uniform(x0 + r, x1 - r), self.rng.uniform(y0 + r, y1 - r)


# ── 1. 두더지 잡기 ─────────────────────────────────────────────
class _Mole:
    __slots__ = ("hole", "t0", "stay", "state", "t_state")

    def __init__(self, hole, t0, stay):
        self.hole, self.t0, self.stay, self.state, self.t_state = hole, t0, stay, "up", t0


class MoleGame(MiniGame):
    kind = "mole"
    title = "두더지 잡기"
    tagline = "튀어나온 두더지를\n바라보면 잡혀요"
    accent = (242, 160, 90)
    howto = ["구멍에서 두더지가 튀어나와요.",
             "두더지를 0.1초만 바라보면 잡혀요!",
             "연속으로 잡으면 콤보 점수가 쌓여요.",
             "늦으면 도망가니까 빨리빨리!",
             "갈수록 더 빠르게, 더 많이 나와요."]

    def set_size(self, w, h):
        super().set_size(w, h)
        self.S = max(110.0, min(h * 0.27, w * 0.2, 320.0))                # 두더지 그림 크기
        self.holes = [(cx * w, ry * h) for ry in (0.30, 0.57, 0.84) for cx in (1 / 6, 0.5, 5 / 6)]

    def reset_game(self):
        self.moles, self.next_spawn, self.last_hole = [], 0.0, None

    def begin(self, now):
        self.next_spawn = now + 0.3

    def _pick_hole(self):
        busy = {m.hole for m in self.moles}
        free = [i for i in range(9) if i not in busy]
        pool = [i for i in free if i != self.last_hole] or free
        return self.rng.choice(pool) if pool else None

    def step(self, now, ptr):
        prog, el = self.progress(now), self.elapsed(now)
        for m in self.moles:                                                # 시간 초과 → 도망
            if m.state == "up" and now - m.t0 >= m.stay:
                m.state, m.t_state = "sink", now
                self.misses += 1
                self.lose_combo()
                self.events.append("miss")
        self.moles = [m for m in self.moles
                      if not (m.state == "sink" and now - m.t_state >= SINK_SEC)
                      and not (m.state == "hit" and now - m.t_state >= HIT_SEC)]
        cap = 1 if el < 10 else 2 if el < 25 else 3
        if now >= self.next_spawn and sum(1 for m in self.moles if m.state == "up") < cap:
            hole = self._pick_hole()
            if hole is not None:
                self.moles.append(_Mole(hole, now, lerp(1.7, 0.95, prog) * LIFE_SCALE))
                self.last_hole = hole
                self.next_spawn = now + lerp(0.7, 0.35, prog) + self.rng.uniform(0.0, 0.2)

        target, best = None, None                                           # 시선이 닿은 두더지 (가장 가까운 것)
        if ptr is not None:
            for m in self.moles:
                if m.state == "up" and now - m.t0 >= 0.12:
                    hx, hy = self.holes[m.hole]
                    d = math.hypot(hx - ptr[0], hy - ptr[1])
                    if d <= self.S * 0.55 and (best is None or d < best):
                        target, best = m, d
        fired = self.dwell.step(target.hole if target else None, now, GAME_DWELL)
        self.ring = None
        if target is not None:
            hx, hy = self.holes[target.hole]
            self.ring = (hx, hy + 0.05 * self.S, 0.5 * self.S, self.dwell.progress)
        if fired and target is not None:
            hx, hy = self.holes[target.hole]
            target.state, target.t_state = "hit", now
            pts = self.gain()
            self.burst(hx, hy, now)
            self.popup(hx, hy - 0.55 * self.S, f"+{pts}", now)
            self.events.append("good")
            self.samples.append((hx, hy, now))                  # 두더지 코 위치 = 보고 있던 곳

    def result_line(self):
        return f"잡은 두더지 {self.hits}마리 · 놓친 두더지 {self.misses}마리 · 최대 콤보 {self.max_combo}"


# ── 2. 반짝이 잡기 / 6. 폭탄 피하기 ────────────────────────────
class _Item:
    __slots__ = ("id", "x", "y", "r", "t0", "life", "kind", "state", "t_state")


class SparkleGame(MiniGame):
    kind = "sparkle"
    title = "반짝이 잡기"
    tagline = "반짝이는 별을\n눈으로 터뜨려요"
    accent = (248, 196, 60)
    bombs = False
    calib = True                                 # 터뜨린 별 위치를 보정에 사용 (폭탄 게임은 끔)
    howto = ["반짝이는 별이 여기저기 나타나요.",
             "별을 0.1초만 바라보면 팡! 터져요.",
             "연속으로 터뜨리면 콤보 점수!",
             "별은 금방 사라지니까 놓치지 마세요.",
             "갈수록 더 빠르고 더 작아져요."]

    def reset_game(self):
        self.items, self.next_spawn, self._id = [], 0.0, 0

    def begin(self, now):
        self.next_spawn = now + 0.2

    def radius(self, now):
        return self.h * lerp(0.085, 0.06, self.progress(now))

    def _spawn(self, now, ptr):
        r, prog = self.radius(now), self.progress(now)
        live = [i for i in self.items if i.state == "live"]
        bomb = self.bombs and self.rng.random() < 0.35 and sum(1 for i in live if i.kind == "bomb") < 3
        for _ in range(30):
            x, y = self.rand_pos(r)
            if any(math.hypot(x - i.x, y - i.y) < 2.4 * r for i in live):
                continue
            if bomb and ptr is not None and math.hypot(x - ptr[0], y - ptr[1]) < 3.0 * r:
                continue                                                    # 지금 보고 있는 자리엔 폭탄을 안 놓음
            it = _Item()
            self._id += 1
            it.id, it.x, it.y, it.r, it.t0 = self._id, x, y, r, now
            it.kind = "bomb" if bomb else "star"
            it.life = 1.7 if bomb else lerp(1.5, 0.9, prog) * LIFE_SCALE
            it.state, it.t_state = "live", now
            self.items.append(it)
            return

    def step(self, now, ptr):
        prog = self.progress(now)
        for it in self.items:
            if it.state == "live" and now - it.t0 >= it.life:
                it.state, it.t_state = "gone", now
                if it.kind == "star":
                    self.misses += 1
                    self.lose_combo()
                    self.events.append("miss")
        self.items = [i for i in self.items if not (i.state in ("pop", "gone") and now - i.t_state >= 0.35)]
        cap = int(lerp(3, 5, prog) + 0.5)
        if now >= self.next_spawn and sum(1 for i in self.items if i.state == "live") < cap:
            self._spawn(now, ptr)
            self.next_spawn = now + lerp(0.5, 0.25, prog) + self.rng.uniform(0.0, 0.15)

        target, best = None, None
        if ptr is not None:
            for it in self.items:
                if it.state == "live":
                    d = math.hypot(it.x - ptr[0], it.y - ptr[1])
                    if d <= it.r * 1.15 and (best is None or d < best):
                        target, best = it, d
        need = BOMB_DWELL if (target is not None and target.kind == "bomb") else GAME_DWELL
        fired = self.dwell.step(target.id if target else None, now, need)
        self.ring = None
        if target is not None:
            self.ring = (target.x, target.y, target.r * 1.25, self.dwell.progress)
        if fired and target is not None:
            target.state, target.t_state = "pop", now
            if target.kind == "star":
                pts = self.gain()
                self.burst(target.x, target.y, now)
                self.popup(target.x, target.y - target.r, f"+{pts}", now)
                self.events.append("good")
                if self.calib:
                    self.samples.append((target.x, target.y, now))   # 별 중심 = 보고 있던 곳
            else:
                self.score = max(0, self.score - 20)
                self.lose_combo()
                self.misses += 1
                self.flash_t = now
                self.burst(target.x, target.y, now, good=False)
                self.popup(target.x, target.y - target.r, "-20", now, (224, 88, 80))
                self.events.append("bad")

    def result_line(self):
        return f"터뜨린 별 {self.hits}개 · 놓친 별 {self.misses}개 · 최대 콤보 {self.max_combo}"


class BombGame(SparkleGame):
    kind = "bombs"
    calib = False
    title = "폭탄 피하기"
    tagline = "별은 터뜨리고\n폭탄은 피하세요"
    accent = (224, 88, 80)
    bombs = True
    howto = ["별은 바라보면 점수! 폭탄은 조심!",
             "폭탄을 바라보면 점수가 깎여요(-20).",
             "폭탄은 오래 머무니 피해서 별만 노려요.",
             "별을 놓쳐도 감점은 없어요."]

    def result_line(self):
        return f"터뜨린 별 {self.hits}개 · 폭탄 {self.misses}번 건드림 · 최대 콤보 {self.max_combo}"


# ── 3. 숫자 순서 찍기 ──────────────────────────────────────────
class NumberGame(MiniGame):
    kind = "numbers"
    title = "숫자 순서 찍기"
    tagline = "숫자를 1번부터\n순서대로 찾아요"
    accent = (59, 142, 234)
    howto = ["1, 2, 3 … 숫자가 흩어져 있어요.",
             "작은 숫자부터 차례대로 바라보세요.",
             "숫자에 시선을 잠깐 머물러야 찍혀요.",
             "한 판을 다 찾으면 보너스 점수!",
             "새 판은 숫자가 더 많아져요."]

    def reset_game(self):
        self.boards, self.nxt, self.nums, self.r = 0, 1, [], self.h * 0.062
        self._new_board(0.0)

    def hud_extra(self, now):
        return f"다음 숫자 {self.nxt}" if self.nxt <= len(self.nums) else ""

    def _new_board(self, now):
        n = min(12, 8 + self.boards)
        r = self.h * (0.066 if n <= 9 else 0.058)
        self.r, self.nxt, self.nums = r, 1, []
        spots, gap = [], 2.5 * r
        for _ in range(600):
            x, y = self.rand_pos(r)
            if all(math.hypot(x - sx, y - sy) >= gap for sx, sy in spots):
                spots.append((x, y))
                if len(spots) == n:
                    break
            if _ == 300 and len(spots) < n:
                gap *= 0.85
        while len(spots) < n:                                               # 아주 작은 창에서 자리가 모자랄 때
            spots.append(self.rand_pos(r))
        order = list(range(1, n + 1))
        self.rng.shuffle(order)
        self.nums = [{"n": order[i], "x": spots[i][0], "y": spots[i][1], "state": "live", "t": now}
                     for i in range(n)]

    def step(self, now, ptr):
        self.nums = [m for m in self.nums if not (m["state"] == "done" and now - m["t"] >= 0.3)]
        if not self.nums:                                                   # 판 클리어 → 새 판 (숫자가 하나씩 더 늘어남)
            self.boards += 1
            self._new_board(now)
        cur = next((m for m in self.nums if m["n"] == self.nxt and m["state"] == "live"), None)
        self.ring = None
        key = None
        if cur is not None and ptr is not None and math.hypot(cur["x"] - ptr[0], cur["y"] - ptr[1]) <= self.r * 1.15:
            key = cur["n"]
        fired = self.dwell.step(key, now, NUMBER_DWELL)
        if cur is not None and key is not None:
            self.ring = (cur["x"], cur["y"], self.r * 1.3, self.dwell.progress)
        if fired and cur is not None:
            cur["state"], cur["t"] = "done", now
            self.nxt += 1
            self.hits += 1
            self.score += 10
            self.popup(cur["x"], cur["y"] - self.r, "+10", now)
            self.burst(cur["x"], cur["y"], now)
            self.events.append("good")
            if all(m["state"] == "done" for m in self.nums):
                self.score += 30
                self.max_combo += 1                                          # 클리어한 판 수로 사용
                self.popup(self.w / 2, self.h * 0.45, "판 클리어! +30", now, (70, 180, 110))
                self.events.append("combo")

    def result_line(self):
        return f"찾은 숫자 {self.hits}개 · 클리어한 판 {self.max_combo}번"


# ── 4. 따라잡기 ───────────────────────────────────────────────
class TrackGame(MiniGame):
    kind = "track"
    title = "따라잡기"
    tagline = "움직이는 공을\n끝까지 따라가요"
    accent = (70, 180, 110)
    round_sec = 30.0
    howto = ["화면을 돌아다니는 공을 바라보세요.",
             "0.1초 바라보면 공이 붙잡혀요.",
             "붙잡고 있는 동안 점수가 쌓여요.",
             "놓치면 다시 바라봐서 붙잡으세요.",
             "공은 갈수록 빨라져요!"]

    def reset_game(self):
        self.ph1, self.ph2 = self.rng.uniform(0, 6.28), self.rng.uniform(0, 6.28)
        self.locked, self.lost_since, self.last_t = False, None, None
        self.score_f, self.track_time, self.streak, self.best_streak = 0.0, 0.0, 0.0, 0.0
        self.x, self.y, self.r, self.trail = self.w / 2, self.h * 0.56, self.h * 0.075, []
        self.dist = None

    def _place(self):
        self.x = self.w * 0.5 + self.w * 0.38 * math.sin(self.ph1)
        self.y = self.h * 0.56 + self.h * 0.28 * math.sin(self.ph2)
        self.r = self.h * 0.075

    def step(self, now, ptr):
        dt = 0.016 if self.last_t is None else max(0.0, min(0.1, now - self.last_t))
        self.last_t = now
        prog = self.progress(now)
        w1 = lerp(0.8, 1.7, prog)
        self.ph1 += w1 * dt
        self.ph2 += w1 * 1.31 * dt
        self._place()
        self.trail.append((self.x, self.y))
        self.trail = self.trail[-12:]
        d = math.hypot(self.x - ptr[0], self.y - ptr[1]) if ptr is not None else None
        self.dist = d
        self.ring = None
        if not self.locked:
            key = "ball" if (d is not None and d <= self.r * 1.3) else None
            if self.dwell.step(key, now, GAME_DWELL):
                self.locked, self.lost_since = True, None
                self.events.append("good")
            elif key:
                self.ring = (self.x, self.y, self.r * 1.4, self.dwell.progress)
        else:
            if d is not None and d <= self.r * 1.9:
                self.lost_since = None
            elif self.lost_since is None:
                self.lost_since = now
            elif now - self.lost_since > 0.25:
                self.locked, self.streak = False, 0.0
                self.events.append("miss")
        if self.locked:
            self.score_f += 20 * (1 + prog) * dt
            self.track_time += dt
            self.streak += dt
            self.best_streak = max(self.best_streak, self.streak)
            self.score = int(self.score_f)
            self.max_combo = int(self.best_streak)

    def hud_extra(self, now):
        return "붙잡는 중!" if self.locked else "공을 바라보세요"

    def result_line(self):
        return f"붙잡은 시간 {self.track_time:.1f}초 · 가장 길게 따라간 시간 {self.best_streak:.1f}초"


# ── 5. 다른 그림 찾기 ──────────────────────────────────────────
ODD_SHAPES = ("circle", "square", "diamond", "triangle", "star")


class OddGame(MiniGame):
    kind = "odd"
    title = "다른 그림 찾기"
    tagline = "다른 그림 하나를\n찾아내세요"
    accent = (150, 110, 220)
    howto = ["비슷한 그림들 사이에 하나만 달라요.",
             "다른 하나를 잠깐 바라보면 정답!",
             "엉뚱한 그림을 오래 보면 시간 -3초.",
             "갈수록 그림이 많아지고 더 닮아져요."]

    def reset_game(self):
        self.round_no, self.cells, self.odd, self.n, self.cell = 0, [], 0, 3, 0.0
        self._new_round(0.0)

    def _new_round(self, now):
        k = self.round_no
        n = 3 if k < 2 else 4 if k < 6 else 5
        side = min((self.area[2] - self.area[0]) * 0.62, self.area[3] - self.area[1]) * 0.96
        cell = side / n
        ox = (self.area[0] + self.area[2]) / 2 - side / 2
        oy = (self.area[1] + self.area[3]) / 2 - side / 2
        shape = self.rng.choice(ODD_SHAPES)
        hue = self.rng.random()
        base = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.55, 0.92))
        mode = "shape" if k % 3 == 0 else "color"
        shift = lerp(45, 14, k / 12.0) / 360.0 * self.rng.choice((-1, 1))
        odd_col = tuple(int(c * 255) for c in colorsys.hsv_to_rgb((hue + shift) % 1.0, 0.55, 0.92))
        odd_shape = self.rng.choice([s for s in ODD_SHAPES if s != shape])
        prev = self.odd if self.cells else -1
        self.odd = self.rng.choice([i for i in range(n * n) if i != prev])
        self.n, self.cell, self.cells = n, cell, []
        for i in range(n * n):
            r_, c_ = divmod(i, n)
            is_odd = i == self.odd
            self.cells.append({
                "x": ox + (c_ + 0.5) * cell, "y": oy + (r_ + 0.5) * cell,
                "shape": odd_shape if (is_odd and mode == "shape") else shape,
                "color": odd_col if (is_odd and mode == "color") else base,
                "block": 0.0, "flash": -10.0})
        self.dwell.reset()

    def step(self, now, ptr):
        target, best = None, None
        if ptr is not None:
            for i, c in enumerate(self.cells):
                d = math.hypot(c["x"] - ptr[0], c["y"] - ptr[1])
                if d <= self.cell * 0.45 and now >= c["block"] and (best is None or d < best):
                    target, best = i, d
        need = ODD_DWELL if target == self.odd else WRONG_DWELL
        fired = self.dwell.step(target, now, need)
        self.ring = None
        if target is not None:
            c = self.cells[target]
            self.ring = (c["x"], c["y"], self.cell * 0.46, self.dwell.progress)
        if not fired:
            return
        c = self.cells[target]
        if target == self.odd:
            pts = self.gain()
            self.burst(c["x"], c["y"], now)
            self.popup(c["x"], c["y"] - self.cell * 0.4, f"+{pts}", now)
            self.events.append("good")
            self.round_no += 1
            self._new_round(now)
        else:
            self.penalty += 3.0
            self.misses += 1
            self.lose_combo()
            c["block"], c["flash"] = now + 0.8, now
            self.popup(c["x"], c["y"] - self.cell * 0.4, "-3초", now, (224, 88, 80))
            self.events.append("bad")

    def result_line(self):
        return f"찾은 그림 {self.hits}개 · 엉뚱한 곳 {self.misses}번 · 최대 콤보 {self.max_combo}"


GAMES = [MoleGame, SparkleGame, NumberGame, TrackGame, OddGame, BombGame]


# ════════════════════════════════════════════════════════════════
#  4. 시선 입력 (눈동자 마우스가 UDP 로 보내주는 좌표) / 효과음 파일 만들기
# ════════════════════════════════════════════════════════════════
class GazeListener:
    def __init__(self, port):
        self.sock, self.x, self.y, self.t = None, None, None, 0.0
        if port:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.bind(("127.0.0.1", port))
                s.setblocking(False)
                self.sock = s
            except OSError as e:
                print(f"[시선] 포트 {port} 를 열 수 없어요({e}) → 마우스 위치를 시선처럼 씁니다.")

    def poll(self, now):
        """받은 최신 좌표를 반영. 반환: 최근 소식이 있으면 (x, y), 없으면 None."""
        if self.sock is not None:
            while True:
                try:
                    data, _ = self.sock.recvfrom(256)
                except (BlockingIOError, InterruptedError):
                    break
                except OSError:
                    break
                try:
                    xs, ys = data.decode("ascii", "ignore").split(",")[:2]
                    self.x, self.y, self.t = float(xs), float(ys), now
                except ValueError:
                    pass
        return (self.x, self.y) if (self.x is not None and now - self.t < GAZE_FRESH) else None


# 효과음: (주파수 또는 (시작, 끝) 주파수, 길이(초), 크기) 를 이어붙임
TONES = {
    "good": [((660, 920), 0.09, 0.55)],
    "bad": [((220, 110), 0.28, 0.65)],
    "miss": [((330, 250), 0.07, 0.35)],
    "combo": [(660, 0.07, 0.5), (880, 0.07, 0.5), (1320, 0.13, 0.5)],
    "select": [(520, 0.05, 0.4)],
    "start": [(440, 0.09, 0.5), (660, 0.09, 0.5), (880, 0.16, 0.5)],
    "end": [(880, 0.10, 0.5), (660, 0.10, 0.5), (440, 0.22, 0.5)],
}


def write_tone(path, spec, rate=22050):
    frames = bytearray()
    for freq, dur, vol in spec:
        f0, f1 = freq if isinstance(freq, tuple) else (freq, freq)
        n, phase = int(rate * dur), 0.0
        for i in range(n):
            k = i / max(1, n - 1)
            phase += 2 * math.pi * (f0 + (f1 - f0) * k) / rate
            env = min(1.0, i / (rate * 0.005)) * (1.0 - k) ** 0.6
            frames += struct.pack("<h", int(32767 * vol * env * math.sin(phase)))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(bytes(frames))


# ════════════════════════════════════════════════════════════════
#  5. PyQt5 화면
# ════════════════════════════════════════════════════════════════
from PyQt5 import QtWidgets, QtCore, QtGui   # noqa: E402  (위의 게임 규칙은 Qt 없이도 불러올 수 있게 아래에 둠)

HERE = Path(__file__).resolve().parent
_ROOTS = [HERE, HERE.parent, Path.cwd()]
ASSET_DIRS = [r / sub for r in _ROOTS for sub in ("ui/assets", "assets", ".")]
FONT_FILES = [r / sub / "BMJUA_ttf.ttf" for r in _ROOTS for sub in ("ui/fonts/ttf", "fonts", ".")]
_ASSET_WARNED = set()
FALLBACK_FONT = "Malgun Gothic"

SAND = QtGui.QColor(238, 226, 200)
SAND_MARK = QtGui.QColor(221, 205, 172)
HOLE_DARK = QtGui.QColor(66, 42, 34)
HOLE_RIM = QtGui.QColor(122, 84, 62)
HOLE_EDGE = QtGui.QColor(70, 45, 35)
INK = QtGui.QColor(74, 52, 40)
INK_SOFT = QtGui.QColor(120, 95, 78)
CARD = QtGui.QColor(255, 249, 240)
EDGE = QtGui.QColor(150, 115, 85)
WHITE = QtGui.QColor(255, 255, 255)
GREEN = QtGui.QColor(70, 180, 110)
YELLOW = QtGui.QColor(248, 196, 60)
RED = QtGui.QColor(224, 88, 80)
ORANGE = QtGui.QColor(242, 130, 40)
SKY = QtGui.QColor(59, 142, 234)
PEACH = QtGui.QColor(255, 235, 200)


def _load_pixmap(name):
    for d in ASSET_DIRS:
        path = d / name
        if path.exists():
            pm = QtGui.QPixmap(str(path))
            if not pm.isNull():
                return pm
    if name not in _ASSET_WARNED:
        _ASSET_WARNED.add(name)
        print(f"[그림] {name} 을(를) 못 찾았어요 → 직접 그린 그림을 씁니다. "
              f"minigames.py 를 main.py 가 있는 폴더(ui/assets 가 보이는 곳)에 두고 실행하세요.")
    return None


def _vector_mole_ops(hit):
    """mole.png 가 없을 때 쓰는 직접 그린 두더지의 설계도 (좌표는 그림 크기에 대한 비율)."""
    BROWN, BROWN2, TAN = (150, 100, 70), (128, 84, 58), (206, 162, 122)
    PINK, CHEEK, WHITE_, INK_ = (236, 150, 160), (222, 140, 120), (255, 255, 255), (75, 50, 38)
    ops = [
        ("ellipse", (0.22, 0.17, 0.36, 0.31), BROWN2), ("ellipse", (0.64, 0.17, 0.78, 0.31), BROWN2),
        ("ellipse", (0.20, 0.16, 0.80, 0.84), BROWN),
        ("ellipse", (0.30, 0.46, 0.39, 0.54), CHEEK), ("ellipse", (0.61, 0.46, 0.70, 0.54), CHEEK),
        ("ellipse", (0.35, 0.47, 0.65, 0.69), TAN), ("ellipse", (0.45, 0.475, 0.55, 0.545), PINK),
        ("line", (0.50, 0.545, 0.50, 0.600)),
        ("ellipse", (0.465, 0.595, 0.498, 0.655), WHITE_), ("ellipse", (0.502, 0.595, 0.535, 0.655), WHITE_),
        ("ellipse", (0.36, 0.29, 0.44, 0.40), WHITE_), ("ellipse", (0.56, 0.29, 0.64, 0.40), WHITE_),
    ]
    if hit:
        for ex in (0.40, 0.60):
            ops += [("line", (ex - 0.03, 0.325, ex + 0.03, 0.375)), ("line", (ex - 0.03, 0.375, ex + 0.03, 0.325))]
    else:
        ops += [("ellipse", (0.375, 0.325, 0.425, 0.385), INK_), ("ellipse", (0.575, 0.325, 0.625, 0.385), INK_)]
    ops += [("ellipse", (0.29, 0.73, 0.43, 0.86), TAN), ("ellipse", (0.57, 0.73, 0.71, 0.86), TAN)]
    for px in (0.31, 0.36, 0.41, 0.59, 0.64, 0.69):
        ops.append(("line", (px, 0.84, px - 0.005, 0.89)))
    return ops


def _vector_mole(S, hit):
    S = int(S)
    pm = QtGui.QPixmap(S, S)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    line = QtGui.QPen(QtGui.QColor(75, 50, 38), max(2.0, S * 0.012))
    line.setCapStyle(QtCore.Qt.RoundCap)
    for op in _vector_mole_ops(hit):
        p.setPen(line)
        if op[0] == "ellipse":
            (x0, y0, x1, y1), fill = op[1], op[2]
            p.setBrush(QtGui.QColor(*fill))
            p.drawEllipse(QtCore.QRectF(S * x0, S * y0, S * (x1 - x0), S * (y1 - y0)))
        else:
            x0, y0, x1, y1 = op[1]
            p.drawLine(QtCore.QPointF(S * x0, S * y0), QtCore.QPointF(S * x1, S * y1))
    p.end()
    return pm


class Sounds:
    """효과음. QtMultimedia 가 없거나 소리 장치가 없으면 조용히 건너뜀."""

    def __init__(self, enabled=True):
        self.fx = {}
        if not enabled:
            return
        try:
            from PyQt5.QtMultimedia import QSoundEffect
            d = Path(tempfile.mkdtemp(prefix="minigame_snd_"))
            for name, spec in TONES.items():
                path = d / f"{name}.wav"
                write_tone(path, spec)
                e = QSoundEffect()
                e.setSource(QtCore.QUrl.fromLocalFile(str(path)))
                e.setVolume(0.6)
                self.fx[name] = e
        except Exception as ex:               # 소리가 안 나도 게임은 돌아가야 함
            print(f"[소리] 효과음을 쓸 수 없어요({ex}) → 소리 없이 진행합니다.")
            self.fx = {}

    def play(self, name):
        e = self.fx.get(name)
        if e is not None:
            e.play()


# ── 그림 도구 (여러 곳에서 같이 씀) ──
def _poly(points):
    return QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in points])


def draw_star(p, x, y, r, fill, angle=0.0, edge=INK):
    pts = []
    for i in range(10):
        a = math.radians(i * 36 - 90 + angle)
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
    p.setPen(QtGui.QPen(edge, max(2.0, r * 0.07)))
    p.setBrush(fill)
    p.drawPolygon(_poly(pts))


def draw_bomb(p, x, y, r, now):
    p.setPen(QtGui.QPen(INK, max(2.0, r * 0.07)))
    p.setBrush(QtGui.QColor(55, 50, 62))
    p.drawEllipse(QtCore.QPointF(x, y + 0.12 * r), 0.82 * r, 0.82 * r)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(QtGui.QColor(255, 255, 255, 120))
    p.drawEllipse(QtCore.QRectF(x - 0.5 * r, y - 0.42 * r, 0.36 * r, 0.24 * r))
    p.setPen(QtGui.QPen(INK, max(2.0, r * 0.07)))
    p.setBrush(QtGui.QColor(120, 120, 130))
    p.drawRoundedRect(QtCore.QRectF(x - 0.22 * r, y - 0.82 * r, 0.44 * r, 0.26 * r), 3, 3)
    pen = QtGui.QPen(INK, max(3.0, r * 0.09))
    pen.setCapStyle(QtCore.Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QtCore.QPointF(x, y - 0.82 * r), QtCore.QPointF(x + 0.26 * r, y - 1.05 * r))
    flick = 0.7 + 0.3 * math.sin(now * 25)
    draw_star(p, x + 0.30 * r, y - 1.10 * r, 0.30 * r * flick, YELLOW, now * 90)


def draw_shape(p, shape, x, y, r, color, edge=INK):
    p.setPen(QtGui.QPen(edge, max(2.0, r * 0.07)))
    p.setBrush(QtGui.QColor(*color) if isinstance(color, tuple) else color)
    if shape == "circle":
        p.drawEllipse(QtCore.QPointF(x, y), r, r)
    elif shape == "square":
        p.drawRoundedRect(QtCore.QRectF(x - 0.85 * r, y - 0.85 * r, 1.7 * r, 1.7 * r), 0.2 * r, 0.2 * r)
    elif shape == "diamond":
        p.drawPolygon(_poly([(x, y - 1.1 * r), (x + 0.9 * r, y), (x, y + 1.1 * r), (x - 0.9 * r, y)]))
    elif shape == "triangle":
        p.drawPolygon(_poly([(x, y - 1.0 * r), (x + 1.0 * r, y + 0.8 * r), (x - 1.0 * r, y + 0.8 * r)]))
    else:
        draw_star(p, x, y, r * 1.1, QtGui.QColor(*color) if isinstance(color, tuple) else color, edge=edge)


class MiniGameWindow(QtWidgets.QWidget):
    def __init__(self, windowed=False, mute=False, hide_cursor=False, gaze_port=GAZE_PORT, calib_port=CALIB_PORT):
        super().__init__()
        geo = QtWidgets.QApplication.primaryScreen().geometry()
        if windowed:
            self.setWindowTitle("시선 미니게임")
            self.resize(1280, 720)
        else:
            self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
            self.setGeometry(geo)
        self.hide_cursor = hide_cursor
        if hide_cursor:
            self.setCursor(QtCore.Qt.BlankCursor)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        self.fonts_family = self._load_font()
        self.sounds = Sounds(not mute)
        self.gaze = GazeListener(gaze_port)
        self.calib_port = calib_port
        self._cs = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.mode, self.idx, self.game = "menu", 0, None        # mode: menu / howto / game
        self.slide, self.slide_t = 0, -10.0
        self.bdwell = Dwell()
        self._lock, self._lock_t = "*", time.time()             # 화면이 바뀐 직후엔 버튼에서 시선을 한 번 떼야 눌림
        self.ptr, self.ptr_src = None, "mouse"
        self._bg_cache, self._pix = {}, {}

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    # ═════════ 보정 데이터 보내기 ═════════
    def _send_target(self, x, y):
        """맞힌 별·두더지의 화면 좌표를 눈동자 마우스에 알려줌 (UDP, 이 PC 안에서만). 받는 쪽이 없으면 그냥 버려짐."""
        if not self.calib_port:
            return
        try:
            g = self.mapToGlobal(QtCore.QPoint(int(x), int(y)))
            self._cs.sendto(f"T,{g.x()},{g.y()}".encode(), ("127.0.0.1", self.calib_port))
        except OSError:
            pass

    # ═════════ 입력 ═════════
    def _pointer(self, now):
        g = self.gaze.poll(now)
        if g is not None:
            self.ptr_src = "gaze"
            loc = self.mapFromGlobal(QtCore.QPoint(int(g[0]), int(g[1])))
        else:
            self.ptr_src = "mouse"
            loc = self.mapFromGlobal(QtGui.QCursor.pos())
        return loc.x(), loc.y()

    def _buttons(self, now):
        w, h = self.width(), self.height()
        L = layout(w, h)
        if self.mode == "menu":
            return [Btn("howto", "rect", L["howto"], MENU_DWELL),
                    Btn("prev", "circle", L["prev"], MENU_DWELL),
                    Btn("next", "circle", L["next"], MENU_DWELL),
                    Btn("card", "rect", L["card"], MENU_DWELL)]
        if self.mode == "howto":
            return [Btn("close", "rect", L["close"], MENU_DWELL)]
        out = [Btn("exit", "rect", L["exit"], EXIT_DWELL)]
        if self.game is not None and self.game.state == "result" and now - self.game.t_state >= RESULT_ARM_SEC:
            out += [Btn("retry", "rect", L["retry"], MENU_DWELL), Btn("tomenu", "rect", L["tomenu"], MENU_DWELL)]
        return out

    def _buttons_step(self, now, ptr):
        btns = self._buttons(now)
        hit = None
        if ptr is not None:
            pad = self.height() * 0.012                          # 시선 오차를 감안해 버튼을 살짝 넉넉하게
            hit = next((b for b in btns if b.contains(ptr[0], ptr[1], pad)), None)
        key = hit.key if hit else None
        if self._lock == "*":                                    # 화면이 바뀐 직후: 버튼에서 벗어날 때까지 무시
            if key is None and now - self._lock_t > 0.3:
                self._lock = None
            self.bdwell.reset()
            return
        if self._lock is not None:                               # 방금 누른 버튼: 한 번 벗어나야 다시 눌림
            if key != self._lock:
                self._lock = None
            else:
                self.bdwell.reset()
                return
        if self.bdwell.step(key, now, hit.need if hit else 1.0):
            self._activate(key, now)

    def _activate(self, key, now):
        n = len(GAMES)
        lock = "*"
        if key in ("prev", "next"):
            self.idx = (self.idx + (-1 if key == "prev" else 1)) % n
            self.slide, self.slide_t = (-1 if key == "prev" else 1), now
            self.sounds.play("select")
            lock = key
        elif key == "card":
            self._start_game(now)
        elif key == "howto":
            self.mode = "howto"
            self.sounds.play("select")
        elif key == "close":
            self.mode = "menu"
            self.sounds.play("select")
        elif key in ("exit", "tomenu"):
            self.mode = "menu"
            self.sounds.play("select")
        elif key == "retry" and self.game is not None:
            self.game.start(now)
            self.sounds.play("start")
        self._lock, self._lock_t = lock, now
        self.bdwell.reset()

    def _start_game(self, now):
        self.game = GAMES[self.idx](self.width(), self.height())
        self.game.start(now)
        self.mode = "game"
        self.sounds.play("start")

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:               # 테스트용: 클릭하면 버튼이 바로 눌림
            now = time.time()
            for b in self._buttons(now):
                if b.contains(event.x(), event.y()):
                    self._activate(b.key, now)
                    break

    def keyPressEvent(self, event):
        key, now = event.key(), time.time()
        K = QtCore.Qt
        if key == K.Key_Escape:
            if self.mode == "menu":
                self.close()
            else:
                self.mode = "menu"
                self._lock, self._lock_t = "*", now
        elif self.mode == "menu" and key in (K.Key_Left, K.Key_Right):
            self._activate("prev" if key == K.Key_Left else "next", now)
        elif self.mode == "menu" and key in (K.Key_Return, K.Key_Enter, K.Key_Space):
            self._activate("card", now)
        elif self.mode == "menu" and key == K.Key_H:
            self._activate("howto", now)
        elif self.mode == "howto" and key in (K.Key_Return, K.Key_Enter, K.Key_Space, K.Key_H):
            self._activate("close", now)
        elif self.mode == "game" and key == K.Key_R:
            self._activate("retry", now)

    def showEvent(self, event):
        super().showEvent(event)
        self.activateWindow()
        self.setFocus()

    def _tick(self):
        now = time.time()
        w, h = self.width(), self.height()
        self.ptr = self._pointer(now)
        if self.mode == "game" and self.game is not None:
            self.game.set_size(w, h)
            self.game.update(now, self.ptr)
            for ev in self.game.pop_events():
                self.sounds.play(ev)
            for sx, sy, _t in self.game.pop_samples():
                self._send_target(sx, sy)
        self._buttons_step(now, self.ptr)
        self.update()

    # ═════════ 글꼴 / 그림 준비 ═════════
    def _load_font(self):
        for f in FONT_FILES:
            if f.exists():
                fid = QtGui.QFontDatabase.addApplicationFont(str(f))
                fams = QtGui.QFontDatabase.applicationFontFamilies(fid) if fid != -1 else []
                if fams:
                    return fams[0]
        return FALLBACK_FONT

    def _font(self, px, bold=True):
        f = QtGui.QFont(self.fonts_family)
        f.setPixelSize(max(8, int(px)))
        f.setBold(bold)
        return f

    def _mole_pix(self, name, S):
        """name: mole / hit / hammer. 크기별로 한 번만 만들어 둠."""
        S = int(S)
        key = (name, S)
        if key in self._pix:
            return self._pix[key]
        smooth, keep = QtCore.Qt.SmoothTransformation, QtCore.Qt.KeepAspectRatio
        if name == "hammer":
            src = _load_pixmap("hammer.png")
            pm = src.scaledToHeight(int(S * 1.1), smooth) if src else None
        else:
            src = _load_pixmap("mole.png" if name == "mole" else "mole_hit.png")
            pm = src.scaled(S, S, keep, smooth) if src else _vector_mole(S, name == "hit")
        self._pix[key] = pm
        return pm

    def _bg(self, kind):
        """모래색 땅 + 흙 자국 (두더지는 구멍 9개까지) 을 한 장으로 미리 그려 둠."""
        w, h = self.width(), self.height()
        key = (kind, w, h)
        if key in self._bg_cache:
            return self._bg_cache[key]
        if len(self._bg_cache) > 6:
            self._bg_cache.clear()
        pix = QtGui.QPixmap(w, h)
        pix.fill(SAND)
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        rng = random.Random(7)
        pen = QtGui.QPen(SAND_MARK, 3.5)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen)
        for _ in range(int(w * h / 9000)):
            x, y = rng.uniform(0, w), rng.uniform(0, h)
            length, ang = rng.uniform(10, 34), math.radians(rng.uniform(-14, 14))
            dx, dy = math.cos(ang) * length / 2, math.sin(ang) * length / 2
            p.drawLine(QtCore.QPointF(x - dx, y - dy), QtCore.QPointF(x + dx, y + dy))
        if kind == "mole" and self.game is not None:
            S = self.game.S
            for cx, cy in self.game.holes:
                p.save()
                p.translate(cx, cy - MOLE_NOSE_Y * S + MOLE_BOTTOM_Y * S)
                self._draw_hole(p, S)
                p.restore()
        p.end()
        self._bg_cache[key] = pix
        return pix

    def _draw_hole(self, p, S):
        y = (HOLE_MID_Y + 0.02 - MOLE_BOTTOM_Y) * S
        p.setPen(QtGui.QPen(HOLE_EDGE, 3))
        p.setBrush(HOLE_RIM)
        p.drawEllipse(QtCore.QPointF(0, y), 0.39 * S, 0.105 * S)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(HOLE_DARK)
        p.drawEllipse(QtCore.QPointF(0, y + 0.004 * S), 0.33 * S, 0.075 * S)

    # ═════════ 글씨 ═════════
    def _outlined_text(self, p, x, y, text, font, fill, outline, width, alpha=1.0, align="c"):
        fm = QtGui.QFontMetricsF(font)
        tw = fm.horizontalAdvance(text)
        left = x - tw / 2 if align == "c" else (x if align == "l" else x - tw)
        path = QtGui.QPainterPath()
        path.addText(left, y + (fm.ascent() - fm.descent()) / 2, font, text)
        out_c, fill_c = QtGui.QColor(outline), QtGui.QColor(fill)
        out_c.setAlphaF(alpha)
        fill_c.setAlphaF(alpha)
        pen = QtGui.QPen(out_c, width)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawPath(path)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(fill_c)
        p.drawPath(path)

    def _text(self, p, x, y, text, px, color=INK, align="c", bold=True):
        """테두리 없는 보통 글씨. y 는 글씨의 세로 가운데."""
        p.setPen(color)
        p.setFont(self._font(px, bold))
        flag = {"c": QtCore.Qt.AlignCenter, "l": QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                "r": QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter}[align]
        bw = 4000.0
        left = x - bw / 2 if align == "c" else (x if align == "l" else x - bw)
        p.drawText(QtCore.QRectF(left, y - px, bw, 2 * px), flag, text)

    # ═════════ 그리기 ═════════
    def paintEvent(self, event):
        now = time.time()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        if self.mode == "game" and self.game is not None:
            self._paint_game(p, now)
        else:
            self._paint_menu(p, now)
            if self.mode == "howto":
                self._paint_howto(p, now)
        self._paint_pointer(p)

    def _paint_pointer(self, p):
        """시선 점. 마우스 커서가 그대로 보이는 상태(마우스 모드)에선 그리지 않음."""
        if self.ptr is None or (self.ptr_src == "mouse" and not self.hide_cursor):
            return
        r = self.height() * 0.014
        x, y = self.ptr
        p.setBrush(QtCore.Qt.NoBrush)
        p.setPen(QtGui.QPen(INK, 7))
        p.drawEllipse(QtCore.QPointF(x, y), r, r)
        p.setPen(QtGui.QPen(WHITE, 3.5))
        p.drawEllipse(QtCore.QPointF(x, y), r, r)

    def _progress_of(self, key):
        return self.bdwell.progress if self.bdwell.key == key else 0.0

    def _draw_button(self, p, rect, label, pr, fill=CARD, px=None):
        x0, y0, x1, y1 = rect
        r = QtCore.QRectF(x0, y0, x1 - x0, y1 - y0)
        rad = (y1 - y0) / 2
        p.setPen(QtGui.QPen(INK, 4))
        p.setBrush(fill)
        p.drawRoundedRect(r, rad, rad)
        if pr > 0:
            path = QtGui.QPainterPath()
            path.addRoundedRect(r, rad, rad)
            p.save()
            p.setClipPath(path)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(70, 180, 110, 170))
            p.drawRect(QtCore.QRectF(x0, y0, (x1 - x0) * pr, y1 - y0))
            p.restore()
        self._text(p, (x0 + x1) / 2, (y0 + y1) / 2, label, px or (y1 - y0) * 0.5)

    def _draw_arrow(self, p, geom, left, pr):
        cx, cy, r = geom
        p.setPen(QtGui.QPen(INK, 5))
        p.setBrush(CARD)
        p.drawEllipse(QtCore.QPointF(cx, cy), r, r)
        if pr > 0:
            p.setBrush(QtCore.Qt.NoBrush)
            pen = QtGui.QPen(GREEN, 9)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(QtCore.QRectF(cx - r * 1.12, cy - r * 1.12, r * 2.24, r * 2.24), 90 * 16, int(-360 * 16 * pr))
        d = r * 0.32 * (-1 if left else 1)
        pen = QtGui.QPen(INK, max(6.0, r * 0.18))
        pen.setCapStyle(QtCore.Qt.RoundCap)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        p.setPen(pen)
        p.drawLine(QtCore.QPointF(cx - d * 0.6, cy - r * 0.42), QtCore.QPointF(cx + d * 0.6, cy))
        p.drawLine(QtCore.QPointF(cx + d * 0.6, cy), QtCore.QPointF(cx - d * 0.6, cy + r * 0.42))

    # ── 메뉴 ──
    def _paint_menu(self, p, now):
        w, h = self.width(), self.height()
        L = layout(w, h)
        p.drawPixmap(0, 0, self._bg("menu"))
        self._outlined_text(p, w / 2, h * 0.055, "눈으로 하는 미니게임", self._font(h * 0.062), WHITE, INK, 9)

        g = GAMES[self.idx]
        k = max(0.0, 1.0 - (now - self.slide_t) / 0.22)
        cw, ch = L["card_size"]
        x0, y0, x1, y1 = L["card"]
        p.save()
        p.translate(self.slide * k * cw * 0.35, 0)
        p.setOpacity(1.0 - 0.6 * k)
        p.setPen(QtGui.QPen(EDGE, 5))
        p.setBrush(CARD)
        p.drawRoundedRect(QtCore.QRectF(x0, y0, cw, ch), cw * 0.09, cw * 0.09)
        qx, qy, qw, qh = x0 + cw * 0.07, y0 + ch * 0.05, cw * 0.86, ch * 0.54       # 그림 칸
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(g.accent[0], g.accent[1], g.accent[2], 70))
        p.drawRoundedRect(QtCore.QRectF(qx, qy, qw, qh), cw * 0.06, cw * 0.06)
        self._draw_icon(p, g.kind, qx + qw / 2, qy + qh / 2, qh, now)
        self._text(p, (x0 + x1) / 2, y0 + ch * 0.68, g.title, cw * 0.115)
        for i, line in enumerate(g.tagline.split("\n")):
            self._text(p, (x0 + x1) / 2, y0 + ch * 0.775 + i * cw * 0.085, line, cw * 0.063, INK_SOFT, bold=False)
        bx, by, bw, bh = x0 + cw * 0.12, y0 + ch * 0.90, cw * 0.76, ch * 0.05
        p.setPen(QtGui.QPen(INK, 3))
        p.setBrush(PEACH)
        p.drawRoundedRect(QtCore.QRectF(bx, by, bw, bh), bh / 2, bh / 2)
        pr = self._progress_of("card")
        if pr > 0:
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(GREEN)
            p.drawRoundedRect(QtCore.QRectF(bx + 3, by + 3, max(bh - 6, (bw - 6) * pr), bh - 6),
                              (bh - 6) / 2, (bh - 6) / 2)
        self._text(p, bx + bw / 2, by + bh / 2, "바라보면 시작!", bh * 0.58)
        p.restore()

        self._draw_button(p, L["howto"], "게임방법", self._progress_of("howto"), PEACH)
        self._draw_arrow(p, L["prev"], True, self._progress_of("prev"))
        self._draw_arrow(p, L["next"], False, self._progress_of("next"))
        n = len(GAMES)
        for i in range(n):                                                    # 페이지 점
            px = w / 2 + (i - (n - 1) / 2) * h * 0.04
            p.setPen(QtGui.QPen(INK, 2))
            p.setBrush(ORANGE if i == self.idx else CARD)
            rr = h * (0.0135 if i == self.idx else 0.01)
            p.drawEllipse(QtCore.QPointF(px, y1 + h * 0.05), rr, rr)
        p.setPen(INK_SOFT)
        p.setFont(self._font(h * 0.02, bold=False))
        p.drawText(QtCore.QRectF(0, 0, w - 24, h - 14), QtCore.Qt.AlignRight | QtCore.Qt.AlignBottom,
                   "←/→ 고르기   Enter 시작   H 게임방법   ESC 종료")

    def _draw_icon(self, p, kind, cx, cy, size, now):
        s = size
        if kind == "mole":
            S = int(s * 0.85)
            p.save()
            p.translate(cx, cy + s * 0.36)
            self._draw_hole(p, S)
            p.restore()
            p.drawPixmap(QtCore.QPointF(cx - S / 2, cy + s * 0.36 - MOLE_BOTTOM_Y * S - 4 * math.sin(now * 3)),
                         self._mole_pix("mole", S))
        elif kind in ("sparkle", "bombs"):
            draw_star(p, cx - s * 0.18, cy - s * 0.08, s * 0.24, YELLOW, math.sin(now * 2) * 10)
            draw_star(p, cx + s * 0.22, cy + s * 0.14, s * 0.17, QtGui.QColor(255, 220, 110), -math.sin(now * 2) * 10)
            if kind == "bombs":
                draw_bomb(p, cx + s * 0.18, cy - s * 0.12, s * 0.2, now)
            else:
                draw_star(p, cx + s * 0.12, cy - s * 0.3, s * 0.1, QtGui.QColor(255, 240, 160))
        elif kind == "numbers":
            for i, (dx, dy) in enumerate(((-0.22, -0.12), (0.2, -0.2), (0.02, 0.2))):
                self._draw_number(p, cx + dx * s, cy + dy * s, s * 0.15, i + 1, "live")
        elif kind == "track":
            for i in range(8):
                a = now * 1.5 - i * 0.28
                x, y = cx + math.sin(a) * s * 0.3, cy + math.sin(a * 1.31) * s * 0.2
                c = QtGui.QColor(59, 142, 234, int(255 * (1 - i / 8)))
                p.setPen(QtCore.Qt.NoPen)
                p.setBrush(c)
                rr = s * 0.13 * (1 - i * 0.07)
                p.drawEllipse(QtCore.QPointF(x, y), rr, rr)
        else:                                                                 # odd
            base = QtGui.QColor(120, 190, 240)
            for i in range(4):
                dx, dy = (i % 2 - 0.5) * s * 0.34, (i // 2 - 0.5) * s * 0.34
                if i == 3:
                    draw_shape(p, "star", cx + dx, cy + dy, s * 0.13, QtGui.QColor(240, 150, 90))
                else:
                    draw_shape(p, "circle", cx + dx, cy + dy, s * 0.13, base)

    def _draw_number(self, p, x, y, r, n, state, alpha=1.0):
        p.setPen(QtGui.QPen(INK, max(3.0, r * 0.07)))
        p.setBrush(QtGui.QColor(70, 180, 110) if state == "done" else CARD)
        p.drawEllipse(QtCore.QPointF(x, y), r, r)
        self._text(p, x, y, str(n), r * 1.15, INK)

    # ── 게임방법 ──
    def _paint_howto(self, p, now):
        w, h = self.width(), self.height()
        L = layout(w, h)
        g = GAMES[self.idx]
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, 150))
        p.drawRect(QtCore.QRectF(0, 0, w, h))
        pw, ph = min(w * 0.85, h * 1.2), h * 0.62
        px0, py0 = (w - pw) / 2, h * 0.14
        p.setPen(QtGui.QPen(EDGE, 5))
        p.setBrush(CARD)
        p.drawRoundedRect(QtCore.QRectF(px0, py0, pw, ph), h * 0.04, h * 0.04)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(g.accent[0], g.accent[1], g.accent[2], 90))
        p.drawRoundedRect(QtCore.QRectF(px0 + pw * 0.03, py0 + h * 0.025, pw * 0.94, h * 0.1), h * 0.03, h * 0.03)
        self._text(p, w / 2, py0 + h * 0.075, f"{g.title} · 게임 방법", h * 0.05)
        for i, line in enumerate(g.howto):
            self._text(p, px0 + pw * 0.08, py0 + h * 0.19 + i * h * 0.075, f"{i + 1}.  {line}", h * 0.035, INK, "l", bold=False)
        self._draw_button(p, L["close"], "알겠어요!", self._progress_of("close"), PEACH)

    # ── 게임 화면 ──
    def _paint_game(self, p, now):
        g, w, h = self.game, self.width(), self.height()
        L = layout(w, h)
        p.drawPixmap(0, 0, self._bg("mole" if g.kind == "mole" else "plain"))
        {"mole": self._draw_mole_game, "sparkle": self._draw_item_game, "bombs": self._draw_item_game,
         "numbers": self._draw_number_game, "track": self._draw_track_game, "odd": self._draw_odd_game}[g.kind](p, now)

        ring = g.ring                                                        # 바라보는 중인 대상에 차오르는 링
        if ring is not None and ring[3] > 0:
            x, y, r, pr = ring
            p.setBrush(QtCore.Qt.NoBrush)
            p.setPen(QtGui.QPen(WHITE, 12))
            p.drawEllipse(QtCore.QPointF(x, y), r, r)
            pen = QtGui.QPen(GREEN, 8)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(QtCore.QRectF(x - r, y - r, 2 * r, 2 * r), 90 * 16, int(-360 * 16 * pr))
        for e in g.effects:
            self._draw_effect(p, e, now)
        if now - g.flash_t < 0.3:                                            # 폭탄을 봤을 때 붉은 번쩍임
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(224, 60, 50, int(130 * (1 - (now - g.flash_t) / 0.3))))
            p.drawRect(QtCore.QRectF(0, 0, w, h))

        self._draw_hud(p, now)
        self._draw_button(p, L["exit"], "나가기", self._progress_of("exit"), CARD)
        if g.state == "intro":
            t = now - g.t_state
            self._outlined_text(p, w / 2, h * 0.5, g.title, self._font(h * 0.07), WHITE, INK, 9)
            self._outlined_text(p, w / 2, h * 0.62, "준비~" if t < 0.55 else "시작!", self._font(h * 0.11), YELLOW, INK, 10)
        elif g.state == "result":
            self._draw_result(p, now, L)

    def _draw_hud(self, p, now):
        g, w, h = self.game, self.width(), self.height()
        size = h * 0.062
        self._outlined_text(p, w * 0.03, h * 0.058, f"점수 {g.score}", self._font(size), WHITE, INK, 7, align="l")
        sub = g.hud_extra(now)
        if g.combo >= 2:
            sub = f"콤보 x{g.combo}!"
        if sub:
            self._outlined_text(p, w * 0.03, h * 0.115, sub, self._font(h * 0.036), YELLOW, INK, 5, align="l")
        bar_w, bar_h = w * 0.30, h * 0.03
        x0, y0 = (w - bar_w) / 2, h * 0.04
        frac = g.time_left(now) / g.round_sec
        p.setPen(QtGui.QPen(INK, 4))
        p.setBrush(QtGui.QColor(255, 255, 255, 200))
        p.drawRoundedRect(QtCore.QRectF(x0, y0, bar_w, bar_h), bar_h / 2, bar_h / 2)
        if frac > 0:
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(RED if frac < 0.2 else GREEN)
            p.drawRoundedRect(QtCore.QRectF(x0 + 3, y0 + 3, max(bar_h - 6, (bar_w - 6) * frac), bar_h - 6),
                              (bar_h - 6) / 2, (bar_h - 6) / 2)
        self._outlined_text(p, w / 2, y0 + bar_h + h * 0.03, f"{math.ceil(g.time_left(now))}초", self._font(h * 0.03), WHITE, INK, 5)

    def _draw_result(self, p, now, L):
        g, w, h = self.game, self.width(), self.height()
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, 120))
        p.drawRect(QtCore.QRectF(0, 0, w, h))
        pw, ph = min(w * 0.85, h * 1.3), h * 0.5
        px0, py0 = (w - pw) / 2, h * 0.2
        p.setPen(QtGui.QPen(EDGE, 5))
        p.setBrush(CARD)
        p.drawRoundedRect(QtCore.QRectF(px0, py0, pw, ph), h * 0.04, h * 0.04)
        self._text(p, w / 2, py0 + h * 0.07, "게임 끝!", h * 0.06)
        self._text(p, w / 2, py0 + h * 0.18, f"점수 {g.score}점", h * 0.085, ORANGE)
        self._text(p, w / 2, py0 + h * 0.30, g.result_line(), h * 0.03, INK_SOFT, bold=False)
        if now - g.t_state >= RESULT_ARM_SEC:
            self._draw_button(p, L["retry"], "다시 하기", self._progress_of("retry"), PEACH)
            self._draw_button(p, L["tomenu"], "메뉴로", self._progress_of("tomenu"), CARD)

    def _draw_effect(self, p, e, now):
        age, g = now - e["t"], self.game
        if e["kind"] == "burst":
            k = min(age / 0.45, 1.0)
            if k >= 1.0:
                return
            col = QtGui.QColor(255, 205, 60) if e["good"] else QtGui.QColor(80, 80, 90)
            col.setAlphaF(1.0 - k)
            pen = QtGui.QPen(col, 6)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen)
            r0, r1 = 20 + 40 * k, 50 + 80 * k
            for i in range(10):
                a = i * math.tau / 10
                p.drawLine(QtCore.QPointF(e["x"] + r0 * math.cos(a), e["y"] + r0 * math.sin(a)),
                           QtCore.QPointF(e["x"] + r1 * math.cos(a), e["y"] + r1 * math.sin(a)))
        else:
            k = min(age / 0.9, 1.0)
            if k >= 1.0:
                return
            self._outlined_text(p, e["x"], e["y"] - 60 * k, e["text"], self._font(g.h * 0.06),
                                QtGui.QColor(*e["color"]), INK, 7, alpha=1.0 - k * k)

    # ── 게임별 그림 ──
    def _draw_mole_game(self, p, now):
        g = self.game
        for m in g.moles:
            self._draw_mole(p, m, now)

    def _draw_mole(self, p, m, now):
        g, S = self.game, self.game.S
        cx, cy = g.holes[m.hole]
        squash, rise, name = 1.0, 1.0, "mole"
        t = after = 0.0
        hitting, impact = m.state == "hit", False
        if m.state == "up":
            k = min((now - m.t0) / POP_SEC, 1.0)
            rise = 1 - (1 - k) ** 3
        elif m.state == "sink":
            rise = 1 - min((now - m.t_state) / SINK_SEC, 1.0)
        elif hitting:
            t = (now - m.t_state) / HIT_SEC
            impact = t >= HIT_AT
            after = min((t - HIT_AT) / (1 - HIT_AT), 1.0) if impact else 0.0
            squash = 1.0 - 0.22 * math.sin(after * math.pi) if impact else 1.0
            name = "hit" if impact else "mole"
        if rise <= 0.02:
            return
        top = cy - MOLE_NOSE_Y * S
        p.save()
        p.translate(cx, top + MOLE_BOTTOM_Y * S)
        if rise < 1.0:
            self._draw_hole(p, S)
            clip_bottom = (HOLE_MID_Y + (1.0 - HOLE_MID_Y) * rise ** 2 - MOLE_BOTTOM_Y) * S
            p.setClipRect(QtCore.QRectF(-S, -2 * S, 2 * S, 2 * S + clip_bottom))
            p.translate(0, (1.0 - rise) * RISE_DEPTH * S)
        p.scale(1.0, squash)
        p.drawPixmap(QtCore.QPointF(-S / 2, -MOLE_BOTTOM_Y * S), self._mole_pix(name, S))
        p.restore()
        if hitting:
            hammer = self._mole_pix("hammer", S)
            if hammer is not None:
                angle = 28 - 78 * (t / HIT_AT) ** 2 if t < HIT_AT else -50 + 8 * math.sin(after * math.pi)
                pw, ph = hammer.width(), hammer.height()
                p.save()
                p.translate(cx + 0.60 * S, cy + 0.16 * S)
                p.rotate(angle)
                p.drawPixmap(QtCore.QPointF(-pw / 2, -HAMMER_PIVOT_Y * ph), hammer)
                p.restore()
            if impact:
                draw_star(p, cx - 0.28 * S, cy - 0.45 * S, 0.14 * S * max(0.05, math.sin(after * math.pi) * 1.15),
                          QtGui.QColor(255, 205, 60))

    def _draw_item_game(self, p, now):
        g = self.game
        for it in g.items:
            age = now - it.t_state
            if it.state == "live":
                pop = min((now - it.t0) / 0.12, 1.0)                         # 나타날 때 커지는 효과
                r = it.r * (0.4 + 0.6 * pop)
                if it.kind == "star":
                    draw_star(p, it.x, it.y, r, YELLOW, math.sin(now * 3 + it.id) * 12)
                else:
                    draw_bomb(p, it.x, it.y, r, now)
                left = max(0.0, 1.0 - (now - it.t0) / it.life)                # 남은 시간 가는 호
                p.setBrush(QtCore.Qt.NoBrush)
                pen = QtGui.QPen(RED if it.kind == "bomb" else QtGui.QColor(255, 255, 255, 190), 5)
                pen.setCapStyle(QtCore.Qt.RoundCap)
                p.setPen(pen)
                p.drawArc(QtCore.QRectF(it.x - r * 1.3, it.y - r * 1.3, r * 2.6, r * 2.6), 90 * 16, int(360 * 16 * left))
            elif it.state == "gone":
                p.save()
                p.setOpacity(max(0.0, 1.0 - age / 0.35))
                if it.kind == "star":
                    draw_star(p, it.x, it.y, it.r * (1 - age), QtGui.QColor(200, 190, 150))
                else:
                    draw_bomb(p, it.x, it.y, it.r * (1 - age), now)
                p.restore()

    def _draw_number_game(self, p, now):
        g = self.game
        for m in g.nums:
            if m["state"] == "done":
                k = (now - m["t"]) / 0.3
                self._draw_number(p, m["x"], m["y"], g.r * max(0.1, 1.0 - 0.5 * k), m["n"], "done")
            else:
                self._draw_number(p, m["x"], m["y"], g.r, m["n"], "live")

    def _draw_track_game(self, p, now):
        g = self.game
        n = len(g.trail)
        for i, (x, y) in enumerate(g.trail[:-1]):
            c = QtGui.QColor(59, 142, 234, int(120 * (i + 1) / max(1, n)))
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(c)
            rr = g.r * (0.4 + 0.5 * (i + 1) / max(1, n))
            p.drawEllipse(QtCore.QPointF(x, y), rr, rr)
        if g.locked:
            p.setBrush(QtCore.Qt.NoBrush)
            p.setPen(QtGui.QPen(GREEN, 12))
            p.drawEllipse(QtCore.QPointF(g.x, g.y), g.r * 1.45, g.r * 1.45)
        p.setPen(QtGui.QPen(INK, 5))
        p.setBrush(GREEN if g.locked else SKY)
        p.drawEllipse(QtCore.QPointF(g.x, g.y), g.r, g.r)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(255, 255, 255, 150))
        p.drawEllipse(QtCore.QRectF(g.x - g.r * 0.55, g.y - g.r * 0.6, g.r * 0.5, g.r * 0.32))

    def _draw_odd_game(self, p, now):
        g = self.game
        for c in g.cells:
            r = g.cell * 0.34
            if now - c["flash"] < 0.5:
                p.setPen(QtCore.Qt.NoPen)
                p.setBrush(QtGui.QColor(224, 88, 80, 150))
                p.drawEllipse(QtCore.QPointF(c["x"], c["y"]), r * 1.3, r * 1.3)
            draw_shape(p, c["shape"], c["x"], c["y"], r, c["color"])


def main():
    global GAME_DWELL, MENU_DWELL, LIFE_SCALE
    ap = argparse.ArgumentParser(description="눈동자 마우스 시연용 시선 미니게임 모음")
    ap.add_argument("--windowed", action="store_true", help="전체화면 대신 창으로 실행 (테스트용)")
    ap.add_argument("--mute", action="store_true", help="효과음 끄기")
    ap.add_argument("--hide-cursor", action="store_true", help="윈도우 마우스 커서 숨기기")
    ap.add_argument("--gaze-port", type=int, default=GAZE_PORT, help="눈동자 마우스가 시선을 보내는 UDP 포트 (0 = 안 받음)")
    ap.add_argument("--game-dwell", type=float, default=None, metavar="SEC", help=f"게임 중 인정 시간 (기본 {GAME_DWELL})")
    ap.add_argument("--menu-dwell", type=float, default=None, metavar="SEC", help=f"메뉴 버튼 인정 시간 (기본 {MENU_DWELL})")
    ap.add_argument("--life", type=float, default=None, metavar="배수", help=f"별·두더지가 머무는 시간 배수 (기본 {LIFE_SCALE}, 클수록 느긋)")
    ap.add_argument("--calib-port", type=int, default=CALIB_PORT, help="맞힌 별·두더지를 눈동자 마우스 자동 보정에 보내는 UDP 포트 (0 = 안 보냄)")
    args = ap.parse_args()
    if args.life is not None:
        LIFE_SCALE = max(0.5, args.life)
    if args.game_dwell is not None:
        GAME_DWELL = max(0.02, args.game_dwell)
    if args.menu_dwell is not None:
        MENU_DWELL = max(0.1, args.menu_dwell)

    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    app = QtWidgets.QApplication(sys.argv)
    win = MiniGameWindow(windowed=args.windowed, mute=args.mute, hide_cursor=args.hide_cursor, gaze_port=args.gaze_port, calib_port=args.calib_port)
    if args.windowed:
        win.show()
    else:
        win.showFullScreen()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
