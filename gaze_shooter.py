# -*- coding: utf-8 -*-
"""
gaze_shooter.py — 눈동자 마우스 시연용 "시선 슈터" 게임 (단독 실행 파일 1개)

이 파일 하나로 돌아갑니다. 프로젝트의 다른 .py 파일을 불러오지 않아요.
(글꼴은 프로젝트의 ui/fonts 폴더에 있으면 그걸 쓰고, 없으면 기본 글꼴로 대신합니다. 그림 파일은 필요 없어요)

실행
    python gaze_shooter.py                 전체화면 (ESC 로 나가기)
    python gaze_shooter.py --windowed      창 모드 (테스트용)
    python gaze_shooter.py --mute          효과음 끄기
    python gaze_shooter.py --hide-cursor   윈도우 마우스 커서를 숨김 (시선 점만 보이게)

게임 방법
    - 길이 왼쪽 / 가운데 / 오른쪽 3칸이에요. 바라보는 칸으로 군인 분대가 이동하고, 자동으로 사격합니다.
    - 위에서 외계인 무리가 내려와요. 무리 아래 숫자는 체력. 분대가 있는 칸의 가장 가까운 것을 쏩니다.
    - 무리가 맨 아래 선까지 내려오면 목숨이 1개 줄어요 (목숨 3개).
    - 초록 강화 상자(분대 +N명 / 화력 +N% / 수류탄 충전)도 외계인처럼 내려와요. 상자의 체력 숫자만큼 쏴서 부수면 강화를 얻어요.
      (못 부수고 지나가도 벌은 없어요. 대신 그 칸을 쏘는 동안 다른 칸의 외계인이 내려오니 선택!)
    - 진행: 외계인 무리 → 중간보스 1 → 무리 → 중간보스 2 → 무리 → 최종보스. 중간보스를 잡으면 목숨이 1개 회복돼요.
    - 보스는 붉게 경고하는 칸(한 칸 또는 두 칸)을 내려쳐요. 그 칸에 있으면 목숨이 줄어요. 피하세요!
      최종보스는 체력이 절반 이하가 되면 분노해서 더 빠르고 자주 내려칩니다.
    - 윙크(마우스 클릭) 또는 스페이스바 = 수류탄. 화면의 모든 외계인과 보스에게 큰 피해 (재사용 대기 30초)

화면 조작
    바라보기          시작 / 다시 하기 / 나가기 버튼 (실수로 눌리지 않게 0.5초, 나가기는 0.8초 바라보기)
    윙크 = 마우스 클릭   게임 중엔 수류탄, 버튼 위에선 바로 누름
    키보드            ← → 칸 이동(테스트용) / Space 수류탄 / Enter 시작 / R 다시 하기 / ESC 나가기

시선(눈동자 마우스)과 연결하는 법 — minigames.py 와 똑같습니다
    눈동자 마우스(main.py)가 시선 좌표를 UDP(127.0.0.1:47321)로 보내주면 그걸 시선으로 씁니다.
    시선 소식이 없으면(0.3초 이상) 자동으로 마우스 커서 위치를 시선처럼 씁니다.
    포트를 바꾸려면 --gaze-port 번호, 끄려면 --gaze-port 0

구성: 위쪽은 화면과 상관없는 게임 규칙(Game, Qt 없이 테스트 가능), 아래쪽이 PyQt5 화면입니다.
"""
import argparse
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
#  1. 설정 (숫자를 바꾸면 난이도가 바뀝니다)
# ════════════════════════════════════════════════════════════════
# 진행 순서: 외계인 무리 → 중간보스 1 → 무리 → 중간보스 2 → 무리 → 최종보스.  ("waves", 초) = 그 시간 동안 무리가 나옴
STAGES = (("waves", 30.0), ("boss", "mid1"), ("waves", 24.0), ("boss", "mid2"), ("waves", 24.0), ("boss", "final"))
BOSS_WAIT_SEC = 4.0          # 보스가 나오기 이 시간 전부터는 새 무리를 내보내지 않음
DIFF_RAMP = 150.0            # 이 시간(초)이 지나면 난이도가 최대가 됨 (무리 체력·속도·개수)

LANE_BOUNDS = (0.32, 0.68)   # 시선 가로 위치(화면 너비 비율)로 나눈 3칸의 경계 — 길 아래쪽 경계선과 맞춤
LANE_HYST = 0.035            # 경계에서 이만큼(화면 너비 비율) 더 넘어가야 칸이 바뀜 → 시선이 떨려도 칸이 깜빡이지 않음
LANE_FRAC = ((0.0, 0.30), (0.30, 0.70), (0.70, 1.0))   # 길 폭 기준 각 칸의 범위
LANE_MID = tuple((a + b) / 2 for a, b in LANE_FRAC)
PLAYER_D = 0.835             # 군인이 서 있는 깊이 (0 = 길 맨 위, 1 = 화면 맨 아래)
HIT_D = 0.78                 # 적·강화 상자가 이 깊이에 닿으면 처리

START_LIVES = 3
START_SQUAD = 3              # 처음 분대 인원
MAX_SQUAD = 8
DPS_PER_SOLDIER = 16.0       # 군인 한 명의 초당 피해
POWER_MIN, POWER_MAX = 0.5, 3.0   # 화력 배수 범위

SPAWN_GAP = (3.6, 2.2)
WAVE_SIZES = ((1, 55), (2, 37), (3, 8))     # 한 번에 나오는 무리 수와 비율(가중치)
SWARM_SPEED = (0.085, 0.12)  # 무리가 내려오는 속도(깊이/초): 처음 → 난이도 최대
SWARM_HP_BASE, SWARM_HP_PER_SEC, SWARM_HP_RAND = 130.0, 4.2, 60.0
SWARM_SPACING_D = 0.12       # 같은 칸에서 무리끼리 최소한 벌려 두는 거리(깊이)

BUFF_EVERY = 8.0             # 강화 상자가 나오는 간격(초)
BUFF_HP = (70.0, 170.0)
SPACING_D = 0.26             # 같은 칸에서 강화 상자와 외계인 무리 사이에 항상 벌려 두는 거리(깊이)
# 강화 종류: (글자, 종류, 값).  종류: squad = 분대 인원, power = 화력 배수에 더함, nade = 수류탄 바로 충전
BUFF_TYPES = [("분대 +2", "squad", 2), ("분대 +3", "squad", 3), ("화력 +30%", "power", 0.3),
              ("화력 +50%", "power", 0.5), ("수류탄 충전", "nade", 0)]

GRENADE_CD = 30.0            # 수류탄 재사용 대기(초)
GRENADE_DMG = 260.0
GRENADE_BOSS_DMG = 320.0

# 보스 3종. tele = 내려치기 전 경고 시간, idle = 다음 공격까지 쉬는 시간, double = 두 칸을 한꺼번에 내려칠 확률,
# summon_every = 몇 번 공격마다 부하를 부르는지, rage_* = 체력이 rage_hp 비율 이하가 되면 더 빨라지는 값
BOSSES = {
    "mid1": dict(name="중간보스 1", hp=1500.0, tele=1.5, idle=2.4, double=0.0, summon_every=2, summon_n=1, summon_hp=100,
                 size=0.80, body=(32, 168, 158), light=(112, 222, 210), reward=600),
    "mid2": dict(name="중간보스 2", hp=2600.0, tele=1.2, idle=2.0, double=0.30, summon_every=1, summon_n=1, summon_hp=130,
                 size=0.95, body=(232, 122, 32), light=(255, 186, 104), reward=900),
    "final": dict(name="최종보스", hp=5600.0, tele=1.0, idle=1.7, double=0.55, summon_every=1, summon_n=2, summon_hp=150,
                  rage_hp=0.5, rage_tele=0.75, rage_idle=1.1, rage_double=0.9,
                  size=1.22, body=(162, 77, 255), light=(197, 139, 255), reward=1500),
}
BOSS_D = 0.30                # 보스가 머무는 깊이
BOSS_ENTER_SEC = 3.0
BOSS_OFFLANE_MUL = 0.6       # 보스가 내려치려는 칸이 아닌 곳에서 쏠 때 주는 피해 비율
INVULN_SEC = 1.2             # 목숨을 잃은 직후 무적 시간

