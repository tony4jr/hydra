// Commex Renewal — shared mock data for design review
// 실데이터 연결은 차후 단계.

export type Niche = {
  id: string
  name: string
  desc: string
  keywords: string[]
  presets: string[]
  videos: number
}
export type Brand = {
  id: string
  name: string
  summary: string
  niches: Niche[]
}
export type AutoJob = {
  id: string
  brand: string
  niche: string
  active: boolean
  nextRun: string
  lastRun: string
  keywords: string[]
  limit: string
  time: string
}
export type QueueStatus =
  | 'draft'
  | 'pending'
  | 'scheduled'
  | 'running'
  | 'done'
  | 'failed'
export type QueueItem = {
  id: string
  title: string
  brand: string
  niche: string
  createdAt: string
  status: QueueStatus
  worker: string
}
export type VideoStatus = '후보' | '수집완료' | '보류' | '제외'
export type Video = {
  id: string
  title: string
  brand: string
  niche: string
  source: string
  date: string
  lang: string
  views: string
  comments: string
  relevance: number
  status: VideoStatus
  url: string
  duration: string
}
export type GlobalPreset = {
  id: string
  name: string
  desc: string
  used: number
  version: string
}
export type WorkerInfo = {
  id: number
  name: string
  status: 'online' | 'paused' | 'offline'
  currentTask?: string
  heartbeat: string
  version: string
  os: 'win' | 'mac'
}
export type ActivityItem = {
  id: string
  kind: 'draft' | 'auto' | 'pending' | 'done' | 'fail' | 'video' | 'preset'
  title: string
  body: string
  time: string
}
export type LogEntry = {
  time: string
  event: string
  meta: string[]
}

// ============================================================
// BRANDS / NICHES
// ============================================================

export const BRANDS: Brand[] = [
  {
    id: 'b1',
    name: '모렉신',
    summary: '탈모/두피 케어 제품 중심 운영',
    niches: [
      {
        id: 'n1',
        name: '탈모 고민',
        desc: '공감형 진입과 감정 반응 중심',
        keywords: ['탈모', '머리빠짐', '두피', '고민', 'M자탈모'],
        presets: ['공감형 메인 댓글', '답글 세트 A', '감정 공감 메인'],
        videos: 128,
      },
      {
        id: 'n2',
        name: '두피 관리',
        desc: '정보형/솔루션형 댓글 중심',
        keywords: ['두피관리', '샴푸', '각질', '케어', '두피염'],
        presets: ['정보형 메인 댓글', '질문형 후속', '두피 케어 정보형'],
        videos: 76,
      },
      {
        id: 'n3',
        name: '남성 헤어',
        desc: '남성 헤어/볼륨 관련 반응형',
        keywords: ['남성헤어', '볼륨', '스타일링', '모발'],
        presets: ['볼륨 고민 반응형', '질문형 진입'],
        videos: 42,
      },
      {
        id: 'n6',
        name: '여성 헤어 케어',
        desc: '굵기·윤기 관련 정보형',
        keywords: ['여성탈모', '머리굵기', '헤어케어'],
        presets: ['정보형 메인 댓글', '경험 공유형'],
        videos: 58,
      },
    ],
  },
  {
    id: 'b2',
    name: '픽셀브루',
    summary: '직장인 루틴/생산성 운영',
    niches: [
      {
        id: 'n4',
        name: '직장인 루틴',
        desc: '짧은 공감과 루틴 대화 중심',
        keywords: ['출근루틴', '생산성', '아침', '습관'],
        presets: ['루틴 공감형', '질문형 진입'],
        videos: 91,
      },
      {
        id: 'n7',
        name: '카페/홈카페',
        desc: '취향 공감 + 추천 정보',
        keywords: ['홈카페', '에스프레소', '드립커피'],
        presets: ['취향 공감형', '정보형 메인 댓글'],
        videos: 33,
      },
    ],
  },
  {
    id: 'b3',
    name: '루미핏',
    summary: '홈트/입문자 운동 중심',
    niches: [
      {
        id: 'n5',
        name: '홈트 초보',
        desc: '초보 공감형과 실수 방지형',
        keywords: ['홈트', '초보', '실수', '운동루틴'],
        presets: ['초보 공감형', '정보형 메인 댓글'],
        videos: 58,
      },
      {
        id: 'n8',
        name: '식단 관리',
        desc: '다이어트 식단 후기형',
        keywords: ['다이어트', '식단', '저탄고지', '단백질'],
        presets: ['후기형 세트', '질문형 진입'],
        videos: 47,
      },
    ],
  },
  {
    id: 'b4',
    name: '노마셀',
    summary: '뷰티/올리브영 추천 운영',
    niches: [
      {
        id: 'n9',
        name: '신상 추천',
        desc: '경험형 후기 + 추천 댓글',
        keywords: ['올리브영', '신상', '추천', '5월신상'],
        presets: ['후기형 세트', '공감형 메인 댓글'],
        videos: 64,
      },
      {
        id: 'n10',
        name: '스킨케어 루틴',
        desc: '루틴 공유 + 정보형',
        keywords: ['스킨케어', '루틴', '여드름', '진정케어'],
        presets: ['정보형 메인 댓글', '경험 공유형'],
        videos: 39,
      },
    ],
  },
  {
    id: 'b5',
    name: '헬릭스코어',
    summary: '건강기능식품 / 면역 케어',
    niches: [
      {
        id: 'n11',
        name: '면역 / 비타민',
        desc: '정보형 + 권유 약한 톤',
        keywords: ['비타민', '면역', '영양제', '아연'],
        presets: ['정보형 메인 댓글', '질문형 후속'],
        videos: 51,
      },
      {
        id: 'n12',
        name: '수면 / 멜라토닌',
        desc: '공감형 진입 + 후기',
        keywords: ['불면증', '수면', '멜라토닌'],
        presets: ['공감형 메인 댓글', '후기형 세트'],
        videos: 29,
      },
    ],
  },
]

