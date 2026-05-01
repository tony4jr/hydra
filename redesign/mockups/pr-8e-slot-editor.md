# PR-8e 슬롯 편집 mockup (시각 가이드)

원본 HTML mockup (파일 인코딩 깨짐) 의 핵심 시각 결정 정리. fix/pr-8e-visual 의
구현이 따라야 할 시각 사양.

## 슬롯 아바타 (36x36 원형, gradient)
- A: linear-gradient(135deg, #f59e0b, #ef4444)  주황→빨강
- B: linear-gradient(135deg, #3b82f6, #1e40af)  파랑→남색
- C: linear-gradient(135deg, #10b981, #047857)  녹색→진녹
- D: linear-gradient(135deg, #8b5cf6, #6d28d9)  보라
- E: linear-gradient(135deg, #ec4899, #be185d)  핑크
- F: linear-gradient(135deg, #14b8a6, #0f766e)  청록

## 답글 들여쓰기 (트리)
- depth 1: ml-12 (48px), border-left 2px solid var(--border), pl-3.5
- depth 2: ml-24 (96px)
- depth 3: ml-36 (144px)

## 좋아요 박스 (분홍)
- bg #fef2f2, border 1px #fecaca, rounded-md
- 한 줄: [❤ 좋아요] [최소 input 42px] ~ [최대] [시점 select]
- ❤ 아이콘: lucide Heart, fill #dc2626, color #dc2626
- input: w-[42px] text-center

## ↻ 재등장 마크
- 아바타 우하단 16x16 원형 (background #a16207, border 2px solid bg)
- 흰 ↻ 텍스트 (lucide RotateCcw)
- 메타 라벨도 주황: bg #fef3c7, color #a16207

## 화력 요약 (상단 4 카드)
- 총 댓글 (액션) / 슬롯 (워커 수, 주황) / 총 좋아요 (빨강) / 필요 워커
- card: padding 10px 12px, surface bg, border, rounded-lg

## 슬롯 사용 통계 (칩 그룹)
- "슬롯 사용:" + 칩들
- 각 칩: [컬러 letter 18x18] [A] [3번 등장]

## 미리보기 모드 (YouTube 댓글 영역)
- 빨간 YouTube 헤더
- 영상 정보 카드
- 댓글 트리 (들여쓰기 + 같은 색 아바타)
- 메타 태그: "A · W1 · ❤ 12" (보라 배지)
- ↻ 재등장: "A · ↻ 재등장 · ❤ 6" (주황 배지)

## AI 변형 슬라이더 라벨
- 0~20%: "안전 — 양식 그대로"
- 30~60%: "균형"
- 70~80%: "맥락 우선"
- 90~100%: "완전 자유"

## placeholder 양식 텍스트
- 메인: "저도 [고민] 때문에 고생했는데, 이 영상 보고 [공감]..."
- 답글: "오 그거 [질문]?"
- 답답글: "[답변] 입니다!"
