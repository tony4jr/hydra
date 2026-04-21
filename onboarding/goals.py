"""각 온보딩 목표의 detect + apply 인터페이스.

Goal 은 동일 인터페이스로 호출되어 verifier 가 순차 실행한다.
실행 가능한 goals 는 이 파일 하단의 ALL_GOALS 리스트에 등록.
"""
from typing import Literal, Protocol, runtime_checkable


State = Literal["done", "not_done", "blocked"]
ApplyResult = Literal["done", "failed", "blocked"]


@runtime_checkable
class Goal(Protocol):
    name: str
    required: bool

    async def detect(self, page, acct) -> State: ...
    async def apply(self, page, acct) -> ApplyResult: ...


# --- 각 goal 은 다음 task 에서 추가됨. ALL_GOALS 는 verifier 가 import.
ALL_GOALS: list[Goal] = []
