// HYDRA 대시보드 SPA — v2 (UI 개선)
const API = '';
let currentPage = 'dashboard';

function navigate(page) {
    currentPage = page;
    document.querySelectorAll('.sidebar nav a').forEach(a => a.classList.toggle('active', a.dataset.page === page));
    renderPage();
}

async function api(path, opts = {}) {
    const resp = await fetch(API + path, {
        headers: {'Content-Type':'application/json'}, ...opts,
        body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    return resp.json();
}

const STATUS_KO = {
    active:'활성',warmup:'웜업',cooldown:'쿨다운',retired:'폐기',registered:'등록됨',
    profile_set:'프로필완료',in_progress:'진행중',completed:'완료',failed:'실패',
    planning:'계획중',cancelled:'취소',suspended:'정지',login_failed:'로그인실패',
    checkpoint:'보안검사',captcha_stuck:'캡차오류',ip_blocked:'IP차단',pending:'대기',
    generating:'생성중',ready:'준비됨',running:'실행중',done:'완료',
    visible:'보임',ghost:'고스트',suspicious:'의심',unchecked:'미확인',
    available:'이용가능',comments_disabled:'댓글비활성',
    urgent:'긴급',high:'높음',normal:'보통',low:'낮음',
    info:'정보',warning:'경고',error:'에러',critical:'심각',
    manual:'수동',auto_expanded:'자동확장',paused:'일시정지',excluded:'제외됨',
};
const ROLE_KO = {seed:'시드',asker:'질문자',witness:'증인',agree:'동조',curious:'궁금이',info:'정보통',fan:'팬',qa:'답변자'};
const SCENARIO_DESC = {
    A:'씨앗 심기 — 단독 댓글, 브랜드 언급 없음',B:'질문 유도 — 3턴 티키타카',
    C:'동조 여론 — 대댓글 5~8개',D:'비포애프터 — 경험담',E:'슥 지나가기 — 짧은 단독',
    F:'정보형 교육 — 성분 공유',G:'올라타기 — 남의 댓글에 답글',H:'반박→중재 — 부정 활용',
    I:'간접 경험 — 선물/추천',J:'숏폼 전용 — 극짧 댓글',
};

function badge(status) {
    const m = {active:'active',warmup:'warmup',cooldown:'cooldown',retired:'retired',
        registered:'pending',profile_set:'pending',in_progress:'progress',completed:'completed',
        failed:'failed',planning:'pending',cancelled:'retired',suspended:'failed',
        login_failed:'failed',checkpoint:'cooldown',captcha_stuck:'cooldown',ip_blocked:'cooldown',
        done:'completed',running:'progress',pending:'pending',ready:'pending',generating:'progress',
        urgent:'failed',high:'warmup',normal:'active',low:'pending',
        info:'active',warning:'warmup',error:'failed',critical:'failed',paused:'warmup',excluded:'retired'};
    return `<span class="badge badge-${m[status]||'pending'}">${STATUS_KO[status]||status}</span>`;
}
function toast(msg) { const el=document.createElement('div');el.className='toast';el.textContent=msg;document.body.appendChild(el);setTimeout(()=>el.remove(),3000); }
function hint(t) { return `<div style="font-size:11px;color:var(--text2);margin-top:2px;margin-bottom:8px">${t}</div>`; }

async function renderPage() {
    const el = document.getElementById('content');
    const pages = {dashboard:renderDashboard,accounts:renderAccounts,brands:renderBrands,
        campaigns:renderCampaigns,keywords:renderKeywords,videos:renderVideos,
        settings:renderSettings,logs:renderLogs,pools:renderPools};
    if (pages[currentPage]) pages[currentPage](el);
}

// ==================== 대시보드 ====================
async function renderDashboard(el) {
    const [stats, sys] = await Promise.all([api('/api/stats'), api('/system/api/status')]);
    const a=stats.accounts||{}, t=stats.today||{};
    const pauseBtn = sys.paused
        ? `<button class="btn btn-primary" onclick="sysResume()">시스템 재개</button>`
        : `<button class="btn btn-danger" onclick="sysPause()">전체 일시정지</button>`;
    el.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center">
            <h1 class="page-title">대시보드</h1>
            <div style="display:flex;gap:8px">${pauseBtn}
                <button class="btn btn-danger" style="background:#c0392b" onclick="sysEmergency()">긴급 정지</button></div>
        </div>
        ${sys.paused?'<div style="background:rgba(225,112,85,0.15);border:1px solid var(--red);border-radius:var(--radius);padding:12px;margin-bottom:16px;color:var(--red);font-weight:600">시스템이 일시정지 상태입니다.</div>':''}
        <div class="stats-grid">
            <div class="stat-card"><div class="label">활성 계정</div><div class="value green">${a.active||0}</div></div>
            <div class="stat-card"><div class="label">웜업 중</div><div class="value yellow">${a.warmup||0}</div></div>
            <div class="stat-card"><div class="label">쿨다운/폐기</div><div class="value red">${(a.cooldown||0)+(a.retired||0)}</div></div>
            <div class="stat-card"><div class="label">전체</div><div class="value">${Object.values(a).reduce((x,y)=>x+y,0)}</div></div>
        </div>
        <div class="stats-grid">
            <div class="stat-card"><div class="label">오늘 홍보 댓글</div><div class="value blue">${t.promo_comments||0}</div></div>
            <div class="stat-card"><div class="label">비홍보 활동</div><div class="value">${t.non_promo_actions||0}</div></div>
            <div class="stat-card"><div class="label">좋아요 부스팅</div><div class="value green">${t.like_boosts||0}</div></div>
            <div class="stat-card"><div class="label">오늘 에러</div><div class="value red">${stats.errors_today||0}</div></div>
        </div>
        <div class="stats-grid">
            <div class="stat-card"><div class="label">진행중 캠페인</div><div class="value blue">${stats.campaigns?.active||0}</div></div>
            <div class="stat-card"><div class="label">오늘 완료</div><div class="value green">${stats.campaigns?.completed_today||0}</div></div>
            <div class="stat-card"><div class="label">실행중 계정</div><div class="value yellow">${sys.running_accounts||0}</div></div>
        </div>`;
}
async function sysPause(){await api('/system/api/pause',{method:'POST'});toast('일시정지됨');renderDashboard(document.getElementById('content'));}
async function sysResume(){await api('/system/api/resume',{method:'POST'});toast('재개됨');renderDashboard(document.getElementById('content'));}
async function sysEmergency(){if(!confirm('긴급 정지하시겠습니까?\n모든 작업이 즉시 중단됩니다.'))return;await api('/system/api/emergency-stop',{method:'POST'});toast('긴급 정지 완료');renderDashboard(document.getElementById('content'));}

// ==================== 계정 관리 ====================
async function renderAccounts(el) {
    const data = await api('/accounts/api/list');
    el.innerHTML = `
        <h1 class="page-title">계정 관리</h1>
        <div class="filter-bar">
            <select onchange="filterAccounts(this.value)">
                <option value="">전체</option><option value="registered">등록됨</option>
                <option value="profile_set">프로필완료</option><option value="warmup">웜업</option>
                <option value="active">활성</option><option value="cooldown">쿨다운</option><option value="retired">폐기</option>
            </select>
            <button class="btn btn-primary" onclick="showImportModal()">CSV 가져오기</button>
            <button class="btn btn-outline" onclick="batchProfiles()">일괄 프로필 생성</button>
            <button class="btn btn-outline" onclick="batchPersonas()">일괄 페르소나 배정</button>
        </div>
        <div class="card"><table><thead><tr>
            <th>ID</th><th>Gmail</th><th>상태</th><th>웜업</th><th>고스트</th><th>AdsPower</th><th>페르소나</th><th>최근 활동</th><th></th>
        </tr></thead><tbody id="acc-tbody">${accRows(data.items||[])}</tbody></table></div>
        <div id="modal-container"></div>`;
}
function accRows(items){return items.map(a=>`<tr>
    <td>${a.id}</td><td>${a.gmail}</td><td>${badge(a.status)}</td>
    <td>${a.warmup_group||'-'}${a.warmup_end_date?'<br><span style="font-size:10px;color:var(--text2)">~'+new Date(a.warmup_end_date).toLocaleDateString('ko')+'</span>':''}</td>
    <td>${a.ghost_count}</td>
    <td>${a.adspower_profile_id?'<span style="color:var(--green)">연결됨</span>':'<span style="color:var(--text2)">없음</span>'}</td>
    <td>${a.has_persona?'<span style="color:var(--green)">있음</span>':'<span style="color:var(--text2)">없음</span>'}</td>
    <td>${a.last_active_at?new Date(a.last_active_at).toLocaleDateString('ko'):'-'}</td>
    <td><button class="btn btn-sm btn-outline" onclick="viewAccount(${a.id})">상세</button></td>
</tr>`).join('');}
async function filterAccounts(s){const d=await api('/accounts/api/list'+(s?'?status='+s:''));document.getElementById('acc-tbody').innerHTML=accRows(d.items||[]);}
async function batchProfiles(){const r=await api('/accounts/api/batch/create-profiles',{method:'POST'});toast(`성공 ${r.success}, 실패 ${r.failed}`);renderAccounts(document.getElementById('content'));}
async function batchPersonas(){const r=await api('/accounts/api/batch/assign-personas',{method:'POST'});toast(`${r.count}개 배정`);renderAccounts(document.getElementById('content'));}

async function viewAccount(id){
    const a=await api(`/accounts/api/${id}`);
    const p=a.persona?JSON.parse(a.persona):null;
    document.getElementById('modal-container').innerHTML=`
        <div class="modal-overlay show" onclick="if(event.target===this)this.remove()"><div class="modal">
            <h2 class="modal-title">계정 #${a.id}</h2>
            <div class="form-row">
                <div class="form-group"><label>Gmail</label><input value="${a.gmail}" readonly></div>
                <div class="form-group"><label>상태</label><div style="padding-top:8px">${badge(a.status)}</div></div>
            </div>
            <div class="form-row">
                <div class="form-group"><label>AdsPower</label><div style="padding-top:8px">${a.adspower_profile_id||'<span style="color:var(--text2)">미연결</span>'}</div></div>
                <div class="form-group"><label>쿠키</label><div style="padding-top:8px">${a.has_cookies?'<span style="color:var(--green)">저장됨</span>':'<span style="color:var(--text2)">없음</span>'}</div></div>
            </div>
            <div class="form-row">
                <div class="form-group"><label>웜업 그룹</label><input value="${a.warmup_group||'-'}" readonly></div>
                <div class="form-group"><label>고스트 횟수</label><input value="${a.ghost_count}" readonly></div>
            </div>
            ${p?`<div class="card" style="margin-top:12px"><div class="card-header">페르소나</div><div class="card-body">
                <div class="form-row-3">
                    <div><label style="font-size:11px;color:var(--text2)">나이</label><div>${p.age}세</div></div>
                    <div><label style="font-size:11px;color:var(--text2)">성별</label><div>${p.gender==='female'?'여성':'남성'}</div></div>
                    <div><label style="font-size:11px;color:var(--text2)">지역</label><div>${p.region}</div></div>
                </div>
                <div style="margin-top:8px"><label style="font-size:11px;color:var(--text2)">관심사</label><div>${(p.interests||[]).join(', ')}</div></div>
                <div style="margin-top:8px"><label style="font-size:11px;color:var(--text2)">말투</label><div>${p.speech_style}</div></div>
            </div></div>`:`<div style="margin-top:12px"><button class="btn btn-outline" onclick="doAssignPersona(${a.id})">페르소나 생성</button></div>`}
            ${!a.adspower_profile_id?`<div style="margin-top:8px"><button class="btn btn-outline" onclick="doCreateProfile(${a.id})">AdsPower 프로필 생성</button></div>`:''}
            <div class="form-group" style="margin-top:16px"><label>상태 변경</label>
                <select id="new-status">${['registered','profile_set','warmup','active','cooldown','retired'].map(s=>
                    `<option value="${s}" ${s===a.status?'selected':''}>${STATUS_KO[s]}</option>`).join('')}</select></div>
            <div class="modal-actions">
                <button class="btn btn-outline" onclick="this.closest('.modal-overlay').remove()">닫기</button>
                <button class="btn btn-primary" onclick="updateAccStatus(${a.id})">저장</button></div>
        </div></div>`;
}
async function updateAccStatus(id){await api(`/accounts/api/${id}/status?status=${document.getElementById('new-status').value}`,{method:'POST'});toast('변경됨');document.querySelector('.modal-overlay').remove();renderAccounts(document.getElementById('content'));}
async function doCreateProfile(id){const r=await api(`/accounts/api/${id}/create-profile`,{method:'POST'});toast(r.ok?'생성 완료':r.error);document.querySelector('.modal-overlay').remove();renderAccounts(document.getElementById('content'));}
async function doAssignPersona(id){toast('생성 중...');const r=await api(`/accounts/api/${id}/assign-persona`,{method:'POST'});toast(r.ok?'배정 완료':r.error);document.querySelector('.modal-overlay').remove();renderAccounts(document.getElementById('content'));}

function showImportModal(){
    document.getElementById('modal-container').innerHTML=`
        <div class="modal-overlay show" onclick="if(event.target===this)this.remove()"><div class="modal">
            <h2 class="modal-title">CSV 계정 가져오기</h2>
            <div class="card" style="margin-bottom:16px"><div class="card-header">CSV 양식</div><div class="card-body">
                <table style="font-size:12px"><tr><th>필드</th><th>필수</th><th>설명</th><th>예시</th></tr>
                <tr><td>gmail</td><td style="color:var(--red)">필수</td><td>Gmail 주소</td><td>user@gmail.com</td></tr>
                <tr><td>password</td><td style="color:var(--red)">필수</td><td>비밀번호</td><td>MyP@ss123</td></tr>
                <tr><td>recovery_email</td><td>선택</td><td>복구 이메일</td><td>backup@gmail.com</td></tr>
                <tr><td>phone_number</td><td>선택</td><td>전화번호</td><td>+821012345678</td></tr>
                <tr><td>totp_secret</td><td>선택</td><td>2FA 시크릿</td><td>JBSWY3DPEHPK3PXP</td></tr>
                </table></div></div>
            <div class="form-group"><label>CSV 파일 경로</label><input type="text" id="csv-path" placeholder="/Users/username/accounts.csv"></div>
            <div class="modal-actions">
                <button class="btn btn-outline" onclick="this.closest('.modal-overlay').remove()">취소</button>
                <button class="btn btn-primary" onclick="importCsv()">가져오기</button></div>
        </div></div>`;
}
async function importCsv(){const r=await api('/accounts/api/import',{method:'POST',body:{path:document.getElementById('csv-path').value}});toast(r.message);document.querySelector('.modal-overlay').remove();renderAccounts(document.getElementById('content'));}

// ==================== 브랜드 관리 ====================
async function renderBrands(el){
    const brands=await api('/brands/api/list');
    el.innerHTML=`<h1 class="page-title">브랜드 관리</h1>
        <div class="filter-bar"><button class="btn btn-primary" onclick="showBrandModal()">브랜드 추가</button></div>
        <div class="card"><table><thead><tr><th>ID</th><th>브랜드명</th><th>카테고리</th><th>상태</th><th></th></tr></thead>
        <tbody>${brands.map(b=>`<tr><td>${b.id}</td><td>${b.name}</td><td>${b.category||'-'}</td><td>${badge(b.status)}</td>
            <td><button class="btn btn-sm btn-outline" onclick="viewBrand(${b.id})">수정</button></td></tr>`).join('')}</tbody>
        </table></div><div id="modal-container"></div>`;
}
function showBrandModal(b={}){
    document.getElementById('modal-container').innerHTML=`
        <div class="modal-overlay show" onclick="if(event.target===this)this.remove()"><div class="modal">
            <h2 class="modal-title">${b.id?'브랜드 수정':'브랜드 추가'}</h2>
            <div class="form-group"><label>브랜드명</label><input id="b-name" value="${b.name||''}"></div>
            <div class="form-row">
                <div class="form-group"><label>카테고리</label><input id="b-cat" value="${b.category||''}"></div>
                <div class="form-group"><label>타겟 고객</label><input id="b-aud" value="${b.target_audience||''}"></div></div>
            <div class="form-group"><label>핵심 메시지</label><textarea id="b-msg">${b.core_message||''}</textarea></div>
            <div class="form-group"><label>브랜드 스토리</label><textarea id="b-story">${b.brand_story||''}</textarea></div>
            <div class="form-row">
                <div class="form-group"><label>허용 키워드 (쉼표)</label><input id="b-allowed" value="${(b.allowed_keywords||[]).join(', ')}"></div>
                <div class="form-group"><label>금지 키워드 (쉼표)</label><input id="b-banned" value="${(b.banned_keywords||[]).join(', ')}"></div></div>
            <div class="form-group"><label>셀링포인트 (쉼표)</label><input id="b-sell" value="${(b.selling_points||[]).join(', ')}"></div>
            <div class="form-group"><label>톤 가이드</label><input id="b-tone" value="${b.tone_guide||''}">${hint('예: 경험 공유, 과장 금지, 자연스러운 추천')}</div>
            <div class="form-row-3">
                <div class="form-group"><label>브랜드 직접 언급</label><select id="bmd"><option value="true" ${b.mention_rules?.brand_direct?'selected':''}>허용</option><option value="false">불가</option></select></div>
                <div class="form-group"><label>성분명만 언급</label><select id="bmi"><option value="true">허용</option><option value="false">불가</option></select></div>
                <div class="form-group"><label>간접 암시</label><select id="bmh"><option value="true">허용</option><option value="false">불가</option></select></div></div>
            <div class="modal-actions">
                <button class="btn btn-outline" onclick="this.closest('.modal-overlay').remove()">취소</button>
                <button class="btn btn-primary" onclick="saveBrand()">저장</button></div>
        </div></div>`;
}
async function saveBrand(){
    const sp=v=>v?v.split(',').map(s=>s.trim()).filter(Boolean):[];
    await api('/brands/api/create',{method:'POST',body:{name:document.getElementById('b-name').value,
        product_category:document.getElementById('b-cat').value,core_message:document.getElementById('b-msg').value,
        brand_story:document.getElementById('b-story').value,target_audience:document.getElementById('b-aud').value,
        allowed_keywords:sp(document.getElementById('b-allowed').value),banned_keywords:sp(document.getElementById('b-banned').value),
        selling_points:sp(document.getElementById('b-sell').value),tone_guide:document.getElementById('b-tone').value,
        mention_rules:{brand_direct:document.getElementById('bmd').value==='true',ingredient_only:document.getElementById('bmi').value==='true',indirect_hint:document.getElementById('bmh').value==='true'}}});
    toast('저장됨');document.querySelector('.modal-overlay').remove();renderBrands(document.getElementById('content'));
}
async function viewBrand(id){showBrandModal(await api(`/brands/api/${id}`));}

// ==================== 캠페인 ====================
async function renderCampaigns(el){
    const data=await api('/campaigns/api/list');
    el.innerHTML=`<h1 class="page-title">캠페인</h1>
        <div class="filter-bar">
            <select onchange="filterCamp(this.value)"><option value="">전체</option><option value="in_progress">진행중</option><option value="completed">완료</option><option value="failed">실패</option></select>
            <button class="btn btn-primary" onclick="showCreateCampaign()">캠페인 생성</button></div>
        <div class="card"><table><thead><tr><th>ID</th><th>영상</th><th>브랜드</th><th>시나리오</th><th>진행도</th><th>고스트</th><th>상태</th><th>생성일</th><th></th></tr></thead>
        <tbody>${(data.items||[]).map(c=>`<tr>
            <td>${c.id}</td>
            <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${c.video_title||'-'}</td>
            <td>${c.brand_name||'-'}</td><td>${c.scenario}</td>
            <td><div class="progress" style="width:80px"><div class="progress-bar" style="width:${c.steps_total?(c.steps_done/c.steps_total*100):0}%"></div></div>
                <span style="font-size:11px;color:var(--text2)">${c.steps_done}/${c.steps_total}</span></td>
            <td>${STATUS_KO[c.ghost_status]||'-'}</td><td>${badge(c.status)}</td>
            <td>${new Date(c.created_at).toLocaleDateString('ko')}</td>
            <td><button class="btn btn-sm btn-outline" onclick="viewCampaign(${c.id})">상세</button></td>
        </tr>`).join('')}</tbody></table></div><div id="modal-container"></div>`;
}
async function filterCamp(s){renderCampaigns(document.getElementById('content'));}

async function showCreateCampaign(){
    const brands=await api('/brands/api/list');
    document.getElementById('modal-container').innerHTML=`
        <div class="modal-overlay show" onclick="if(event.target===this)this.remove()"><div class="modal" style="max-width:650px">
            <h2 class="modal-title">캠페인 생성</h2>
            <div class="form-group"><label>브랜드</label>
                <select id="c-brand">${brands.map(b=>`<option value="${b.id}">${b.name}</option>`).join('')}</select></div>
            <div class="form-group"><label>영상 ID</label><input id="c-video" placeholder="YouTube 영상 ID (v= 뒤의 값)">
                ${hint('수집된 영상 목록에서 "캠페인 생성" 버튼으로도 가능합니다')}</div>
            <div class="form-group"><label>시나리오</label>
                <select id="c-scenario"><option value="">자동 선택 (영상 상태에 따라)</option>
                ${Object.entries(SCENARIO_DESC).map(([k,v])=>`<option value="${k}">${k}: ${v}</option>`).join('')}</select></div>
            <div class="form-group"><label>좋아요 프리셋</label>
                <select id="c-preset"><option value="conservative">보수적 — 30개, 24시간</option>
                <option value="normal" selected>보통 — 100개, 24시간</option>
                <option value="aggressive">공격적 — 100개, 6시간</option></select></div>
            <div class="modal-actions">
                <button class="btn btn-outline" onclick="this.closest('.modal-overlay').remove()">취소</button>
                <button class="btn btn-primary" onclick="createCampaign()">생성</button></div>
        </div></div>`;
}
async function createCampaign(){
    const r=await api('/campaigns/api/create',{method:'POST',body:{video_id:document.getElementById('c-video').value,
        brand_id:parseInt(document.getElementById('c-brand').value),
        scenario:document.getElementById('c-scenario').value||null,
        like_preset:document.getElementById('c-preset').value}});
    if(r.error){toast('오류: '+r.error);return;}
    toast(`캠페인 #${r.id} 생성됨 (시나리오 ${r.scenario}, ${r.steps}스텝)`);
    document.querySelector('.modal-overlay').remove();renderCampaigns(document.getElementById('content'));
}

async function viewCampaign(id){
    const c=await api(`/campaigns/api/${id}`);
    document.getElementById('modal-container').innerHTML=`
        <div class="modal-overlay show" onclick="if(event.target===this)this.remove()"><div class="modal" style="max-width:800px">
            <h2 class="modal-title">캠페인 #${c.id} — 시나리오 ${c.scenario} (${SCENARIO_DESC[c.scenario]?.split('—')[0]||''})</h2>
            <div class="form-row-3">
                <div><label style="font-size:11px;color:var(--text2)">상태</label><div>${badge(c.status)}</div></div>
                <div><label style="font-size:11px;color:var(--text2)">고스트</label><div>${STATUS_KO[c.ghost_check_status]||'미확인'}</div></div>
                <div><label style="font-size:11px;color:var(--text2)">영상</label><div><a href="https://youtube.com/watch?v=${c.video_id}" target="_blank" style="color:var(--blue)">YouTube에서 보기</a></div></div>
            </div>
            <h3 style="margin:16px 0 8px;font-size:14px">타임라인</h3>
            <div style="border-left:2px solid var(--border);margin-left:12px;padding-left:16px">
                ${(c.steps||[]).map(s=>`
                    <div style="margin-bottom:14px;position:relative">
                        <div style="position:absolute;left:-23px;top:2px;width:10px;height:10px;border-radius:50%;background:${
                            s.status==='done'?'var(--green)':s.status==='running'?'var(--blue)':s.status==='failed'?'var(--red)':'var(--border)'}"></div>
                        <div style="display:flex;justify-content:space-between;align-items:center">
                            <div>
                                <span style="font-weight:600;color:var(--primary)">[${ROLE_KO[s.role]||s.role}]</span>
                                <span style="color:var(--text2);font-size:12px;margin-left:8px">계정 #${s.account_id}</span>
                                <span style="color:var(--text2);font-size:12px;margin-left:8px">${s.type==='comment'?'댓글':'답글'}</span>
                            </div>
                            <div style="display:flex;align-items:center;gap:8px">
                                ${badge(s.status)}
                                <span style="font-size:11px;color:var(--text2)">${s.scheduled_at?new Date(s.scheduled_at).toLocaleString('ko',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):''}</span>
                            </div>
                        </div>
                        ${s.content?`<div style="margin-top:4px;padding:8px 12px;background:var(--surface2);border-radius:6px;font-size:13px">"${s.content}"</div>`:''}
                        ${s.error?`<div style="margin-top:4px;font-size:11px;color:var(--red)">${s.error}</div>`:''}
                    </div>`).join('')}
            </div>
            <div class="modal-actions">
                ${c.status==='in_progress'?`<button class="btn btn-danger" onclick="cancelCamp(${c.id})">캠페인 취소</button>`:''}
                <button class="btn btn-outline" onclick="this.closest('.modal-overlay').remove()">닫기</button></div>
        </div></div>`;
}
async function cancelCamp(id){if(!confirm('취소하시겠습니까?'))return;await api(`/campaigns/api/${id}/cancel`,{method:'POST'});toast('취소됨');document.querySelector('.modal-overlay').remove();renderCampaigns(document.getElementById('content'));}

// ==================== 키워드 ====================
async function renderKeywords(el){
    const kws=await api('/keywords/api/list');
    el.innerHTML=`<h1 class="page-title">키워드</h1>
        <div class="filter-bar">
            <select onchange="filterKw(this.value)"><option value="">전체</option><option value="active">활성</option><option value="paused">정지</option><option value="excluded">제외</option></select>
            <button class="btn btn-primary" onclick="showKwModal()">키워드 추가</button></div>
        <div class="card"><table><thead><tr><th>ID</th><th>키워드</th><th>출처</th><th>우선순위</th><th>수집 영상</th><th>작성 댓글</th><th>상태</th><th></th></tr></thead>
        <tbody>${kws.map(k=>`<tr>
            <td>${k.id}</td><td>${k.text}</td><td>${STATUS_KO[k.source]||k.source}</td>
            <td>${k.priority}</td><td>${k.videos_found}</td><td>${k.comments_posted}</td><td>${badge(k.status)}</td>
            <td style="white-space:nowrap">
                <button class="btn btn-sm btn-outline" onclick="expandKw(${k.id})">자동 확장</button>
                ${k.status==='active'?`<button class="btn btn-sm btn-outline" onclick="pauseKw(${k.id})">정지</button>`:''}
                ${k.status==='paused'?`<button class="btn btn-sm btn-outline" onclick="activateKw(${k.id})">활성화</button>`:''}
                ${k.status!=='excluded'?`<button class="btn btn-sm btn-danger" onclick="excludeKw(${k.id})">제외</button>`:''}
            </td></tr>`).join('')}</tbody></table></div><div id="modal-container"></div>`;
}
async function filterKw(s){renderKeywords(document.getElementById('content'));}
async function expandKw(id){toast('확장 중...');const r=await api(`/keywords/api/${id}/expand`,{method:'POST'});toast(r.ok?`${r.count}개 생성: ${r.keywords.join(', ')}`:'오류: '+r.error);renderKeywords(document.getElementById('content'));}
async function pauseKw(id){await api(`/keywords/api/${id}/pause`,{method:'POST'});renderKeywords(document.getElementById('content'));}
async function activateKw(id){await api(`/keywords/api/${id}/activate`,{method:'POST'});renderKeywords(document.getElementById('content'));}
async function excludeKw(id){await api(`/keywords/api/${id}/exclude`,{method:'POST'});renderKeywords(document.getElementById('content'));}
function showKwModal(){
    document.getElementById('modal-container').innerHTML=`
        <div class="modal-overlay show" onclick="if(event.target===this)this.remove()"><div class="modal">
            <h2 class="modal-title">키워드 추가</h2>
            <div class="form-group"><label>키워드</label><input id="kw-text" placeholder="예: 탈모 영양제"></div>
            <div class="form-row">
                <div class="form-group"><label>브랜드 ID</label><input type="number" id="kw-brand" value="1"></div>
                <div class="form-group"><label>우선순위 (1~10)</label><input type="number" id="kw-pri" value="5" min="1" max="10">
                    ${hint('8 이상 = 핵심 (4시간마다 수집). 7 이하 = 일반 (1일 1회)')}</div></div>
            <div class="modal-actions">
                <button class="btn btn-outline" onclick="this.closest('.modal-overlay').remove()">취소</button>
                <button class="btn btn-primary" onclick="saveKw()">저장</button></div>
        </div></div>`;
}
async function saveKw(){await api('/keywords/api/create',{method:'POST',body:{text:document.getElementById('kw-text').value,brand_id:parseInt(document.getElementById('kw-brand').value),priority:parseInt(document.getElementById('kw-pri').value)}});toast('추가됨');document.querySelector('.modal-overlay').remove();renderKeywords(document.getElementById('content'));}

// ==================== 영상 ====================
async function renderVideos(el){
    const data=await api('/videos/api/list');
    el.innerHTML=`<h1 class="page-title">수집된 영상</h1>
        <div class="filter-bar"><select onchange="filterVid(this.value)"><option value="">전체</option><option value="urgent">긴급</option><option value="normal">보통</option></select></div>
        <div class="card"><table><thead><tr><th>제목</th><th>채널</th><th>조회수</th><th>댓글수</th><th>숏폼</th><th>우선순위</th><th>수집일</th><th></th></tr></thead>
        <tbody>${(data.items||[]).map(v=>`<tr>
            <td style="max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><a href="https://youtube.com/watch?v=${v.id}" target="_blank" style="color:var(--blue)">${v.title}</a></td>
            <td>${v.channel||'-'}</td><td>${(v.views||0).toLocaleString()}</td><td>${v.comments||'-'}</td>
            <td>${v.is_short?'Y':''}</td><td>${badge(v.priority)}</td><td>${new Date(v.collected_at).toLocaleDateString('ko')}</td>
            <td><button class="btn btn-sm btn-primary" onclick="quickCamp('${v.id}')">캠페인 생성</button></td>
        </tr>`).join('')}</tbody></table></div><div id="modal-container"></div>`;
}
async function filterVid(s){renderVideos(document.getElementById('content'));}
async function quickCamp(vid){
    const brands=await api('/brands/api/list');
    if(!brands.length){toast('먼저 브랜드를 등록하세요');return;}
    document.getElementById('modal-container').innerHTML=`
        <div class="modal-overlay show" onclick="if(event.target===this)this.remove()"><div class="modal">
            <h2 class="modal-title">빠른 캠페인 생성</h2>
            <div class="form-group"><label>영상 ID</label><input value="${vid}" readonly></div>
            <div class="form-group"><label>브랜드</label><select id="qc-brand">${brands.map(b=>`<option value="${b.id}">${b.name}</option>`).join('')}</select></div>
            <div class="form-group"><label>시나리오</label><select id="qc-sc"><option value="">자동</option>${Object.entries(SCENARIO_DESC).map(([k,v])=>`<option value="${k}">${k}: ${v.split('—')[0]}</option>`).join('')}</select></div>
            <div class="modal-actions">
                <button class="btn btn-outline" onclick="this.closest('.modal-overlay').remove()">취소</button>
                <button class="btn btn-primary" onclick="doQuickCamp('${vid}')">생성</button></div>
        </div></div>`;
}
async function doQuickCamp(vid){const r=await api('/campaigns/api/create',{method:'POST',body:{video_id:vid,brand_id:parseInt(document.getElementById('qc-brand').value),scenario:document.getElementById('qc-sc').value||null}});if(r.error){toast('오류: '+r.error);return;}toast(`캠페인 #${r.id} 생성됨`);document.querySelector('.modal-overlay').remove();}

// ==================== 설정 ====================
async function renderSettings(el){
    const c=await api('/settings/api/all');
    el.innerHTML=`<h1 class="page-title">설정</h1>
        <div class="tabs">
            <div class="tab active" onclick="setTab('behavior')">행동 엔진</div>
            <div class="tab" onclick="setTab('likes')">좋아요 부스팅</div>
            <div class="tab" onclick="setTab('ai')">AI (Claude)</div>
            <div class="tab" onclick="setTab('api')">API 키</div>
            <div class="tab" onclick="setTab('cooldown')">쿨다운</div>
            <div class="tab" onclick="setTab('backup')">백업</div></div>
        <div id="settings-content">${settingsBehavior(c)}</div>`;
}
function setTab(tab){
    document.querySelectorAll('.tabs .tab').forEach(t=>{
        const m={behavior:'행동',likes:'좋아요',ai:'AI',api:'API',cooldown:'쿨다운',backup:'백업'};
        t.classList.toggle('active',t.textContent.includes(m[tab]||tab));});
    api('/settings/api/all').then(c=>{
        document.getElementById('settings-content').innerHTML=
            ({behavior:settingsBehavior,likes:settingsLikes,ai:settingsAI,api:settingsAPI,cooldown:settingsCooldown,backup:settingsBackup})[tab](c);});
}

function settingsBehavior(c){return `<div class="card"><div class="card-body">
    <p style="color:var(--text2);font-size:13px;margin-bottom:16px">각 계정이 "진짜 사람"처럼 행동하는 방식을 설정합니다. 모든 값은 확률 기반이며 계정마다 매일 다르게 적용됩니다.</p>
    <h3 style="font-size:14px;margin-bottom:4px">주간 목표</h3>${hint('계정 1개가 일주일간 수행할 작업 수. 남은 일수에 따라 하루 목표가 자동 분배됩니다.')}
    <div class="form-row">
        <div class="form-group"><label>주간 홍보 댓글</label><input type="number" data-key="behavior.weekly_promo_comments" value="${c['behavior.weekly_promo_comments']||70}">${hint('기본 70 = 하루 약 10개')}</div>
        <div class="form-group"><label>주간 비홍보 활동</label><input type="number" data-key="behavior.weekly_non_promo_actions" value="${c['behavior.weekly_non_promo_actions']||140}">${hint('시청, 좋아요, 검색 등')}</div></div>
    <div class="form-row-3">
        <div class="form-group"><label>일일 최대 홍보</label><input type="number" data-key="behavior.daily_max_promo" value="${c['behavior.daily_max_promo']||25}">${hint('밀려도 이 이상은 안 함')}</div>
        <div class="form-group"><label>쉬는 날 확률</label><input type="number" step="0.01" data-key="behavior.day_off_probability" value="${c['behavior.day_off_probability']||0.10}">${hint('0.10=10%. 쉬는날엔 시청만')}</div>
        <div class="form-group"><label>주말 부스트</label><input type="number" step="0.1" data-key="behavior.weekend_boost" value="${c['behavior.weekend_boost']||1.2}">${hint('1.2=주말 20% 더 활동')}</div></div>
    <h3 style="font-size:14px;margin:16px 0 4px">하루 접속 횟수</h3>${hint('YouTube를 하루에 몇 번 여는지. 합이 100%가 되어야 합니다.')}
    <div class="form-row">
        <div class="form-group"><label>1회 (바쁜 날)</label><input type="number" data-key="behavior.session_1_weight" value="${c['behavior.session_1_weight']||20}"> %</div>
        <div class="form-group"><label>2회 (평범)</label><input type="number" data-key="behavior.session_2_weight" value="${c['behavior.session_2_weight']||35}"> %</div></div>
    <div class="form-row">
        <div class="form-group"><label>3회 (활발)</label><input type="number" data-key="behavior.session_3_weight" value="${c['behavior.session_3_weight']||30}"> %</div>
        <div class="form-group"><label>4회 (여유)</label><input type="number" data-key="behavior.session_4_weight" value="${c['behavior.session_4_weight']||15}"> %</div></div>
    <h3 style="font-size:14px;margin:16px 0 4px">행동 선택 비율</h3>${hint('YouTube 접속 중 어떤 행동을 할지. 합이 100%가 되어야 합니다.')}
    <div class="form-row-3">
        <div class="form-group"><label>홈피드 스크롤</label><input type="number" data-key="behavior.action_home_scroll" value="${c['behavior.action_home_scroll']||25}"> %${hint('홈 스크롤 → 영상 클릭')}</div>
        <div class="form-group"><label>키워드 검색</label><input type="number" data-key="behavior.action_keyword_search" value="${c['behavior.action_keyword_search']||20}"> %${hint('검색창에 타이핑')}</div>
        <div class="form-group"><label>추천 영상</label><input type="number" data-key="behavior.action_recommended" value="${c['behavior.action_recommended']||25}"> %${hint('사이드바 추천에서 클릭')}</div></div>
    <div class="form-row">
        <div class="form-group"><label>숏폼 탐색</label><input type="number" data-key="behavior.action_shorts" value="${c['behavior.action_shorts']||15}"> %${hint('Shorts 탭 스와이프')}</div>
        <div class="form-group"><label>세션 종료</label><input type="number" data-key="behavior.action_end_session" value="${c['behavior.action_end_session']||15}"> %${hint('"질림" — YouTube 닫기')}</div></div>
    <h3 style="font-size:14px;margin:16px 0 4px">시청 후 행동 확률</h3>${hint('타겟 영상 시청 후 댓글을 남길 확률')}
    <div class="form-row-3">
        <div class="form-group"><label>홍보 댓글</label><input type="number" data-key="behavior.comment_promo_prob" value="${c['behavior.comment_promo_prob']||60}"> %</div>
        <div class="form-group"><label>비홍보 댓글</label><input type="number" data-key="behavior.comment_non_promo_prob" value="${c['behavior.comment_non_promo_prob']||5}"> %</div>
        <div class="form-group"><label>남 댓글 좋아요</label><input type="number" data-key="behavior.like_others_prob" value="${c['behavior.like_others_prob']||30}"> %</div></div>
    <h3 style="font-size:14px;margin:16px 0 4px">입력 방식</h3>
    <div class="form-row-3">
        <div class="form-group"><label>붙여넣기 비율</label><input type="number" data-key="behavior.clipboard_paste_ratio" value="${c['behavior.clipboard_paste_ratio']||80}"> %${hint('나머지는 글자별 타이핑')}</div>
        <div class="form-group"><label>타이핑 최소</label><input type="number" data-key="behavior.typing_delay_min_ms" value="${c['behavior.typing_delay_min_ms']||50}"> ms</div>
        <div class="form-group"><label>타이핑 최대</label><input type="number" data-key="behavior.typing_delay_max_ms" value="${c['behavior.typing_delay_max_ms']||200}"> ms</div></div>
    <button class="btn btn-primary" style="margin-top:16px" onclick="saveSet()">설정 저장</button>
</div></div>`;}

function settingsLikes(c){
    function wRows(key,def){
        return(c[key]||def).split(',').map(w=>w.trim().split(':')).map((w,i)=>`<tr>
            <td style="text-align:center">${i+1}</td>
            <td><input type="number" class="wave-min" value="${w[0]}" style="width:80px"> 분 후</td>
            <td><input type="number" class="wave-cnt" value="${w[1]}" style="width:80px"> 개</td>
            <td><button class="btn btn-sm btn-danger" onclick="this.closest('tr').remove()">삭제</button></td>
        </tr>`).join('');
    }
    return `<div class="card"><div class="card-body">
        <h3 style="font-size:14px;margin-bottom:4px">기본 프리셋</h3>${hint('캠페인 생성 시 기본 좋아요 배치 방식')}
        <div class="form-group"><select data-key="like_boost.default_preset">
            ${[['conservative','보수적 — 30개, 24시간'],['normal','보통 — 100개, 24시간'],['aggressive','공격적 — 100개, 6시간']].map(([v,l])=>
                `<option value="${v}" ${(c['like_boost.default_preset']||'normal')===v?'selected':''}>${l}</option>`).join('')}</select></div>
        <h3 style="font-size:14px;margin:16px 0 4px">보수적</h3>${hint('행 추가/삭제 가능. 대기시간(분) + 좋아요 수')}
        <table id="w-con"><thead><tr><th>웨이브</th><th>대기 시간</th><th>좋아요 수</th><th></th></tr></thead>
            <tbody>${wRows('like_boost.conservative_waves','30:3,180:5,720:10,1440:12')}</tbody></table>
        <button class="btn btn-sm btn-outline" onclick="addWave('w-con')">+ 웨이브 추가</button>
        <h3 style="font-size:14px;margin:16px 0 4px">보통</h3>
        <table id="w-nor"><thead><tr><th>웨이브</th><th>대기 시간</th><th>좋아요 수</th><th></th></tr></thead>
            <tbody>${wRows('like_boost.normal_waves','30:5,120:10,360:20,720:30,1440:35')}</tbody></table>
        <button class="btn btn-sm btn-outline" onclick="addWave('w-nor')">+ 웨이브 추가</button>
        <h3 style="font-size:14px;margin:16px 0 4px">공격적</h3>
        <table id="w-agg"><thead><tr><th>웨이브</th><th>대기 시간</th><th>좋아요 수</th><th></th></tr></thead>
            <tbody>${wRows('like_boost.aggressive_waves','15:10,60:20,180:30,360:40')}</tbody></table>
        <button class="btn btn-sm btn-outline" onclick="addWave('w-agg')">+ 웨이브 추가</button>
        <h3 style="font-size:14px;margin:16px 0 4px">주변 위장 좋아요</h3>${hint('우리 댓글만 좋아요하면 티남. 주변 댓글에도 랜덤 좋아요')}
        <div class="form-row">
            <div class="form-group"><label>최소</label><input type="number" data-key="like_boost.surrounding_min" value="${c['like_boost.surrounding_min']||2}"></div>
            <div class="form-group"><label>최대</label><input type="number" data-key="like_boost.surrounding_max" value="${c['like_boost.surrounding_max']||5}"></div></div>
        <button class="btn btn-primary" style="margin-top:16px" onclick="saveLikes()">설정 저장</button>
    </div></div>`;
}
function addWave(tid){const tb=document.getElementById(tid).querySelector('tbody');const n=tb.rows.length+1;
    tb.insertAdjacentHTML('beforeend',`<tr><td style="text-align:center">${n}</td><td><input type="number" class="wave-min" value="60" style="width:80px"> 분 후</td><td><input type="number" class="wave-cnt" value="10" style="width:80px"> 개</td><td><button class="btn btn-sm btn-danger" onclick="this.closest('tr').remove()">삭제</button></td></tr>`);}
function collectW(tid){return Array.from(document.getElementById(tid).querySelectorAll('tbody tr')).map(r=>r.querySelector('.wave-min').value+':'+r.querySelector('.wave-cnt').value).join(', ');}
async function saveLikes(){const s={};document.querySelectorAll('[data-key]').forEach(el=>{s[el.dataset.key]=el.value;});
    s['like_boost.conservative_waves']=collectW('w-con');s['like_boost.normal_waves']=collectW('w-nor');s['like_boost.aggressive_waves']=collectW('w-agg');
    await api('/settings/api/save',{method:'POST',body:s});toast('저장됨');}

function settingsAI(c){return `<div class="card"><div class="card-body">
    <div class="form-group"><label>Claude 모델</label><select data-key="ai.model">
        <option value="claude-sonnet-4-20250514" ${(c['ai.model']||'')?.includes('sonnet')?'selected':''}>Sonnet — 빠르고 저렴</option>
        <option value="claude-opus-4-20250514" ${(c['ai.model']||'')?.includes('opus')?'selected':''}>Opus — 고성능</option>
    </select>${hint('대부분 Sonnet으로 충분합니다. Opus는 비용 10배+')}</div>
    <div class="form-row">
        <div class="form-group"><label>댓글 최대 토큰</label><input type="number" data-key="ai.max_tokens_comment" value="${c['ai.max_tokens_comment']||300}">${hint('300 ≈ 한글 150자')}</div>
        <div class="form-group"><label>페르소나 최대 토큰</label><input type="number" data-key="ai.max_tokens_persona" value="${c['ai.max_tokens_persona']||500}"></div></div>
    <div class="form-group"><label>추가 지시사항</label><textarea data-key="ai.custom_system_prompt" rows="4">${c['ai.custom_system_prompt']||''}</textarea>
        ${hint('⚠️ 페르소나 프롬프트는 유지됩니다. 여기 내용은 뒤에 추가로 붙습니다. 톤/말투를 덮어쓰지 않도록 주의.')}</div>
    <div class="form-group"><label>추가 금지 패턴 (줄당 1개)</label><textarea data-key="ai.extra_banned_patterns" rows="3">${c['ai.extra_banned_patterns']||''}</textarea>
        ${hint('예: 구매.*링크')}</div>
    <button class="btn btn-primary" style="margin-top:16px" onclick="saveSet()">설정 저장</button>
</div></div>`;}

function settingsAPI(c){return `<div class="card"><div class="card-body">
    <div class="form-group"><label>Claude API 키</label><input type="password" data-key="api.claude_key" value="${c['api.claude_key']||''}"></div>
    <div class="form-row">
        <div class="form-group"><label>YouTube API 키 1</label><input type="password" data-key="api.youtube_key_1" value="${c['api.youtube_key_1']||''}">${hint('쿼터 초과 시 키 2로 자동 전환')}</div>
        <div class="form-group"><label>YouTube API 키 2</label><input type="password" data-key="api.youtube_key_2" value="${c['api.youtube_key_2']||''}"></div></div>
    <div class="form-group"><label>2Captcha API 키</label><input type="password" data-key="api.twocaptcha_key" value="${c['api.twocaptcha_key']||''}">${hint('캡차 자동 해결용')}</div>
    <div class="form-row">
        <div class="form-group"><label>텔레그램 봇 토큰</label><input type="password" data-key="api.telegram_token" value="${c['api.telegram_token']||''}"></div>
        <div class="form-group"><label>텔레그램 채팅 ID</label><input data-key="api.telegram_chat_id" value="${c['api.telegram_chat_id']||''}"></div></div>
    <div class="form-group"><label>AdsPower API URL</label><input data-key="api.adspower_url" value="${c['api.adspower_url']||'http://local.adspower.net:50325'}"></div>
    <button class="btn btn-primary" style="margin-top:16px" onclick="saveSet()">설정 저장</button>
</div></div>`;}

function settingsCooldown(c){return `<div class="card"><div class="card-body">
    <p style="color:var(--text2);font-size:13px;margin-bottom:16px">계정/IP 재사용 간격. 너무 짧으면 탐지 위험 증가.</p>
    <div class="form-row">
        <div class="form-group"><label>같은 작업 같은 영상</label><input type="number" data-key="cooldown.same_task_video_days" value="${c['cooldown.same_task_video_days']||7}"> 일${hint('같은 계정이 같은 영상에 같은 작업 재시도 최소 간격')}</div>
        <div class="form-group"><label>세션 간 간격</label><input type="number" data-key="cooldown.session_gap_hours" value="${c['cooldown.session_gap_hours']||2}"> 시간${hint('같은 계정 연속 세션 최소 대기')}</div></div>
    <div class="form-row">
        <div class="form-group"><label>고스트 쿨다운</label><input type="number" data-key="cooldown.ghost_cooldown_days" value="${c['cooldown.ghost_cooldown_days']||7}"> 일${hint('고스트 1회 시 홍보 중단 기간')}</div>
        <div class="form-group"><label>같은 IP 재사용</label><input type="number" data-key="cooldown.same_ip_minutes" value="${c['cooldown.same_ip_minutes']||30}"> 분${hint('다른 계정이 같은 IP 사용 후 대기')}</div></div>
    <div class="form-group"><label>IP당 동시 계정</label><input type="number" data-key="cooldown.max_per_ip" value="${c['cooldown.max_per_ip']||1}">${hint('절대 규칙: 1. 같은 IP에 2계정 금지')}</div>
    <button class="btn btn-primary" style="margin-top:16px" onclick="saveSet()">설정 저장</button>
</div></div>`;}

function settingsBackup(c){return `<div class="card"><div class="card-body">
    <div class="form-row">
        <div class="form-group"><label>자동 백업 주기</label><input type="number" data-key="backup.interval_hours" value="${c['backup.interval_hours']||4}"> 시간</div>
        <div class="form-group"><label>보관 기간</label><input type="number" data-key="backup.retention_days" value="${c['backup.retention_days']||7}"> 일</div></div>
    <div style="margin-top:8px"><button class="btn btn-primary" onclick="doBackup()">지금 백업</button>
    <button class="btn btn-primary" style="margin-left:8px" onclick="saveSet()">설정 저장</button></div>
</div></div>`;}

async function saveSet(){const s={};document.querySelectorAll('[data-key]').forEach(el=>{s[el.dataset.key]=el.value;});await api('/settings/api/save',{method:'POST',body:s});toast('저장됨');}
async function doBackup(){await api('/settings/api/backup',{method:'POST'});toast('백업 완료');}

// ==================== 프로필 풀 ====================
async function renderPools(el){
    const pools=await api('/pools/api/list');
    const types=[['avatar','아바타'],['banner','배너'],['name','이름'],['description','설명'],['contact','연락처'],['hashtag','해시태그']];
    el.innerHTML=`<h1 class="page-title">프로필 풀</h1>
        ${hint('채널 프로필 랜덤화 소스. 유형별로 여러 항목 등록 → 자동 랜덤 선택')}
        <div class="tabs">${types.map(([v,l],i)=>`<div class="tab ${i===0?'active':''}" onclick="filterPool('${v}',this)">${l}</div>`).join('')}</div>
        <div class="filter-bar"><button class="btn btn-primary" onclick="showPoolModal()">항목 추가</button></div>
        <div class="card"><table><thead><tr><th>ID</th><th>유형</th><th>내용</th><th>사용</th><th>상태</th><th></th></tr></thead>
        <tbody id="pool-tbody">${poolRows(pools)}</tbody></table></div><div id="modal-container"></div>`;
}
function poolRows(pools){return(pools||[]).map(p=>`<tr><td>${p.id}</td><td>${p.pool_type}</td>
    <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${p.content}</td>
    <td>${p.used_count}</td>
    <td>${p.disabled?'<span class="badge badge-retired">비활성</span>':'<span class="badge badge-active">활성</span>'}</td>
    <td><button class="btn btn-sm btn-danger" onclick="togglePool(${p.id})">전환</button></td></tr>`).join('');}
function showPoolModal(){
    const types=[['avatar','아바타 — 이미지 경로'],['banner','배너 — 이미지 경로'],['name','이름 — 채널명'],['description','설명 — 소개글'],['contact','연락처'],['hashtag','해시태그 — JSON']];
    document.getElementById('modal-container').innerHTML=`
        <div class="modal-overlay show" onclick="if(event.target===this)this.remove()"><div class="modal">
            <h2 class="modal-title">풀 항목 추가</h2>
            <div class="form-group"><label>유형</label><select id="pool-type">${types.map(([v,l])=>`<option value="${v}">${l}</option>`).join('')}</select></div>
            <div class="form-group"><label>내용</label><textarea id="pool-content" rows="3"></textarea>${hint('아바타/배너: 파일 절대경로. 이름/설명: 텍스트. 해시태그: ["태그1","태그2"]')}</div>
            <div class="modal-actions">
                <button class="btn btn-outline" onclick="this.closest('.modal-overlay').remove()">취소</button>
                <button class="btn btn-primary" onclick="savePool()">저장</button></div>
        </div></div>`;
}
async function savePool(){await api('/pools/api/create',{method:'POST',body:{pool_type:document.getElementById('pool-type').value,content:document.getElementById('pool-content').value}});toast('추가됨');document.querySelector('.modal-overlay').remove();renderPools(document.getElementById('content'));}
async function togglePool(id){await api(`/pools/api/${id}/toggle`,{method:'POST'});renderPools(document.getElementById('content'));}
async function filterPool(type,tab){document.querySelectorAll('.tabs .tab').forEach(t=>t.classList.remove('active'));tab.classList.add('active');
    const pools=await api(`/pools/api/list?type=${type}`);document.getElementById('pool-tbody').innerHTML=poolRows(pools);}

// ==================== 로그 ====================
async function renderLogs(el){
    const logs=await api('/logs/api/list');
    el.innerHTML=`<h1 class="page-title">에러 로그</h1>
        <div class="filter-bar"><select onchange="filterLog(this.value)"><option value="">전체</option><option value="critical">심각</option><option value="error">에러</option><option value="warning">경고</option><option value="info">정보</option></select></div>
        <div class="card"><table><thead><tr><th>시간</th><th>레벨</th><th>출처</th><th>메시지</th><th>해결</th></tr></thead>
        <tbody>${(logs||[]).map(l=>`<tr>
            <td style="white-space:nowrap">${l.created_at?new Date(l.created_at).toLocaleString('ko'):'-'}</td>
            <td>${badge(l.level)}</td><td>${l.source||'-'}</td>
            <td style="max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${l.message}</td>
            <td>${l.resolved?'예':'아니오'}</td></tr>`).join('')}</tbody></table></div>`;
}
async function filterLog(l){renderLogs(document.getElementById('content'));}

// ==================== 초기화 ====================
document.addEventListener('DOMContentLoaded',()=>{
    document.querySelectorAll('.sidebar nav a[data-page]').forEach(a=>a.addEventListener('click',e=>{e.preventDefault();navigate(a.dataset.page);}));
    navigate('dashboard');
    setInterval(()=>{if(currentPage==='dashboard')renderDashboard(document.getElementById('content'));},30000);
});
