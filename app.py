import streamlit as st
import pandas as pd
import sqlite3
import io
import difflib
from datetime import datetime

# ==========================================
# 1. 페이지 기본 설정 및 스타일
# ==========================================
st.set_page_config(
    page_title="대학-사학진흥재단 결산서 스마트 검증기",
    page_icon="📊",
    layout="wide"
)

# ==========================================
# 2. SQLite 데이터베이스 초기화 및 관리 함수
# ==========================================
def get_db_connection():
    conn = sqlite3.connect("accounting_audit.db", check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 프로젝트 관리 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
    """)
    
    # 계정과목 매칭 규칙 영구 저장 테이블 (과목명 기준)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS account_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_name TEXT NOT NULL,
            foundation_name TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(school_name, foundation_name)
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

def get_saved_mappings():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT school_name, foundation_name FROM account_mappings", conn)
    conn.close()
    mapping_dict = dict(zip(df['school_name'], df['foundation_name']))
    return mapping_dict

def save_mapping_rules(mapping_list):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for item in mapping_list:
        school_name = item.get("school_name", "")
        foundation_name = item.get("foundation_name", "")
        if school_name and foundation_name:
            cursor.execute("""
                INSERT INTO account_mappings (school_name, foundation_name, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(school_name, foundation_name) 
                DO UPDATE SET updated_at=excluded.updated_at
            """, (school_name, foundation_name, now))
    conn.commit()
    conn.close()

# ==========================================
# 3. 사이드바: 프로젝트 관리
# ==========================================
with st.sidebar:
    st.header("📂 프로젝트 관리")
    
    with st.expander("➕ 새 프로젝트 만들기", expanded=False):
        new_proj_name = st.text_input("프로젝트 이름", placeholder="예: 2025학년도 본결산_등록금회계")
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
        st.caption(f"생성일시: {current_project['created_at']}")
        
        if st.button("🗑️ 현재 프로젝트 삭제", type="secondary", use_container_width=True):
            delete_project(current_project['id'])
            st.warning("프로젝트가 삭제되었습니다.")
            st.rerun()
    else:
        selected_project_name = None
        st.info("왼쪽 상단에서 새 프로젝트를 먼저 생성해 주세요.")

# ==========================================
# 4. 메인 화면 로직
# ==========================================
st.title("📊 대학-사학진흥재단 결산서 스마트 검증기")
st.markdown("학교 자체 결산서와 사학진흥재단 제출 양식을 대조하여 계정별 입력 오류와 차액을 자동으로 검증합니다.")

if not selected_project_name:
    st.warning("👈 왼쪽 사이드바에서 프로젝트를 생성하거나 선택해 주세요.")
    st.stop()

st.info(f"📌 현재 활성 프로젝트: **{selected_project_name}**")

# 세션 상태 초기화
if "school_df" not in st.session_state:
    st.session_state.school_df = None
if "foundation_df" not in st.session_state:
    st.session_state.foundation_df = None

# ----------------------------------------------------
# 1단계: 엑셀 파일 업로드 및 시트 지정
# ----------------------------------------------------
st.subheader("1단계: 결산서 엑셀 파일 업로드 및 시트 지정")
col1, col2 = st.columns(2)

with col1:
    st.markdown("##### 🏫 학교 자체 결산서 (.xlsx)")
    school_file = st.file_uploader("학교 결산서 파일 업로드", type=["xlsx"], key="school_uploader")
    school_sheet = None
    if school_file:
        try:
            xl_school = pd.ExcelFile(school_file)
            school_sheet = st.selectbox("학교 결산서 대상 시트 선택", xl_school.sheet_names, key="school_sheet_select")
            if school_sheet:
                st.session_state.school_df = pd.read_excel(school_file, sheet_name=school_sheet)
                st.success(f"학교 데이터 로드 완료 ({len(st.session_state.school_df)}행)")
        except Exception as e:
            st.error(f"학교 파일 읽기 오류: {e}")

with col2:
    st.markdown("##### 🏛️ 사학진흥재단 양식 (.xlsx)")
    foundation_file = st.file_uploader("사학진흥재단 양식 파일 업로드", type=["xlsx"], key="found_uploader")
    foundation_sheet = None
    if foundation_file:
        try:
            xl_found = pd.ExcelFile(foundation_file)
            foundation_sheet = st.selectbox("재단 양식 대상 시트 선택", xl_found.sheet_names, key="found_sheet_select")
            if foundation_sheet:
                st.session_state.foundation_df = pd.read_excel(foundation_file, sheet_name=foundation_sheet)
                st.success(f"재단 데이터 로드 완료 ({len(st.session_state.foundation_df)}행)")
        except Exception as e:
            st.error(f"재단 파일 읽기 오류: {e}")

# 두 파일 모두 로드된 경우 다음 단계 진행
if st.session_state.school_df is not None and st.session_state.foundation_df is not None:
    st.divider()
    
    # ----------------------------------------------------
    # 2단계: 기준 열(Column) 지정 (계정코드 제외, 계정과목명만 지정)
    # ----------------------------------------------------
    st.subheader("2단계: 대조할 열(Column) 설정")
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.markdown("**[학교 결산서]**")
        school_cols = list(st.session_state.school_df.columns)
        s_name_col = st.selectbox("학교 계정과목명 열", school_cols, index=0)
        
    with col_c2:
        st.markdown("**[사학진흥재단 양식]**")
        found_cols = list(st.session_state.foundation_df.columns)
        f_name_col = st.selectbox("재단 계정과목명 열", found_cols, index=0)

    st.markdown("**[비교할 금액 열(Column) 짝짓기]**")
    st.caption("예산액, 결산액 등 비교할 금액 열들을 각각 선택해 주세요.")
    
    amount_col_count = st.number_input("비교할 금액 열 개수", min_value=1, max_value=5, value=1)
    matched_amount_cols = []
    
    for i in range(amount_col_count):
        ac1, ac2 = st.columns(2)
        with ac1:
            s_amt = st.selectbox(f"금액 열 #{i+1} (학교 결산서)", school_cols, key=f"s_amt_{i}")
        with ac2:
            f_amt = st.selectbox(f"금액 열 #{i+1} (재단 양식)", found_cols, key=f"f_amt_{i}")
        matched_amount_cols.append((s_amt, f_amt))
        
    st.divider()

    # ----------------------------------------------------
    # 3단계: 스마트 계정과목 매칭 엔진
    # ----------------------------------------------------
    st.subheader("3단계: 계정과목 스마트 매칭")
    st.markdown("DB 저장 기록, 완전 일치, 유사도 분석을 거쳐 최적의 재단 계정과목을 자동 추천합니다.")

    # 데이터 정리
    s_df_clean = st.session_state.school_df.dropna(subset=[s_name_col]).copy()
    f_df_clean = st.session_state.foundation_df.dropna(subset=[f_name_col]).copy()
    
    s_df_clean[s_name_col] = s_df_clean[s_name_col].astype(str).str.strip()
    f_df_clean[f_name_col] = f_df_clean[f_name_col].astype(str).str.strip()
    
    foundation_unique_names = ["(매칭 제외)"] + sorted(f_df_clean[f_name_col].unique().tolist())
    saved_history = get_saved_mappings()
    
    # 고유 학교 계정과목 목록 추출
    unique_school_accounts = sorted(s_df_clean[s_name_col].unique().tolist())
    
    mapping_form_data = []
    st.write("아래 매칭 결과를 확인하시고, 필요한 경우 드롭다운을 열어 직접 변경해 주세요:")
    
    with st.expander("🔍 계정과목 매칭 테이블 펼치기 / 접기", expanded=True):
        m_head1, m_head2, m_head3 = st.columns([3, 3, 1.5])
        m_head1.markdown("**학교 계정과목명**")
        m_head2.markdown("**매칭할 사학진흥재단 계정명**")
        m_head3.markdown("**매칭 판정**")

        for idx, name_val in enumerate(unique_school_accounts):
            # 매칭 우선순위 판단
            selected_match = "(매칭 제외)"
            status_text = "미매칭"
            
            if name_val in saved_history and saved_history[name_val] in foundation_unique_names:
                selected_match = saved_history[name_val]
                status_text = "💾 DB기억"
            elif name_val in foundation_unique_names:
                selected_match = name_val
                status_text = "🎯 완전일치"
            else:
                # 유사도 분석
                candidates = difflib.get_close_matches(name_val, foundation_unique_names[1:], n=1, cutoff=0.4)
                if candidates:
                    selected_match = candidates[0]
                    status_text = "🤖 AI추천"

            col_m1, col_m2, col_m3 = st.columns([3, 3, 1.5])
            col_m1.text(name_val)
            
            default_index = foundation_unique_names.index(selected_match) if selected_match in foundation_unique_names else 0
            user_choice = col_m2.selectbox(
                f"선택_{idx}", 
                foundation_unique_names, 
                index=default_index, 
                key=f"match_select_{idx}",
                label_visibility="collapsed"
            )
            col_m3.caption(status_text)
            
            mapping_form_data.append({
                "school_name": name_val,
                "foundation_name": user_choice
            })
            
        if st.button("💾 현재 매칭 규칙 DB에 저장하기 (다음 결산 때 자동 기억)", type="primary"):
            valid_mappings = [m for m in mapping_form_data if m["foundation_name"] != "(매칭 제외)"]
            save_mapping_rules(valid_mappings)
            st.success("매칭 규칙이 영구 데이터베이스(SQLite)에 성공적으로 저장되었습니다!")

    st.divider()

    # ----------------------------------------------------
    # 4단계: 실시간 금액 대조 및 오류 검증
    # ----------------------------------------------------
    st.subheader("4단계: 결산 금액 대조 및 불일치 검증 결과")
    
    mapping_dict = {item["school_name"]: item["foundation_name"] for item in mapping_form_data}
    
    # 금액 숫자 변환 보조 함수
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

    # 재단 데이터 계정별 합산 (재단 계정명 기준)
    f_grouped = f_df_clean.copy()
    for _, f_amt in matched_amount_cols:
        f_grouped[f_amt] = f_grouped[f_amt].apply(clean_number)
    f_summary = f_grouped.groupby(f_name_col)[[f_amt for _, f_amt in matched_amount_cols]].sum().reset_index()

    # 학교 데이터 집계 및 병합
    s_grouped = s_df_clean.copy()
    for s_amt, _ in matched_amount_cols:
        s_grouped[s_amt] = s_grouped[s_amt].apply(clean_number)
    
    # 학교 데이터에 매칭된 재단 계정명 부여
    s_grouped["__matched_foundation_name"] = s_grouped[s_name_col].map(mapping_dict)
    
    result_rows = []
    for _, row in s_grouped.iterrows():
        sch_name = row[s_name_col]
        fd_name = row["__matched_foundation_name"]
        
        row_res = {
            "학교 계정과목명": sch_name,
            "매칭 재단 계정명": fd_name if fd_name else "(미매칭)"
        }
        
        has_error = False
        if not fd_name or fd_name == "(매칭 제외)":
            for s_amt, f_amt in matched_amount_cols:
                row_res[f"학교_{s_amt}"] = row[s_amt]
                row_res[f"재단_{f_amt}"] = 0.0
                row_res[f"차액({s_amt}-{f_amt})"] = row[s_amt]
            row_res["검증 상태"] = "⚠️ 미매칭"
        else:
            fd_match_rows = f_summary[f_summary[f_name_col] == fd_name]
            for s_amt, f_amt in matched_amount_cols:
                s_val = row[s_amt]
                f_val = fd_match_rows[f_amt].values[0] if not fd_match_rows.empty else 0.0
                diff = s_val - f_val
                row_res[f"학교_{s_amt}"] = s_val
                row_res[f"재단_{f_amt}"] = f_val
                row_res[f"차액({s_amt}-{f_amt})"] = diff
                if abs(diff) > 0.01:
                    has_error = True
                    
            row_res["검증 상태"] = "❌ 불일치(오류)" if has_error else "✅ 정상 일치"
            
        result_rows.append(row_res)
        
    result_df = pd.DataFrame(result_rows)

    # 요약 통계 대시보드
    total_count = len(result_df)
    match_count = len(result_df[result_df["검증 상태"] == "✅ 정상 일치"])
    error_count = len(result_df[result_df["검증 상태"] == "❌ 불일치(오류)"])
    unmatched_count = len(result_df[result_df["검증 상태"] == "⚠️ 미매칭"])

    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    m_col1.metric("전체 계정 수", f"{total_count}건")
    m_col2.metric("정상 일치", f"{match_count}건")
    m_col3.metric("불일치(오류)", f"{error_count}건", delta=-error_count if error_count > 0 else 0)
    m_col4.metric("미매칭 계정", f"{unmatched_count}건")

    # 필터 옵션
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
    
    file_name = f"결산검증결과_{selected_project_name}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    
    st.download_button(
        label="📥 검증 결과 엑셀(.xlsx) 파일 내려받기",
        data=excel_buffer,
        file_name=file_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True
    )