// ============================================================
// AUTO JOBS
// ============================================================

export const AUTO_JOBS: AutoJob[] = [
  { id: 'aj1', brand: '모렉신', niche: '탈모 고민', active: true, nextRun: '오늘 14:00', lastRun: '방금 전', keywords: ['탈모', '고민', '머리빠짐'], limit: '하루 12건', time: '평일 10:00 ~ 18:00' },
  { id: 'aj2', brand: '모렉신', niche: '두피 관리', active: true, nextRun: '오늘 15:30', lastRun: '2분 전', keywords: ['두피', '케어', '각질'], limit: '하루 8건', time: '매일 11:00 ~ 20:00' },
  { id: 'aj3', brand: '모렉신', niche: '남성 헤어', active: true, nextRun: '오늘 16:00', lastRun: '12분 전', keywords: ['볼륨', '스타일링'], limit: '하루 6건', time: '평일 12:00 ~ 18:00' },
  { id: 'aj4', brand: '픽셀브루', niche: '직장인 루틴', active: true, nextRun: '오늘 16:00', lastRun: '5분 전', keywords: ['아침루틴', '습관'], limit: '하루 6건', time: '주중 08:00 ~ 12:00' },
  { id: 'aj5', brand: '픽셀브루', niche: '카페/홈카페', active: false, nextRun: '내일 09:00', lastRun: '어제 18:42', keywords: ['홈카페', '드립'], limit: '하루 4건', time: '매일 09:00 ~ 17:00' },
  { id: 'aj6', brand: '루미핏', niche: '홈트 초보', active: false, nextRun: '내일 10:00', lastRun: '—', keywords: ['홈트', '초보'], limit: '하루 5건', time: '주중 14:00 ~ 20:00' },
  { id: 'aj7', brand: '루미핏', niche: '식단 관리', active: true, nextRun: '오늘 17:30', lastRun: '8분 전', keywords: ['식단', '다이어트'], limit: '하루 6건', time: '매일 11:00 ~ 21:00' },
  { id: 'aj8', brand: '노마셀', niche: '신상 추천', active: true, nextRun: '오늘 18:00', lastRun: '3분 전', keywords: ['올리브영', '신상'], limit: '하루 10건', time: '평일 10:00 ~ 19:00' },
  { id: 'aj9', brand: '노마셀', niche: '스킨케어 루틴', active: true, nextRun: '오늘 19:00', lastRun: '15분 전', keywords: ['스킨케어', '루틴'], limit: '하루 7건', time: '매일 11:00 ~ 22:00' },
  { id: 'aj10', brand: '헬릭스코어', niche: '면역 / 비타민', active: true, nextRun: '오늘 20:00', lastRun: '21분 전', keywords: ['비타민', '면역'], limit: '하루 5건', time: '매일 12:00 ~ 20:00' },
]

