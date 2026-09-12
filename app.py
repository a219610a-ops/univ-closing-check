import streamlit as st
import pandas as pd
import sqlite3
import io
import difflib
import re
from datetime import datetime

# ==========================================
# 1. 페이지 기본 설정 및 모던 밝은 톤 스타일 주입
# ==========================================
st.set_page_config(
    page_title="데이터 스마트 검증기 | 스마트 결산 대조 룸",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 화사하고 세련된 Bright Light UI 스타일링
st.markdown("""
<style>
    /* 전체 배경 */
    .stApp {
        background-color: #F8FAFC;
    }
    
    /* 카드 컨테이너 스타일 */
    .kpi-card {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .kpi-val {
        font-size: 24px;
        font-weight: 700;
        margin-top: 4px;
    }
    
    /* 3분할 브릿지 패널 공통 */
    .panel-box {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 14px 16px;
        margin-bottom: 12px;
        min-height: 82px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }
    .panel-selected {
        border: 2px solid #3B82F6 !important;
        background-color: #EFF6FF !important;
    }
    
    /* 중앙 브릿지 상태별 스타일 */
    .bridge-match {
        background-color: #ECFDF5;
        border: 1px solid #A7F3D0;
    }
    .bridge-error {
        background-color: #FEF2F2;
        border: 1.5px solid #FECACA;
    }
    .bridge-unmatched {
        background-color: #FFFBEB;
        border: 1px solid #FDE68A;
    }
    
    /* 하단 인스펙터 패널 */
    .inspector-box {
        background-color: #FFFFFF;
        border: 2px solid #EF4444;
        border-radius: 14px;
        padding: 20px;
        margin-top: 24px;
        box-shadow: 0 4px 12px rgba(239, 68, 68, 0.08);
    }
    
    /* 뱃지 */
    .badge {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. SQLite 데이터베이스 초기화 및 자동 보정
# ==========================================
def get_db_connection():
    conn = sqlite3.connect("accounting_audit.db", check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
    """)
    
    cursor.execute("SELECT count(name) FROM sqlite_master WHERE type='table' AND name='account_mappings'")
    table_exists = cursor.fetchone()[0] > 0
    
    if table_exists:
        cursor.execute("PRAGMA table_info(account_mappings)")
        columns = [col[1] for col in cursor.fetchall()]
        if "school_name" in columns and "source_name" not in columns:
            cursor.execute("ALTER TABLE account_mappings RENAME TO account_mappings_old")
            cursor.execute("""
                CREATE TABLE account_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT NOT NULL,
                    target_name TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(source_name, target_name)
                )
            """)
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO account_mappings (source_name, target_name, updated_at)
                    SELECT school_name, foundation_name, updated_at FROM account_mappings_old
                """)
            except Exception:
                pass
            cursor.execute("DROP TABLE IF EXISTS account_mappings_old")
    else:
        cursor.execute("""
            CREATE TABLE account_mappings (
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
            source_data_json TEXT,
            target_data_json TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()

init_db()

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
            INSERT INTO project_workspaces (project_id, left_label, right_label, source_data_json, target_data_json, updated_at)
            VALUES (?, '학교 결산서', '사학진흥재단 양식', NULL, NULL, ?)
        """, (new_id, now))
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

def get_workspace(project_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT left_label, right_label, source_data_json, target_data_json FROM project_workspaces WHERE project_id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        s_df = None
        t_df = None
        try:
            if row[2]:
                s_df = pd.read_json(io.StringIO(row[2]))
            if row[3]:
                t_df = pd.read_json(io.StringIO(row[3]))
        except Exception:
            pass
        return {
            "left_label": row[0] or "학교 결산서",
            "right_label": row[1] or "사학진흥재단 양식",
            "source_data": s_df,
            "target_data": t_df
        }
    return {"left_label": "학교 결산서", "right_label": "사학진흥재단 양식", "source_data": None, "target_data": None}

def update_workspace(project_id, left_label, right_label, source_df, target_df):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    s_json = source_df.to_json(orient='records', force_ascii=False) if source_df is not None else None
    t_json = target_df.to_json(orient='records', force_ascii=False) if target_df is not None else None
    
    cursor.execute("""
        INSERT INTO project_workspaces (project_id, left_label, right_label, source_data_json, target_data_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id) DO UPDATE SET
            left_label=excluded.left_label,
            right_label=excluded.right_label,
            source_data_json=excluded.source_data_json,
            target_data_json=excluded.target_data_json,
            updated_at=excluded.updated_at
    """, (project_id, left_label, right_label, s_json, t_json, now))
    conn.commit()
    conn.close()

def reset_workspace_data(project_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        UPDATE project_workspaces 
        SET source_data_json = NULL, target_data_json = NULL, updated_at = ? 
        WHERE project_id = ?
    """, (now, project_id))
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

def save_single_mapping(source_name, target_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if source_name and target_name and target_name != "(매칭 제외)":
        cursor.execute("""
            INSERT INTO account_mappings (source_name, target_name, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(source_name, target_name) 
            DO UPDATE SET updated_at=excluded.updated_at
        """, (source_name.strip(), target_name.strip(), now))
        conn.commit()
    conn.close()

# ==========================================
# 3. 고도화된 정밀 스마트 매칭 엔진
# ==========================================
EXCLUDE_KEYWORDS = ["총계", "합계", "소계", "차기이월", "전기이월", "이월자금", "수입총계", "지출총계"]

def is_aggregate_account(name):
    for kw in EXCLUDE_KEYWORDS:
        if kw in name:
            return True
    return False

def clean_account_name(raw_name):
    if pd.isna(raw_name):
        return ""
    text = str(raw_name).strip()
    text = re.sub(r'^[0-9\.\-\_\(\)\[\]\s]+', '', text)
    clean_text = re.sub(r'[\s\.\-\_\(\)\[\]]+', '', text)
    return clean_text if clean_text else text

def clean_number(val):
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).replace(",", "").strip()
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def find_smart_match(source_name, target_options, target_clean_dict, saved_history):
    if source_name in saved_history and saved_history[source_name] in target_options:
        return saved_history[source_name], "💾 DB기억"
        
    src_clean = clean_account_name(source_name)
    if not src_clean:
        return "(매칭 제외)", "미매칭"
        
    # 순수 일치
    for raw_target, clean_target in target_clean_dict.items():
        if is_aggregate_account(raw_target):
            continue
        if src_clean == clean_target:
            return raw_target, "🎯 순수일치"

    # 정밀 부분 포함
    if len(src_clean) >= 3:
        for raw_target, clean_target in target_clean_dict.items():
            if is_aggregate_account(raw_target):
                continue
            if len(clean_target) >= 3:
                if src_clean in clean_target or clean_target in src_clean:
                    return raw_target, "🔍 정밀포함"

    # 엄격 유사도
    valid_targets = [raw for raw in target_options if raw != "(매칭 제외)" and not is_aggregate_account(raw)]
    valid_clean_map = {target_clean_dict[raw]: raw for raw in valid_targets if target_clean_dict.get(raw)}
    
    matches = difflib.get_close_matches(src_clean, list(valid_clean_map.keys()), n=1, cutoff=0.75)
    if matches:
        return valid_clean_map[matches[0]], "🤖 정밀추천"
                
    return "(매칭 제외)", "미매칭"

# ==========================================
# 4. 스마트 공식 총계 추출 함수 (중복 합산 방지)
# ==========================================
def extract_smart_grand_total(df, name_col, amt_col):
    """
    엑셀 시트에서 '자금수입총계', '자금지출총계', '총계' 등 공식 총계 행을 지능적으로 탐색.
    발견 시 해당 행의 금액과 행 이름을 반환하고,
    총계 행이 없으면 소계/합계를 제외한 순수 세부 계정의 합계를 산출.
    """
    if df is None or df.empty or name_col not in df.columns or amt_col not in df.columns:
        return 0.0, "데이터 없음"
        
    temp = df.dropna(subset=[name_col]).copy()
    temp[name_col] = temp[name_col].astype(str).str.strip()
    temp['__amt_clean'] = temp[amt_col].apply(clean_number)
    
    # 1순위: '자금수입총계', '자금지출총계', '수입총계', '지출총계' 등 명확한 총계 행 탐색
    primary_patterns = [r'자금수입총계', r'자금지출총계', r'수입총계', r'지출총계', r'총\s*계', r'합\s*계']
    for pat in primary_patterns:
        matched = temp[temp[name_col].str.contains(pat, regex=True, na=False)]
        if not matched.empty:
            # 0이 아닌 유효 금액을 가진 마지막 총계 행 선택
            valid_rows = matched[matched['__amt_clean'] > 0]
            if not valid_rows.empty:
                chosen = valid_rows.iloc[-1]
                return float(chosen['__amt_clean']), chosen[name_col]
            else:
                chosen = matched.iloc[-1]
                return float(chosen['__amt_clean']), chosen[name_col]

    # 2순위: 총계 행이 따로 명시되지 않은 경우, 소계/합계를 제외한 순수 세부 계정만의 합산
    exclude_pattern = '|'.join(EXCLUDE_KEYWORDS)
    pure_details = temp[~temp[name_col].str.contains(exclude_pattern, regex=True, na=False)]
    pure_sum = pure_details['__amt_clean'].sum()
    return float(pure_sum), "세부계정 순합계"

# ==========================================
# 5. 사이드바: 프로젝트 관리
# ==========================================
with st.sidebar:
    st.header("📂 프로젝트 관리")
    
    with st.expander("➕ 새 프로젝트 생성", expanded=False):
        new_proj_name = st.text_input("프로젝트 이름 입력", placeholder="예: 2025 본결산 (등록금)")
        if st.button("프로젝트 등록", use_container_width=True, type="primary"):
            if new_proj_name.strip():
                if create_project(new_proj_name.strip()):
                    st.success("프로젝트가 생성되었습니다!")
                    st.rerun()
                else:
                    st.error("이미 존재하는 이름입니다.")
            else:
                st.warning("이름을 입력해 주세요.")
                
    projects_df = get_projects()
    
    if not projects_df.empty:
        project_names = projects_df['name'].tolist()
        selected_project_name = st.selectbox("📋 작업 대상 프로젝트", project_names)
        current_project = projects_df[projects_df['name'] == selected_project_name].iloc[0]
        curr_project_id = int(current_project['id'])
        st.caption(f"생성일시: {current_project['created_at']}")
        
        st.divider()
        if st.button("🗑️ 선택된 프로젝트 삭제", type="secondary", use_container_width=True):
            delete_project(curr_project_id)
            st.warning("프로젝트가 삭제되었습니다.")
            st.rerun()
    else:
        selected_project_name = None
        curr_project_id = None
        st.info("새 프로젝트를 먼저 등록해 주세요.")

# ==========================================
# 6. 메인 화면 로직
# ==========================================
if not selected_project_name:
    st.title("⚡ 데이터 스마트 검증기")
    st.info("👈 왼쪽 사이드바를 열어 프로젝트를 생성하거나 선택해 주세요.")
    st.stop()

workspace_state = get_workspace(curr_project_id)

if "selected_inspect_item" not in st.session_state:
    st.session_state.selected_inspect_item = None

# 탑 헤더 바
h_col1, h_col2 = st.columns([4, 1])
with h_col1:
    st.title("⚡ 스마트 결산 대조 룸 (Reconciliation Room)")
    st.caption(f"📌 현재 활성 프로젝트: **{selected_project_name}** | 양측 결산서를 실시간 브릿지로 대조하고 차액을 진단합니다.")
with h_col2:
    if st.button("🔄 데이터 초기화", use_container_width=True):
        reset_workspace_data(curr_project_id)
        st.session_state.selected_inspect_item = None
        st.success("데이터가 초기화되었습니다.")
        st.rerun()

# ----------------------------------------------------
# 1단계: 엑셀 파일 업로드 및 시트 지정
# ----------------------------------------------------
with st.expander("📁 1단계: 대조 파일 업로드 및 대상 시트 설정", expanded=(workspace_state["source_data"] is None or workspace_state["target_data"] is None)):
    lbl_c1, lbl_c2 = st.columns(2)
    with lbl_c1:
        left_label_input = st.text_input("기준 파일 라벨", value=workspace_state["left_label"], key=f"left_lbl_{curr_project_id}")
    with lbl_c2:
        right_label_input = st.text_input("대조 파일 라벨", value=workspace_state["right_label"], key=f"right_lbl_{curr_project_id}")

    if (left_label_input != workspace_state["left_label"]) or (right_label_input != workspace_state["right_label"]):
        update_workspace(curr_project_id, left_label_input, right_label_input, workspace_state["source_data"], workspace_state["target_data"])
        st.rerun()

    f_col1, f_col2 = st.columns(2)
    source_df = workspace_state["source_data"]
    target_df = workspace_state["target_data"]

    with f_col1:
        st.markdown(f"**🏫 {left_label_input} (.xlsx)**")
        school_file = st.file_uploader(f"{left_label_input} 파일", type=["xlsx"], key=f"s_file_{curr_project_id}")
        if school_file:
            try:
                xl_s = pd.ExcelFile(school_file)
                s_sheet = st.selectbox(f"{left_label_input} 대상 시트", xl_s.sheet_names, key=f"s_sheet_{curr_project_id}")
                if s_sheet:
                    source_df = pd.read_excel(school_file, sheet_name=s_sheet)
                    update_workspace(curr_project_id, left_label_input, right_label_input, source_df, target_df)
                    st.success(f"{left_label_input} 로드 완료 ({len(source_df)}행)")
            except Exception as e:
                st.error(f"오류: {e}")
        elif source_df is not None:
            st.info(f"💾 저장된 {left_label_input} 데이터 유지 중 ({len(source_df)}행)")

    with f_col2:
        st.markdown(f"**🏛️ {right_label_input} (.xlsx)**")
        found_file = st.file_uploader(f"{right_label_input} 파일", type=["xlsx"], key=f"t_file_{curr_project_id}")
        if found_file:
            try:
                xl_t = pd.ExcelFile(found_file)
                t_sheet = st.selectbox(f"{right_label_input} 대상 시트", xl_t.sheet_names, key=f"t_sheet_{curr_project_id}")
                if t_sheet:
                    target_df = pd.read_excel(found_file, sheet_name=t_sheet)
                    update_workspace(curr_project_id, left_label_input, right_label_input, source_df, target_df)
                    st.success(f"{right_label_input} 로드 완료 ({len(target_df)}행)")
            except Exception as e:
                st.error(f"오류: {e}")
        elif target_df is not None:
            st.info(f"💾 저장된 {right_label_input} 데이터 유지 중 ({len(target_df)}행)")

if source_df is None or target_df is None:
    st.info("💡 상단의 1단계 카드에서 두 엑셀 파일을 업로드해 주시면 스마트 대조 룸이 열립니다.")
    st.stop()

# ----------------------------------------------------
# 2단계: 대조 열(과목명 및 금액) 설정
# ----------------------------------------------------
with st.expander("⚙️ 2단계: 대조 열(과목명 및 금액) 설정", expanded=False):
    col_c1, col_c2 = st.columns(2)
    source_cols = list(source_df.columns)
    target_cols = list(target_df.columns)
    with col_c1:
        s_name_col = st.selectbox(f"{left_label_input} 항목명 열", source_cols, index=0)
    with col_c2:
        t_name_col = st.selectbox(f"{right_label_input} 항목명 열", target_cols, index=0)

    ac1, ac2 = st.columns(2)
    with ac1:
        s_amt = st.selectbox(f"비교할 금액 열 ({left_label_input})", source_cols, index=min(2, len(source_cols)-1))
    with ac2:
        t_amt = st.selectbox(f"비교할 금액 열 ({right_label_input})", target_cols, index=min(2, len(target_cols)-1))

# ----------------------------------------------------
# 3단계: 정밀 총계 산출 및 데이터 매칭
# ----------------------------------------------------
s_df_clean = source_df.dropna(subset=[s_name_col]).copy()
t_df_clean = target_df.dropna(subset=[t_name_col]).copy()

s_df_clean[s_name_col] = s_df_clean[s_name_col].astype(str).str.strip()
t_df_clean[t_name_col] = t_df_clean[t_name_col].astype(str).str.strip()
s_df_clean[s_amt] = s_df_clean[s_amt].apply(clean_number)
t_df_clean[t_amt] = t_df_clean[t_amt].apply(clean_number)

# ★ 핵심 개선: 엑셀 파일 내 실제 '공식 총계' 추출 (중복 합산 원천 차단)
official_s_total, s_total_source_name = extract_smart_grand_total(s_df_clean, s_name_col, s_amt)
official_t_total, t_total_source_name = extract_smart_grand_total(t_df_clean, t_name_col, t_amt)
grand_diff = official_s_total - official_t_total

# 재단 항목별 합산 룩업 생성
target_sum_lookup = {}
for t_name, grp in t_df_clean.groupby(t_name_col):
    target_sum_lookup[str(t_name).strip()] = grp[t_amt].sum()

raw_target_list = sorted([str(x).strip() for x in t_df_clean[t_name_col].unique() if str(x).strip()])
target_clean_dict = {raw_name: clean_account_name(raw_name) for raw_name in raw_target_list}
target_options = ["(매칭 제외)"] + raw_target_list

saved_history = get_saved_mappings()
# 세부 계정만 추출 (상위 집계 행은 브릿지 목록에서 배제하여 오매칭 방지)
unique_source_items = sorted([str(x).strip() for x in s_df_clean[s_name_col].unique() if str(x).strip() and not is_aggregate_account(str(x))])

# 매칭 결과 구성
matched_rows = []
for s_name in unique_source_items:
    state_key = f"match_override_{curr_project_id}_{re.sub(r'[^a-zA-Z0-9가-힣]', '_', s_name)}"
    if state_key in st.session_state:
        selected_match = st.session_state[state_key]
        status_text = "✏️ 수동지정"
    else:
        selected_match, status_text = find_smart_match(s_name, target_options, target_clean_dict, saved_history)

    s_val = s_df_clean[s_df_clean[s_name_col] == s_name][s_amt].sum()
    
    if not selected_match or selected_match == "(매칭 제외)":
        t_val = 0.0
        diff = s_val
        val_status = "⚠️ 미매칭"
    else:
        t_val = target_sum_lookup.get(selected_match, 0.0)
        diff = s_val - t_val
        val_status = "❌ 차액 발생" if abs(diff) > 0.01 else "✅ 정상 일치"

    matched_rows.append({
        "source_name": s_name,
        "source_val": s_val,
        "target_name": selected_match,
        "target_val": t_val,
        "diff": diff,
        "val_status": val_status,
        "match_type": status_text
    })

res_df = pd.DataFrame(matched_rows)

# ----------------------------------------------------
# 4단계: 상단 정합성 배너 & 통계 카드
# ----------------------------------------------------
total_items = len(res_df)
match_items = len(res_df[res_df["val_status"] == "✅ 정상 일치"])
error_items = len(res_df[res_df["val_status"] == "❌ 차액 발생"])
unmatched_items = len(res_df[res_df["val_status"] == "⚠️ 미매칭"])

# 총계 출처가 명시된 자금 정합성 배너
border_color = "#059669" if abs(grand_diff) < 1 else "#DC2626"
diff_summary_text = "총계 완벽 일치 (0원)" if abs(grand_diff) < 1 else f"총계 차액: {grand_diff:+,.0f} 원"

st.markdown(f"""
<div class="kpi-card" style="margin-bottom: 20px; border-left: 6px solid {border_color};">
    <div style="font-size: 13px; font-weight: 600; color: #64748B;">자금 결산 정합성 현황 (시트 내 공식 총계 행 기반)</div>
    <div style="font-size: 17px; font-weight: 700; color: #0F172A; margin-top: 6px;">
        {left_label_input} 총계: <b style="color:#1E40AF;">{official_s_total:,.0f} 원</b> 
        <span style="font-size:12px; color:#64748B; font-weight:normal;">(출처: {s_total_source_name})</span>
        &nbsp;↔&nbsp; 
        {right_label_input} 총계: <b style="color:#6D28D9;">{official_t_total:,.0f} 원</b> 
        <span style="font-size:12px; color:#64748B; font-weight:normal;">(출처: {t_total_source_name})</span>
        &nbsp;
        <span style="color: {border_color}; font-size: 15px;">
            [ {diff_summary_text} ]
        </span>
    </div>
</div>
""", unsafe_allow_html=True)

# 4개 통계 카드
m1, m2, m3, m4 = st.columns(4)
m1.markdown(f"""<div class="kpi-card"><div style="color: #64748B; font-size:12px; font-weight:600;">세부 검증 항목</div><div class="kpi-val" style="color: #0F172A;">{total_items}건</div></div>""", unsafe_allow_html=True)
m2.markdown(f"""<div class="kpi-card" style="border-color: #A7F3D0; background-color: #F0FDF4;"><div style="color: #059669; font-size:12px; font-weight:600;">정상 일치</div><div class="kpi-val" style="color: #059669;">{match_items}건 <span style="font-size:13px;">({(match_items/total_items*100 if total_items else 0):.1f}%)</span></div></div>""", unsafe_allow_html=True)
m3.markdown(f"""<div class="kpi-card" style="border-color: #FECACA; background-color: #FEF2F2;"><div style="color: #DC2626; font-size:12px; font-weight:600;">차액 오류(확인필요)</div><div class="kpi-val" style="color: #DC2626;">{error_items}건</div></div>""", unsafe_allow_html=True)
m4.markdown(f"""<div class="kpi-card" style="border-color: #FDE68A; background-color: #FFFBEB;"><div style="color: #D97706; font-size:12px; font-weight:600;">미매칭 항목</div><div class="kpi-val" style="color: #D97706;">{unmatched_items}건</div></div>""", unsafe_allow_html=True)

st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

# ----------------------------------------------------
# 5단계: 3분할 스마트 매칭 브릿지 대조 룸 (메인 뷰)
# ----------------------------------------------------
view_ctrl1, view_ctrl2 = st.columns([2, 1])
with view_ctrl1:
    filter_choice = st.radio("표시 필터", ["전체 항목", "❌ 차액 오류만 집중 검토", "⚠️ 미매칭 항목만 보기"], horizontal=True)
with view_ctrl2:
    search_keyword = st.text_input("🔍 계정명 빠른 검색", placeholder="예: 수업료, 예수금...")

filtered_df = res_df.copy()
if filter_choice == "❌ 차액 오류만 집중 검토":
    filtered_df = filtered_df[filtered_df["val_status"] == "❌ 차액 발생"]
elif filter_choice == "⚠️ 미매칭 항목만 보기":
    filtered_df = filtered_df[filtered_df["val_status"] == "⚠️ 미매칭"]

if search_keyword.strip():
    kw = search_keyword.strip()
    filtered_df = filtered_df[filtered_df["source_name"].str.contains(kw) | filtered_df["target_name"].str.contains(kw)]

# 대조 룸 헤더 3열
b_col1, b_col2, b_col3 = st.columns([1.2, 1.6, 1.2])
with b_col1:
    st.markdown(f"#### 🏫 {left_label_input} (기준 원장)")
    st.caption("계정명 및 결산액")
with b_col2:
    st.markdown("#### ⚡ 스마트 매칭 & 차액 브릿지")
    st.caption("실시간 오차 계산 및 1클릭 변경")
with b_col3:
    st.markdown(f"#### 🏛️ {right_label_input} (대조 원장)")
    st.caption("매칭 계정 및 재단 합산액")

st.markdown("<hr style='margin-top: 2px; margin-bottom: 12px; border-color: #E2E8F0;'>", unsafe_allow_html=True)

# 브릿지 행 리스트 렌더링
selected_row_data = None

for idx, r in filtered_df.iterrows():
    s_name = r["source_name"]
    s_val = r["source_val"]
    t_name = r["target_name"]
    t_val = r["target_val"]
    diff = r["diff"]
    v_status = r["val_status"]
    
    is_selected = (st.session_state.selected_inspect_item == s_name)
    if is_selected:
        selected_row_data = r
        
    c1, c2, c3 = st.columns([1.2, 1.6, 1.2])
    
    # 1열: 학교 결산 카드
    with c1:
        sel_class = "panel-selected" if is_selected else ""
        st.markdown(f"""
        <div class="panel-box {sel_class}">
            <div style="font-weight: 700; color: #1E293B; font-size: 14px;">{s_name}</div>
            <div style="font-size: 12px; color: #64748B; margin-top: 4px;">결산: <b>{s_val:,.0f}</b> 원</div>
        </div>
        """, unsafe_allow_html=True)

    # 2열: 중앙 실시간 브릿지 (차액 & 변경)
    with c2:
        bridge_style = "bridge-match" if v_status == "✅ 정상 일치" else ("bridge-error" if v_status == "❌ 차액 발생" else "bridge-unmatched")
        diff_color = "#059669" if v_status == "✅ 정상 일치" else ("#DC2626" if v_status == "❌ 차액 발생" else "#D97706")
        diff_text = "0 원 (완벽 일치)" if abs(diff) < 0.01 else f"차액: {diff:+,.0f} 원"

        bc_sub1, bc_sub2 = st.columns([2.2, 1])
        with bc_sub1:
            st.markdown(f"""
            <div class="panel-box {bridge_style}">
                <div style="font-weight: 700; font-size: 13.5px; color: {diff_color};">{diff_text}</div>
                <div style="font-size: 11.5px; color: #475569; margin-top: 4px;">상태: {v_status} <span class="badge" style="background:#E2E8F0; color:#334155;">{r['match_type']}</span></div>
            </div>
            """, unsafe_allow_html=True)
        with bc_sub2:
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            if v_status != "✅ 정상 일치":
                if st.button("🔍 진단", key=f"btn_inspect_{idx}", use_container_width=True, type="primary"):
                    st.session_state.selected_inspect_item = s_name
                    st.rerun()
            else:
                if st.button("상세", key=f"btn_inspect_{idx}", use_container_width=True):
                    st.session_state.selected_inspect_item = s_name
                    st.rerun()

    # 3열: 재단 양식 카드
    with c3:
        sel_class = "panel-selected" if is_selected else ""
        t_display_name = t_name if t_name != "(매칭 제외)" else "<span style='color:#D97706;'>(매칭 제외)</span>"
        st.markdown(f"""
        <div class="panel-box {sel_class}">
            <div style="font-weight: 700; color: #6D28D9; font-size: 14px;">{t_display_name}</div>
            <div style="font-size: 12px; color: #64748B; margin-top: 4px;">재단: <b>{t_val:,.0f}</b> 원</div>
        </div>
        """, unsafe_allow_html=True)

# ----------------------------------------------------
# 6단계: 하단 스마트 인스펙터 (오류 원인 자동 진단 & 1클릭 해결)
# ----------------------------------------------------
if selected_row_data is not None:
    s_curr = selected_row_data["source_name"]
    t_curr = selected_row_data["target_name"]
    diff_curr = selected_row_data["diff"]
    s_amt_val = selected_row_data["source_val"]
    
    st.markdown(f"""
    <div class="inspector-box">
        <div style="font-size: 16px; font-weight: 700; color: #DC2626; margin-bottom: 12px;">
            🔍 [원인 진단 & 1클릭 해결 패널]  선택 항목: {s_curr} (차액: {diff_curr:+,.0f} 원)
        </div>
    """, unsafe_allow_html=True)
    
    insp1, insp2, insp3 = st.columns([1.1, 1.4, 1.2])
    
    # 1열: 자동 문제 원인 진단
    with insp1:
        st.markdown("##### 1. 문제 원인 자동 진단")
        if is_aggregate_account(t_curr):
            st.error(f"• 현재 매칭된 **[{t_curr}]**은 상위 집계(관/항/총계) 항목입니다.")
            st.caption("상위 합계 금액이 통째로 잡혀 차액이 크게 발생했습니다. 세부 계정(목)으로 교체가 필요합니다.")
        elif t_curr == "(매칭 제외)":
            st.warning("• 현재 매칭된 재단 계정이 없습니다.")
            st.caption(f"{left_label_input}에 결산액({s_amt_val:,.0f}원)이 존재하므로 대응되는 재단 계정을 짝지어 주어야 합니다.")
        else:
            st.info(f"• 계정명은 유사하나 금액이 {abs(diff_curr):,.0f}원 일치하지 않습니다.")
            st.caption("양측 회계 처리 기준 차이 또는 다른 세부 계정과의 분할 입력을 확인하세요.")

    # 2열: AI/스마트 추천 (차액 0원 되는 계정 탐색)
    with insp2:
        st.markdown("##### 2. AI 추천 최적 재단 계정")
        zero_diff_candidates = []
        for raw_t, sum_val in target_sum_lookup.items():
            if not is_aggregate_account(raw_t) and abs(sum_val - s_amt_val) < 1:
                zero_diff_candidates.append(raw_t)

        if zero_diff_candidates:
            best_t = zero_diff_candidates[0]
            st.success(f"👉 **추천 1순위: [{best_t}]**")
            st.caption(f"재단 결산액이 **{s_amt_val:,.0f}원**으로 학교 금액과 100% 일치합니다! (오차 0원)")
            if st.button("✨ 추천 1순위로 즉시 1클릭 변경 적용", key="btn_apply_best", type="primary", use_container_width=True):
                safe_key = f"match_override_{curr_project_id}_{re.sub(r'[^a-zA-Z0-9가-힣]', '_', s_curr)}"
                st.session_state[safe_key] = best_t
                save_single_mapping(s_curr, best_t)
                st.success("즉시 변경 및 DB 저장이 완료되었습니다!")
                st.rerun()
        else:
            clean_s = clean_account_name(s_curr)
            valid_targets = [t for t in raw_target_list if not is_aggregate_account(t)]
            fuzzy_cands = difflib.get_close_matches(clean_s, [clean_account_name(t) for t in valid_targets], n=2, cutoff=0.3)
            if fuzzy_cands:
                match_raw = [t for t in valid_targets if clean_account_name(t) == fuzzy_cands[0]][0]
                cand_val = target_sum_lookup.get(match_raw, 0.0)
                st.info(f"유사 계정 추천: **[{match_raw}]** (재단액: {cand_val:,.0f}원)")
                if st.button(f"[{match_raw}] 계정으로 변경 적용", key="btn_apply_fuzzy", use_container_width=True):
                    safe_key = f"match_override_{curr_project_id}_{re.sub(r'[^a-zA-Z0-9가-힣]', '_', s_curr)}"
                    st.session_state[safe_key] = match_raw
                    save_single_mapping(s_curr, match_raw)
                    st.success("변경 적용 완료!")
                    st.rerun()
            else:
                st.caption("자동 추천 후보가 없습니다. 3번에서 직접 선택해 주세요.")

    # 3열: 수동 검색 및 매칭 확정
    with insp3:
        st.markdown("##### 3. 수동 검색 및 확정")
        def_idx = target_options.index(t_curr) if t_curr in target_options else 0
        manual_pick = st.selectbox("재단 계정 직접 선택", target_options, index=def_idx, key="manual_pick_inspect")
        
        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            if st.button("💾 매칭 확정", use_container_width=True, type="primary"):
                safe_key = f"match_override_{curr_project_id}_{re.sub(r'[^a-zA-Z0-9가-힣]', '_', s_curr)}"
                st.session_state[safe_key] = manual_pick
                save_single_mapping(s_curr, manual_pick)
                st.success("저장 완료!")
                st.rerun()
        with btn_c2:
            if st.button("🚫 매칭 제외", use_container_width=True):
                safe_key = f"match_override_{curr_project_id}_{re.sub(r'[^a-zA-Z0-9가-힣]', '_', s_curr)}"
                st.session_state[safe_key] = "(매칭 제외)"
                st.info("제외 처리되었습니다.")
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# ----------------------------------------------------
# 7단계: 결과 엑셀 다운로드
# ----------------------------------------------------
st.divider()

export_df = pd.DataFrame([
    {
        f"{left_label_input} 항목명": r["source_name"],
        f"{left_label_input} 결산액": r["source_val"],
        f"매칭 {right_label_input} 항목명": r["target_name"],
        f"{right_label_input} 결산액": r["target_val"],
        "차액": r["diff"],
        "검증 상태": r["val_status"]
    }
    for _, r in res_df.iterrows()
])

excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
    export_df.to_excel(writer, index=False, sheet_name="검증결과리포트")
excel_buffer.seek(0)

file_name = f"결산검증_{selected_project_name}_{datetime.now().strftime('%Y%m%d')}.xlsx"

st.download_button(
    label="📥 최종 검증 결과 엑셀(.xlsx) 리포트 다운로드",
    data=excel_buffer,
    file_name=file_name,
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary",
    use_container_width=True
)
