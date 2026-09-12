import streamlit as st
import pandas as pd
import sqlite3
import io
import difflib
import re
import json
from datetime import datetime

# ==========================================
# 1. 페이지 기본 설정 및 엑셀 그리드 전용 스타일
# ==========================================
st.set_page_config(
    page_title="데이터 스마트 검증기",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stApp {
        background-color: #F8FAFC;
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
# 2. SQLite 데이터베이스 초기화 및 설정 테이블 확장
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
    
    cursor.execute("PRAGMA table_info(project_workspaces)")
    cols = [c[1] for c in cursor.fetchall()]
    for col_name, col_type in [
        ("source_raw_blob", "BLOB"),
        ("target_raw_blob", "BLOB"),
        ("source_sheet_name", "TEXT"),
        ("target_sheet_name", "TEXT"),
        ("settings_json", "TEXT")
    ]:
        if col_name not in cols:
            try:
                cursor.execute(f"ALTER TABLE project_workspaces ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass

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
    return {
        "left_label": "학교 양식", "right_label": "재단 양식",
        "source_raw_blob": None, "target_raw_blob": None,
        "source_sheet_name": None, "target_sheet_name": None,
        "settings": {}
    }

def update_workspace_file_blob(project_id, side, file_bytes, default_sheet=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    blob_col = "source_raw_blob" if side == "source" else "target_raw_blob"
    sheet_col = "source_sheet_name" if side == "source" else "target_sheet_name"
    
    if default_sheet:
        cursor.execute(f"""
            UPDATE project_workspaces 
            SET {blob_col} = ?, {sheet_col} = ?, updated_at = ?
            WHERE project_id = ?
        """, (file_bytes, default_sheet, now, project_id))
    else:
        cursor.execute(f"""
            UPDATE project_workspaces 
            SET {blob_col} = ?, updated_at = ?
            WHERE project_id = ?
        """, (file_bytes, now, project_id))
    conn.commit()
    conn.close()

def update_workspace_sheet_choice(project_id, side, sheet_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    col_name = "source_sheet_name" if side == "source" else "target_sheet_name"
    cursor.execute(f"""
        UPDATE project_workspaces 
        SET {col_name} = ?, updated_at = ?
        WHERE project_id = ?
    """, (sheet_name, now, project_id))
    conn.commit()
    conn.close()

def update_workspace_labels(project_id, left_label, right_label):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        UPDATE project_workspaces 
        SET left_label = ?, right_label = ?, updated_at = ?
        WHERE project_id = ?
    """, (left_label, right_label, now, project_id))
    conn.commit()
    conn.close()

def save_workspace_settings(project_id, settings_dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    s_str = json.dumps(settings_dict, ensure_ascii=False)
    cursor.execute("""
        UPDATE project_workspaces
        SET settings_json = ?, updated_at = ?
        WHERE project_id = ?
    """, (s_str, now, project_id))
    conn.commit()
    conn.close()

def reset_workspace_data(project_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        UPDATE project_workspaces 
        SET source_raw_blob = NULL, target_raw_blob = NULL, 
            source_sheet_name = NULL, target_sheet_name = NULL, 
            settings_json = '{}', updated_at = ? 
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
        
    for raw_target, clean_target in target_clean_dict.items():
        if is_aggregate_account(raw_target):
            continue
        if src_clean == clean_target:
            return raw_target, "🎯 순수일치"

    if len(src_clean) >= 3:
        for raw_target, clean_target in target_clean_dict.items():
            if is_aggregate_account(raw_target):
                continue
            if len(clean_target) >= 3:
                if src_clean in clean_target or clean_target in src_clean:
                    return raw_target, "🔍 정밀포함"

    valid_targets = [raw for raw in target_options if raw != "(매칭 제외)" and not is_aggregate_account(raw)]
    valid_clean_map = {target_clean_dict[raw]: raw for raw in valid_targets if target_clean_dict.get(raw)}
    
    matches = difflib.get_close_matches(src_clean, list(valid_clean_map.keys()), n=1, cutoff=0.75)
    if matches:
        return valid_clean_map[matches[0]], "🤖 정밀추천"
                
    return "(매칭 제외)", "미매칭"

# ==========================================
# 4. 스마트 공식 총계 추출 및 후보 탐색 함수
# ==========================================
def get_all_row_candidates(df, name_col):
    if df is None or df.empty or name_col not in df.columns:
        return ["(자동 감지)"]
    
    all_names = [str(x).strip() for x in df[name_col].dropna().unique() if str(x).strip()]
    pats = [r'자금수입총계', r'자금지출총계', r'수입총계', r'지출총계', r'총\s*계', r'합\s*계', r'수입합계', r'지출합계', r'계']
    priority_pattern = re.compile('|'.join(pats))
    
    priority_rows = []
    normal_rows = []
    for name in all_names:
        if priority_pattern.search(name):
            priority_rows.append(name)
        else:
            normal_rows.append(name)
            
    return ["(자동 감지)"] + sorted(priority_rows) + sorted(normal_rows)

def extract_smart_grand_total(df, name_col, amt_col, target_total_type="수입", forced_row=None):
    if df is None or df.empty or name_col not in df.columns or amt_col not in df.columns:
        return 0.0, "데이터 없음"
        
    temp = df.dropna(subset=[name_col]).copy()
    temp[name_col] = temp[name_col].astype(str).str.strip()
    temp['__amt_clean'] = temp[amt_col].apply(clean_number)
    
    if forced_row and forced_row != "(자동 감지)":
        matched = temp[temp[name_col] == forced_row]
        if not matched.empty:
            return float(matched.iloc[-1]['__amt_clean']), forced_row

    if "수입" in target_total_type:
        patterns = [r'자금수입총계', r'자금수입\s*총계', r'수입총계', r'수입\s*총계', r'수입합계', r'총\s*계']
    elif "지출" in target_total_type:
        patterns = [r'자금지출총계', r'자금지출\s*총계', r'지출총계', r'지출\s*총계', r'지출합계', r'총\s*계']
    else:
        patterns = [r'자금수입총계', r'자금지출총계', r'수입총계', r'지출총계', r'총\s*계']
        
    for pat in patterns:
        matched = temp[temp[name_col].str.contains(pat, regex=True, na=False)]
        valid_rows = matched[matched['__amt_clean'] > 0]
        if not valid_rows.empty:
            chosen = valid_rows.iloc[-1]
            return float(chosen['__amt_clean']), chosen[name_col]

    exclude_pattern = '|'.join(EXCLUDE_KEYWORDS)
    pure_details = temp[~temp[name_col].str.contains(exclude_pattern, regex=True, na=False)]
    
    if "수입" in target_total_type:
        s_income = pure_details[pure_details[name_col].str.contains(r'^(5\d{3}|수입)', regex=True, na=False)]
        if not s_income.empty and s_income['__amt_clean'].sum() > 0:
            return float(s_income['__amt_clean'].sum()), "수입계정(5천번대) 순합계"
    elif "지출" in target_total_type:
        s_expense = pure_details[pure_details[name_col].str.contains(r'^(4\d{3}|지출)', regex=True, na=False)]
        if not s_expense.empty and s_expense['__amt_clean'].sum() > 0:
            return float(s_expense['__amt_clean'].sum()), "지출계정(4천번대) 순합계"

    pure_sum = pure_details['__amt_clean'].sum()
    return float(pure_sum), "세부계정 순합계"

# ==========================================
# 5. 사이드바: 나열형 프로젝트 리스트
# ==========================================
projects_df = get_projects()

with st.sidebar:
    st.markdown("#### 📂 프로젝트 목록")
    
    with st.expander("➕ 새 프로젝트 추가", expanded=False):
        new_proj_name = st.text_input("새 프로젝트명", placeholder="예: 2025 본결산", key="new_proj_input_side")
        if st.button("추가", use_container_width=True, type="primary"):
            if new_proj_name.strip():
                if create_project(new_proj_name.strip()):
                    st.query_params["project"] = new_proj_name.strip()
                    st.success("추가되었습니다!")
                    st.rerun()
                else:
                    st.error("이미 존재하는 프로젝트입니다.")
            else:
                st.warning("이름을 입력해 주세요.")
                
    st.markdown("<div style='height: 6px;'></div>", unsafe_allow_html=True)
    
    if not projects_df.empty:
        project_names = projects_df['name'].tolist()
        url_proj = st.query_params.get("project", None)
        if url_proj not in project_names:
            url_proj = project_names[0]
            st.query_params["project"] = url_proj
            
        selected_project_name = url_proj
        selected_row = projects_df[projects_df['name'] == selected_project_name].iloc[0]
        curr_project_id = int(selected_row['id'])

        for _, p_row in projects_df.iterrows():
            p_id = int(p_row['id'])
            p_name = p_row['name']
            is_active = (p_name == selected_project_name)
            
            p_col1, p_col2 = st.columns([4, 1])
            with p_col1:
                btn_type = "primary" if is_active else "secondary"
                prefix = "✓ " if is_active else "• "
                if st.button(f"{prefix}{p_name}", key=f"sel_proj_{p_id}", type=btn_type, use_container_width=True):
                    st.query_params["project"] = p_name
                    st.rerun()
                    
            with p_col2:
                with st.popover("✏️", help="프로젝트명 수정 및 삭제"):
                    st.markdown(f"**[{p_name}] 관리**")
                    new_pname = st.text_input("새 이름", value=p_name, key=f"inline_rename_{p_id}")
                    if st.button("이름 저장", key=f"btn_save_rename_{p_id}", use_container_width=True):
                        clean_name = new_pname.strip()
                        if clean_name and clean_name != p_name:
                            if rename_project(p_id, clean_name):
                                if is_active:
                                    st.query_params["project"] = clean_name
                                st.success("변경 완료!")
                                st.rerun()
                            else:
                                st.error("중복된 이름입니다.")
                    
                    st.markdown("<hr style='margin: 8px 0;'>", unsafe_allow_html=True)
                    if st.button("🗑️ 프로젝트 삭제", key=f"btn_del_{p_id}", type="secondary", use_container_width=True):
                        delete_project(p_id)
                        if is_active and "project" in st.query_params:
                            del st.query_params["project"]
                        st.warning("삭제되었습니다.")
                        st.rerun()
    else:
        selected_project_name = None
        curr_project_id = None
        st.info("새 프로젝트를 먼저 추가해 주세요.")

# ==========================================
# 6. 메인 화면 로직
# ==========================================
if not selected_project_name:
    st.markdown('<div class="main-app-title">📊 데이터 스마트 검증기</div>', unsafe_allow_html=True)
    st.info("👈 왼쪽 사이드바에서 새 프로젝트를 추가해 주세요.")
    st.stop()

workspace_files = get_workspace_files(curr_project_id)
saved_settings = workspace_files.get("settings", {})

h_col1, h_col2 = st.columns([4, 1])
with h_col1:
    st.markdown('<div class="main-app-title">📊 데이터 스마트 검증기</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="main-app-caption">📌 현재 프로젝트: <b>{selected_project_name}</b> | 양쪽 파일의 대상 시트를 자유롭게 선택해 검증할 수 있습니다.</div>', unsafe_allow_html=True)
with h_col2:
    if st.button("🔄 데이터 초기화", use_container_width=True):
        reset_workspace_data(curr_project_id)
        for k in list(st.session_state.keys()):
            if k.startswith(f"match_override_{curr_project_id}_"):
                del st.session_state[k]
        st.success("데이터가 초기화되었습니다.")
        st.rerun()

# ----------------------------------------------------
# 1단계: 엑셀 파일 업로드 및 상시 대상 시트 선택 (충돌 완벽 제거)
# ----------------------------------------------------
source_blob = workspace_files["source_raw_blob"]
target_blob = workspace_files["target_raw_blob"]
source_df = None
target_df = None

with st.expander("📁 1단계: 대조 파일 업로드 및 대상 시트 선택 (양쪽 모두 상시 변경 가능)", expanded=(source_blob is None or target_blob is None)):
    lbl_c1, lbl_c2 = st.columns(2)
    with lbl_c1:
        left_label_input = st.text_input("기준 파일 라벨", value=workspace_files["left_label"], key=f"left_lbl_{curr_project_id}")
    with lbl_c2:
        right_label_input = st.text_input("대조 파일 라벨", value=workspace_files["right_label"], key=f"right_lbl_{curr_project_id}")

    if (left_label_input != workspace_files["left_label"]) or (right_label_input != workspace_files["right_label"]):
        update_workspace_labels(curr_project_id, left_label_input, right_label_input)
        st.rerun()

    f_col1, f_col2 = st.columns(2)

    # 1) 기준 파일 (학교 양식)
    with f_col1:
        st.markdown(f"**🏫 {left_label_input} 파일**")
        new_s_file = st.file_uploader(f"{left_label_input} 등록 (.xlsx, .xls)", type=["xlsx", "xls"], key=f"s_uploader_{curr_project_id}")
        if new_s_file is not None:
            bytes_val = new_s_file.getvalue()
            # 파일이 변경되었을 때만 저장
            if source_blob != bytes_val:
                try:
                    xl_test = pd.ExcelFile(io.BytesIO(bytes_val))
                    init_sheet = xl_test.sheet_names[0]
                    update_workspace_file_blob(curr_project_id, "source", bytes_val, default_sheet=init_sheet)
                    st.rerun()
                except Exception as e:
                    st.error(f"엑셀 파일 읽기 실패: {e}")

        if source_blob is not None:
            try:
                xl_s = pd.ExcelFile(io.BytesIO(source_blob))
                s_sheet_names = xl_s.sheet_names
                cur_s_sheet = workspace_files.get("source_sheet_name")
                s_idx = s_sheet_names.index(cur_s_sheet) if cur_s_sheet in s_sheet_names else 0
                
                chosen_s_sheet = st.selectbox(
                    f"📑 [{left_label_input}] 대상 시트 선택",
                    s_sheet_names,
                    index=s_idx,
                    key=f"select_s_sheet_{curr_project_id}"
                )
                if chosen_s_sheet != cur_s_sheet:
                    update_workspace_sheet_choice(curr_project_id, "source", chosen_s_sheet)
                    st.rerun()

                source_df = pd.read_excel(io.BytesIO(source_blob), sheet_name=chosen_s_sheet)
                st.caption(f"✓ '{chosen_s_sheet}' 로드됨 ({len(source_df)}행)")
            except Exception as e:
                st.error(f"시트 로드 실패: {e}")
        else:
            st.info(f"👆 {left_label_input} 파일을 업로드해 주세요.")

    # 2) 대조 파일 (재단 양식) - 완벽 복원
    with f_col2:
        st.markdown(f"**🏛️ {right_label_input} 파일**")
        new_t_file = st.file_uploader(f"{right_label_input} 등록 (.xlsx, .xls)", type=["xlsx", "xls"], key=f"t_uploader_{curr_project_id}")
        if new_t_file is not None:
            bytes_val_t = new_t_file.getvalue()
            if target_blob != bytes_val_t:
                try:
                    xl_test_t = pd.ExcelFile(io.BytesIO(bytes_val_t))
                    init_sheet_t = xl_test_t.sheet_names[0]
                    update_workspace_file_blob(curr_project_id, "target", bytes_val_t, default_sheet=init_sheet_t)
                    st.rerun()
                except Exception as e:
                    st.error(f"엑셀 파일 읽기 실패: {e}")

        if target_blob is not None:
            try:
                xl_t = pd.ExcelFile(io.BytesIO(target_blob))
                t_sheet_names = xl_t.sheet_names
                cur_t_sheet = workspace_files.get("target_sheet_name")
                t_idx = t_sheet_names.index(cur_t_sheet) if cur_t_sheet in t_sheet_names else 0
                
                # ★ 대조 파일 대상 시트 선택 드롭다운 (완벽 활성화)
                chosen_t_sheet = st.selectbox(
                    f"📑 [{right_label_input}] 대상 시트 선택",
                    t_sheet_names,
                    index=t_idx,
                    key=f"select_t_sheet_{curr_project_id}"
                )
                if chosen_t_sheet != cur_t_sheet:
                    update_workspace_sheet_choice(curr_project_id, "target", chosen_t_sheet)
                    st.rerun()

                target_df = pd.read_excel(io.BytesIO(target_blob), sheet_name=chosen_t_sheet)
                st.caption(f"✓ '{chosen_t_sheet}' 로드됨 ({len(target_df)}행)")
            except Exception as e:
                st.error(f"시트 로드 실패: {e}")
        else:
            st.info(f"👆 {right_label_input} 파일을 업로드해 주세요.")

if source_df is None or target_df is None:
    st.info("💡 1단계 카드에서 두 엑셀 파일을 업로드하고 [대상 시트]를 각각 선택해 주세요.")
    st.stop()

# ----------------------------------------------------
# 2단계: 대조 열 및 총계 행 설정 (자동 영구 저장)
# ----------------------------------------------------
source_cols = list(source_df.columns)
target_cols = list(target_df.columns)

def_s_name = saved_settings.get("s_name_col", source_cols[0] if source_cols else None)
def_t_name = saved_settings.get("t_name_col", target_cols[0] if target_cols else None)
def_s_amt = saved_settings.get("s_amt", source_cols[min(2, len(source_cols)-1)] if source_cols else None)
def_t_amt = saved_settings.get("t_amt", target_cols[min(2, len(target_cols)-1)] if target_cols else None)
def_s_tot = saved_settings.get("forced_s_total_row", "(자동 감지)")
def_t_tot = saved_settings.get("forced_t_total_row", "(자동 감지)")

with st.expander("⚙️ 2단계: 대조 열 및 양측 총계 행 설정 (자동 저장됨)", expanded=False):
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        s_name_idx = source_cols.index(def_s_name) if def_s_name in source_cols else 0
        s_name_col = st.selectbox(f"{left_label_input} 항목명 열", source_cols, index=s_name_idx)
    with col_c2:
        t_name_idx = target_cols.index(def_t_name) if def_t_name in target_cols else 0
        t_name_col = st.selectbox(f"{right_label_input} 항목명 열", target_cols, index=t_name_idx)

    ac1, ac2 = st.columns(2)
    with ac1:
        s_amt_idx = source_cols.index(def_s_amt) if def_s_amt in source_cols else min(2, len(source_cols)-1)
        s_amt = st.selectbox(f"비교할 금액 열 ({left_label_input})", source_cols, index=s_amt_idx)
    with ac2:
        t_amt_idx = target_cols.index(def_t_amt) if def_t_amt in target_cols else min(2, len(target_cols)-1)
        t_amt = st.selectbox(f"비교할 금액 열 ({right_label_input})", target_cols, index=t_amt_idx)

    st.markdown("---")
    st.markdown("##### 📌 공식 총계 행 지정 (좌우 각각 선택 및 실시간 금액 확인)")

    tc1, tc2 = st.columns(2)
    s_candidates = get_all_row_candidates(source_df, s_name_col)
    with tc1:
        s_tot_idx = s_candidates.index(def_s_tot) if def_s_tot in s_candidates else 0
        forced_s_total_row = st.selectbox(
            f"🏫 [{left_label_input}] 총계 행 선택",
            s_candidates,
            index=s_tot_idx,
            key=f"forced_s_tot_{curr_project_id}"
        )
        if forced_s_total_row != "(자동 감지)":
            row_match = source_df[source_df[s_name_col].astype(str).str.strip() == forced_s_total_row]
            if not row_match.empty:
                preview_amt = clean_number(row_match.iloc[-1][s_amt])
                st.caption(f"확인된 금액: **{preview_amt:,.0f} 원**")

    t_candidates = get_all_row_candidates(target_df, t_name_col)
    with tc2:
        t_tot_idx = t_candidates.index(def_t_tot) if def_t_tot in t_candidates else 0
        forced_t_total_row = st.selectbox(
            f"🏛️ [{right_label_input}] 총계 행 선택",
            t_candidates,
            index=t_tot_idx,
            key=f"forced_t_tot_{curr_project_id}"
        )
        if forced_t_total_row != "(자동 감지)":
            row_match_t = target_df[target_df[t_name_col].astype(str).str.strip() == forced_t_total_row]
            if not row_match_t.empty:
                preview_amt_t = clean_number(row_match_t.iloc[-1][t_amt])
                st.caption(f"확인된 금액: **{preview_amt_t:,.0f} 원**")

    current_settings = {
        "s_name_col": s_name_col,
        "t_name_col": t_name_col,
        "s_amt": s_amt,
        "t_amt": t_amt,
        "forced_s_total_row": forced_s_total_row,
        "forced_t_total_row": forced_t_total_row
    }
    if current_settings != saved_settings:
        save_workspace_settings(curr_project_id, current_settings)

# ----------------------------------------------------
# 3단계: 정밀 총계 산출 및 데이터 매칭
# ----------------------------------------------------
s_df_clean = source_df.dropna(subset=[s_name_col]).copy()
t_df_clean = target_df.dropna(subset=[t_name_col]).copy()

s_df_clean[s_name_col] = s_df_clean[s_name_col].astype(str).str.strip()
t_df_clean[t_name_col] = t_df_clean[t_name_col].astype(str).str.strip()
s_df_clean[s_amt] = s_df_clean[s_amt].apply(clean_number)
t_df_clean[t_amt] = t_df_clean[t_amt].apply(clean_number)

official_t_total, t_total_source_name = extract_smart_grand_total(
    t_df_clean, t_name_col, t_amt, 
    forced_row=forced_t_total_row
)
total_type = "수입" if "수입" in t_total_source_name else ("지출" if "지출" in t_total_source_name else "전체")

official_s_total, s_total_source_name = extract_smart_grand_total(
    s_df_clean, s_name_col, s_amt, 
    target_total_type=total_type, 
    forced_row=forced_s_total_row
)
grand_diff = official_s_total - official_t_total

target_sum_lookup = {}
for t_name, grp in t_df_clean.groupby(t_name_col):
    target_sum_lookup[str(t_name).strip()] = grp[t_amt].sum()

raw_target_list = sorted([str(x).strip() for x in t_df_clean[t_name_col].unique() if str(x).strip()])
target_clean_dict = {raw_name: clean_account_name(raw_name) for raw_name in raw_target_list}
target_options = ["(매칭 제외)"] + raw_target_list

saved_history = get_saved_mappings()
unique_source_items = sorted([str(x).strip() for x in s_df_clean[s_name_col].unique() if str(x).strip() and not is_aggregate_account(str(x))])

matched_rows = []
for s_name in unique_source_items:
    state_key = f"match_override_{curr_project_id}_{re.sub(r'[^a-zA-Z0-9가-힣]', '_', s_name)}"
    if state_key in st.session_state:
        selected_match = st.session_state[state_key]
        status_text = "✏️ 수동"
    elif s_name in saved_history and saved_history[s_name] in target_options:
        selected_match = saved_history[s_name]
        status_text = "💾 저장됨"
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
        val_status = "❌ 오류" if abs(diff) > 0.01 else "✅ 일치"

    ai_hint = "-"
    if val_status != "✅ 일치":
        zero_diffs = [rt for rt, sv in target_sum_lookup.items() if not is_aggregate_account(rt) and abs(sv - s_val) < 1]
        if zero_diffs:
            ai_hint = f"👉 {zero_diffs[0]} (0원)"
        else:
            fuzzy_c = difflib.get_close_matches(clean_account_name(s_name), [clean_account_name(t) for t in raw_target_list if not is_aggregate_account(t)], n=1, cutoff=0.4)
            if fuzzy_c:
                raw_c = [t for t in raw_target_list if clean_account_name(t) == fuzzy_c[0]][0]
                ai_hint = f"💡 {raw_c}"

    matched_rows.append({
        "상태": val_status,
        f"{left_label_input} 항목명": s_name,
        f"{left_label_input} 결산액": int(round(s_val)),
        f"매칭 {right_label_input} 항목명": selected_match,
        f"{right_label_input} 결산액": int(round(t_val)),
        "차액": int(round(diff)),
        "AI 추천 힌트": ai_hint,
        "매칭유형": status_text
    })

res_df = pd.DataFrame(matched_rows)

# ----------------------------------------------------
# 4단계: 상단 자금 정합성 배너 & 컴팩트 KPI
# ----------------------------------------------------
total_items = len(res_df)
match_items = len(res_df[res_df["상태"] == "✅ 일치"])
error_items = len(res_df[res_df["상태"] == "❌ 오류"])
unmatched_items = len(res_df[res_df["상태"] == "⚠️ 미매칭"])

border_color = "#059669" if abs(grand_diff) < 1 else "#DC2626"
diff_summary_text = "총계 완벽 일치 (0원)" if abs(grand_diff) < 1 else f"총계 차액: {grand_diff:+,.0f} 원"

st.markdown(f"""
<div class="kpi-card" style="margin-bottom: 16px; border-left: 5px solid {border_color};">
    <div style="font-size: 13px; font-weight: 600; color: #64748B;">자금 결산 정합성 현황 (공식 총계 행 기준)</div>
    <div style="font-size: 16px; font-weight: 700; color: #0F172A; margin-top: 4px;">
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

m1, m2, m3, m4 = st.columns(4)
m1.markdown(f"""<div class="kpi-card"><div style="color: #64748B; font-size:11.5px; font-weight:600;">전체 검증 항목</div><div class="kpi-val" style="color: #0F172A;">{total_items}건</div></div>""", unsafe_allow_html=True)
m2.markdown(f"""<div class="kpi-card" style="border-color: #A7F3D0; background-color: #F0FDF4;"><div style="color: #059669; font-size:11.5px; font-weight:600;">정상 일치</div><div class="kpi-val" style="color: #059669;">{match_items}건 <span style="font-size:12px;">({(match_items/total_items*100 if total_items else 0):.1f}%)</span></div></div>""", unsafe_allow_html=True)
m3.markdown(f"""<div class="kpi-card" style="border-color: #FECACA; background-color: #FEF2F2;"><div style="color: #DC2626; font-size:11.5px; font-weight:600;">차액 오류</div><div class="kpi-val" style="color: #DC2626;">{error_items}건</div></div>""", unsafe_allow_html=True)
m4.markdown(f"""<div class="kpi-card" style="border-color: #FDE68A; background-color: #FFFBEB;"><div style="color: #D97706; font-size:11.5px; font-weight:600;">미매칭 항목</div><div class="kpi-val" style="color: #D97706;">{unmatched_items}건</div></div>""", unsafe_allow_html=True)

st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

# ----------------------------------------------------
# 5단계: 📑 엑셀형 인터랙티브 스마트 시트
# ----------------------------------------------------
ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 1.8, 1.2])

with ctrl_col1:
    filter_choice = st.radio(
        "검증 필터",
        ["전체 항목 보기", "❌ 차액 오류만", "⚠️ 미매칭만"],
        horizontal=True
    )

with ctrl_col2:
    search_keyword = st.text_input("🔍 계정명 빠른 검색", placeholder="예: 수업료, 예수금, 자산...")

with ctrl_col3:
    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    export_buffer = io.BytesIO()
    with pd.ExcelWriter(export_buffer, engine='openpyxl') as writer:
        res_df.to_excel(writer, index=False, sheet_name="검증결과리포트")
    export_buffer.seek(0)
    
    st.download_button(
        label="📥 결과 엑셀 다운로드",
        data=export_buffer,
        file_name=f"검증결과_{selected_project_name}_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True
    )

display_df = res_df.copy()
if filter_choice == "❌ 차액 오류만":
    display_df = display_df[display_df["상태"] == "❌ 오류"]
elif filter_choice == "⚠️ 미매칭만":
    display_df = display_df[display_df["상태"] == "⚠️ 미매칭"]

if search_keyword.strip():
    kw = search_keyword.strip()
    s_col_name = f"{left_label_input} 항목명"
    t_col_name = f"매칭 {right_label_input} 항목명"
    display_df = display_df[display_df[s_col_name].str.contains(kw) | display_df[t_col_name].str.contains(kw)]

st.info(f"💡 **인라인 편집 안내:** 아래 표에서 **[매칭 {right_label_input} 항목명]** 칸을 더블클릭하여 변경한 뒤, 아래 **[💾 일괄 영구 저장]** 버튼을 누르면 영구 보존됩니다.")

target_column_title = f"매칭 {right_label_input} 항목명"

edited_df = st.data_editor(
    display_df,
    use_container_width=True,
    height=480,
    hide_index=True,
    key=f"editor_{curr_project_id}",
    column_config={
        "상태": st.column_config.TextColumn("검증 상태", width=85, disabled=True),
        f"{left_label_input} 항목명": st.column_config.TextColumn(f"{left_label_input} 항목명 (기준)", width=210, disabled=True),
        f"{left_label_input} 결산액": st.column_config.NumberColumn(
            f"{left_label_input} 금액 (원)", 
            format="%,d", 
            width=135,
            disabled=True
        ),
        target_column_title: st.column_config.SelectboxColumn(
            f"매칭 {right_label_input} 항목명 (더블클릭)",
            help="클릭하여 대조할 재단 계정을 변경할 수 있습니다.",
            options=target_options,
            required=True,
            width=210
        ),
        f"{right_label_input} 결산액": st.column_config.NumberColumn(
            f"{right_label_input} 금액 (원)", 
            format="%,d", 
            width=135,
            disabled=True
        ),
        "차액": st.column_config.NumberColumn(
            "차액 (원)", 
            format="%,d", 
            width=135,
            disabled=True
        ),
        "AI 추천 힌트": st.column_config.TextColumn("AI 추천 힌트", width=180, disabled=True),
        "매칭유형": st.column_config.TextColumn("유형", width=75, disabled=True)
    }
)

save_col1, save_col2 = st.columns([3, 1])
with save_col2:
    if st.button("💾 표에서 변경한 매칭 일괄 영구 저장", type="primary", use_container_width=True):
        changed_count = 0
        batch_to_save = {}
        for _, row in edited_df.iterrows():
            s_name = row[f"{left_label_input} 항목명"]
            t_name = row[target_column_title]
            safe_key = f"match_override_{curr_project_id}_{re.sub(r'[^a-zA-Z0-9가-힣]', '_', s_name)}"
            
            if st.session_state.get(safe_key) != t_name:
                st.session_state[safe_key] = t_name
                batch_to_save[s_name] = t_name
                changed_count += 1
            elif s_name not in saved_history or saved_history[s_name] != t_name:
                batch_to_save[s_name] = t_name
                changed_count += 1
                
        if changed_count > 0:
            save_batch_mappings(batch_to_save)
            st.success(f"{changed_count}개 계정의 매칭 정보가 영구 저장되었습니다!")
            st.rerun()
        else:
            st.info("변경된 항목이 없습니다.")