// ============================================================
// QUEUE
// ============================================================

export const QUEUE: QueueItem[] = [
  { id: 'q1', title: '머리 숱이 줄어드는 이유 5가지', brand: '모렉신', niche: '탈모 고민', createdAt: '방금 전', status: 'draft', worker: 'worker-03' },
  { id: 'q2', title: '샴푸 바꿔도 비듬이 계속 생기는 이유', brand: '모렉신', niche: '두피 관리', createdAt: '3분 전', status: 'draft', worker: 'worker-01' },
  { id: 'q3', title: '출근 전 5분 홈카페 루틴', brand: '픽셀브루', niche: '직장인 루틴', createdAt: '5분 전', status: 'pending', worker: '—' },
  { id: 'q4', title: '홈트 초보가 자주 하는 실수 7가지', brand: '루미핏', niche: '홈트 초보', createdAt: '8분 전', status: 'scheduled', worker: 'worker-02' },
  { id: 'q5', title: '두피 각질 관리 루틴', brand: '모렉신', niche: '두피 관리', createdAt: '12분 전', status: 'running', worker: 'worker-04' },
  { id: 'q6', title: '남자 머리 볼륨 쉽게 살리는 법', brand: '모렉신', niche: '남성 헤어', createdAt: '18분 전', status: 'done', worker: 'worker-04' },
  { id: 'q7', title: '아침 루틴 BEST 5', brand: '픽셀브루', niche: '직장인 루틴', createdAt: '24분 전', status: 'failed', worker: 'worker-06' },
  { id: 'q8', title: '올리브영 5월 신상 솔직 후기', brand: '노마셀', niche: '신상 추천', createdAt: '32분 전', status: 'done', worker: 'worker-02' },
  { id: 'q9', title: '드립커피 처음 시작할 때 알아야 할 것', brand: '픽셀브루', niche: '카페/홈카페', createdAt: '38분 전', status: 'pending', worker: '—' },
  { id: 'q10', title: '여성 탈모 초기 신호 정리', brand: '모렉신', niche: '여성 헤어 케어', createdAt: '45분 전', status: 'scheduled', worker: 'worker-05' },
  { id: 'q11', title: '저탄고지 일주일 식단 공유', brand: '루미핏', niche: '식단 관리', createdAt: '52분 전', status: 'running', worker: 'worker-01' },
  { id: 'q12', title: '여드름 진정 루틴 — 1주일 변화', brand: '노마셀', niche: '스킨케어 루틴', createdAt: '1시간 전', status: 'done', worker: 'worker-03' },
  { id: 'q13', title: '비타민 D 부족 자가진단 5가지', brand: '헬릭스코어', niche: '면역 / 비타민', createdAt: '1시간 전', status: 'done', worker: 'worker-05' },
  { id: 'q14', title: '잠 안 올 때 멜라토닌? 의사 의견', brand: '헬릭스코어', niche: '수면 / 멜라토닌', createdAt: '1시간 전', status: 'pending', worker: '—' },
  { id: 'q15', title: 'M자탈모 진행 막는 5가지 습관', brand: '모렉신', niche: '탈모 고민', createdAt: '2시간 전', status: 'failed', worker: 'worker-06' },
  { id: 'q16', title: '직장인 책상 위 필수 아이템', brand: '픽셀브루', niche: '직장인 루틴', createdAt: '2시간 전', status: 'done', worker: 'worker-02' },
  { id: 'q17', title: '홈트 30일 챌린지 결과', brand: '루미핏', niche: '홈트 초보', createdAt: '2시간 전', status: 'done', worker: 'worker-04' },
  { id: 'q18', title: '올리브영 토너 TOP 5 비교', brand: '노마셀', niche: '신상 추천', createdAt: '3시간 전', status: 'scheduled', worker: 'worker-02' },
  { id: 'q19', title: '남자 헤어 스타일링 기본 3단계', brand: '모렉신', niche: '남성 헤어', createdAt: '3시간 전', status: 'done', worker: 'worker-03' },
  { id: 'q20', title: '아연 영양제 효과 정리', brand: '헬릭스코어', niche: '면역 / 비타민', createdAt: '3시간 전', status: 'draft', worker: 'worker-01' },
  { id: 'q21', title: '진정 토너 진짜 효과 있나?', brand: '노마셀', niche: '스킨케어 루틴', createdAt: '4시간 전', status: 'failed', worker: 'worker-06' },
  { id: 'q22', title: '커피 원두 보관법 — 신선도 유지', brand: '픽셀브루', niche: '카페/홈카페', createdAt: '4시간 전', status: 'done', worker: 'worker-04' },
  { id: 'q23', title: '두피 마사지 5분 루틴', brand: '모렉신', niche: '두피 관리', createdAt: '5시간 전', status: 'done', worker: 'worker-02' },
  { id: 'q24', title: '단백질 보충제 비교 — 입문자', brand: '루미핏', niche: '식단 관리', createdAt: '5시간 전', status: 'pending', worker: '—' },
  { id: 'q25', title: '여성 탈모 영양제 추천', brand: '모렉신', niche: '여성 헤어 케어', createdAt: '6시간 전', status: 'scheduled', worker: 'worker-05' },
]

