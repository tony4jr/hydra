# onboarding/selectors.py
"""YT/Google DOM 셀렉터 — UI 변경 시 이 파일만 수정하면 모든 goal 에 반영."""

# --- Google accounts / signin ---
EMAIL_INPUT = "input[type='email']"
PASSWORD_INPUT = "input[type='password'][name='Passwd']"
RECOVERY_CODE_INPUT = "input[name='Pin'], input[type='text'][name='Pin'], input[type='tel']"

# --- Google myaccount ---
ACCOUNT_AVATAR_SELECTORS = [
    "#avatar-btn img",
    "ytcp-entity-avatar img",
    "#account-menu-button img",
]

# --- YouTube ---
YT_AVATAR_BTN = "button#avatar-btn, img.yt-spec-avatar-shape__image"
YT_AVATAR_SRC_DEFAULT_PREFIX = "AIdro_"  # 기본 placeholder src 해시 접두

# --- YT Studio 맞춤설정 ---
STUDIO_HANDLE_INPUT = "input[placeholder='핸들 설정']"
STUDIO_NAME_INPUT_WRAPPER = "ytcp-channel-editing-channel-name input"
STUDIO_PUBLISH_BUTTON = "ytcp-button#publish-button button"
STUDIO_PROFILE_IMAGE_SECTION = "ytcp-profile-image-upload"
STUDIO_REPLACE_BUTTON = (
    "ytcp-profile-image-upload ytcp-button#replace-button button, "
    "ytcp-profile-image-upload ytcp-button#upload-button button, "
    "ytcp-profile-image-upload button:has-text('변경'), "
    "ytcp-profile-image-upload button:has-text('업로드'), "
    "ytcp-profile-image-upload button:has-text('Change'), "
    "ytcp-profile-image-upload button:has-text('Upload')"
)
STUDIO_HANDLE_SUGGESTION_ANCHOR = "ytcp-anchor.YtcpChannelEditingChannelHandleSuggestedHandleAnchor"

# --- URL 패턴 (startswith 체크용) ---
URL_SIGNIN_IDENTIFIER = "https://accounts.google.com/v3/signin/identifier"
URL_CHALLENGE_PWD = "https://accounts.google.com/v3/signin/challenge/pwd"
URL_CHALLENGE_IPE_VERIFY = "https://accounts.google.com/v3/signin/challenge/ipe/verify"
URL_CHALLENGE_SELECTION = "https://accounts.google.com/v3/signin/challenge/selection"
URL_CHALLENGE_TOTP = "https://accounts.google.com/v3/signin/challenge/totp"
URL_CHALLENGE_DP = "https://accounts.google.com/v3/signin/challenge/dp"  # 계정 사망 신호 — 폐기
URL_CHALLENGE_IPP = "https://accounts.google.com/v3/signin/challenge/ipp"  # 복구 전화 변경 확인 — 7일 쿨다운
URL_GDS_RECOVERY = "https://gds.google.com/web/recoveryoptions"
URL_GDS_HOMEADDRESS = "https://gds.google.com/web/homeaddress"
URL_GDS_PREFIX = "https://gds.google.com/web/"
URL_MYACCOUNT = "https://myaccount.google.com/"
URL_YOUTUBE = "https://www.youtube.com/"
