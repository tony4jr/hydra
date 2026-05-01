/**
 * 코드 식별자 → UI 표시 문자열 매핑.
 *
 * CLAUDE.md §6 용어 매핑표 기준. PR-1 명세 (redesign/PR-1-terminology.md).
 *
 * 원칙:
 *   - DB 컬럼명, API 필드명, 변수명 (코드 식별자) 는 절대 안 바꿈
 *   - UI 표시 문자열만 한국어 운영자 용어로
 *   - 매핑 없는 키는 fallback (term 헬퍼)
 *
 * 예: lifecycle_phase=1 (코드) → "신규 영상" (UI 표시)
 */

// ─────────────────────────────────────────────────────────────────
// Lifecycle phase (영상 나이 기준 4단계)
// 코드: lifecycle_phase: 1|2|3|4
// ─────────────────────────────────────────────────────────────────
export const lifecyclePhase = {
  1: '신규 영상',
  2: '활성',
  3: '안정',
  4: '장기',
} as const

// ─────────────────────────────────────────────────────────────────
// L tier (시간 민감도 기준 4단계)
// 코드: l_tier: 'L1' | 'L2' | 'L3' | 'L4'
// ─────────────────────────────────────────────────────────────────
export const tier = {
  L1: '장기 자산',
  L2: '신규',
  L3: '트렌딩',
  L4: '롱테일',
} as const

// ─────────────────────────────────────────────────────────────────
// Task state (작업 큐)
// 코드: tasks.status
// ─────────────────────────────────────────────────────────────────
export const taskState = {
  pending: '대기',
  in_progress: '진행중',
  done: '완료',
  failed: '실패',
} as const

// ─────────────────────────────────────────────────────────────────
// Account state (계정 풀)
// 코드: accounts.status
// ─────────────────────────────────────────────────────────────────
export const accountState = {
  active: '활성',
  warmup: '워밍업',
  cooldown: '쿨다운',
  suspended: '정지',
  ghost: '고스트',
  verifying: '본인 인증',
} as const

// ─────────────────────────────────────────────────────────────────
// Video state (영상 풀)
// 코드: videos.state
// ─────────────────────────────────────────────────────────────────
export const videoState = {
  active: '활성',
  pending: '대기',
  blocked: '차단',
  blacklisted: '차단',  // 코드의 blacklisted 도 같은 표시
  paused: '일시정지',
  retired: '은퇴',
  completed: '완료',
} as const

// ─────────────────────────────────────────────────────────────────
// Priority
// 코드: tasks.priority
// ─────────────────────────────────────────────────────────────────
export const priority = {
  high: '높음',
  normal: '보통',
  low: '낮음',
} as const

// ─────────────────────────────────────────────────────────────────
// 단일 진실의 원천: 자주 쓰는 도메인 라벨
// PR-2 이후 페이지에서도 import 해서 사용
// ─────────────────────────────────────────────────────────────────
export const labels = {
  // 사이드바 그룹 (PR-2와 함께 적용)
  groupHome: '홈',
  groupOperation: '제품 운영',
  groupInfra: '인프라',

  // 페이지명
  pageHome: '운영 현황',
  pageProducts: '제품 목록',
  pageNiche: '타겟',
  pageCampaigns: '캠페인',
  pageVideos: '영상',
  pageTasks: '작업 큐',
  pageAccounts: '계정 풀',
  pageWorkers: '작업 PC',
  pageAvatars: '아바타·페르소나',
  pageSettings: '시스템 설정',

  // 도메인 핵심 용어 (운영자 멘탈모델)
  niche: '타겟',
  marketDefinition: '시장 정의',         // ← embedding_reference_text 의 UI 라벨
  marketFitness: '시장 적합도',          // ← embedding_score 의 UI 라벨
  collectionFunnel: '수집 흐름',
  autoExclusion: '자동 제외',            // ← hard_block_rules 의 UI 라벨
  protectionRules: '영상 보호 룰',
  ghostDetection: '댓글 생존 검증',
  apiQuota: 'API 사용량',                // ← quota 의 UI 라벨

  // 시장 페이지 5탭 (PR-4)
  tabOverview: '개요',
  tabCollection: '수집',
  tabMessaging: '메시지',
  tabCampaigns: '캠페인',
  tabAnalytics: '분석',

  // 상태 동사
  pause: '일시정지',
  resume: '재개',
  emergency: '비상정지',
  deploy: '배포',
  restoreDefault: '기본값으로 복원',
} as const

// ─────────────────────────────────────────────────────────────────
// Helper: 안전한 매핑 조회
// 매핑에 없는 키는 fallback (또는 키 자체) 반환
// ─────────────────────────────────────────────────────────────────

/**
 * 매핑 헬퍼.
 *
 * @param map  매핑 객체 (예: lifecyclePhase, tier)
 * @param key  조회할 키
 * @param fallback  매핑 없을 때 반환값. 미지정 시 키 자체 반환
 *
 * @example
 *   term(tier, 'L1')                  // → '장기 자산'
 *   term(tier, 'L99')                 // → 'L99' (fallback)
 *   term(tier, 'L99', '알 수 없음')    // → '알 수 없음'
 */
export function term<T extends Record<string | number, string>>(
  map: T,
  key: keyof T | string | number,
  fallback?: string,
): string {
  const value = (map as Record<string | number, string>)[key as string | number]
  if (value !== undefined) return value
  if (fallback !== undefined) return fallback
  return String(key)
}