// ============================================================
// VIDEOS
// ============================================================

export const VIDEOS: Video[] = [
  { id: 'v1', title: '머리 숱이 줄어드는 이유 5가지', brand: '모렉신', niche: '탈모 고민', source: '닥터두피', date: '2026-05-08', lang: 'KO', views: '84,500', comments: '435', relevance: 93, status: '후보', url: 'https://youtube.com/watch?v=hair001', duration: '8:23' },
  { id: 'v2', title: '샴푸 바꿔도 비듬이 계속 생기는 이유', brand: '모렉신', niche: '두피 관리', source: '헤어랩', date: '2026-05-07', lang: 'KO', views: '52,100', comments: '211', relevance: 88, status: '수집완료', url: 'https://youtube.com/watch?v=scalp002', duration: '6:51' },
  { id: 'v3', title: '남자 머리 볼륨 쉽게 살리는 법', brand: '모렉신', niche: '남성 헤어', source: '그루밍노트', date: '2026-05-06', lang: 'KO', views: '37,700', comments: '96', relevance: 71, status: '후보', url: 'https://youtube.com/watch?v=hair003', duration: '5:42' },
  { id: 'v4', title: '출근 전 5분 홈카페 루틴', brand: '픽셀브루', niche: '직장인 루틴', source: '모닝로그', date: '2026-05-08', lang: 'KO', views: '129,000', comments: '788', relevance: 91, status: '후보', url: 'https://youtube.com/watch?v=routine004', duration: '4:18' },
  { id: 'v5', title: '홈트 초보가 자주 하는 실수', brand: '루미핏', niche: '홈트 초보', source: '핏데일리', date: '2026-05-05', lang: 'KO', views: '64,200', comments: '305', relevance: 79, status: '보류', url: 'https://youtube.com/watch?v=home005', duration: '9:15' },
  { id: 'v6', title: '두피 각질 관리 루틴', brand: '모렉신', niche: '두피 관리', source: '스킨앤헤어', date: '2026-05-07', lang: 'KO', views: '21,400', comments: '64', relevance: 85, status: '후보', url: 'https://youtube.com/watch?v=scalp006', duration: '7:02' },
  { id: 'v7', title: '올리브영 5월 신상 BEST 7', brand: '노마셀', niche: '신상 추천', source: '뷰티로그', date: '2026-05-08', lang: 'KO', views: '184,200', comments: '1,025', relevance: 96, status: '후보', url: 'https://youtube.com/watch?v=oy007', duration: '12:08' },
  { id: 'v8', title: '여성 탈모 초기 진단법', brand: '모렉신', niche: '여성 헤어 케어', source: '닥터두피', date: '2026-05-06', lang: 'KO', views: '45,800', comments: '178', relevance: 87, status: '수집완료', url: 'https://youtube.com/watch?v=female008', duration: '6:40' },
  { id: 'v9', title: '드립커피 입문자 가이드', brand: '픽셀브루', niche: '카페/홈카페', source: '커피하우스', date: '2026-05-05', lang: 'KO', views: '38,900', comments: '142', relevance: 73, status: '후보', url: 'https://youtube.com/watch?v=coffee009', duration: '11:24' },
  { id: 'v10', title: '저탄고지 1주일 식단 후기', brand: '루미핏', niche: '식단 관리', source: '핏데일리', date: '2026-05-04', lang: 'KO', views: '92,400', comments: '512', relevance: 84, status: '후보', url: 'https://youtube.com/watch?v=keto010', duration: '8:55' },
  { id: 'v11', title: '여드름 피부 진정 루틴 1주일', brand: '노마셀', niche: '스킨케어 루틴', source: '스킨로그', date: '2026-05-07', lang: 'KO', views: '67,300', comments: '298', relevance: 89, status: '수집완료', url: 'https://youtube.com/watch?v=skin011', duration: '10:12' },
  { id: 'v12', title: '비타민 D 부족 신호 5가지', brand: '헬릭스코어', niche: '면역 / 비타민', source: '의학채널', date: '2026-05-06', lang: 'KO', views: '156,000', comments: '634', relevance: 92, status: '후보', url: 'https://youtube.com/watch?v=vit012', duration: '7:38' },
  { id: 'v13', title: '불면증에 멜라토닌 — 의사 의견', brand: '헬릭스코어', niche: '수면 / 멜라토닌', source: '닥터수면', date: '2026-05-08', lang: 'KO', views: '74,500', comments: '321', relevance: 86, status: '후보', url: 'https://youtube.com/watch?v=sleep013', duration: '9:01' },
  { id: 'v14', title: '아연 영양제 효과 — 의사가 알려드립니다', brand: '헬릭스코어', niche: '면역 / 비타민', source: '의학채널', date: '2026-05-04', lang: 'KO', views: '48,200', comments: '189', relevance: 81, status: '수집완료', url: 'https://youtube.com/watch?v=zinc014', duration: '6:24' },
  { id: 'v15', title: '직장인 5분 명상 루틴', brand: '픽셀브루', niche: '직장인 루틴', source: '모닝로그', date: '2026-05-03', lang: 'KO', views: '23,500', comments: '88', relevance: 65, status: '보류', url: 'https://youtube.com/watch?v=routine015', duration: '5:32' },
  { id: 'v16', title: '단백질 보충제 추천 — 입문자', brand: '루미핏', niche: '식단 관리', source: '핏데일리', date: '2026-05-02', lang: 'KO', views: '54,700', comments: '241', relevance: 77, status: '후보', url: 'https://youtube.com/watch?v=protein016', duration: '8:42' },
  { id: 'v17', title: '올리브영 토너 비교 TOP 5', brand: '노마셀', niche: '신상 추천', source: '뷰티로그', date: '2026-05-01', lang: 'KO', views: '112,800', comments: '587', relevance: 90, status: '수집완료', url: 'https://youtube.com/watch?v=oy017', duration: '11:18' },
  { id: 'v18', title: '남자 헤어 스타일링 기본', brand: '모렉신', niche: '남성 헤어', source: '그루밍노트', date: '2026-04-30', lang: 'KO', views: '29,400', comments: '102', relevance: 68, status: '제외', url: 'https://youtube.com/watch?v=hair018', duration: '4:58' },
  { id: 'v19', title: 'M자탈모 진행 막는 5가지', brand: '모렉신', niche: '탈모 고민', source: '닥터두피', date: '2026-05-08', lang: 'KO', views: '198,500', comments: '892', relevance: 95, status: '후보', url: 'https://youtube.com/watch?v=hair019', duration: '9:45' },
  { id: 'v20', title: '홈트 30일 챌린지 결과', brand: '루미핏', niche: '홈트 초보', source: '핏데일리', date: '2026-05-07', lang: 'KO', views: '83,600', comments: '402', relevance: 82, status: '수집완료', url: 'https://youtube.com/watch?v=home020', duration: '13:24' },
]