EFFECT_LIFE = 0.9
GAZE_PORT = 47321
GAZE_FRESH = 0.30            # 시선 소식이 이보다 오래되면 마우스를 씀
MENU_DWELL = 0.50            # 시작·다시하기 버튼
EXIT_DWELL = 0.80            # 나가기 버튼
GRACE = 0.06                 # 시선이 잠깐(이 시간 이하) 튀어도 바라보던 걸 이어서 셈
RESULT_ARM_SEC = 0.8         # 결과 화면에서 버튼이 눌리기 시작하는 시간


def lerp(a, b, k):
    return a + (b - a) * max(0.0, min(1.0, k))


# ════════════════════════════════════════════════════════════════
#  2. 게임 규칙 (화면과 무관 — 시간·좌표만 받아서 계산)
# ════════════════════════════════════════════════════════════════
class Swarm:
    """외계인 무리 하나. lane 0~2, d = 깊이(0 위 → 1 아래)."""
    __slots__ = ("lane", "d", "hp", "max_hp", "speed", "offs", "born")

    def __init__(self, lane, d, hp, speed, rng, born):
        self.lane, self.d, self.hp, self.max_hp, self.speed, self.born = lane, d, hp, hp, speed, born
        self.offs = [(rng.uniform(-1, 1), rng.uniform(-1, 1), rng.random()) for _ in range(30)]


class Buff:
    """강화 상자. 외계인처럼 내려오고, 체력만큼 쏴서 부수면 강화를 얻음 (못 부수고 지나가면 그냥 사라짐)."""
    __slots__ = ("lane", "d", "hp", "max_hp", "speed", "label", "kind", "val")

    def __init__(self, lane, hp, speed, spec):
        self.lane, self.d, self.hp, self.max_hp, self.speed = lane, 0.04, hp, hp, speed
        self.label, self.kind, self.val = spec


class Boss:
    """보스. phase: enter(내려오는 중) / idle(대기) / tele(경고) / slam(내려치는 순간). lanes = 내려칠 칸들."""
    __slots__ = ("key", "spec", "d", "hp", "max_hp", "lanes", "xf", "phase", "t0", "cycle", "rage")

    def __init__(self, key, now):
        self.key, self.spec = key, BOSSES[key]
        self.d, self.hp, self.max_hp = 0.0, self.spec["hp"], self.spec["hp"]
        self.lanes, self.xf = [1], LANE_MID[1]
        self.phase, self.t0, self.cycle, self.rage = "enter", now, 0, False

    @property
    def name(self):
        return self.spec["name"]


