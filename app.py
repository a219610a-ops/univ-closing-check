import streamlit as st
import pandas as pd
import sqlite3
import io
import difflib
from datetime import datetime

# ==========================================
# 1. 페이지 기본 설정
# ==========================================
st.set_page_config(
    page_title="데이터 스마트 검증기",
    page_icon="📊",
    layout="wide"
)

# ==========================================
# 2. SQLite 데이터베이스 초기화 및 자동 보정(Migration)
# ==========================================
def get_db_connection():
    conn = sqlite3.connect("accounting_audit.db", check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1) 프로젝트 관리 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
    """)
    
    # 2) 계정 매칭 학습 규칙 테이블 (구버전 컬럼 자동 보정 검사)
    cursor.execute("SELECT count(name) FROM sqlite_master WHERE type='table' AND name='account_mappings'")
    table_exists = cursor.fetchone()[0] > 0
    
    if table_exists:
        cursor.execute("PRAGMA table_info(account_mappings)")
        columns = [col[1] for col in cursor.fetchall()]
        # 구버전 컬럼(school_name)이 남아있을 경우 최신 규격으로 테이블 재생성
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
        
    # 3) 프로젝트별 작업 상태 영구 저장 테이블 (새로고침 방지용)
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

# DB 조작 함수들
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
            VALUES (?, '기준 데이터', '대조 데이터', NULL, NULL, ?)
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
            "left_label": row[0] or "기준 데이터",
            "right_label": row[1] or "대조 데이터",
            "source_data": s_df,
            "target_data": t_df
        }
    return {"left_label": "기준 데이터", "right_label": "대조 데이터", "source_data": None, "target_data": None}

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

def save_mapping_rules(mapping_list):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for item in mapping_list:
        s_name = item.get("source_name", "").strip()
        t_name = item.get("target_name", "").strip()
        if s_name and t_name and t_name != "(매칭 제외)":
            cursor.execute("""
                INSERT INTO account_mappings (source_name, target_name, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(source_name, target_name) 
                DO UPDATE SET updated_at=excluded.updated_at
            """, (s_name, t_name, now))
    conn.commit()
    conn.close()

# ==========================================
# 3. 사이드바: 프로젝트 관리
# ==========================================
with st.sidebar:
    st.header("📂 프로젝트 관리")
    
    with st.expander("➕ 새 프로젝트 만들기", expanded=False):
        new_proj_name = st.text_input("프로젝트 이름", placeholder="예: 2025학년도 결산 검증")
        if st.button("프로젝트 생성", use_container_width=True):
            if new_proj_name.strip():
                if create_project(new_proj_name.strip()):
                    st.success("프로젝트가 생성되었습니다!")
                    st.rerun()
                else:
                    st.error("이미 존재하는 프로젝트 이름입니다.")
            else:
                st.warning("이름을 입력해 주세요.")
                
    projects_df = get_projects()
    
    if not projects_df.empty:
        project_names = projects_df['name'].tolist()
        selected_project_name = st.selectbox("📋 작업할 프로젝트 선택", project_names)
        current_project = projects_df[projects_df['name'] == selected_project_name].iloc[0]
        curr_project_id = int(current_project['id'])
        st.caption(f"생성일시: {current_project['created_at']}")
        
        if st.button("🗑️ 현재 프로젝트 삭제", type="secondary", use_container_width=True):
            delete_project(curr_project_id)
            st.warning("프로젝트가 삭제되었습니다.")
            st.rerun()
    else:
        selected_project_name = None
        curr_project_id = None
        st.info("왼쪽 상단에서 새 프로젝트를 먼저 생성해 주세요.")

# ==========================================
# 4. 메인 화면 헤더 및 설명
# ==========================================
st.title("📊 데이터 스마트 검증기")
st.markdown("서로 다른 두 양식의 데이터를 스마트 매칭하여 항목별 입력 오류와 차액을 자동으로 대조·검증합니다.")

if not selected_project_name:
    st.warning("👈 왼쪽 사이드바에서 프로젝트를 생성하거나 선택해 주세요.")
    st.stop()

# 현재 프로젝트의 DB 저장 데이터 로드
workspace_state = get_workspace(curr_project_id)

top_c1, top_c2 = st.columns([3, 1])
with top_c1:
    st.info(f"📌 현재 활성 프로젝트: **{selected_project_name}**")
with top_c2:
    if st.button("🔄 데이터 초기화 (새 파일 업로드)", use_container_width=True):
        reset_workspace_data(curr_project_id)
        st.success("데이터가 초기화되었습니다.")
        st.rerun()

# ----------------------------------------------------
# 1단계: 대조 대상 엑셀 파일 업로드 및 명칭 설정
# ----------------------------------------------------
st.subheader("1단계: 대조 대상 엑셀 파일 업로드 및 시트 지정")
st.caption("비교할 두 파일의 라벨을 설정할 수 있으며, 새로고침해도 작업 상태가 자동 보존됩니다.")

lbl_c1, lbl_c2 = st.columns(2)
with lbl_c1:
    left_label_input = st.text_input(
        "왼쪽 파일 라벨", 
        value=workspace_state["left_label"], 
        key=f"left_lbl_{curr_project_id}"
    )
with lbl_c2:
    right_label_input = st.text_input(
        "오른쪽 파일 라벨", 
        value=workspace_state["right_label"], 
        key=f"right_lbl_{curr_project_id}"
    )

if (left_label_input != workspace_state["left_label"]) or (right_label_input != workspace_state["right_label"]):
    update_workspace(
        curr_project_id, 
        left_label_input, 
        right_label_input, 
        workspace_state["source_data"], 
        workspace_state["target_data"]
    )
    st.rerun()

col1, col2 = st.columns(2)

source_df = workspace_state["source_data"]
target_df = workspace_state["target_data"]

with col1:
    st.markdown(f"##### 📁 {left_label_input} (.xlsx)")
    school_file = st.file_uploader(f"{left_label_input} 파일 업로드", type=["xlsx"], key=f"s_file_{curr_project_id}")
    if school_file:
        try:
            xl_s = pd.ExcelFile(school_file)
            s_sheet = st.selectbox(f"{left_label_input} 대상 시트 선택", xl_s.sheet_names, key=f"s_sheet_{curr_project_id}")
            if s_sheet:
                source_df = pd.read_excel(school_file, sheet_name=s_sheet)
                update_workspace(curr_project_id, left_label_input, right_label_input, source_df, target_df)
                st.success(f"{left_label_input} 로드 완료 ({len(source_df)}행)")
        except Exception as e:
            st.error(f"파일 읽기 오류: {e}")
    elif source_df is not None:
        st.info(f"💾 이전에 저장된 {left_label_input} 유지 중 ({len(source_df)}행)")

with col2:
    st.markdown(f"##### 📁 {right_label_input} (.xlsx)")
    found_file = st.file_uploader(f"{right_label_input} 파일 업로드", type=["xlsx"], key=f"t_file_{curr_project_id}")
    if found_file:
        try:
            xl_t = pd.ExcelFile(found_file)
            t_sheet = st.selectbox(f"{right_label_input} 대상 시트 선택", xl_t.sheet_names, key=f"t_sheet_{curr_project_id}")
            if t_sheet:
                target_df = pd.read_excel(found_file, sheet_name=t_sheet)
                update_workspace(curr_project_id, left_label_input, right_label_input, source_df, target_df)
                st.success(f"{right_label_input} 로드 완료 ({len(target_df)}행)")
        except Exception as e:
            st.error(f"파일 읽기 오류: {e}")
    elif target_df is not None:
        st.info(f"💾 이전에 저장된 {right_label_input} 유지 중 ({len(target_df)}행)")

# 두 데이터가 준비된 경우 후속 단계 진행
if source_df is not None and target_df is not None:
    st.divider()
    
    # ----------------------------------------------------
    # 2단계: 기준 열(Column) 지정
    # ----------------------------------------------------
    st.subheader("2단계: 대조할 열(Column) 설정")
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.markdown(f"**[{left_label_input}]**")
        source_cols = list(source_df.columns)
        s_name_col = st.selectbox(f"{left_label_input} 항목명 열", source_cols, index=0)
        
    with col_c2:
        st.markdown(f"**[{right_label_input}]**")
        target_cols = list(target_df.columns)
        t_name_col = st.selectbox(f"{right_label_input} 항목명 열", target_cols, index=0)

    st.markdown("**[비교할 금액 열(Column) 짝짓기]**")
    st.caption("비교가 필요한 금액 열들을 짝지어 선택해 주세요.")
    
    amount_col_count = st.number_input("비교할 금액 열 개수", min_value=1, max_value=5, value=1)
    matched_amount_cols = []
    
    for i in range(amount_col_count):
        ac1, ac2 = st.columns(2)
        with ac1:
            s_amt = st.selectbox(f"금액 열 #{i+1} ({left_label_input})", source_cols, key=f"s_amt_{i}")
        with ac2:
            t_amt = st.selectbox(f"금액 열 #{i+1} ({right_label_input})", target_cols, key=f"t_amt_{i}")
        matched_amount_cols.append((s_amt, t_amt))
        
    st.divider()

    # ----------------------------------------------------
    # 3단계: 스마트 항목 매칭 엔진
    # ----------------------------------------------------
    st.subheader("3단계: 항목 스마트 매칭")
    st.markdown("DB 과거 기록, 완전 일치, 유사도 분석을 거쳐 최적의 매칭 항목을 자동 추천합니다.")

    s_df_clean = source_df.dropna(subset=[s_name_col]).copy()
    t_df_clean = target_df.dropna(subset=[t_name_col]).copy()
    
    s_df_clean[s_name_col] = s_df_clean[s_name_col].astype(str).str.strip()
    t_df_clean[t_name_col] = t_df_clean[t_name_col].astype(str).str.strip()
    
    target_unique_names = ["(매칭 제외)"] + sorted(t_df_clean[t_name_col].unique().tolist())
    saved_history = get_saved_mappings()
    
    unique_source_items = sorted(s_df_clean[s_name_col].unique().tolist())
    
    mapping_form_data = []
    st.write("아래 매칭 결과를 확인하시고, 필요한 경우 드롭다운을 열어 변경해 주세요:")
    
    with st.expander("🔍 항목 매칭 테이블 펼치기 / 접기", expanded=True):
        m_head1, m_head2, m_head3 = st.columns([3, 3, 1.5])
        m_head1.markdown(f"**{left_label_input} 항목명**")
        m_head2.markdown(f"**매칭할 {right_label_input} 항목명**")
        m_head3.markdown("**매칭 판정**")

        for idx, name_val in enumerate(unique_source_items):
            selected_match = "(매칭 제외)"
            status_text = "미매칭"
            
            if name_val in saved_history and saved_history[name_val] in target_unique_names:
                selected_match = saved_history[name_val]
                status_text = "💾 DB기억"
            elif name_val in target_unique_names:
                selected_match = name_val
                status_text = "🎯 완전일치"
            else:
                candidates = difflib.get_close_matches(name_val, target_unique_names[1:], n=1, cutoff=0.4)
                if candidates:
                    selected_match = candidates[0]
                    status_text = "🤖 AI추천"

            col_m1, col_m2, col_m3 = st.columns([3, 3, 1.5])
            col_m1.text(name_val)
            
            default_index = target_unique_names.index(selected_match) if selected_match in target_unique_names else 0
            user_choice = col_m2.selectbox(
                f"선택_{idx}", 
                target_unique_names, 
                index=default_index, 
                key=f"match_select_{curr_project_id}_{idx}",
                label_visibility="collapsed"
            )
            col_m3.caption(status_text)
            
            mapping_form_data.append({
                "source_name": name_val,
                "target_name": user_choice
            })
            
        if st.button("💾 현재 매칭 규칙 DB에 영구 저장하기 (다음 작업 시 자동 기억)", type="primary"):
            save_mapping_rules(mapping_form_data)
            st.success("매칭 규칙이 영구 데이터베이스(SQLite)에 성공적으로 저장되었습니다!")

    st.divider()

    # ----------------------------------------------------
    # 4단계: 실시간 금액 대조 및 오류 검증
    # ----------------------------------------------------
    st.subheader("4단계: 데이터 대조 및 불일치 검증 결과")
    
    mapping_dict = {item["source_name"]: item["target_name"] for item in mapping_form_data}
    
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

    t_grouped = t_df_clean.copy()
    for _, t_amt in matched_amount_cols:
        t_grouped[t_amt] = t_grouped[t_amt].apply(clean_number)
    t_summary = t_grouped.groupby(t_name_col)[[t_amt for _, t_amt in matched_amount_cols]].sum().reset_index()

    s_grouped = s_df_clean.copy()
    for s_amt, _ in matched_amount_cols:
        s_grouped[s_amt] = s_grouped[s_amt].apply(clean_number)
    
    s_grouped["__matched_target_name"] = s_grouped[s_name_col].map(mapping_dict)
    
    result_rows = []
    for _, row in s_grouped.iterrows():
        s_name = row[s_name_col]
        t_name = row["__matched_target_name"]
        
        row_res = {
            f"{left_label_input} 항목명": s_name,
            f"매칭 {right_label_input} 항목명": t_name if t_name else "(미매칭)"
        }
        
        has_error = False
        if not t_name or t_name == "(매칭 제외)":
            for s_amt, t_amt in matched_amount_cols:
                row_res[f"{left_label_input}_{s_amt}"] = row[s_amt]
                row_res[f"{right_label_input}_{t_amt}"] = 0.0
                row_res[f"차액({s_amt}-{t_amt})"] = row[s_amt]
            row_res["검증 상태"] = "⚠️ 미매칭"
        else:
            t_match_rows = t_summary[t_summary[t_name_col] == t_name]
            for s_amt, t_amt in matched_amount_cols:
                s_val = row[s_amt]
                t_val = t_match_rows[t_amt].values[0] if not t_match_rows.empty else 0.0
                diff = s_val - t_val
                row_res[f"{left_label_input}_{s_amt}"] = s_val
                row_res[f"{right_label_input}_{t_amt}"] = t_val
                row_res[f"차액({s_amt}-{t_amt})"] = diff
                if abs(diff) > 0.01:
                    has_error = True
                    
            row_res["검증 상태"] = "❌ 불일치(오류)" if has_error else "✅ 정상 일치"
            
        result_rows.append(row_res)
        
    result_df = pd.DataFrame(result_rows)

    total_count = len(result_df)
    match_count = len(result_df[result_df["검증 상태"] == "✅ 정상 일치"])
    error_count = len(result_df[result_df["검증 상태"] == "❌ 불일치(오류)"])
    unmatched_count = len(result_df[result_df["검증 상태"] == "⚠️ 미매칭"])

    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    m_col1.metric("전체 항목 수", f"{total_count}건")
    m_col2.metric("정상 일치", f"{match_count}건")
    m_col3.metric("불일치(오류)", f"{error_count}건", delta=-error_count if error_count > 0 else 0)
    m_col4.metric("미매칭 항목", f"{unmatched_count}건")

    filter_option = st.radio("표시할 결과 선택", ["전체 보기", "❌ 불일치(오류) 항목만 보기", "⚠️ 미매칭 항목만 보기"], horizontal=True)
    if filter_option == "❌ 불일치(오류) 항목만 보기":
        display_df = result_df[result_df["검증 상태"] == "❌ 불일치(오류)"]
    elif filter_option == "⚠️ 미매칭 항목만 보기":
        display_df = result_df[result_df["검증 상태"] == "⚠️ 미매칭"]
    else:
        display_df = result_df

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ----------------------------------------------------
    # 5단계: 결과 엑셀 다운로드
    # ----------------------------------------------------
    st.divider()
    st.subheader("5단계: 검증 결과 엑셀 다운로드")
    
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        result_df.to_excel(writer, index=False, sheet_name="검증결과리포트")
    excel_buffer.seek(0)
    
    file_name = f"검증결과_{selected_project_name}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    
    st.download_button(
        label="📥 검증 결과 엑셀(.xlsx) 파일 내려받기",
        data=excel_buffer,
        file_name=file_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True
    )