// ============================================================
// PRESETS
// ============================================================

export const GLOBAL_PRESETS: GlobalPreset[] = [
  { id: 'g1', name: '공감형 메인 댓글', desc: '강한 공감과 자기 경험을 살짝', used: 1245, version: 'v2.3' },
  { id: 'g2', name: '질문형 진입', desc: '질문으로 대화 흐름을 여는 타입', used: 987, version: 'v1.8' },
  { id: 'g3', name: '정보형 메인 댓글', desc: '정보/팁을 자연스럽게 녹임', used: 756, version: 'v3.1' },
  { id: 'g4', name: '후기형 세트', desc: '경험과 변화 강조', used: 654, version: 'v2.0' },
  { id: 'g5', name: '경험 공유형', desc: '본인 경험·실패담 자연스럽게', used: 521, version: 'v1.4' },
  { id: 'g6', name: '취향 공감형', desc: '소소한 취향 일치 표현', used: 412, version: 'v1.2' },
  { id: 'g7', name: '루틴 공감형', desc: '루틴/습관 공감 + 추가 질문', used: 398, version: 'v1.6' },
  { id: 'g8', name: '초보 공감형', desc: '초보 입장 공감 + 격려', used: 287, version: 'v1.0' },
]

// ============================================================
// WORKERS
// ============================================================