class Game:
    """
    상태:  play ─(최종보스 처치)→ win        play ─(목숨 0)→ lose
    사용법:  game.update(now, 시선x좌표 또는 None) 를 계속 부르고, 윙크(클릭)가 오면 game.grenade(now).
    소리는 game.pop_events() 로 이름만 받아서 화면 쪽에서 재생합니다.
    """

    def __init__(self, w, h, rng=None):
        self.rng = rng or random.Random()
        self.best = 0
        self.set_size(w, h)
        self.start(0.0)

    def set_size(self, w, h):
        self.w, self.h = w, h

    def start(self, now):
        self.state = "play"
        self.t = 0.0
        self.last_now = None
        self.lives, self.squad, self.power = START_LIVES, START_SQUAD, 1.0
        self.lane = 1
        self.sf = LANE_MID[1]                  # 분대의 실제 가로 위치(길 폭 비율). 칸 중앙으로 스르륵 움직임
        self.swarms, self.buffs, self.boss = [], [], None
        self.stage, self.stage_t0 = 0, 0.0
        self.next_spawn, self.next_buff = 1.2, 5.0
        self.score, self.kills = 0, 0
        self.g_last = -GRENADE_CD              # 수류탄: 시작하자마자 쓸 수 있음
        self.invuln_until = 0.0
        self.effects, self.events = [], []
        self.firing = None                     # 지금 쏘는 대상: ("swarm", Swarm) / ("buff", Buff) / ("boss", Boss) / None
        self._acc = {}                         # 떠오르는 피해 숫자를 모으는 곳
        self.t_end = 0.0
        self.t_end_wall = 0.0                  # 결과 화면이 뜬 시각(화면 쪽에서 기록)
        self.result_text = ""
        self.bosses_down = 0

    # ── 입력 ──
    def set_lane(self, lane):
        self.lane = max(0, min(2, lane))

    def lane_from_x(self, x):
        """시선 가로 위치(화면 좌표) → 칸. 경계를 LANE_HYST 만큼 넘어야 바뀜(히스테리시스)."""
        if x is None or self.w <= 0:
            return self.lane
        b = (LANE_BOUNDS[0] * self.w, LANE_BOUNDS[1] * self.w)
        m = LANE_HYST * self.w
        cur = self.lane
        while cur < 2 and x > b[cur] + m:
            cur += 1
        while cur > 0 and x < b[cur - 1] - m:
            cur -= 1
        return cur

    def grenade_ready(self):
        return self.state == "play" and self.t - self.g_last >= GRENADE_CD

    def grenade_cd_left(self):
        return max(0.0, GRENADE_CD - (self.t - self.g_last))

    def grenade(self, now=None):
        if not self.grenade_ready():
            return False
        self.g_last = self.t
        for s in list(self.swarms):
            if s.d > 0.05:
                s.hp -= GRENADE_DMG
                self._fx("dmg", s.lane, s.d, f"-{GRENADE_DMG:.0f}")
        if self.boss is not None and self.boss.phase != "enter":
            self.boss.hp -= GRENADE_BOSS_DMG
            self._fx("dmg", self.boss.lanes[0], self.boss.d, f"-{GRENADE_BOSS_DMG:.0f}")
        self._fx("boom", self.lane, PLAYER_D, "")
        self.events.append("boom")
        self._reap()
        return True

    def pop_events(self):
        ev, self.events = self.events, []
        return ev

    # ── 도우미 ──
    def _fx(self, kind, lane, d, text, good=True):
        self.effects.append({"kind": kind, "lane": lane, "d": d, "text": text, "t": self.t, "good": good})

    def dps(self):
        return self.squad * DPS_PER_SOLDIER * self.power

    def difficulty(self):
        return min(1.0, self.t / DIFF_RAMP)

    def next_boss_name(self):
        """지금(또는 다음) 나올 보스 이름 — 화면 위 막대 글자용"""
        for kind, arg in STAGES[self.stage:]:
            if kind == "boss":
                return BOSSES[arg]["name"]
        return ""

    def wave_progress(self):
        """무리 단계에서 다음 보스까지 얼마나 왔는지 0~1"""
        kind, arg = STAGES[min(self.stage, len(STAGES) - 1)]
        if kind != "waves":
            return 1.0
        return max(0.0, min(1.0, (self.t - self.stage_t0) / arg))

    def _lose_life(self, reason):
        if self.t < self.invuln_until:
            return
        self.lives -= 1
        self.invuln_until = self.t + INVULN_SEC
        self._fx("hurt", self.lane, PLAYER_D, reason, good=False)
        self.events.append("hurt")
        if self.lives <= 0:
            self._finish("lose")

    def _finish(self, state):
        if self.state != "play":
            return
        self.state = state
        self.t_end = self.t
        if state == "win":
            self.score += self.lives * 300
            self.result_text = "클리어!"
            self.events.append("win")
        else:
            self.result_text = "실패…"
            self.events.append("lose")
        self.best = max(self.best, self.score)

    # ── 무리 / 강화 상자 만들기 ──
    def _lane_free_for_swarm(self, ln):
        return (all(b.d >= 0.03 + SPACING_D for b in self.buffs if b.lane == ln)
                and all(s.d >= 0.03 + SWARM_SPACING_D for s in self.swarms if s.lane == ln))

    def _lane_free_for_buff(self, ln):
        return (all(s.d >= 0.04 + SPACING_D for s in self.swarms if s.lane == ln)
                and all(b.d >= 0.04 + SWARM_SPACING_D for b in self.buffs if b.lane == ln))

    def _spawn_swarm(self, lane, hp=None):
        k = self.difficulty()
        if hp is None:
            hp = SWARM_HP_BASE + SWARM_HP_PER_SEC * self.t + self.rng.uniform(0, SWARM_HP_RAND)
        self.swarms.append(Swarm(lane, 0.03, round(hp), lerp(SWARM_SPEED[0], SWARM_SPEED[1], k), self.rng, self.t))

    def _spawn_wave(self):
        sizes, weights = zip(*WAVE_SIZES)
        n = self.rng.choices(sizes, weights)[0]
        lanes = [0, 1, 2]
        self.rng.shuffle(lanes)
        lanes = [ln for ln in lanes if self._lane_free_for_swarm(ln)][:n]
        for ln in lanes:
            self._spawn_swarm(ln)
        return bool(lanes)

    def _spawn_buffs(self):
        lanes = [0, 1, 2]
        self.rng.shuffle(lanes)
        lanes = [ln for ln in lanes if self._lane_free_for_buff(ln)][:2]
        if not lanes:
            return False
        k = self.difficulty()
        specs = self.rng.sample(BUFF_TYPES, len(lanes))
        for ln, spec in zip(lanes, specs):
            self.buffs.append(Buff(ln, round(lerp(BUFF_HP[0], BUFF_HP[1], k)), lerp(SWARM_SPEED[0], SWARM_SPEED[1], k), spec))
        return True

    def _apply_buff(self, b):
        if b.kind == "squad":
            self.squad = max(1, min(MAX_SQUAD, self.squad + int(b.val)))
        elif b.kind == "power":
            self.power = max(POWER_MIN, min(POWER_MAX, self.power + b.val))
        else:                                             # nade: 수류탄 바로 충전
            self.g_last = self.t - GRENADE_CD
        self._fx("pop", b.lane, b.d, b.label, True)
        self.events.append("gate_good")

    def _reap(self):
        """체력이 0 이하가 된 무리·강화 상자·보스를 처리"""
        for s in list(self.swarms):
            if s.hp <= 0:
                self.swarms.remove(s)
                self.kills += 1
                self.score += 10 + int(s.max_hp // 10)
                self._fx("pop", s.lane, s.d, "+%d" % (10 + int(s.max_hp // 10)))
                self.events.append("kill")
        for b in list(self.buffs):
            if b.hp <= 0:
                self.buffs.remove(b)
                self._apply_buff(b)
        bo = self.boss
        if bo is not None and bo.hp <= 0 and self.state == "play":
            bo.hp = 0
            self.score += bo.spec["reward"]
            self.bosses_down += 1
            self.boss = None
            self.swarms = []                                              # 보스를 잡으면 남은 졸개도 함께 사라짐
            if bo.key == "final":
                self._finish("win")
            else:
                self.stage += 1
                self.stage_t0 = self.t
                if self.lives < START_LIVES:                              # 중간보스 보상: 목숨 1개 회복
                    self.lives += 1
                    self._fx("pop", self.lane, PLAYER_D - 0.1, "목숨 +1", True)
                self._fx("pop", 1, BOSS_D, f"{bo.name} 처치!", True)
                self.events.append("win")

    # ── 매 프레임 ──
    def update(self, now, gaze_x=None):
        if self.last_now is None:
            self.last_now = now
        dt = max(0.0, min(0.1, now - self.last_now))
        self.last_now = now
        if self.state != "play":
            self.sf += (LANE_MID[self.lane] - self.sf) * min(1.0, dt * 14)
            return
        self.t += dt
        self.lane = self.lane_from_x(gaze_x)
        self.sf += (LANE_MID[self.lane] - self.sf) * min(1.0, dt * 14)

        # 진행 단계: 무리 → 보스 → 무리 → …
        kind, arg = STAGES[self.stage]
        spawning = False
        if kind == "waves":
            st = self.t - self.stage_t0
            spawning = st < arg - BOSS_WAIT_SEC
            if st >= arg and (len(self.swarms) <= 1 or st >= arg + 6.0) and self.boss is None:
                self.boss = Boss(arg_next(self.stage), self.t)
                self.stage += 1
                self.events.append("boss")
        if spawning:
            if self.t >= self.next_spawn and self._spawn_wave():
                self.next_spawn = self.t + lerp(SPAWN_GAP[0], SPAWN_GAP[1], self.difficulty())
        if (spawning or self.boss is not None) and self.t >= self.next_buff and self._spawn_buffs():
            self.next_buff = self.t + BUFF_EVERY

        # 움직임
        for s in list(self.swarms):
            s.d += s.speed * dt
            if s.d >= HIT_D:
                self.swarms.remove(s)
                self._fx("pop", s.lane, HIT_D, "뚫렸다!", good=False)
                self._lose_life("뚫렸다!")
        for b in list(self.buffs):
            b.d += b.speed * dt
            if b.d >= HIT_D:                                  # 못 부수고 지나가면 그냥 사라짐 (벌은 없음)
                self.buffs.remove(b)
                self._fx("pop", b.lane, HIT_D, "놓침", good=False)
        self._update_boss()

        # 사격: 분대가 있는 칸에서 가장 가까운 것(무리 또는 강화 상자) → 없으면 보스
        target, kind_t = None, None
        for s in self.swarms:
            if s.lane == self.lane and 0.06 < s.d < HIT_D and (target is None or s.d > target.d):
                target, kind_t = s, "swarm"
        for b in self.buffs:
            if b.lane == self.lane and 0.06 < b.d < HIT_D and (target is None or b.d > target.d):
                target, kind_t = b, "buff"
        dmg = self.dps() * dt
        self.firing = None
        bo = self.boss
        if target is not None:
            target.hp -= dmg
            self.firing = (kind_t, target)
            self._acc_dmg(id(target), target.lane, target.d, dmg)
        elif bo is not None and bo.phase != "enter" and bo.hp > 0:
            mul = 1.0 if self.lane in bo.lanes else BOSS_OFFLANE_MUL
            bo.hp -= dmg * mul
            self.firing = ("boss", bo)
            self._acc_dmg("boss", bo.lanes[0], bo.d, dmg * mul)
        self._reap()
        self.effects = [e for e in self.effects if self.t - e["t"] < EFFECT_LIFE]

    def _acc_dmg(self, key, lane, d, dmg):
        a = self._acc.setdefault(key, [0.0, 0.0])      # [쌓인 피해, 마지막으로 띄운 시각]
        a[0] += dmg
        if self.t - a[1] >= 0.35 and a[0] >= 1:
            self._fx("dmg", lane, d, f"-{a[0]:.0f}")
            a[0], a[1] = 0.0, self.t

    def _update_boss(self):
        b = self.boss
        if b is None or self.state != "play":
            return
        sp = b.spec
        rage_hp = sp.get("rage_hp")
        if rage_hp and not b.rage and b.hp <= b.max_hp * rage_hp:
            b.rage = True                                  # 체력이 절반 이하 → 더 빠르고 더 자주 두 칸을 내려침
            self._fx("pop", 1, BOSS_D + 0.1, "분노!", False)
            self.events.append("boss")
        tele = sp["rage_tele"] if b.rage else sp["tele"]
        idle = sp["rage_idle"] if b.rage else sp["idle"]
        dbl = sp["rage_double"] if b.rage else sp["double"]
        if b.phase == "enter":
            b.d = lerp(0.0, BOSS_D, (self.t - b.t0) / BOSS_ENTER_SEC)
            if self.t - b.t0 >= BOSS_ENTER_SEC:
                b.phase, b.t0 = "idle", self.t
        elif b.phase == "idle":
            if self.t - b.t0 >= idle:
                if self.rng.random() < dbl:                # 두 칸을 한꺼번에: 안전한 칸은 하나
                    safe = self.lane if self.rng.random() < 0.35 else self.rng.choice([0, 1, 2])
                    b.lanes = [x for x in (0, 1, 2) if x != safe]
                else:
                    b.lanes = [self.lane if self.rng.random() < 0.6 else self.rng.choice([0, 1, 2])]
                b.phase, b.t0 = "tele", self.t
                self.events.append("warn")
        elif b.phase == "tele":
            if self.t - b.t0 >= tele:
                b.phase, b.t0 = "slam", self.t
                self.events.append("slam")
                for ln in b.lanes:
                    self._fx("slam", ln, BOSS_D + 0.25, "")
                if self.lane in b.lanes:
                    self._lose_life("내려쳤다!")
        elif b.phase == "slam":
            if self.t - b.t0 >= 0.35:
                b.cycle += 1
                b.phase, b.t0 = "idle", self.t
                if b.cycle % sp["summon_every"] == 0:      # 부하 무리를 부름
                    n = sp["summon_n"] + (1 if b.rage else 0)
                    free = [x for x in (0, 1, 2) if x not in b.lanes] or [0, 1, 2]
                    self.rng.shuffle(free)
                    for ln in free[:min(n, 3)]:
                        if self._lane_free_for_swarm(ln):
                            self._spawn_swarm(ln, hp=sp["summon_hp"] + 8 * b.cycle)
        target_x = sum(LANE_MID[x] for x in b.lanes) / len(b.lanes)
        b.xf += (target_x - b.xf) * min(1.0, 0.016 * 9)


def arg_next(stage_idx):
    """STAGES[stage_idx] 다음 칸(= 보스 단계)의 보스 이름표"""
    return STAGES[stage_idx + 1][1]


# ════════════════════════════════════════════════════════════════
#  3. 화면 배치 (Qt 없이 계산하는 부분 — 버튼 위치, 원근법)
# ════════════════════════════════════════════════════════════════
class Btn:
    """화면 속 버튼 (x0, y0, x1, y1)."""

    def __init__(self, key, rect, need):
        self.key, self.rect, self.need = key, rect, need

    def contains(self, x, y, pad=0.0):
        x0, y0, x1, y1 = self.rect
        return x0 - pad <= x <= x1 + pad and y0 - pad <= y <= y1 + pad


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


def ui_layout(w, h):
    """버튼 위치. 전부 화면 높이(h)에 비례."""
    L = {}
    bw, bh = h * 0.34, h * 0.095
    L["start"] = (w / 2 - bw / 2, h * 0.70, w / 2 + bw / 2, h * 0.70 + bh)
    ew, eh = h * 0.17, h * 0.062
    L["exit"] = (w - ew - h * 0.03, h * 0.085, w - h * 0.03, h * 0.085 + eh)
    rw = h * 0.30
    L["retry"] = (w / 2 - rw - h * 0.02, h * 0.66, w / 2 - h * 0.02, h * 0.66 + bh)
    L["quit"] = (w / 2 + h * 0.02, h * 0.66, w / 2 + rw + h * 0.02, h * 0.66 + bh)
    return L


class Geom:
    """원근법으로 그린 길: 깊이 d(0 위 ~ 1 아래) → 화면 좌표."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.y0, self.y1 = h * 0.13, h * 1.0
        self.ht, self.hb = w * 0.15, w * 0.47
        self.cx = w / 2
        self.u = h * 0.115                     # 그림 크기의 기준 단위

    def y(self, d):
        return self.y0 + (self.y1 - self.y0) * d

    def half(self, d):
        return self.ht + (self.hb - self.ht) * d

    def x(self, frac, d):
        return self.cx + (frac - 0.5) * 2 * self.half(d)

    @staticmethod
    def sc(d):
        return 0.28 + 0.72 * max(0.0, min(1.2, d))


# ════════════════════════════════════════════════════════════════
#  4. 시선 입력 / 효과음 파일 만들기
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


TONES = {
    "gate_good": [((600, 900), 0.09, 0.5)],
    "gate_bad": [((300, 150), 0.22, 0.6)],
    "kill": [((800, 1200), 0.05, 0.3)],
    "boom": [((220, 60), 0.35, 0.7)],
    "hurt": [((220, 110), 0.30, 0.65)],
    "warn": [(500, 0.08, 0.45), (400, 0.08, 0.45)],
    "slam": [((140, 50), 0.28, 0.75)],
    "boss": [(180, 0.15, 0.6), (140, 0.25, 0.6)],
    "select": [(520, 0.05, 0.4)],
    "start": [(440, 0.09, 0.5), (660, 0.09, 0.5), (880, 0.16, 0.5)],
    "win": [(660, 0.09, 0.5), (880, 0.09, 0.5), (1320, 0.25, 0.5)],
    "lose": [(880, 0.10, 0.5), (660, 0.10, 0.5), (440, 0.30, 0.5)],
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
FONT_FILES = [r / sub / "BMJUA_ttf.ttf" for r in _ROOTS for sub in ("ui/fonts/ttf", "fonts", ".")]
FALLBACK_FONT = "Malgun Gothic"


def C(r, g, b, a=255):
    return QtGui.QColor(r, g, b, a)


NIGHT_TOP, NIGHT_BOT = C(8, 12, 38), C(26, 20, 66)
ROAD, ROAD_EDGE = C(38, 45, 82), C(76, 88, 150)
LANE_HI = C(126, 200, 255, 36)
WHITE, INKW = C(255, 255, 255), C(232, 236, 248)
MUTED = C(140, 150, 180)
GOOD, BAD = C(61, 220, 132), C(255, 93, 93)
GOLD = C(255, 211, 107)
ALIEN, ALIEN2, ALIEN_EYE = C(255, 107, 107), C(255, 157, 77), C(60, 12, 20)
OLIVE, OLIVE_D, OLIVE_DD = C(85, 107, 63), C(59, 74, 46), C(68, 88, 47)
HELMET, GUN, GUN_D = C(107, 130, 80), C(170, 178, 190), C(125, 133, 146)
BOSS_C, BOSS_L = C(162, 77, 255), C(197, 139, 255)


def _poly(points):
    return QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in points])


def _pen(color, width, round_cap=False):
    pen = QtGui.QPen(color, width)
    if round_cap:
        pen.setCapStyle(QtCore.Qt.RoundCap)
    return pen


def draw_soldier(p, x, y, k, firing, now, idx=0):
    """뒷모습 군인. (x, y) = 발 위쪽 몸 중심, k = 크기 배율 (전체 키 ≈ 70k)"""
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(OLIVE_D)
    p.drawRoundedRect(QtCore.QRectF(x - 9 * k, y + 10 * k, 7 * k, 14 * k), 2 * k, 2 * k)
    p.drawRoundedRect(QtCore.QRectF(x + 2 * k, y + 10 * k, 7 * k, 14 * k), 2 * k, 2 * k)
    p.setBrush(OLIVE)
    p.drawRoundedRect(QtCore.QRectF(x - 14 * k, y - 6 * k, 28 * k, 22 * k), 7 * k, 7 * k)
    p.setBrush(OLIVE_DD)
    p.drawRoundedRect(QtCore.QRectF(x - 8 * k, y - 2 * k, 16 * k, 14 * k), 3 * k, 3 * k)
    p.setPen(_pen(OLIVE, 6 * k, True))
    p.drawLine(QtCore.QPointF(x - 12 * k, y - 2 * k), QtCore.QPointF(x + 3 * k, y - 15 * k))
    p.drawLine(QtCore.QPointF(x + 12 * k, y - 2 * k), QtCore.QPointF(x + 8 * k, y - 12 * k))
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(GUN)
    p.drawRoundedRect(QtCore.QRectF(x + 5 * k, y - 42 * k, 5 * k, 32 * k), 2 * k, 2 * k)
    p.setBrush(GUN_D)
    p.drawRoundedRect(QtCore.QRectF(x + 3 * k, y - 22 * k, 9 * k, 8 * k), 2 * k, 2 * k)
    p.setBrush(HELMET)
    p.drawEllipse(QtCore.QPointF(x, y - 13 * k), 10 * k, 10 * k)
    p.setBrush(OLIVE_DD)
    p.drawRoundedRect(QtCore.QRectF(x - 11 * k, y - 14 * k, 22 * k, 4 * k), 2 * k, 2 * k)
    if firing and int(now * 18 + idx) % 2 == 0:                       # 총구 불꽃이 깜빡임
        p.setBrush(C(255, 227, 107))
        p.drawEllipse(QtCore.QPointF(x + 7.5 * k, y - 46 * k), 4.5 * k, 4.5 * k)
        p.setBrush(C(255, 255, 255, 200))
        p.drawEllipse(QtCore.QPointF(x + 7.5 * k, y - 46 * k), 2 * k, 2 * k)


def draw_minion(p, x, y, r, col):
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(col)
    p.drawEllipse(QtCore.QPointF(x, y), r * 1.3, r)
    p.setPen(_pen(col, max(1.0, r * 0.18), True))
    p.drawLine(QtCore.QPointF(x - r * 0.7, y - r * 0.8), QtCore.QPointF(x - r * 1.0, y - r * 1.5))
    p.drawLine(QtCore.QPointF(x + r * 0.7, y - r * 0.8), QtCore.QPointF(x + r * 1.0, y - r * 1.5))
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(ALIEN_EYE)
    p.drawEllipse(QtCore.QPointF(x - r * 0.42, y - r * 0.12), r * 0.26, r * 0.28)
    p.drawEllipse(QtCore.QPointF(x + r * 0.42, y - r * 0.12), r * 0.26, r * 0.28)


def draw_heart(p, cx, cy, s, col):
    path = QtGui.QPainterPath()
    path.moveTo(cx, cy + s * 0.9)
    path.cubicTo(cx - s * 1.7, cy - s * 0.2, cx - s * 0.8, cy - s * 1.4, cx, cy - s * 0.5)
    path.cubicTo(cx + s * 0.8, cy - s * 1.4, cx + s * 1.7, cy - s * 0.2, cx, cy + s * 0.9)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(col)
    p.drawPath(path)


def _text(p, font, color, rect, flags, s):
    p.setFont(font)
    p.setPen(color)
    p.drawText(rect, flags, s)


def _tag(p, fontfn, cx, cy, text, px, fill, fg=WHITE):
    """둥근 알약 모양 글자표"""
    f = fontfn(px)
    fm = QtGui.QFontMetricsF(f)
    tw = fm.horizontalAdvance(text) + px * 1.1
    r = QtCore.QRectF(cx - tw / 2, cy - px * 0.78, tw, px * 1.56)
    p.setPen(_pen(C(255, 255, 255, 120), max(1.0, px * 0.08)))
    p.setBrush(fill)
    p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
    _text(p, f, fg, r, QtCore.Qt.AlignCenter, text)


_STARS = []


def _stars(w, h):
    if not _STARS or _STARS[0] != (w, h):
        rng = random.Random(5)
        _STARS[:] = [(w, h)] + [(rng.random() * w, rng.random() * h, rng.choice([1.0, 1.4, 2.0]), rng.choice([70, 120, 190])) for _ in range(90)]
    return _STARS[1:]


def draw_scene(p, g, w, h, now, fontfn, ptr=None, show_game=True):
    """게임 장면 전체(배경·길·적·문·보스·분대·효과·HUD)를 그림. g 는 Game."""
    G = Geom(w, h)
    # 하늘
    grad = QtGui.QLinearGradient(0, 0, 0, h)
    grad.setColorAt(0.0, NIGHT_TOP)
    grad.setColorAt(1.0, NIGHT_BOT)
    p.fillRect(QtCore.QRectF(0, 0, w, h), QtGui.QBrush(grad))
    p.setPen(QtCore.Qt.NoPen)
    for sx, sy, sr, sa in _stars(w, h):
        p.setBrush(C(255, 255, 255, sa))
        p.drawEllipse(QtCore.QPointF(sx, sy), sr, sr)
    # 길
    p.setBrush(ROAD)
    p.drawPolygon(_poly([(G.x(0, 0), G.y(0)), (G.x(1, 0), G.y(0)), (G.x(1, 1), G.y(1)), (G.x(0, 1), G.y(1))]))
    if show_game:
        a, b = LANE_FRAC[g.lane]
        p.setBrush(LANE_HI)
        p.drawPolygon(_poly([(G.x(a, 0), G.y(0)), (G.x(b, 0), G.y(0)), (G.x(b, 1), G.y(1)), (G.x(a, 1), G.y(1))]))
    p.setPen(_pen(ROAD_EDGE, max(2.0, h * 0.005)))
    p.drawLine(QtCore.QPointF(G.x(0, 0), G.y(0)), QtCore.QPointF(G.x(0, 1), G.y(1)))
    p.drawLine(QtCore.QPointF(G.x(1, 0), G.y(0)), QtCore.QPointF(G.x(1, 1), G.y(1)))
    scroll = (g.t * 0.4) % 1.0 if show_game else 0.0                  # 점선이 아래로 흘러 달리는 느낌
    N = 14
    for f in (LANE_BOUNDS_FRAC[0], LANE_BOUNDS_FRAC[1]):
        p.setPen(_pen(C(255, 255, 255, 60), max(1.5, h * 0.003)))
        for i in range(N):
            d0 = ((i + scroll) / N) ** 1.6
            d1 = ((i + scroll + 0.5) / N) ** 1.6
            if d1 > 1.0:
                continue
            p.drawLine(QtCore.QPointF(G.x(f, d0), G.y(d0)), QtCore.QPointF(G.x(f, d1), G.y(d1)))
    if not show_game:
        return
    t = g.t

    # 보스 경고: 내려칠 칸을 붉게
    b = g.boss
    if b is not None and b.phase in ("tele", "slam"):
        tele_sec = (b.spec["rage_tele"] if b.rage else b.spec["tele"])
        k = (t - b.t0) / tele_sec if b.phase == "tele" else 1.0
        alpha = int(50 + 70 * (0.5 + 0.5 * math.sin(t * 16)) * min(1.0, k + 0.3))
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(C(255, 60, 60, alpha))
        for ln in b.lanes:
            a_, b_ = LANE_FRAC[ln]
            p.drawPolygon(_poly([(G.x(a_, 0), G.y(0)), (G.x(b_, 0), G.y(0)), (G.x(b_, 1), G.y(1)), (G.x(a_, 1), G.y(1))]))

    # 멀리 있는 것부터 그림: 강화 상자 / 무리 / 보스
    items = [(r.d, "buff", r) for r in g.buffs] + [(s.d, "swarm", s) for s in g.swarms]
    if b is not None:
        items.append((b.d, "boss", b))
    items.sort(key=lambda it: it[0])
    for d, kind, obj in items:
        if kind == "buff":
            _draw_buff(p, G, obj, fontfn, t)
        elif kind == "swarm":
            _draw_swarm(p, G, obj, fontfn, t)
        else:
            _draw_boss(p, G, obj, fontfn, t, h)

    # 분대
    _draw_squad(p, G, g, now)

    # 떠오르는 글자·효과
    for e in g.effects:
        age = (t - e["t"]) / EFFECT_LIFE
        if age < 0 or age > 1:
            continue
        if e["kind"] == "boom":
            rr = h * (0.15 + 0.9 * age)
            p.setBrush(QtCore.Qt.NoBrush)
            p.setPen(_pen(C(255, 220, 120, int(220 * (1 - age))), h * 0.02 * (1 - age) + 2))
            p.drawEllipse(QtCore.QPointF(w / 2, h * 0.55), rr, rr * 0.6)
            p.fillRect(QtCore.QRectF(0, 0, w, h), C(255, 240, 200, int(110 * (1 - age) ** 2)))
        elif e["kind"] == "slam":
            a_, b_ = LANE_FRAC[e["lane"]]
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(C(255, 255, 255, int(150 * (1 - age))))
            p.drawPolygon(_poly([(G.x(a_, 0), G.y(0)), (G.x(b_, 0), G.y(0)), (G.x(b_, 1), G.y(1)), (G.x(a_, 1), G.y(1))]))
        elif e["kind"] == "hurt":
            p.fillRect(QtCore.QRectF(0, 0, w, h), C(255, 40, 40, int(120 * (1 - age))))
        elif e["kind"] in ("dmg", "pop") and e["text"]:
            fa, fb = LANE_FRAC[e["lane"]]
            ex = G.x((fa + fb) / 2, e["d"])
            ey = G.y(e["d"]) - h * (0.05 + 0.08 * age)
            px = h * (0.034 if e["kind"] == "pop" else 0.028) * (0.7 + 0.5 * G.sc(e["d"]))
            col = (GOOD if e["good"] else BAD) if e["kind"] == "pop" else WHITE
            f = fontfn(px)
            r = QtCore.QRectF(ex - px * 4, ey - px, px * 8, px * 2)
            _text(p, f, C(0, 0, 0, int(200 * (1 - age))), r.translated(px * 0.06, px * 0.06), QtCore.Qt.AlignCenter, e["text"])
            _text(p, f, C(col.red(), col.green(), col.blue(), int(255 * (1 - age * 0.7))), r, QtCore.Qt.AlignCenter, e["text"])

    _draw_hud(p, g, w, h, now, fontfn, ptr)


LANE_BOUNDS_FRAC = (LANE_FRAC[0][1], LANE_FRAC[1][1])


def _draw_buff(p, G, b, fontfn, t):
    """강화 상자: 초록 판 + 글자 + 남은 체력. 쏠수록 초록 채움이 줄어들고, 다 없어지면 강화를 얻음."""
    d = b.d
    fa, fb = LANE_FRAC[b.lane]
    xl, xr = G.x(fa + 0.04, d), G.x(fb - 0.04, d)
    y = G.y(d)
    hh = G.h * 0.085 * G.sc(d)
    r = QtCore.QRectF(xl, y - hh / 2, xr - xl, hh)
    ratio = max(0.0, b.hp / b.max_hp)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(C(20, 60, 44, 200))
    p.drawRoundedRect(r, hh * 0.18, hh * 0.18)
    p.setBrush(C(61, 220, 132, 130))
    p.drawRoundedRect(QtCore.QRectF(r.left(), r.top(), max(hh * 0.3, r.width() * ratio), r.height()), hh * 0.18, hh * 0.18)
    p.setPen(_pen(GOOD, max(2.0, hh * 0.07)))
    p.setBrush(QtCore.Qt.NoBrush)
    p.drawRoundedRect(r, hh * 0.18, hh * 0.18)
    px = max(10.0, G.h * 0.036 * G.sc(d))
    _text(p, fontfn(px), WHITE, r, QtCore.Qt.AlignCenter, b.label)
    _tag(p, fontfn, (xl + xr) / 2, y + hh * 0.5 + G.h * 0.026 * G.sc(d), f"{max(0, int(math.ceil(b.hp)))}",
         max(11.0, G.h * 0.024 * (0.6 + G.sc(d))), C(22, 120, 80))


def _draw_swarm(p, G, s, fontfn, t):
    d = s.d
    fa, fb = LANE_FRAC[s.lane]
    lw = G.x(fb, d) - G.x(fa, d)
    cx, cy = G.x((fa + fb) / 2, d), G.y(d)
    r = G.u * 0.26 * G.sc(d)
    base_n = 10 + int(min(20, s.max_hp / 18))
    n = max(2, int(math.ceil(base_n * max(0.0, s.hp) / s.max_hp)))
    pts = []
    for ox, oy, rr in s.offs[:n]:
        bob = math.sin(t * 6 + rr * 6.28) * r * 0.12
        pts.append((cy + oy * G.h * 0.032 * G.sc(d) + bob, cx + ox * lw * 0.36, rr))
    pts.sort()
    for py, px_, rr in pts:
        draw_minion(p, px_, py, r, ALIEN if rr > 0.25 else ALIEN2)
    _tag(p, fontfn, cx, cy + G.h * 0.05 * G.sc(d) + r, f"{max(0, int(math.ceil(s.hp)))}", max(11.0, G.h * 0.026 * (0.6 + G.sc(d))), C(217, 58, 74))


def _draw_boss(p, G, b, fontfn, t, h):
    d = b.d
    cx, cy = G.x(b.xf, d), G.y(d)
    sp = b.spec
    body, light = C(*sp["body"]), C(*sp["light"])
    sx = G.u * 2.4 * G.sc(d + 0.25) * sp["size"]
    sy = sx * 0.62
    shake = (math.sin(t * 40) * sx * 0.02) if b.phase == "tele" else 0.0
    cx += shake
    if b.phase in ("tele", "slam"):
        cy += sy * 0.08 * (1 if b.phase == "slam" else 0)
    if b.rage:                                                          # 분노: 몸 둘레에 붉은 빛
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(C(255, 40, 40, int(60 + 40 * math.sin(t * 9))))
        p.drawEllipse(QtCore.QPointF(cx, cy), sx * 1.18, sy * 1.25)
    p.setPen(_pen(body, sx * 0.07, True))
    p.drawLine(QtCore.QPointF(cx - sx * 0.62, cy - sy * 0.8), QtCore.QPointF(cx - sx * 0.78, cy - sy * 1.25))
    p.drawLine(QtCore.QPointF(cx + sx * 0.62, cy - sy * 0.8), QtCore.QPointF(cx + sx * 0.78, cy - sy * 1.25))
    if b.key == "final":                                                # 최종보스는 뿔이 하나 더 (가운데)
        p.drawLine(QtCore.QPointF(cx, cy - sy * 0.95), QtCore.QPointF(cx, cy - sy * 1.55))
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(body)
    p.drawEllipse(QtCore.QPointF(cx, cy), sx, sy)
    p.setBrush(light)
    p.drawEllipse(QtCore.QPointF(cx, cy - sy * 0.16), sx * 0.76, sy * 0.6)
    angry = b.phase in ("tele", "slam") or b.rage
    eyes = (-1, 1) if b.key != "mid2" else (-1.0, 0.0, 1.0)             # 중간보스 2는 눈이 세 개
    er = sx * (0.14 if len(eyes) == 2 else 0.1)
    for sgn in eyes:
        ex, ey = cx + sgn * sx * (0.31 if len(eyes) == 2 else 0.3), cy - sy * 0.22
        p.setBrush(WHITE)
        p.drawEllipse(QtCore.QPointF(ex, ey), er, er)
        p.setBrush(C(200, 20, 30) if angry else C(42, 8, 69))
        p.drawEllipse(QtCore.QPointF(ex, ey), er * 0.47, er * 0.47)
    p.setPen(_pen(C(42, 8, 69), sx * 0.045, True))
    if angry:
        p.drawLine(QtCore.QPointF(cx - sx * 0.3, cy + sy * 0.38), QtCore.QPointF(cx + sx * 0.3, cy + sy * 0.38))
    else:
        path = QtGui.QPainterPath()
        path.moveTo(cx - sx * 0.3, cy + sy * 0.36)
        path.quadTo(cx, cy + sy * 0.7, cx + sx * 0.3, cy + sy * 0.36)
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawPath(path)


def _draw_squad(p, G, g, now):
    sf = g.sf
    d = PLAYER_D
    cx, cy = G.x(sf, d), G.y(d)
    k = G.h * 0.135 / 70.0
    form = [(0, 0), (-0.95, 0.5), (0.95, 0.5), (-0.5, -0.6), (0.5, -0.6), (-1.85, 1.0), (1.85, 1.0), (0, -1.2)]
    mem = form[:max(1, min(MAX_SQUAD, g.squad))]
    firing = g.firing is not None
    flicker = g.t < g.invuln_until and int(g.t * 14) % 2 == 0
    # 총알: 각 군인의 총구에서 맞히는 대상을 향해 날아가고, 멀어질수록 작아짐 (원근감)
    if firing:
        kind, tgt = g.firing
        if kind in ("swarm", "buff"):
            fa, fb = LANE_FRAC[tgt.lane]
            tx, ty = G.x((fa + fb) / 2, tgt.d), G.y(tgt.d) + G.u * 0.1 * G.sc(tgt.d)
        else:
            tx, ty = G.x(tgt.xf, tgt.d), G.y(tgt.d) + G.u * 0.9
        for j, (ox, oy) in enumerate(mem):
            bx = cx + ox * G.u * 0.6 + 7.5 * k
            by = cy + oy * G.u * 0.3 - 42 * k
            jit = math.sin(j * 12.9898) * G.u * 0.18            # 군인마다 조금씩 다른 곳을 겨냥
            ex, ey = tx + jit, ty
            dx, dy = ex - bx, ey - by
            dist = math.hypot(dx, dy) or 1.0
            ux, uy = dx / dist, dy / dist
            for m in range(4):
                ph = (g.t * 2.8 + m / 4.0 + j * 0.137) % 1.0
                kk = k * (1.0 - 0.6 * ph)
                hx, hy = bx + dx * ph, by + dy * ph             # 총알 머리
                ln = kk * 22                                     # 꼬리 길이
                a = int(255 * (1 - ph * 0.5))
                p.setPen(_pen(C(255, 150, 40, int(a * 0.35)), kk * 7, True))     # 바깥 빛
                p.drawLine(QtCore.QPointF(hx, hy), QtCore.QPointF(hx - ux * ln, hy - uy * ln))
                p.setPen(_pen(C(255, 240, 170, a), kk * 3, True))               # 밝은 심지
                p.drawLine(QtCore.QPointF(hx, hy), QtCore.QPointF(hx - ux * ln * 0.8, hy - uy * ln * 0.8))
        # 맞는 자리 불꽃
        p.setPen(QtCore.Qt.NoPen)
        for q in range(4):
            sa = math.sin(g.t * 37 + q * 1.9) * 6.283
            sr = G.u * (0.12 + 0.1 * abs(math.sin(g.t * 29 + q)))
            p.setBrush(C(255, 220, 120, 190))
            p.drawEllipse(QtCore.QPointF(tx + math.cos(sa) * sr * 2.2, ty + math.sin(sa) * sr * 1.2), sr * 0.45, sr * 0.45)
    order = sorted(range(len(mem)), key=lambda i: mem[i][1])
    if not flicker:
        for i in order:
            ox, oy = mem[i]
            draw_soldier(p, cx + ox * G.u * 0.6, cy + oy * G.u * 0.3, k * (1.0 - 0.06 * i / 8), firing, now, i)


def _draw_hud(p, g, w, h, now, fontfn, ptr):
    m = h * 0.03
    # 목숨
    for i in range(START_LIVES):
        draw_heart(p, m + h * 0.03 + i * h * 0.062, h * 0.058, h * 0.022, C(255, 93, 122) if i < g.lives else C(58, 63, 85))
    # 점수
    _text(p, fontfn(h * 0.04), INKW, QtCore.QRectF(w - h * 0.5 - m, m * 0.6, h * 0.5, h * 0.06), QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, f"점수 {g.score}")
    # 보스까지 / 보스 체력
    bw, bh = w * 0.30, h * 0.016
    bx, by = w / 2 - bw / 2, h * 0.05
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(C(255, 255, 255, 36))
    p.drawRoundedRect(QtCore.QRectF(bx, by, bw, bh), bh / 2, bh / 2)
    if g.boss is None:
        k = g.wave_progress()
        p.setBrush(C(126, 200, 255))
        label = f"{g.next_boss_name()}까지"
    else:
        k = max(0.0, g.boss.hp / g.boss.max_hp)
        p.setBrush(C(255, 93, 122))
        label = f"{g.boss.name}  {max(0, int(g.boss.hp))}" + ("  (분노!)" if g.boss.rage else "")
    p.drawRoundedRect(QtCore.QRectF(bx, by, max(bh, bw * k), bh), bh / 2, bh / 2)
    _text(p, fontfn(h * 0.026), C(255, 208, 216) if g.boss else MUTED, QtCore.QRectF(bx, by - h * 0.036, bw, h * 0.032), QtCore.Qt.AlignCenter, label)
    # 분대 / 화력
    _text(p, fontfn(h * 0.03), INKW, QtCore.QRectF(m, h * 0.095, w * 0.28, h * 0.045), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, f"분대 {g.squad}명 · 화력 ×{g.power:.1f}")
    # 칸 막대 (아래): 어느 칸을 보는지 + 시선 위치
    names = ("왼쪽", "가운데", "오른쪽")
    xs = [(0.04, LANE_BOUNDS[0]), (LANE_BOUNDS[0], LANE_BOUNDS[1]), (LANE_BOUNDS[1], 0.96)]
    for i, (a, b) in enumerate(xs):
        on = (i == g.lane)
        r = QtCore.QRectF(a * w + 3, h * 0.952, (b - a) * w - 6, h * 0.034)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(C(126, 200, 255, 140) if on else C(255, 255, 255, 30))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        _text(p, fontfn(h * 0.022), WHITE if on else MUTED, r, QtCore.Qt.AlignCenter, names[i])
    # 수류탄
    gx, gy, gr = w - h * 0.085, h * 0.84, h * 0.055
    ready = g.grenade_ready()
    p.setPen(_pen(GOLD if ready else C(90, 96, 120), h * 0.006))
    p.setBrush(C(255, 211, 107, 60) if ready else C(255, 255, 255, 20))
    p.drawEllipse(QtCore.QPointF(gx, gy), gr, gr)
    if ready:
        _text(p, fontfn(h * 0.026), GOLD, QtCore.QRectF(gx - gr, gy - gr, gr * 2, gr * 2), QtCore.Qt.AlignCenter, "준비")
    else:
        left = g.grenade_cd_left()
        p.setPen(_pen(C(126, 200, 255), h * 0.008, True))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawArc(QtCore.QRectF(gx - gr, gy - gr, gr * 2, gr * 2), 90 * 16, int(-360 * 16 * (1 - left / GRENADE_CD)))
        _text(p, fontfn(h * 0.03), MUTED, QtCore.QRectF(gx - gr, gy - gr, gr * 2, gr * 2), QtCore.Qt.AlignCenter, f"{left:.0f}")
    _text(p, fontfn(h * 0.024), GOLD if ready else MUTED, QtCore.QRectF(gx - gr * 1.6, gy + gr * 1.05, gr * 3.2, h * 0.04), QtCore.Qt.AlignCenter, "윙크 = 수류탄")
    # 시선 점
    if ptr is not None:
        p.setBrush(QtCore.Qt.NoBrush)
        p.setPen(_pen(C(126, 200, 255, 200), max(2.0, h * 0.004)))
        p.drawEllipse(QtCore.QPointF(ptr[0], ptr[1]), h * 0.022, h * 0.022)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(C(126, 200, 255, 230))
        p.drawEllipse(QtCore.QPointF(ptr[0], ptr[1]), h * 0.005, h * 0.005)


def _button(p, fontfn, rect, label, progress, hot, h, color=C(61, 140, 220)):
    x0, y0, x1, y1 = rect
    r = QtCore.QRectF(x0, y0, x1 - x0, y1 - y0)
    p.setPen(_pen(WHITE if hot else C(255, 255, 255, 140), h * 0.004))
    p.setBrush(color if hot else C(color.red(), color.green(), color.blue(), 150))
    p.drawRoundedRect(r, r.height() * 0.3, r.height() * 0.3)
    if progress > 0:
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(C(255, 255, 255, 90))
        p.drawRoundedRect(QtCore.QRectF(r.left(), r.top(), r.width() * progress, r.height()), r.height() * 0.3, r.height() * 0.3)
    _text(p, fontfn(r.height() * 0.46), WHITE, r, QtCore.Qt.AlignCenter, label)


def draw_title(p, w, h, fontfn, L, prog, hot_key):
    p.fillRect(QtCore.QRectF(0, 0, w, h), C(6, 8, 26, 170))
    pw, ph = min(w * 0.7, h * 1.25), h * 0.78
    card = QtCore.QRectF(w / 2 - pw / 2, h * 0.08, pw, ph)
    p.setPen(_pen(C(126, 200, 255, 160), h * 0.004))
    p.setBrush(C(14, 18, 50, 235))
    p.drawRoundedRect(card, h * 0.03, h * 0.03)
    _text(p, fontfn(h * 0.09), WHITE, QtCore.QRectF(card.left(), h * 0.11, card.width(), h * 0.11), QtCore.Qt.AlignCenter, "시선 슈터")
    lines = [("바라보는 칸으로 군인 분대가 이동하고 자동으로 쏴요", INKW),
             ("초록 강화 상자는 쏴서 부수면 얻어요 — 체력 숫자만큼!", GOOD),
             ("외계인이 선까지 내려오면 목숨이 줄어요 (목숨 3개)", INKW),
             ("중간보스 2마리 → 최종보스. 붉게 경고하는 칸은 피하세요!", BAD),
             ("윙크(클릭) = 수류탄 · 30초마다 사용", GOLD)]
    for i, (s, col) in enumerate(lines):
        _text(p, fontfn(h * 0.034), col, QtCore.QRectF(card.left(), h * 0.255 + i * h * 0.075, card.width(), h * 0.06), QtCore.Qt.AlignCenter, s)
    _button(p, fontfn, L["start"], "바라보면 시작", prog if hot_key == "start" else 0.0, hot_key == "start", h)
    _button(p, fontfn, L["exit"], "나가기", prog if hot_key == "exit" else 0.0, hot_key == "exit", h, C(120, 90, 100))


def draw_result(p, g, w, h, fontfn, L, prog, hot_key):
    p.fillRect(QtCore.QRectF(0, 0, w, h), C(6, 8, 26, 190))
    pw = min(w * 0.6, h * 1.1)
    card = QtCore.QRectF(w / 2 - pw / 2, h * 0.14, pw, h * 0.66)
    p.setPen(_pen(GOOD if g.state == "win" else BAD, h * 0.005))
    p.setBrush(C(14, 18, 50, 240))
    p.drawRoundedRect(card, h * 0.03, h * 0.03)
    _text(p, fontfn(h * 0.095), GOOD if g.state == "win" else BAD, QtCore.QRectF(card.left(), h * 0.17, card.width(), h * 0.12), QtCore.Qt.AlignCenter, g.result_text)
    rows = [f"점수  {g.score}", f"최고 점수  {g.best}", f"처치한 무리  {g.kills}   ·   남은 목숨  {max(0, g.lives)}", f"버틴 시간  {g.t_end:.0f}초"]
    for i, s in enumerate(rows):
        _text(p, fontfn(h * (0.06 if i == 0 else 0.036)), INKW if i else GOLD, QtCore.QRectF(card.left(), h * 0.31 + i * h * 0.075, card.width(), h * 0.07), QtCore.Qt.AlignCenter, s)
    _button(p, fontfn, L["retry"], "다시 하기", prog if hot_key == "retry" else 0.0, hot_key == "retry", h)
    _button(p, fontfn, L["quit"], "나가기", prog if hot_key == "quit" else 0.0, hot_key == "quit", h, C(120, 90, 100))


class Sounds:
    """효과음. QtMultimedia 가 없거나 소리 장치가 없으면 조용히 건너뜀."""

    def __init__(self, enabled=True):
        self.fx = {}
        if not enabled:
            return
        try:
            from PyQt5.QtMultimedia import QSoundEffect
            d = Path(tempfile.mkdtemp(prefix="shooter_snd_"))
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


class ShooterWindow(QtWidgets.QWidget):
    def __init__(self, windowed=False, mute=False, hide_cursor=False, gaze_port=GAZE_PORT):
        super().__init__()
        geo = QtWidgets.QApplication.primaryScreen().geometry()
        if windowed:
            self.setWindowTitle("시선 슈터")
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
        self.game = Game(self.width(), self.height())
        self.mode = "title"                     # title / play / result
        self.bdwell = Dwell()
        self._lock, self._lock_t = "*", time.time()   # 화면이 바뀐 직후엔 버튼에서 시선을 한 번 떼야 눌림
        self.ptr = None
        self.kb_until = 0.0                     # 키보드로 칸을 옮긴 뒤 잠깐은 시선을 무시
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    # ═════════ 입력 ═════════
    def _pointer(self, now):
        g = self.gaze.poll(now)
        if g is not None:
            loc = self.mapFromGlobal(QtCore.QPoint(int(g[0]), int(g[1])))
        else:
            loc = self.mapFromGlobal(QtGui.QCursor.pos())
        return loc.x(), loc.y()

    def _buttons(self, now):
        L = ui_layout(self.width(), self.height())
        if self.mode == "title":
            return [Btn("start", L["start"], MENU_DWELL), Btn("exit", L["exit"], EXIT_DWELL)]
        if self.mode == "result" and now - self.game.t_end_wall >= RESULT_ARM_SEC:
            return [Btn("retry", L["retry"], MENU_DWELL), Btn("quit", L["quit"], EXIT_DWELL)]
        if self.mode == "play":
            return [Btn("exit", L["exit"], EXIT_DWELL)]
        return []

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
        if self._lock is not None:
            if key != self._lock:
                self._lock = None
            else:
                self.bdwell.reset()
                return
        if self.bdwell.step(key, now, hit.need if hit else 1.0):
            self._activate(key, now)

    def _activate(self, key, now):
        if key == "start" or key == "retry":
            self._start_game(now)
        elif key == "exit":
            if self.mode == "play":
                self._to_title(now)
            else:
                self.close()
        elif key == "quit":
            self.close()
        self._lock, self._lock_t = "*", now
        self.bdwell.reset()

    def _start_game(self, now):
        best = self.game.best
        self.game = Game(self.width(), self.height())
        self.game.best = best
        self.game.t_end_wall = 0.0
        self.mode = "play"
        self.kb_until = 0.0
        self.setCursor(QtCore.Qt.BlankCursor)                 # 게임 중엔 마우스 커서를 숨김
        self.sounds.play("start")

    def _show_cursor(self):
        if not self.hide_cursor:
            self.unsetCursor()

    def _to_title(self, now):
        self.mode = "title"
        self._show_cursor()
        self.sounds.play("select")

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return
        now = time.time()
        if self.mode == "play":                                  # 윙크 = 클릭 = 수류탄
            self.game.grenade(now)
            return
        for b in self._buttons(now):                             # 테스트용: 클릭하면 버튼이 바로 눌림
            if b.contains(event.x(), event.y()):
                self._activate(b.key, now)
                break

    def keyPressEvent(self, event):
        key, now = event.key(), time.time()
        K = QtCore.Qt
        if key == K.Key_Escape:
            if self.mode == "play":
                self._to_title(now)
            else:
                self.close()
        elif self.mode == "title" and key in (K.Key_Return, K.Key_Enter, K.Key_Space):
            self._start_game(now)
        elif self.mode == "play" and key == K.Key_Space:
            self.game.grenade(now)
        elif self.mode == "play" and key in (K.Key_Left, K.Key_Right):
            self.game.set_lane(self.game.lane + (-1 if key == K.Key_Left else 1))
            self.kb_until = now + 1.2
        elif self.mode in ("play", "result") and key == K.Key_R:
            self._start_game(now)

    def showEvent(self, event):
        super().showEvent(event)
        self.activateWindow()
        self.setFocus()

    def _tick(self):
        now = time.time()
        w, h = self.width(), self.height()
        self.ptr = self._pointer(now)
        g = self.game
        if self.mode == "play":
            g.set_size(w, h)
            gx = None if now < self.kb_until else self.ptr[0]
            g.update(now, gx)
            seen = set()
            for ev in g.pop_events():
                if ev not in seen:
                    seen.add(ev)
                    self.sounds.play(ev)
            if g.state != "play":
                self.mode = "result"
                self._show_cursor()
                g.t_end_wall = now
                self._lock, self._lock_t = "*", now
        self._buttons_step(now, self.ptr)
        self.update()

    # ═════════ 글꼴 / 그리기 ═════════
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

    def paintEvent(self, event):
        now = time.time()
        w, h = self.width(), self.height()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        draw_scene(p, self.game, w, h, now, self._font, None, show_game=(self.mode != "title"))   # 게임 중엔 시선 점을 그리지 않음
        L = ui_layout(w, h)
        hot = self.bdwell.key
        prog = self.bdwell.progress
        if self.mode == "title":
            draw_title(p, w, h, self._font, L, prog, hot)
        elif self.mode == "result":
            draw_result(p, self.game, w, h, self._font, L, prog, hot)
        else:
            _button(p, self._font, L["exit"], "나가기", prog if hot == "exit" else 0.0, hot == "exit", h, C(120, 90, 100))
        if self.mode != "play" and self.ptr is not None:         # 메뉴에서도 시선 점이 보이게
            p.setBrush(QtCore.Qt.NoBrush)
            p.setPen(_pen(C(126, 200, 255, 220), max(2.0, h * 0.004)))
            p.drawEllipse(QtCore.QPointF(self.ptr[0], self.ptr[1]), h * 0.022, h * 0.022)
        p.end()


def main():
    ap = argparse.ArgumentParser(description="눈동자 마우스 시연용 시선 슈터")
    ap.add_argument("--windowed", action="store_true", help="전체화면 대신 창으로 실행 (테스트용)")
    ap.add_argument("--mute", action="store_true", help="효과음 끄기")
    ap.add_argument("--hide-cursor", action="store_true", help="윈도우 마우스 커서 숨기기")
    ap.add_argument("--gaze-port", type=int, default=GAZE_PORT, help="눈동자 마우스가 시선을 보내는 UDP 포트 (0 = 안 받음)")
    args = ap.parse_args()
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    app = QtWidgets.QApplication(sys.argv)
    win = ShooterWindow(windowed=args.windowed, mute=args.mute, hide_cursor=args.hide_cursor, gaze_port=args.gaze_port)
    if args.windowed:
        win.show()
    else:
        win.showFullScreen()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
