"""Scenario definitions and selection logic.

Spec Part 6.2-6.3: 10 scenarios (A~J), pure code selection (no AI).
Delays are defined as (min, max) ranges and randomized at campaign creation time.
"""

import random
from dataclasses import dataclass, field
from copy import deepcopy

from hydra.core.enums import Scenario, AccountRole


@dataclass
class ScenarioStep:
    role: AccountRole
    type: str                          # comment | reply
    delay_range: tuple[int, int]       # (min_minutes, max_minutes)
    parent_step: int | None = None     # step index for replies

    @property
    def delay_min(self) -> int:
        """Generate random delay within range. Called each time."""
        lo, hi = self.delay_range
        return random.randint(lo, hi) if lo != hi else lo


@dataclass
class ScenarioTemplate:
    id: Scenario
    name: str
    description: str
    steps: list[ScenarioStep]
    like_target_step: int              # which step gets like boost
    total_likes: tuple[int, int]       # (min, max) total likes


TEMPLATES: dict[Scenario, ScenarioTemplate] = {
    Scenario.A: ScenarioTemplate(
        id=Scenario.A, name="씨앗 심기", description="단독 댓글, 브랜드 언급 0",
        steps=[
            ScenarioStep(AccountRole.SEED, "comment", (0, 0)),
        ],
        like_target_step=0, total_likes=(3, 5),
    ),

    Scenario.B: ScenarioTemplate(
        id=Scenario.B, name="자연스러운 질문 유도", description="티키타카 3턴",
        steps=[
            ScenarioStep(AccountRole.SEED, "comment", (0, 0)),
            ScenarioStep(AccountRole.ASKER, "reply", (30, 60), parent_step=0),
            ScenarioStep(AccountRole.SEED, "reply", (30, 60), parent_step=0),
        ],
        like_target_step=0, total_likes=(5, 10),
    ),

    Scenario.C: ScenarioTemplate(
        id=Scenario.C, name="동조 여론 형성", description="대댓글 5~8개",
        steps=[
            ScenarioStep(AccountRole.SEED, "comment", (0, 0)),
            ScenarioStep(AccountRole.WITNESS, "reply", (30, 50), parent_step=0),
            ScenarioStep(AccountRole.AGREE, "reply", (40, 80), parent_step=0),
            ScenarioStep(AccountRole.CURIOUS, "reply", (90, 150), parent_step=0),
            ScenarioStep(AccountRole.WITNESS, "reply", (20, 40), parent_step=0),
            ScenarioStep(AccountRole.AGREE, "reply", (40, 80), parent_step=0),
        ],
        like_target_step=0, total_likes=(10, 20),
    ),

    Scenario.D: ScenarioTemplate(
        id=Scenario.D, name="비포애프터 경험담", description="대댓글 4~6개",
        steps=[
            ScenarioStep(AccountRole.SEED, "comment", (0, 0)),
            ScenarioStep(AccountRole.CURIOUS, "reply", (20, 40), parent_step=0),
            ScenarioStep(AccountRole.SEED, "reply", (20, 40), parent_step=0),
            ScenarioStep(AccountRole.ASKER, "reply", (40, 80), parent_step=0),
            ScenarioStep(AccountRole.SEED, "reply", (20, 40), parent_step=0),
            ScenarioStep(AccountRole.AGREE, "reply", (90, 150), parent_step=0),
            ScenarioStep(AccountRole.FAN, "reply", (120, 240), parent_step=0),
        ],
        like_target_step=0, total_likes=(15, 30),
    ),

    Scenario.E: ScenarioTemplate(
        id=Scenario.E, name="슥 지나가기", description="짧고 캐주얼 단독",
        steps=[
            ScenarioStep(AccountRole.AGREE, "comment", (0, 0)),
        ],
        like_target_step=0, total_likes=(5, 10),
    ),

    Scenario.F: ScenarioTemplate(
        id=Scenario.F, name="정보형 교육", description="티키타카 4턴",
        steps=[
            ScenarioStep(AccountRole.INFO, "comment", (0, 0)),
            ScenarioStep(AccountRole.CURIOUS, "reply", (40, 80), parent_step=0),
            ScenarioStep(AccountRole.INFO, "reply", (20, 40), parent_step=0),
            ScenarioStep(AccountRole.ASKER, "reply", (40, 80), parent_step=0),
            ScenarioStep(AccountRole.WITNESS, "reply", (20, 40), parent_step=0),
        ],
        like_target_step=0, total_likes=(10, 15),
    ),

    Scenario.G: ScenarioTemplate(
        id=Scenario.G, name="남의 댓글 올라타기", description="기존 댓글에 답글",
        steps=[
            ScenarioStep(AccountRole.QA, "reply", (0, 0)),
            ScenarioStep(AccountRole.CURIOUS, "reply", (40, 80), parent_step=0),
            ScenarioStep(AccountRole.QA, "reply", (20, 40), parent_step=0),
        ],
        like_target_step=0, total_likes=(5, 10),
    ),

    Scenario.H: ScenarioTemplate(
        id=Scenario.H, name="반박 → 중재", description="부정 의견 활용",
        steps=[
            ScenarioStep(AccountRole.SEED, "comment", (0, 0)),
            ScenarioStep(AccountRole.WITNESS, "reply", (40, 80), parent_step=0),
            ScenarioStep(AccountRole.SEED, "reply", (20, 40), parent_step=0),
            ScenarioStep(AccountRole.WITNESS, "reply", (20, 40), parent_step=0),
            ScenarioStep(AccountRole.AGREE, "reply", (90, 150), parent_step=0),
        ],
        like_target_step=1, total_likes=(10, 20),
    ),

    Scenario.I: ScenarioTemplate(
        id=Scenario.I, name="간접 경험 (선물·추천)", description="대댓글 4~6개",
        steps=[
            ScenarioStep(AccountRole.SEED, "comment", (0, 0)),
            ScenarioStep(AccountRole.CURIOUS, "reply", (30, 50), parent_step=0),
            ScenarioStep(AccountRole.SEED, "reply", (20, 40), parent_step=0),
            ScenarioStep(AccountRole.CURIOUS, "reply", (40, 80), parent_step=0),
            ScenarioStep(AccountRole.SEED, "reply", (20, 40), parent_step=0),
            ScenarioStep(AccountRole.FAN, "reply", (90, 150), parent_step=0),
        ],
        like_target_step=0, total_likes=(10, 20),
    ),

    Scenario.J: ScenarioTemplate(
        id=Scenario.J, name="숏폼 전용", description="극도로 짧고 캐주얼",
        steps=[
            ScenarioStep(AccountRole.AGREE, "comment", (0, 0)),
        ],
        like_target_step=0, total_likes=(5, 10),
    ),
}


def select_scenario(
    is_fresh: bool,
    is_short: bool,
    comment_count: int | None,
    has_active_campaign: bool,
) -> Scenario:
    """Select scenario based on video state. Pure code, no AI."""
    if has_active_campaign:
        return Scenario.C

    if is_fresh:
        return random.choices(
            [Scenario.A, Scenario.B, Scenario.D],
            weights=[30, 40, 30],
        )[0]

    if comment_count and comment_count > 100:
        return random.choices(
            [Scenario.G, Scenario.E],
            weights=[60, 40],
        )[0]

    if is_short:
        return Scenario.J

    return random.choices(
        [Scenario.A, Scenario.B, Scenario.C, Scenario.D,
         Scenario.E, Scenario.F, Scenario.H, Scenario.I],
        weights=[15, 20, 20, 15, 5, 10, 5, 10],
    )[0]


def get_template(scenario: Scenario) -> ScenarioTemplate:
    """Return a deep copy so each campaign gets fresh random delays."""
    return deepcopy(TEMPLATES[scenario])