export const WORKERS: WorkerInfo[] = [
  { id: 1, name: 'worker-01', status: 'online', currentTask: '저탄고지 1주일 식단', heartbeat: '3초 전', version: 'v0.9.4', os: 'win' },
  { id: 2, name: 'worker-02', status: 'online', currentTask: '올리브영 토너 비교', heartbeat: '4초 전', version: 'v0.9.4', os: 'win' },
  { id: 3, name: 'worker-03', status: 'online', currentTask: '남자 헤어 스타일링', heartbeat: '2초 전', version: 'v0.9.4', os: 'mac' },
  { id: 4, name: 'worker-04', status: 'online', currentTask: '두피 각질 관리', heartbeat: '5초 전', version: 'v0.9.4', os: 'win' },
  { id: 5, name: 'worker-05', status: 'online', currentTask: '여성 탈모 영양제', heartbeat: '6초 전', version: 'v0.9.4', os: 'mac' },
  { id: 6, name: 'worker-06', status: 'offline', heartbeat: '14분 전', version: 'v0.9.1', os: 'win' },
  { id: 7, name: 'worker-07', status: 'paused', currentTask: '대기 중', heartbeat: '32초 전', version: 'v0.9.3', os: 'win' },
  { id: 8, name: 'worker-08', status: 'online', currentTask: '비타민 D 자가진단', heartbeat: '8초 전', version: 'v0.9.4', os: 'mac' },
]

// ============================================================
// ACTIVITY FEED
// ============================================================

