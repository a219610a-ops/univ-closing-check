import streamlit as st
import pandas as pd
import sqlite3
import io
import difflib
import re
import json
import hashlib
from datetime import datetime

# ==========================================
# 1. 페이지 기본 설정 및 모던 스타일
# ==========================================
st.set_page_config(
    page_title="대학 행정 스마트 통합 포털",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stApp {
        background-color: #F8FAFC;
    }
    .portal-top-bar {
        background-color: #FFFFFF;
        border-bottom: 1px solid #E2E8F0;
        padding: 10px 18px;
        margin-bottom: 16px;
        border-radius: 10px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .main-app-title {
        font-size: 21px !important;
        font-weight: 700 !important;
        color: #0F172A !important;
        margin-bottom: 2px !important;
        padding-top: 0px !important;
    }
    .main-app-caption {
        font-size: 13px !important;
        color: #64748B !important;
        margin-bottom: 14px !important;
    }
    .kpi-card {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 12px 16px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }
    .kpi-val {
        font-size: 20px;
        font-weight: 700;
        margin-top: 2px;
    }
    [data-testid="stDataFrame"] {
        border-radius: 8px;
        border: 1px solid #CBD5E1;
        background-color: #FFFFFF;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. SQLite DB 초기화 (결산 검증 + 기부금 관리 통합)
# ==========================================
def get_db_connection():
    conn = sqlite3.connect("accounting_audit.db", check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1) 결산 검증 프로젝트 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS account_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            target_name TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source_name, target_name)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_workspaces (
            project_id INTEGER PRIMARY KEY,
            left_label TEXT,
            right_label TEXT,
            source_raw_blob BLOB,
            target_raw_blob BLOB,
            source_sheet_name TEXT,
            target_sheet_name TEXT,
            settings_json TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)
    
    # 2) 기부금 관리 테이블 (대학/법인 완전 분리)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS donation_receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL, -- 'UNIVERSITY' or 'FOUNDATION'
            donation_date TEXT NOT NULL,
            budget_subject TEXT NOT NULL, -- 일반기부금, 지정기부금, 현물기부금
            purpose TEXT NOT NULL, -- 사용 용도 (직접입력)
            donor_main_type TEXT NOT NULL, -- 개인, 기업체, 단체및기관
            donor_sub_type TEXT NOT NULL, -- 교직원, 일반인, 기업체, 단체및기관
            donor_name TEXT NOT NULL,
            id_number_masked TEXT NOT NULL,
            id_number_cipher TEXT NOT NULL,
            donation_type TEXT NOT NULL, -- 금전, 현물
            code TEXT NOT NULL, -- 10 등
            amount REAL NOT NULL,
            receipt_no TEXT NOT NULL, -- YY-NN
            receipt_date TEXT NOT NULL,
            is_statutory_transfer INTEGER DEFAULT 0, -- 법정부담금 전출용 여부 (0: 일반, 1: 법정부담금전출)
            created_at TEXT NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS donation_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL, -- 'UNIVERSITY' or 'FOUNDATION'
            expense_date TEXT NOT NULL,
            beneficiary TEXT NOT NULL, -- 수혜자
            content TEXT NOT NULL, -- 수혜 내용
            purpose TEXT NOT NULL, -- 대응 용도
            amount REAL NOT NULL,
            is_statutory_transfer INTEGER DEFAULT 0, -- 법정부담금 전출 지출 여부
            created_at TEXT NOT NULL
        )
    """)
    
    conn.commit()
    conn.close()

init_db()

# 보안 마스킹 및 암호화 도우미
def mask_id_number(raw_id):
    if not raw_id:
        return ""
    clean = str(raw_id).strip().replace("-", "")
    if len(clean) == 13: # 주민등록번호
        return f"{clean[:6]}-{clean[6]}******"
    elif len(clean) == 10: # 사업자등록번호
        return f"{clean[:3]}-{clean[3:5]}-{clean[5:]}"
    return f"{clean[:6]}******" if len(clean) > 6 else clean

def simple_encrypt(raw_text):
    if not raw_text:
        return ""
    # SHA-256 기반 단방향 해시로 안전 저장 (필요 시 복호화 키 연동 가능 구조)
    return hashlib.sha256(raw_text.encode('utf-8')).hexdigest()

# 발급번호 자동 채번 (YY-NN)
def generate_receipt_no(entity_type):
    conn = get_db_connection()
    cursor = conn.cursor()
    yy = datetime.now().strftime("%y")
    cursor.execute("""
        SELECT receipt_no FROM donation_receipts 
        WHERE entity_type = ? AND receipt_no LIKE ? 
        ORDER BY id DESC LIMIT 1
    """, (entity_type, f"{yy}-%"))
    row = cursor.fetchone()
    conn.close()
    
    if row and row[0]:
        try:
            last_seq = int(row[0].split("-")[1])
            new_seq = last_seq + 1
        except Exception:
            new_seq = 1
    else:
        new_seq = 1
    return f"{yy}-{new_seq:02d}"

# ==========================================
# 3. 글로벌 상단 미니 메뉴바 및 페이지 라우팅
# ==========================================
if "current_page" not in st.session_state:
    st.session_state.current_page = "HOME"

# 상단 미니 메뉴바 (어디서나 1클릭 이동)
m_col1, m_col2, m_col3, m_col4 = st.columns([3.5, 1.2, 1.6, 1.4])
with m_col1:
    st.markdown("<h4 style='margin:0; color:#0F172A;'>🏛️ 대학 행정 스마트 통합 포털</h4>", unsafe_allow_html=True)
with m_col2:
    if st.button("🏠 홈 대시보드", use_container_width=True, type="primary" if st.session_state.current_page == "HOME" else "secondary"):
        st.session_state.current_page = "HOME"
        st.rerun()
with m_col3:
    if st.button("📊 결산 데이터 스마트 검증기", use_container_width=True, type="primary" if st.session_state.current_page == "CLOSING" else "secondary"):
        st.session_state.current_page = "CLOSING"
        st.rerun()
with m_col4:
    if st.button("🎗️ 기부금 관리 시스템", use_container_width=True, type="primary" if st.session_state.current_page == "DONATION" else "secondary"):
        st.session_state.current_page = "DONATION"
        st.rerun()

st.markdown("<hr style='margin-top:6px; margin-bottom:18px; border-color:#E2E8F0;'>", unsafe_allow_html=True)

# ==========================================
# PAGE 1: 🏠 포털 메인 홈 대시보드
# ==========================================
if st.session_state.current_page == "HOME":
    st.markdown("""
    <div style="background-color:#EEF2FF; border:1px solid #C7D2FE; border-radius:12px; padding:18px 22px; margin-bottom:22px;">
        <div style="font-size:18px; font-weight:700; color:#1E1B4B;">반갑습니다, 교직원 업무 포털입니다 👋</div>
        <div style="font-size:13.5px; color:#4338CA; margin-top:4px;">
            원하시는 업무 카드를 클릭하시면 해당 작업 화면으로 즉시 연결됩니다.
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("#### 📂 주요 업무 시스템 바로가기")
    
    c_card1, c_card2 = st.columns(2)
    
    with c_card1:
        st.markdown("""
        <div class="kpi-card" style="border-left: 5px solid #2563EB; min-height: 250px;">
            <div style="display:flex; align-items:center; gap:10px;">
                <span style="font-size:26px;">📊</span>
                <div>
                    <div style="font-size:17px; font-weight:700; color:#0F172A;">결산 데이터 스마트 검증기</div>
                    <div style="font-size:12px; color:#64748B;">학교 결산 원장 ↔ 사학진흥재단 양식 크로스체크</div>
                </div>
            </div>
            <hr style="margin:12px 0; border-color:#F1F5F9;">
            <ul style="font-size:12.5px; color:#334155; line-height:1.7; padding-left:18px;">
                <li>대학 본결산 엑셀 시트 자동 로드 및 실시간 금액 대조</li>
                <li>지능형 계정 매칭 엔진 & 1클릭 차액 오차 원인 진단</li>
                <li>엑셀형 스프레드시트 인라인 편집 및 DB 영구 보존</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        if st.button("결산 검증기 시작하기 ➔", key="btn_go_closing", type="primary", use_container_width=True):
            st.session_state.current_page = "CLOSING"
            st.rerun()

    with c_card2:
        st.markdown("""
        <div class="kpi-card" style="border-left: 5px solid #059669; min-height: 250px;">
            <div style="display:flex; align-items:center; gap:10px;">
                <span style="font-size:26px;">🎗️</span>
                <div>
                    <div style="font-size:17px; font-weight:700; color:#0F172A;">기부금 관리 시스템</div>
                    <div style="font-size:12px; color:#64748B;">대학 및 법인 기부금 수입·지출·발급명세 통합 관리</div>
                </div>
            </div>
            <hr style="margin:12px 0; border-color:#F1F5F9;">
            <ul style="font-size:12.5px; color:#334155; line-height:1.7; padding-left:18px;">
                <li><b>대학 회계 / 법인 회계</b> 데이터 완벽 격리 모드 지원</li>
                <li><b>국세청 표준 법정 영수증</b> 엑셀 다운로드 (로컬 직인 날인 가능)</li>
                <li>용도별 실시간 집행 잔액 집계 및 <b>법정부담금 전출 특화 관리</b></li>
                <li>주민등록번호 마스킹 및 강력한 보안 조치 적용</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        if st.button("기부금 시스템 시작하기 ➔", key="btn_go_donation", type="primary", use_container_width=True):
            st.session_state.current_page = "DONATION"
            st.rerun()

# ==========================================
# PAGE 2: 📊 결산 데이터 스마트 검증기
# ==========================================
elif st.session_state.current_page == "CLOSING":
    # ---------------- 결산 검증 로직 함수 ----------------
    def get_projects():
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn)
        conn.close()
        return df

    def create_project(name):
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            cursor.execute("INSERT INTO projects (name, created_at) VALUES (?, ?)", (name, now))
            new_id = cursor.lastrowid
            cursor.execute("""
                INSERT INTO project_workspaces (project_id, left_label, right_label, settings_json, updated_at)
                VALUES (?, '학교 양식', '재단 양식', '{}', ?)
            """, (new_id, now))
            conn.commit()
            success = True
        except sqlite3.IntegrityError:
            success = False
        conn.close()
        return success

    def rename_project(project_id, new_name):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE projects SET name = ? WHERE id = ?", (new_name.strip(), project_id))
            conn.commit()
            success = True
        except sqlite3.IntegrityError:
            success = False
        conn.close()
        return success

    def delete_project(project_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        conn.close()

    def get_workspace_files(project_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT left_label, right_label, source_raw_blob, target_raw_blob, 
                   source_sheet_name, target_sheet_name, settings_json 
            FROM project_workspaces WHERE project_id = ?
        """, (project_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            settings = {}
            try:
                if row[6]:
                    settings = json.loads(row[6])
            except Exception:
                pass
            return {
                "left_label": row[0] or "학교 양식",
                "right_label": row[1] or "재단 양식",
                "source_raw_blob": row[2],
                "target_raw_blob": row[3],
                "source_sheet_name": row[4],
                "target_sheet_name": row[5],
                "settings": settings
            }
        return {"left_label": "학교 양식", "right_label": "재단 양식", "source_raw_blob": None, "target_raw_blob": None, "source_sheet_name": None, "target_sheet_name": None, "settings": {}}

    def update_workspace_file_blob(project_id, side, file_bytes, default_sheet=None):
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        blob_col = "source_raw_blob" if side == "source" else "target_raw_blob"
        sheet_col = "source_sheet_name" if side == "source" else "target_sheet_name"
        if default_sheet:
            cursor.execute(f"UPDATE project_workspaces SET {blob_col} = ?, {sheet_col} = ?, updated_at = ? WHERE project_id = ?", (file_bytes, default_sheet, now, project_id))
        else:
            cursor.execute(f"UPDATE project_workspaces SET {blob_col} = ?, updated_at = ? WHERE project_id = ?", (file_bytes, now, project_id))
        conn.commit()
        conn.close()

    def update_workspace_sheet_choice(project_id, side, sheet_name):
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        col_name = "source_sheet_name" if side == "source" else "target_sheet_name"
        cursor.execute(f"UPDATE project_workspaces SET {col_name} = ?, updated_at = ? WHERE project_id = ?", (sheet_name, now, project_id))
        conn.commit()
        conn.close()

    def update_workspace_labels(project_id, left_label, right_label):
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE project_workspaces SET left_label = ?, right_label = ?, updated_at = ? WHERE project_id = ?", (left_label, right_label, now, project_id))
        conn.commit()
        conn.close()

    def save_workspace_settings(project_id, settings_dict):
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        s_str = json.dumps(settings_dict, ensure_ascii=False)
        cursor.execute("UPDATE project_workspaces SET settings_json = ?, updated_at = ? WHERE project_id = ?", (s_str, now, project_id))
        conn.commit()
        conn.close()

    def reset_workspace_data(project_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE project_workspaces SET source_raw_blob = NULL, target_raw_blob = NULL, source_sheet_name = NULL, target_sheet_name = NULL, settings_json = '{}', updated_at = ? WHERE project_id = ?", (now, project_id))
        conn.commit()
        conn.close()

    def get_saved_mappings():
        conn = get_db_connection()
        mapping_dict = {}
        try:
            df = pd.read_sql_query("SELECT source_name, target_name FROM account_mappings", conn)
            mapping_dict = dict(zip(df['source_name'], df['target_name']))
        except Exception:
            pass
        finally:
            conn.close()
        return mapping_dict

    def save_batch_mappings(mapping_dict):
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for s_name, t_name in mapping_dict.items():
            if s_name and t_name and t_name != "(매칭 제외)":
                cursor.execute("""
                    INSERT INTO account_mappings (source_name, target_name, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(source_name, target_name) 
                    DO UPDATE SET updated_at=excluded.updated_at
                """, (s_name.strip(), t_name.strip(), now))
        conn.commit()
        conn.close()

    EXCLUDE_KEYWORDS = ["총계", "합계", "소계", "차기이월", "전기이월", "이월자금", "수입총계", "지출총계"]
    def is_aggregate_account(name):
        return any(kw in name for kw in EXCLUDE_KEYWORDS)

    def clean_account_name(raw_name):
        if pd.isna(raw_name): return ""
        text = str(raw_name).strip()
        text = re.sub(r'^[0-9\.\-\_\(\)\[\]\s]+', '', text)
        clean_text = re.sub(r'[\s\.\-\_\(\)\[\]]+', '', text)
        return clean_text if clean_text else text

    def clean_number(val):
        if pd.isna(val): return 0.0
        if isinstance(val, (int, float)): return float(val)
        try: return float(str(val).replace(",", "").strip())
        except ValueError: return 0.0

    def find_smart_match(source_name, target_options, target_clean_dict, saved_history):
        if source_name in saved_history and saved_history[source_name] in target_options:
            return saved_history[source_name], "💾 DB기억"
        src_clean = clean_account_name(source_name)
        if not src_clean: return "(매칭 제외)", "미매칭"
        for raw_target, clean_target in target_clean_dict.items():
            if is_aggregate_account(raw_target): continue
            if src_clean == clean_target: return raw_target, "🎯 순수일치"
        if len(src_clean) >= 3:
            for raw_target, clean_target in target_clean_dict.items():
                if is_aggregate_account(raw_target): continue
                if len(clean_target) >= 3 and (src_clean in clean_target or clean_target in src_clean):
                    return raw_target, "🔍 정밀포함"
        valid_targets = [raw for raw in target_options if raw != "(매칭 제외)" and not is_aggregate_account(raw)]
        valid_clean_map = {target_clean_dict[raw]: raw for raw in valid_targets if target_clean_dict.get(raw)}
        matches = difflib.get_close_matches(src_clean, list(valid_clean_map.keys()), n=1, cutoff=0.75)
        if matches: return valid_clean_map[matches[0]], "🤖 정밀추천"
        return "(매칭 제외)", "미매칭"

    def get_all_row_candidates(df, name_col):
        if df is None or df.empty or name_col not in df.columns: return ["(자동 감지)"]
        all_names = [str(x).strip() for x in df[name_col].dropna().unique() if str(x).strip()]
        pats = [r'자금수입총계', r'자금지출총계', r'수입총계', r'지출총계', r'총\s*계', r'합\s*계', r'수입합계', r'지출합계', r'계']
        priority_pattern = re.compile('|'.join(pats))
        priority_rows = [n for n in all_names if priority_pattern.search(n)]
        normal_rows = [n for n in all_names if not priority_pattern.search(n)]
        return ["(자동 감지)"] + sorted(priority_rows) + sorted(normal_rows)

    def extract_smart_grand_total(df, name_col, amt_col, target_total_type="수입", forced_row=None):
        if df is None or df.empty or name_col not in df.columns or amt_col not in df.columns:
            return 0.0, "데이터 없음"
        temp = df.dropna(subset=[name_col]).copy()
        temp[name_col] = temp[name_col].astype(str).str.strip()
        temp['__amt_clean'] = temp[amt_col].apply(clean_number)
        if forced_row and forced_row != "(자동 감지)":
            matched = temp[temp[name_col] == forced_row]
            if not matched.empty: return float(matched.iloc[-1]['__amt_clean']), forced_row

        patterns = [r'자금수입총계', r'수입총계', r'수입합계', r'총\s*계'] if "수입" in target_total_type else [r'자금지출총계', r'지출총계', r'지출합계', r'총\s*계']
        for pat in patterns:
            matched = temp[temp[name_col].str.contains(pat, regex=True, na=False)]
            valid_rows = matched[matched['__amt_clean'] > 0]
            if not valid_rows.empty:
                chosen = valid_rows.iloc[-1]
                return float(chosen['__amt_clean']), chosen[name_col]

        exclude_pattern = '|'.join(EXCLUDE_KEYWORDS)
        pure_details = temp[~temp[name_col].str.contains(exclude_pattern, regex=True, na=False)]
        return float(pure_details['__amt_clean'].sum()), "세부계정 순합계"

    # 사이드바 프로젝트 관리
    projects_df = get_projects()
    with st.sidebar:
        st.markdown("#### 📂 결산 프로젝트 목록")
        with st.expander("➕ 새 프로젝트 추가", expanded=False):
            new_proj_name = st.text_input("새 프로젝트명", placeholder="예: 2025 본결산", key="new_proj_input_side")
            if st.button("추가", use_container_width=True, type="primary"):
                if new_proj_name.strip():
                    if create_project(new_proj_name.strip()):
                        st.query_params["project"] = new_proj_name.strip()
                        st.rerun()
                    else: st.error("이미 존재하는 프로젝트입니다.")

        if not projects_df.empty:
            project_names = projects_df['name'].tolist()
            url_proj = st.query_params.get("project", None)
            if url_proj not in project_names: url_proj = project_names[0]
            selected_project_name = url_proj
            curr_project_id = int(projects_df[projects_df['name'] == selected_project_name].iloc[0]['id'])

            for _, p_row in projects_df.iterrows():
                p_id = int(p_row['id'])
                p_name = p_row['name']
                is_active = (p_name == selected_project_name)
                p_col1, p_col2 = st.columns([4, 1])
                with p_col1:
                    if st.button(f"{'✓ ' if is_active else '• '}{p_name}", key=f"sel_proj_{p_id}", type="primary" if is_active else "secondary", use_container_width=True):
                        st.query_params["project"] = p_name
                        st.rerun()
                with p_col2:
                    with st.popover("✏️"):
                        new_pname = st.text_input("이름 변경", value=p_name, key=f"rename_{p_id}")
                        if st.button("저장", key=f"save_r_{p_id}"):
                            if rename_project(p_id, new_pname.strip()):
                                st.query_params["project"] = new_pname.strip()
                                st.rerun()
                        if st.button("🗑️ 삭제", key=f"del_{p_id}"):
                            delete_project(p_id)
                            st.rerun()
        else:
            selected_project_name = None
            curr_project_id = None

    if not selected_project_name:
        st.info("👈 왼쪽 사이드바에서 새 프로젝트를 추가해 주세요.")
        st.stop()

    workspace_files = get_workspace_files(curr_project_id)
    saved_settings = workspace_files.get("settings", {})

    st.markdown('<div class="main-app-title">📊 데이터 스마트 검증기</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="main-app-caption">📌 현재 프로젝트: <b>{selected_project_name}</b> | 양쪽 파일의 대상 시트를 자유롭게 선택해 검증할 수 있습니다.</div>', unsafe_allow_html=True)

    # 1단계: 파일 업로드 및 시트 선택
    source_blob = workspace_files["source_raw_blob"]
    target_blob = workspace_files["target_raw_blob"]
    source_df = None
    target_df = None

    with st.expander("📁 1단계: 대조 파일 업로드 및 대상 시트 선택 (상시 변경 가능)", expanded=True):
        lbl_c1, lbl_c2 = st.columns(2)
        with lbl_c1: left_label_input = st.text_input("기준 파일 라벨", value=workspace_files["left_label"], key=f"left_lbl_{curr_project_id}")
        with lbl_c2: right_label_input = st.text_input("대조 파일 라벨", value=workspace_files["right_label"], key=f"right_lbl_{curr_project_id}")
        if (left_label_input != workspace_files["left_label"]) or (right_label_input != workspace_files["right_label"]):
            update_workspace_labels(curr_project_id, left_label_input, right_label_input)
            st.rerun()

        f_col1, f_col2 = st.columns(2)
        with f_col1:
            st.markdown(f"**🏫 {left_label_input} 파일**")
            new_s_file = st.file_uploader(f"{left_label_input} 등록 (.xlsx, .xls)", type=["xlsx", "xls"], key=f"s_up_{curr_project_id}")
            if new_s_file is not None:
                bytes_val = new_s_file.getvalue()
                if source_blob != bytes_val:
                    init_s = pd.ExcelFile(io.BytesIO(bytes_val)).sheet_names[0]
                    update_workspace_file_blob(curr_project_id, "source", bytes_val, default_sheet=init_s)
                    st.rerun()
            if source_blob is not None:
                xl_s = pd.ExcelFile(io.BytesIO(source_blob))
                cur_s_sheet = workspace_files.get("source_sheet_name")
                s_idx = xl_s.sheet_names.index(cur_s_sheet) if cur_s_sheet in xl_s.sheet_names else 0
                chosen_s = st.selectbox(f"📑 [{left_label_input}] 시트 선택", xl_s.sheet_names, index=s_idx, key=f"s_sheet_{curr_project_id}")
                if chosen_s != cur_s_sheet:
                    update_workspace_sheet_choice(curr_project_id, "source", chosen_s)
                    st.rerun()
                source_df = pd.read_excel(io.BytesIO(source_blob), sheet_name=chosen_s)
                st.caption(f"✓ '{chosen_s}' 로드됨 ({len(source_df)}행)")

        with f_col2:
            st.markdown(f"**🏛️ {right_label_input} 파일**")
            new_t_file = st.file_uploader(f"{right_label_input} 등록 (.xlsx, .xls)", type=["xlsx", "xls"], key=f"t_up_{curr_project_id}")
            if new_t_file is not None:
                bytes_val_t = new_t_file.getvalue()
                if target_blob != bytes_val_t:
                    init_t = pd.ExcelFile(io.BytesIO(bytes_val_t)).sheet_names[0]
                    update_workspace_file_blob(curr_project_id, "target", bytes_val_t, default_sheet=init_t)
                    st.rerun()
            if target_blob is not None:
                xl_t = pd.ExcelFile(io.BytesIO(target_blob))
                cur_t_sheet = workspace_files.get("target_sheet_name")
                t_idx = xl_t.sheet_names.index(cur_t_sheet) if cur_t_sheet in xl_t.sheet_names else 0
                chosen_t = st.selectbox(f"📑 [{right_label_input}] 시트 선택", xl_t.sheet_names, index=t_idx, key=f"t_sheet_{curr_project_id}")
                if chosen_t != cur_t_sheet:
                    update_workspace_sheet_choice(curr_project_id, "target", chosen_t)
                    st.rerun()
                target_df = pd.read_excel(io.BytesIO(target_blob), sheet_name=chosen_t)
                st.caption(f"✓ '{chosen_t}' 로드됨 ({len(target_df)}행)")

    if source_df is None or target_df is None:
        st.info("💡 1단계 카드에서 두 엑셀 파일을 업로드하고 [대상 시트]를 각각 선택해 주세요.")
        st.stop()

    # 2단계: 대조 열 및 총계 행 설정
    source_cols = list(source_df.columns)
    target_cols = list(target_df.columns)
    def_s_name = saved_settings.get("s_name_col", source_cols[0] if source_cols else None)
    def_t_name = saved_settings.get("t_name_col", target_cols[0] if target_cols else None)
    def_s_amt = saved_settings.get("s_amt", source_cols[min(2, len(source_cols)-1)] if source_cols else None)
    def_t_amt = saved_settings.get("t_amt", target_cols[min(2, len(target_cols)-1)] if target_cols else None)
    def_s_tot = saved_settings.get("forced_s_total_row", "(자동 감지)")
    def_t_tot = saved_settings.get("forced_t_total_row", "(자동 감지)")

    with st.expander("⚙️ 2단계: 대조 열 및 양측 총계 행 설정 (자동 저장됨)", expanded=True):
        c1, c2 = st.columns(2)
        with c1: s_name_col = st.selectbox(f"{left_label_input} 항목명 열", source_cols, index=source_cols.index(def_s_name) if def_s_name in source_cols else 0)
        with c2: t_name_col = st.selectbox(f"{right_label_input} 항목명 열", target_cols, index=target_cols.index(def_t_name) if def_t_name in target_cols else 0)
        a1, a2 = st.columns(2)
        with a1: s_amt = st.selectbox(f"금액 열 ({left_label_input})", source_cols, index=source_cols.index(def_s_amt) if def_s_amt in source_cols else min(2, len(source_cols)-1))
        with a2: t_amt = st.selectbox(f"금액 열 ({right_label_input})", target_cols, index=target_cols.index(def_t_amt) if def_t_amt in target_cols else min(2, len(target_cols)-1))

        tc1, tc2 = st.columns(2)
        s_cands = get_all_row_candidates(source_df, s_name_col)
        with tc1:
            forced_s_total_row = st.selectbox(f"🏫 [{left_label_input}] 총계 행 선택", s_cands, index=s_cands.index(def_s_tot) if def_s_tot in s_cands else 0, key=f"f_s_tot_{curr_project_id}")
            if forced_s_total_row != "(자동 감지)":
                r_m = source_df[source_df[s_name_col].astype(str).str.strip() == forced_s_total_row]
                if not r_m.empty: st.caption(f"확인된 금액: **{clean_number(r_m.iloc[-1][s_amt]):,.0f} 원**")
        t_cands = get_all_row_candidates(target_df, t_name_col)
        with tc2:
            forced_t_total_row = st.selectbox(f"🏛️ [{right_label_input}] 총계 행 선택", t_cands, index=t_cands.index(def_t_tot) if def_t_tot in t_cands else 0, key=f"f_t_tot_{curr_project_id}")
            if forced_t_total_row != "(자동 감지)":
                r_mt = target_df[target_df[t_name_col].astype(str).str.strip() == forced_t_total_row]
                if not r_mt.empty: st.caption(f"확인된 금액: **{clean_number(r_mt.iloc[-1][t_amt]):,.0f} 원**")

        current_settings = {"s_name_col": s_name_col, "t_name_col": t_name_col, "s_amt": s_amt, "t_amt": t_amt, "forced_s_total_row": forced_s_total_row, "forced_t_total_row": forced_t_total_row}
        if current_settings != saved_settings: save_workspace_settings(curr_project_id, current_settings)

    # 3단계: 총계 및 매칭 연산
    s_df_clean = source_df.dropna(subset=[s_name_col]).copy()
    t_df_clean = target_df.dropna(subset=[t_name_col]).copy()
    s_df_clean[s_name_col] = s_df_clean[s_name_col].astype(str).str.strip()
    t_df_clean[t_name_col] = t_df_clean[t_name_col].astype(str).str.strip()
    s_df_clean[s_amt] = s_df_clean[s_amt].apply(clean_number)
    t_df_clean[t_amt] = t_df_clean[t_amt].apply(clean_number)

    official_t_total, t_src_name = extract_smart_grand_total(t_df_clean, t_name_col, t_amt, forced_row=forced_t_total_row)
    t_type = "수입" if "수입" in t_src_name else ("지출" if "지출" in t_src_name else "전체")
    official_s_total, s_src_name = extract_smart_grand_total(s_df_clean, s_name_col, s_amt, target_total_type=t_type, forced_row=forced_s_total_row)
    grand_diff = official_s_total - official_t_total

    target_sum_lookup = dict(t_df_clean.groupby(t_name_col)[t_amt].sum())
    raw_target_list = sorted([str(x).strip() for x in t_df_clean[t_name_col].unique() if str(x).strip()])
    target_clean_dict = {r: clean_account_name(r) for r in raw_target_list}
    target_options = ["(매칭 제외)"] + raw_target_list
    saved_history = get_saved_mappings()
    unique_s_items = sorted([str(x).strip() for x in s_df_clean[s_name_col].unique() if str(x).strip() and not is_aggregate_account(str(x))])

    matched_rows = []
    for s_name in unique_s_items:
        s_key = f"match_override_{curr_project_id}_{re.sub(r'[^a-zA-Z0-9가-힣]', '_', s_name)}"
        if s_key in st.session_state:
            sel_match, st_text = st.session_state[s_key], "✏️ 수동"
        elif s_name in saved_history and saved_history[s_name] in target_options:
            sel_match, st_text = saved_history[s_name], "💾 저장됨"
        else:
            sel_match, st_text = find_smart_match(s_name, target_options, target_clean_dict, saved_history)

        s_val = s_df_clean[s_df_clean[s_name_col] == s_name][s_amt].sum()
        t_val = target_sum_lookup.get(sel_match, 0.0) if sel_match and sel_match != "(매칭 제외)" else 0.0
        diff = s_val - t_val
        val_status = "⚠️ 미매칭" if (not sel_match or sel_match == "(매칭 제외)") else ("❌ 오류" if abs(diff) > 0.01 else "✅ 일치")
        
        matched_rows.append({
            "상태": val_status,
            f"{left_label_input} 항목명": s_name,
            f"{left_label_input} 결산액": int(round(s_val)),
            f"매칭 {right_label_input} 항목명": sel_match,
            f"{right_label_input} 결산액": int(round(t_val)),
            "차액": int(round(diff)),
            "매칭유형": st_text
        })
    res_df = pd.DataFrame(matched_rows)

    # 상단 요약 배너
    border_c = "#059669" if abs(grand_diff) < 1 else "#DC2626"
    diff_txt = "총계 완벽 일치 (0원)" if abs(grand_diff) < 1 else f"총계 차액: {grand_diff:+,.0f} 원"
    st.markdown(f"""
    <div class="kpi-card" style="margin-bottom: 16px; border-left: 5px solid {border_c};">
        <div style="font-size: 13px; font-weight: 600; color: #64748B;">자금 결산 정합성 현황 (공식 총계 행 기준)</div>
        <div style="font-size: 16px; font-weight: 700; color: #0F172A; margin-top: 4px;">
            {left_label_input} 총계: <b style="color:#1E40AF;">{official_s_total:,.0f} 원</b> ↔ 
            {right_label_input} 총계: <b style="color:#6D28D9;">{official_t_total:,.0f} 원</b> 
            &nbsp;<span style="color:{border_c}; font-size:15px;">[ {diff_txt} ]</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 스마트 시트 표 (height=760px)
    t_col_title = f"매칭 {right_label_input} 항목명"
    st.info("💡 **표 편집 안내:** 표 안에서 항목을 더블클릭하여 변경 후 아래 [💾 영구 저장]을 눌러주세요.")
    edited_df = st.data_editor(
        res_df,
        use_container_width=True,
        height=760,
        hide_index=True,
        key=f"editor_{curr_project_id}",
        column_config={
            "상태": st.column_config.TextColumn("검증 상태", width=85, disabled=True),
            f"{left_label_input} 항목명": st.column_config.TextColumn(f"{left_label_input} 항목명 (기준)", width=210, disabled=True),
            f"{left_label_input} 결산액": st.column_config.NumberColumn(f"{left_label_input} 금액 (원)", format="%,d", width=135, disabled=True),
            t_col_title: st.column_config.SelectboxColumn(f"매칭 {right_label_input} 항목명 (더블클릭)", options=target_options, required=True, width=210),
            f"{right_label_input} 결산액": st.column_config.NumberColumn(f"{right_label_input} 금액 (원)", format="%,d", width=135, disabled=True),
            "차액": st.column_config.NumberColumn("차액 (원)", format="%,d", width=135, disabled=True),
            "매칭유형": st.column_config.TextColumn("유형", width=75, disabled=True)
        }
    )
    if st.button("💾 표에서 변경한 매칭 일괄 영구 저장", type="primary", use_container_width=True):
        b_save = {}
        for _, row in edited_df.iterrows():
            sn = row[f"{left_label_input} 항목명"]
            tn = row[t_col_title]
            b_save[sn] = tn
        save_batch_mappings(b_save)
        st.success("저장 완료!")
        st.rerun()

# ==========================================
# PAGE 3: 🎗️ 기부금 관리 시스템
# ==========================================
elif st.session_state.current_page == "DONATION":
    st.markdown('<div class="main-app-title">🎗️ 기부금 관리 시스템</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-app-caption">대학 및 법인 기부금 수입·지출 등록, 국세청 표준 법정 서식 및 발급명세서를 자동 생성합니다.</div>', unsafe_allow_html=True)

    # 1. 회계 모드 선택 (대학 회계 vs 법인 회계 완전 분리)
    ent_c1, ent_c2 = st.columns([2, 3])
    with ent_c1:
        entity_choice = st.radio(
            "회계 분리 모드",
            ["🏫 대학 회계", "🏛️ 법인 회계"],
            horizontal=True
        )
    current_entity = "UNIVERSITY" if "대학" in entity_choice else "FOUNDATION"

    st.markdown("<hr style='margin:10px 0 16px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)

    # 2. 용도별 합계 및 법정부담금 실시간 대시보드
    conn = get_db_connection()
    receipts_df = pd.read_sql_query("SELECT * FROM donation_receipts WHERE entity_type = ?", conn, params=(current_entity,))
    expenses_df = pd.read_sql_query("SELECT * FROM donation_expenses WHERE entity_type = ?", conn, params=(current_entity,))
    conn.close()

    total_income = receipts_df['amount'].sum() if not receipts_df.empty else 0.0
    total_expense = expenses_df['amount'].sum() if not expenses_df.empty else 0.0
    balance = total_income - total_expense

    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"""<div class="kpi-card"><div style="color:#64748B; font-size:12px; font-weight:600;">총 기부금 수입</div><div class="kpi-val" style="color:#2563EB;">{total_income:,.0f} 원</div></div>""", unsafe_allow_html=True)
    k2.markdown(f"""<div class="kpi-card"><div style="color:#64748B; font-size:12px; font-weight:600;">총 기부금 지출</div><div class="kpi-val" style="color:#DC2626;">{total_expense:,.0f} 원</div></div>""", unsafe_allow_html=True)
    k3.markdown(f"""<div class="kpi-card"><div style="color:#64748B; font-size:12px; font-weight:600;">현재 집행 잔액</div><div class="kpi-val" style="color:#059669;">{balance:,.0f} 원</div></div>""", unsafe_allow_html=True)
    k4.markdown(f"""<div class="kpi-card"><div style="color:#64748B; font-size:12px; font-weight:600;">영수증 발급 누계</div><div class="kpi-val" style="color:#0F172A;">{len(receipts_df)} 건</div></div>""", unsafe_allow_html=True)

    # 법인 모드 전용 법정부담금 전출 정산 현황 배너
    if current_entity == "FOUNDATION":
        stat_inc = receipts_df[receipts_df['is_statutory_transfer'] == 1]['amount'].sum() if not receipts_df.empty else 0.0
        stat_exp = expenses_df[expenses_df['is_statutory_transfer'] == 1]['amount'].sum() if not expenses_df.empty else 0.0
        st.markdown(f"""
        <div class="kpi-card" style="margin-top:14px; border-left:5px solid #7C3AED; background-color:#FAF5FF;">
            <div style="font-size:13px; font-weight:700; color:#6B21A8;">🏛️ [법인 전용] 법정부담금 전출 특화 관리 현황</div>
            <div style="font-size:14.5px; color:#1E293B; margin-top:4px;">
                법정부담금 전출용 수입: <b>{stat_inc:,.0f} 원</b> ↔ 학교 전출 지출: <b>{stat_exp:,.0f} 원</b> 
                (정산 잔액: <b>{stat_inc - stat_exp:,.0f} 원</b>)
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

    # 3. 탭 구성: 기부금 수입 등록 | 지출 등록 | 용도별 정산표 | 발급명세서 & 영수증 출력
    tab_in, tab_out, tab_sum, tab_print = st.tabs([
        "📥 기부금 수입 등록 및 영수증 채번", 
        "📤 기부금 지출 내역 등록", 
        "📊 용도별 집행 정산표", 
        "📑 국세청 서식 및 영수증 엑셀 출력"
    ])

    # [TAB 1] 기부금 수입 등록
    with tab_in:
        with st.form(key="form_donation_income"):
            st.markdown("##### 1. 기부자 인적사항 및 회계 분류")
            f1, f2, f3 = st.columns(3)
            with f1:
                d_date = st.date_input("기부일자", datetime.now())
                budget_subj = st.selectbox("예산과목", ["일반기부금", "지정기부금", "현물기부금"])
            with f2:
                purpose_input = st.text_input("사용 용도 (직접 입력)", placeholder="예: 장학기금, 학과발전기금, 건물신축")
                d_main_type = st.selectbox("기부자 구분 (상위)", ["개인", "기업체", "단체및기관"])
            with f3:
                sub_opts = ["교직원", "일반인"] if d_main_type == "개인" else ([d_main_type])
                d_sub_type = st.selectbox("기부자 구분 (하위)", sub_opts)
                donor_name = st.text_input("기부자 성명 (또는 법인/단체명)")

            st.markdown("##### 2. 식별번호 및 기부 명세")
            f4, f5, f6 = st.columns(3)
            with f4:
                raw_id_no = st.text_input("주민등록번호 / 사업자번호", placeholder="예: 900101-1234567 또는 사업자번호", type="password", help="보안을 위해 비밀번호 형태로 마스킹 처리됩니다.")
            with f5:
                d_type = st.selectbox("기부 내용 구분", ["금전", "현물"])
                d_code = st.text_input("구분 코드 (법정 서식)", value="10")
            with f6:
                d_amt = st.number_input("기부 금액 (원)", min_value=0, step=10000, format="%d")

            st.markdown("##### 3. 영수증 발급 정보")
            f7, f8, f9 = st.columns(3)
            auto_rec_no = generate_receipt_no(current_entity)
            with f7:
                rec_no = st.text_input("발급번호 (YY-NN 자동)", value=auto_rec_no)
            with f8:
                rec_date = st.date_input("발급일자", datetime.now())
            with f9:
                is_stat_chk = 0
                if current_entity == "FOUNDATION":
                    is_stat = st.checkbox("📌 법정부담금 전출용 기부금 여부")
                    is_stat_chk = 1 if is_stat else 0

            submit_income = st.form_submit_button("💾 기부금 수입 등록 및 영수증 확정", type="primary", use_container_width=True)

            if submit_income:
                if donor_name.strip() and d_amt > 0:
                    masked_id = mask_id_number(raw_id_no)
                    cipher_id = simple_encrypt(raw_id_no)
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO donation_receipts (
                            entity_type, donation_date, budget_subject, purpose,
                            donor_main_type, donor_sub_type, donor_name,
                            id_number_masked, id_number_cipher, donation_type,
                            code, amount, receipt_no, receipt_date, is_statutory_transfer, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        current_entity, str(d_date), budget_subj, purpose_input.strip() or "일반",
                        d_main_type, d_sub_type, donor_name.strip(),
                        masked_id, cipher_id, d_type,
                        d_code.strip(), float(d_amt), rec_no.strip(), str(rec_date), is_stat_chk, now_str
                    ))
                    conn.commit()
                    conn.close()
                    st.success(f"[{donor_name}] 님의 기부금 ({d_amt:,.0f}원 / 발급번호: {rec_no}) 등록이 완료되었습니다!")
                    st.rerun()
                else:
                    st.warning("기부자 성명과 기부 금액을 올바르게 입력해 주세요.")

        # 최근 등록 목록 표
        st.markdown("##### 📋 최근 기부금 수입 등록 내역")
        if not receipts_df.empty:
            display_rec = receipts_df[[
                'receipt_no', 'donation_date', 'donor_name', 'id_number_masked', 
                'budget_subject', 'purpose', 'amount', 'donation_type', 'receipt_date'
            ]].copy()
            display_rec.columns = ['발급번호', '기부일자', '기부자명', '식별번호(마스킹)', '예산과목', '사용용도', '기부금액(원)', '구분', '발급일자']
            st.dataframe(display_rec, use_container_width=True, height=280)
        else:
            st.caption("등록된 기부금 내역이 없습니다.")

    # [TAB 2] 기부금 지출 내역 등록
    with tab_out:
        with st.form(key="form_donation_expense"):
            st.markdown("##### 기부금 지출(수혜) 내역 등록")
            e1, e2 = st.columns(2)
            with e1:
                e_date = st.date_input("지출일자", datetime.now())
                e_beneficiary = st.text_input("수혜자 (학생 성명, 학과, 기관 등)", placeholder="예: 기계공학과 홍길동 장학생")
                e_purpose = st.text_input("대응 사용 용도", placeholder="수입 당시 용도와 동일하게 입력 (예: 장학기금)")
            with e2:
                e_content = st.text_area("수혜 내용", placeholder="예: 2026학년도 1학기 발전기금 장학금 지급", height=90)
                e_amt = st.number_input("지출 금액 (원)", min_value=0, step=10000, format="%d")
                is_stat_exp = 0
                if current_entity == "FOUNDATION":
                    is_s_e = st.checkbox("📌 법정부담금 전출 지출 여부")
                    is_stat_exp = 1 if is_s_e else 0

            submit_expense = st.form_submit_button("💾 기부금 지출 등록", type="primary", use_container_width=True)
            if submit_expense:
                if e_beneficiary.strip() and e_amt > 0:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    cursor.execute("""
                        INSERT INTO donation_expenses (
                            entity_type, expense_date, beneficiary, content, purpose, amount, is_statutory_transfer, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (current_entity, str(e_date), e_beneficiary.strip(), e_content.strip(), e_purpose.strip() or "일반", float(e_amt), is_stat_exp, now_str))
                    conn.commit()
                    conn.close()
                    st.success("지출 내역이 성공적으로 등록되었습니다.")
                    st.rerun()
                else:
                    st.warning("수혜자와 지출 금액을 입력해 주세요.")

        st.markdown("##### 📋 최근 기부금 지출 내역")
        if not expenses_df.empty:
            display_exp = expenses_df[['expense_date', 'beneficiary', 'content', 'purpose', 'amount']].copy()
            display_exp.columns = ['지출일자', '수혜자', '수혜 내용', '사용용도', '지출금액(원)']
            st.dataframe(display_exp, use_container_width=True, height=240)
        else:
            st.caption("등록된 지출 내역이 없습니다.")

    # [TAB 3] 용도별 집행 정산표
    with tab_sum:
        st.markdown("##### 📊 사용 용도별 수입·지출 및 집행 잔액 현황")
        # 용도별 집계 계산
        inc_by_p = receipts_df.groupby('purpose')['amount'].sum().reset_index() if not receipts_df.empty else pd.DataFrame(columns=['purpose', 'amount'])
        exp_by_p = expenses_df.groupby('purpose')['amount'].sum().reset_index() if not expenses_df.empty else pd.DataFrame(columns=['purpose', 'amount'])
        
        merged_p = pd.merge(inc_by_p, exp_by_p, on='purpose', how='outer', suffixes=('_수입', '_지출')).fillna(0)
        merged_p['집행잔액'] = merged_p['amount_수입'] - merged_p['amount_지출']
        merged_p.columns = ['사용 용도', '수입 누계 (원)', '지출 누계 (원)', '집행 잔액 (원)']
        
        st.dataframe(merged_p.style.format({
            '수입 누계 (원)': '{:,.0f}',
            '지출 누계 (원)': '{:,.0f}',
            '집행 잔액 (원)': '{:,.0f}'
        }), use_container_width=True)

    # [TAB 4] 국세청 표준 서식 및 기부자별 발급명세서 엑셀 출력 (2번 방식 반영)
    with tab_print:
        st.markdown("##### 📑 서식 출력 및 다운로드 (로컬 PC 직인 날인 가능)")
        st.caption("웹 서버에 직인 이미지를 올리지 않고, 국세청 법정 양식 엑셀을 내려받아 로컬 PC에서 직인을 넣거나 출력 후 실물 도장을 날인할 수 있습니다.")

        down_c1, down_c2 = st.columns(2)
        
        # 1) 국세청 기부자별 발급명세서 다운로드
        with down_c1:
            st.markdown("###### 1. 기부자별 발급명세서 (연말정산/세무서 제출용)")
            if not receipts_df.empty:
                # 기부자별 집계
                summary_donor = receipts_df.groupby(['donor_name', 'id_number_masked', 'code']).agg(
                    건수=('amount', 'count'),
                    총금액=('amount', 'sum')
                ).reset_index()
                summary_donor.columns = ['기부자 성명(법인명)', '주민등록번호(사업자번호)', '기부유형코드', '발급건수', '기부금액 합계']

                buf_donor = io.BytesIO()
                with pd.ExcelWriter(buf_donor, engine='openpyxl') as writer:
                    summary_donor.to_excel(writer, index=False, sheet_name="기부자별발급명세서")
                buf_donor.seek(0)

                st.download_button(
                    label="📥 기부자별 발급명세서 (.xlsx) 다운로드",
                    data=buf_donor,
                    file_name=f"기부자별발급명세서_{current_entity}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    type="primary"
                )
            else:
                st.info("데이터가 없어 다운로드할 수 없습니다.")

        # 2) 소득세법 시행규칙 별지 제45호의2 서식 (기부금영수증 개별 엑셀 서식)
        with down_c2:
            st.markdown("###### 2. 국세청 법정 기부금영수증 표준 서식 (개별/전체)")
            if not receipts_df.empty:
                # 표준 법정 서식 시트 생성
                buf_receipt = io.BytesIO()
                with pd.ExcelWriter(buf_receipt, engine='openpyxl') as writer:
                    # 개별 영수증들을 서식 규격에 맞게 엑셀 행으로 구성
                    legal_form_df = receipts_df[[
                        'receipt_no', 'donor_name', 'id_number_masked', 'budget_subject',
                        'donation_date', 'donation_type', 'code', 'amount', 'receipt_date'
                    ]].copy()
                    legal_form_df.columns = [
                        '발급번호(일련번호)', '기부자성명', '주민(사업자)등록번호', '기부금유형(법정/지정)',
                        '기부연월일', '내용(금전/현물)', '코드(10)', '기부금액(원)', '영수증발급일'
                    ]
                    legal_form_df['발급기관 날인란'] = "(직인 생략 - 인쇄 후 날인)"
                    legal_form_df.to_excel(writer, index=False, sheet_name="기부금영수증_법정양식")

                buf_receipt.seek(0)
                st.download_button(
                    label="📥 국세청 기부금영수증 법정서식 (.xlsx) 다운로드",
                    data=buf_receipt,
                    file_name=f"기부금영수증_소득세법서식_{current_entity}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    type="primary"
                )
            else:
                st.info("데이터가 없어 다운로드할 수 없습니다.")
