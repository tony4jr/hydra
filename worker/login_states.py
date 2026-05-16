"""Phase 2.1 — Login FSM 상태 enum + transition map.

login.py 의 6 경로 분기를 명시적 enum 으로 추출.
worker/capture.py 가 UNKNOWN_SCREEN 캡처할 때 screen_state 라벨로도 사용.

Why:
  - phase_config.py 의 phase 는 시간/타이밍 단위 (compose, type, submit)
  - LoginState 는 *화면 상태* 단위 (EMAIL_INPUT, TWO_FACTOR, ...)
  - 두 차원이 직교 — phase + state 이중 추적으로 디버깅/분석 ↑

How to apply:
  log.info(f"login state={LoginState.EMAIL_INPUT.value}")
  capture_unknown_screen(page, screen_state=LoginState.TRUST_DEVICE_PROMPT.value, ...)

Transition: 코드 강제 X (advisory). 실제 분기는 login.py 가 page state 보고 결정.
이 map 은 admin UI / diagnostic 에서 "어디서 막혔는지" 시각화용.
"""
from __future__ import annotations

from enum import StrEnum


class LoginState(StrEnum):
    INIT = "init"
    SIGNIN_LANDING = "signin_landing"        # accounts.google.com/signin 첫 진입
    EMAIL_INPUT = "email_input"               # input[type=email] 보임
    PASSWORD_INPUT = "password_input"         # input[type=password] 보임
    ACCOUNT_CHOOSER = "account_chooser"       # 이미 로그인된 계정 목록 화면
    CONFIRM_IDENTIFIER = "confirm_identifier" # 본인 인증 (email 없이 "다음" 만)
    IDENTITY_CHALLENGE = "identity_challenge" # 휴면/새 IP 등 보안 확인
    TWO_FACTOR = "two_factor"                 # 2FA 코드 입력
    TRUST_DEVICE_PROMPT = "trust_device_prompt"  # "이 기기 안전 등록할까요?"
    POST_LOGIN_PROMPTS = "post_login_prompts" # 복구 전화/사진 추가 스킵
    LOGIN_SUCCESS = "login_success"           # myaccount/youtube 착지
    POST_PASSWORD_UNKNOWN = "post_password_unknown"  # email 없고 known url 도 아님
    LOGIN_FAILED = "login_failed"             # 비번 틀림 등 명시적 실패


# 정상 흐름 (advisory — 코드 강제 X)
EXPECTED_TRANSITIONS: dict[LoginState, set[LoginState]] = {
    LoginState.INIT: {LoginState.SIGNIN_LANDING},
    LoginState.SIGNIN_LANDING: {
        LoginState.EMAIL_INPUT,
        LoginState.ACCOUNT_CHOOSER,
        LoginState.CONFIRM_IDENTIFIER,
        LoginState.LOGIN_SUCCESS,           # 이미 로그인된 채로 redirect
        LoginState.POST_PASSWORD_UNKNOWN,
    },
    LoginState.EMAIL_INPUT: {
        LoginState.PASSWORD_INPUT,
        LoginState.IDENTITY_CHALLENGE,
        LoginState.LOGIN_FAILED,
    },
    LoginState.ACCOUNT_CHOOSER: {
        LoginState.PASSWORD_INPUT,
        LoginState.IDENTITY_CHALLENGE,
    },
    LoginState.CONFIRM_IDENTIFIER: {LoginState.PASSWORD_INPUT},
    LoginState.PASSWORD_INPUT: {
        LoginState.TWO_FACTOR,
        LoginState.IDENTITY_CHALLENGE,
        LoginState.TRUST_DEVICE_PROMPT,
        LoginState.POST_LOGIN_PROMPTS,
        LoginState.LOGIN_SUCCESS,
        LoginState.LOGIN_FAILED,
    },
    LoginState.TWO_FACTOR: {
        LoginState.TRUST_DEVICE_PROMPT,
        LoginState.POST_LOGIN_PROMPTS,
        LoginState.LOGIN_SUCCESS,
        LoginState.LOGIN_FAILED,
    },
    LoginState.IDENTITY_CHALLENGE: {
        LoginState.PASSWORD_INPUT,
        LoginState.TWO_FACTOR,
        LoginState.LOGIN_FAILED,
    },
    LoginState.TRUST_DEVICE_PROMPT: {LoginState.POST_LOGIN_PROMPTS, LoginState.LOGIN_SUCCESS},
    LoginState.POST_LOGIN_PROMPTS: {LoginState.LOGIN_SUCCESS},
    LoginState.LOGIN_SUCCESS: set(),
    LoginState.POST_PASSWORD_UNKNOWN: set(),
    LoginState.LOGIN_FAILED: set(),
}


def is_terminal(state: LoginState) -> bool:
    return state in (LoginState.LOGIN_SUCCESS, LoginState.LOGIN_FAILED, LoginState.POST_PASSWORD_UNKNOWN)


def is_unexpected_transition(from_state: LoginState, to_state: LoginState) -> bool:
    """advisory — 예상 밖 전이면 True (로그에 warning 권장)."""
    return to_state not in EXPECTED_TRANSITIONS.get(from_state, set())