export const ACTIVITY: ActivityItem[] = [
  { id: 'a1', kind: 'draft', title: '댓글 초안 생성', body: '머리 숱이 줄어드는 이유 5가지', time: '방금 전' },
  { id: 'a2', kind: 'auto', title: '자동 작업 실행', body: '모렉신 — 탈모 고민', time: '1분 전' },
  { id: 'a3', kind: 'pending', title: '승인 대기 12건', body: '확인 후 승인해주세요', time: '2분 전' },
  { id: 'a4', kind: 'done', title: '작업 48건 예약 완료', body: '오늘 14:00 ~ 18:00', time: '5분 전' },
  { id: 'a5', kind: 'video', title: '영상 7개 신규 수집', body: '노마셀 · 올리브영 신상', time: '8분 전' },
  { id: 'a6', kind: 'done', title: '캠페인 완료', body: '두피 마사지 5분 루틴 — 18/18', time: '15분 전' },
  { id: 'a7', kind: 'fail', title: '게시 실패 1건', body: 'worker-06 / 아침 루틴 BEST 5', time: '24분 전' },
  { id: 'a8', kind: 'preset', title: '프리셋 v2.3 게시', body: '공감형 메인 댓글 업데이트', time: '32분 전' },
  { id: 'a9', kind: 'auto', title: '자동 작업 실행', body: '픽셀브루 — 직장인 루틴', time: '38분 전' },
  { id: 'a10', kind: 'draft', title: '댓글 초안 8건 생성', body: '헬릭스코어 — 면역/비타민', time: '45분 전' },
]

// ============================================================
// LOGS
// ============================================================

export const LOGS: LogEntry[] = [
  { time: '2026-05-09 14:02:11', event: 'draft.created', meta: ['브랜드: 모렉신', '니치: 탈모 고민', '워커: worker-03'] },
  { time: '2026-05-09 14:01:48', event: 'campaign.completed', meta: ['ID: q23', '슬롯 18/18', '소요 4분 12초'] },
  { time: '2026-05-09 13:57:33', event: 'video.imported', meta: ['URL 3개 추가됨', '브랜드: 루미핏'] },
  { time: '2026-05-09 13:55:01', event: 'auto_job.triggered', meta: ['aj1: 모렉신 · 탈모 고민', '예약 시간 도달'] },
  { time: '2026-05-09 13:50:12', event: 'queue.failed', meta: ['ID: q21', 'worker-06 disconnected', 're-queued'] },
  { time: '2026-05-09 13:41:08', event: 'preset.published', meta: ['니치: 두피 관리', '버전: v2.1'] },
  { time: '2026-05-09 13:38:45', event: 'worker.heartbeat', meta: ['worker-04 online', 'version v0.9.4'] },
  { time: '2026-05-09 13:30:22', event: 'campaign.scheduled', meta: ['브랜드: 노마셀', '니치: 신상 추천', '5건'] },
]

// ============================================================
// AGGREGATED STATS (dashboard)
// ============================================================

export const STATS = {
  today: { comments: 1284, likes: 8930, total_actions: 10214 },
  campaigns: { active: AUTO_JOBS.filter((a) => a.active).length, total: AUTO_JOBS.length },
  errors: { unresolved: QUEUE.filter((q) => q.status === 'failed').length },
  workers: { online: WORKERS.filter((w) => w.status === 'online').length, total: WORKERS.length },
  tasks: {
    today_completed: QUEUE.filter((q) => q.status === 'done').length * 12 + 188, // 시각화용 보강
    today_failed: QUEUE.filter((q) => q.status === 'failed').length,
    pending: QUEUE.filter((q) => q.status === 'pending').length,
    running: QUEUE.filter((q) => q.status === 'running').length,
    scheduled: QUEUE.filter((q) => q.status === 'scheduled').length,
    draft: QUEUE.filter((q) => q.status === 'draft').length,
  },
  accounts: { active: 18, idle: 4, blocked: 2 },
}

// ============================================================
// LABELS / CLASSES
// ============================================================

export const STATUS_LABEL: Record<QueueStatus, string> = {
  draft: '초안',
  pending: '승인 대기',
  scheduled: '예약',
  running: '실행 중',
  done: '완료',
  failed: '실패',
}

export const STATUS_PILL: Record<QueueStatus, string> = {
  draft: 'cx-pill-draft',
  pending: 'cx-pill-pending',
  scheduled: 'cx-pill-scheduled',
  running: 'cx-pill-running',
  done: 'cx-pill-done',
  failed: 'cx-pill-failed',
}
