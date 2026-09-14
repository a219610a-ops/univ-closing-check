import streamlit as st
import pandas as pd
import sqlite3
import io
import difflib
import re
import json
import base64
from datetime import datetime, date

# ==========================================
# 1. 페이지 기본 설정 및 디자인 스타일링
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
    .sub-box {
        background-color: #F1F5F9;
        border-left: 4px solid #3B82F6;
        padding: 12px 16px;
        border-radius: 6px;
        margin-bottom: 14px;
    }
    .total-banner {
        background-color: #EFF6FF;
        border: 1px solid #BFDBFE;
        border-radius: 8px;
        padding: 10px 16px;
        margin-bottom: 12px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    div.title-link-container > button {
        background: none !important;
        border: none !important;
        padding: 0px !important;
        margin: 0px !important;
        color: #1E293B !important;
        font-size: 18px !important;
        font-weight: 700 !important;
        text-align: left !important;
        box-shadow: none !important;
        cursor: pointer !important;
        display: inline-block !important;
    }
    div.title-link-container > button:hover {
        color: #2563EB !important;
        text-decoration: underline !important;
        background: none !important;
    }
    div.title-link-container > button:focus {
        box-shadow: none !important;
        background: none !important;
    }

    /* 탭 이름 글자 크기 키우기 및 스타일링 */
    button[data-baseweb="tab"] {
        font-size: 16px !important;
        font-weight: 700 !important;
        padding-top: 10px !important;
        padding-bottom: 10px !important;
    }

    /* 홈 및 회계선택 카드 균일 높이(Flex) 지정 */
    .equal-card-container {
        display: flex;
        flex-direction: column;
        height: 100%;
        min-height: 290px;
        justify-content: flex-start;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. SQLite DB 초기화 및 관리 함수
# ==========================================
def get_db_connection():
    conn = sqlite3.connect("accounting_audit.db", check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def encode_data(raw_text):
    if not raw_text:
        return ""
    return base64.b64encode(raw_text.encode('utf-8')).decode('utf-8')

def decode_data(cipher_text):
    if not cipher_text:
        return ""
    try:
        return base64.b64decode(cipher_text.encode('utf-8')).decode('utf-8')
    except Exception:
        return cipher_text

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
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS donation_receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            fiscal_year INTEGER NOT NULL,
            donation_date TEXT NOT NULL,
            budget_subject TEXT NOT NULL,
            purpose TEXT NOT NULL,
            donor_main_type TEXT NOT NULL,
            donor_sub_type TEXT NOT NULL,
            donor_name TEXT NOT NULL,
            id_number_masked TEXT NOT NULL,
            id_number_cipher TEXT NOT NULL,
            donation_type TEXT NOT NULL,
            code TEXT NOT NULL,
            amount REAL NOT NULL,
            receipt_no TEXT NOT NULL,
            receipt_date TEXT NOT NULL,
            donor_address TEXT DEFAULT '',
            is_statutory_transfer INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS donation_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            fiscal_year INTEGER NOT NULL,
            receipt_id INTEGER NOT NULL DEFAULT 0,
            donor_name TEXT NOT NULL DEFAULT '',
            expense_date TEXT NOT NULL,
            beneficiary TEXT NOT NULL,
            content TEXT NOT NULL,
            amount REAL NOT NULL,
            is_statutory_transfer INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS donation_pledges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            donor_category TEXT NOT NULL,
            payment_method TEXT NOT NULL,
            donor_name TEXT NOT NULL,
            id_number_masked TEXT NOT NULL,
            id_number_cipher TEXT NOT NULL,
            total_pledge_amt REAL DEFAULT 0,
            installment_count INTEGER DEFAULT 0,
            monthly_amt REAL NOT NULL,
            default_purpose TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '진행중',
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS donation_purposes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            budget_subject TEXT NOT NULL DEFAULT '일반기부금',
            major_category TEXT NOT NULL,
            sub_category TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entity_info (
            entity_type TEXT PRIMARY KEY,
            org_name TEXT NOT NULL,
            biz_no TEXT NOT NULL,
            address TEXT NOT NULL,
            law_basis TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cursor.execute("PRAGMA table_info(donation_receipts)")
    r_cols = [c[1] for c in cursor.fetchall()]
    if "donor_address" not in r_cols:
        try: cursor.execute("ALTER TABLE donation_receipts ADD COLUMN donor_address TEXT DEFAULT ''")
        except Exception: pass

    cursor.execute("PRAGMA table_info(donation_purposes)")
    p_cols = [c[1] for c in cursor.fetchall()]
    if "budget_subject" not in p_cols:
        try: cursor.execute("ALTER TABLE donation_purposes ADD COLUMN budget_subject TEXT DEFAULT '일반기부금'")
        except Exception: pass

    cursor.execute("SELECT COUNT(*) FROM donation_purposes")
    if cursor.fetchone()[0] == 0:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        defaults = [
            ("UNIVERSITY", "일반기부금", "대학발전기금", "일반발전", now_str),
            ("UNIVERSITY", "일반기부금", "대학발전기금", "교육시설확충", now_str),
            ("UNIVERSITY", "지정기부금", "장학기금", "가계곤란장학", now_str),
            ("UNIVERSITY", "지정기부금", "장학기금", "성적우수장학", now_str),
            ("UNIVERSITY", "지정기부금", "학과발전기금", "기계공학과", now_str),
            ("UNIVERSITY", "지정기부금", "학과발전기금", "간호학과", now_str),
            ("UNIVERSITY", "현물기부금", "교육기자재", "실습기자재기증", now_str),
            ("FOUNDATION", "일반기부금", "발전기금", "법인발전기금", now_str),
            ("FOUNDATION", "지정기부금", "법정부담금", "법정부담금", now_str),
            ("FOUNDATION", "지정기부금", "수익사업", "수익사업지원", now_str)
        ]
        cursor.executemany("""
            INSERT INTO donation_purposes (entity_type, budget_subject, major_category, sub_category, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, defaults)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("SELECT COUNT(*) FROM entity_info WHERE entity_type = 'UNIVERSITY'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO entity_info (entity_type, org_name, biz_no, address, law_basis, updated_at)
            VALUES ('UNIVERSITY', 'OO대학교', '123-82-00000', '경상북도 영천시 대학로 123', '「법인세법」 제24조제2항제1호라목', ?)
        """, (now_str,))
    
    cursor.execute("SELECT COUNT(*) FROM entity_info WHERE entity_type = 'FOUNDATION'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO entity_info (entity_type, org_name, biz_no, address, law_basis, updated_at)
            VALUES ('FOUNDATION', '학교법인 OO학원', '123-82-99999', '경상북도 영천시 대학로 123', '「법인세법」 제24조제2항제1호라목', ?)
        """, (now_str,))

    # 요청 반영: 학교회계/법인회계 기존 발급번호 일괄 '미발급'으로 초기화
    cursor.execute("UPDATE donation_receipts SET receipt_no = '미발급'")

    conn.commit()
    conn.close()

init_db()

def get_entity_info(entity_type):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT org_name, biz_no, address, law_basis FROM entity_info WHERE entity_type = ?", (entity_type,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"org_name": row[0], "biz_no": row[1], "address": row[2], "law_basis": row[3]}
    return {
        "org_name": "OO대학교" if entity_type == "UNIVERSITY" else "학교법인 OO학원",
        "biz_no": "123-82-00000" if entity_type == "UNIVERSITY" else "123-82-99999",
        "address": "경상북도 영천시 대학로 123",
        "law_basis": "「법인세법」 제24조제2항제1호라목"
    }

def update_entity_info(entity_type, org_name, biz_no, address, law_basis):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO entity_info (entity_type, org_name, biz_no, address, law_basis, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(entity_type) DO UPDATE SET
            org_name = excluded.org_name,
            biz_no = excluded.biz_no,
            address = excluded.address,
            law_basis = excluded.law_basis,
            updated_at = excluded.updated_at
    """, (entity_type, org_name, biz_no, address, law_basis, now_str))
    conn.commit()
    conn.close()

def parse_money(val_str):
    if not val_str:
        return 0
    clean = re.sub(r'[^0-9]', '', str(val_str))
    return int(clean) if clean else 0

def format_money(val):
    try:
        num = int(val)
        return f"{num:,}"
    except Exception:
        return "0"

def mask_id_number(raw_id):
    if not raw_id:
        return ""
    clean = str(raw_id).strip().replace("-", "")
    if len(clean) == 13:
        return f"{clean[:6]}-{clean[6]}******"
    elif len(clean) == 10:
        return f"{clean[:3]}-{clean[3:5]}-{clean[5:]}"
    return f"{clean[:6]}******" if len(clean) > 6 else clean

def get_existing_fiscal_years(entity_type):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT fiscal_year FROM donation_receipts WHERE entity_type = ?", (entity_type,))
    years = [int(r[0]) for r in cursor.fetchall() if r[0] is not None]
    conn.close()
    
    now_year = datetime.now().year
    if now_year not in years:
        years.append(now_year)
    if (now_year - 1) not in years:
        years.append(now_year - 1)
    return sorted(list(set(years)), reverse=True)

def delete_donation_receipt(receipt_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA table_info(donation_expenses)")
        cols = [c[1] for c in cursor.fetchall()]
        if "receipt_id" in cols:
            cursor.execute("DELETE FROM donation_expenses WHERE receipt_id = ?", (receipt_id,))
        cursor.execute("DELETE FROM donation_receipts WHERE id = ?", (receipt_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_hierarchical_purposes(entity_type):
    conn = get_db_connection()
    df = pd.read_sql_query("""
        SELECT budget_subject, major_category, sub_category FROM donation_purposes 
        WHERE entity_type = ? ORDER BY budget_subject, major_category, sub_category
    """, conn, params=(entity_type,))
    conn.close()
    
    tree = {"일반기부금": {}, "지정기부금": {}, "현물기부금": {}}
    for _, row in df.iterrows():
        b_sub = row['budget_subject'] if row['budget_subject'] in tree else "일반기부금"
        maj = row['major_category']
        sub = row['sub_category']
        if maj not in tree[b_sub]:
            tree[b_sub][maj] = []
        if sub not in tree[b_sub][maj]:
            tree[b_sub][maj].append(sub)
    return tree

@st.dialog("🎉 일괄 기부금 수입 등록 완료")
def show_batch_success_modal(month_val, count_val, total_amt_val, fiscal_yr):
    st.success(f"**{fiscal_yr} 회계연도 [{month_val}월분] 기부금 수입이 등록되었습니다!**")
    st.markdown(f"""
    * **등록 인원:** 총 **{count_val}** 명
    * **수입 합계액:** **{total_amt_val:,.0f}** 원
    * **영수증 발급:** '기부영수증 발급' 탭에서 번호 부여 및 주소 입력이 가능합니다.
    """)
    if st.button("확인 및 닫기", type="primary", use_container_width=True):
        st.rerun()

# ==========================================
# 3. 글로벌 세션 상태 및 상단 미니 메뉴바
# ==========================================
if "current_page" not in st.session_state:
    st.session_state.current_page = "HOME"
if "selected_entity" not in st.session_state:
    st.session_state.selected_entity = None
if "selected_receipt_id_for_expense" not in st.session_state:
    st.session_state.selected_receipt_id_for_expense = None
if "editing_receipt_id" not in st.session_state:
    st.session_state.editing_receipt_id = None
if "editing_purpose_id" not in st.session_state:
    st.session_state.editing_purpose_id = None
if "config_grid_menu" not in st.session_state:
    st.session_state.config_grid_menu = "ENTITY"
if "fiscal_year" not in st.session_state:
    st.session_state.fiscal_year = datetime.now().year

m_col1, m_col2, m_col3, m_col4 = st.columns([3.5, 1.2, 1.6, 1.4])
with m_col1:
    st.markdown("<h4 style='margin:0; color:#0F172A;'>🏛️ 대학 행정 스마트 통합 포털</h4>", unsafe_allow_html=True)
with m_col2:
    if st.button("🏠 홈", use_container_width=True, type="primary" if st.session_state.current_page == "HOME" else "secondary"):
        st.session_state.current_page = "HOME"
        st.rerun()
with m_col3:
    if st.button("📊 데이터 스마트 검증기", use_container_width=True, type="primary" if st.session_state.current_page == "AUDIT" else "secondary"):
        st.session_state.current_page = "AUDIT"
        st.rerun()
with m_col4:
    if st.button("🎁 기부금 관리 시스템", use_container_width=True, type="primary" if st.session_state.current_page.startswith("DONATION") else "secondary"):
        st.session_state.current_page = "DONATION_SELECT"
        st.rerun()

st.markdown("<hr style='margin-top:6px; margin-bottom:18px; border-color:#E2E8F0;'>", unsafe_allow_html=True)

# ==========================================
# PAGE 1: 🏠 홈 대시보드
# ==========================================
if st.session_state.current_page == "HOME":
    st.markdown("""
    <div style="background-color:#EEF2FF; border:1px solid #C7D2FE; border-radius:12px; padding:18px 22px; margin-bottom:22px;">
        <div style="font-size:18px; font-weight:700; color:#1E1B4B;">반갑습니다, 교직원 업무 포털입니다 👋</div>
        <div style="font-size:13.5px; color:#4338CA; margin-top:4px;">
            원하시는 <b>시스템 제목을 클릭</b>하시면 해당 프로그램으로 바로 이동합니다.
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("#### 📂 주요 업무 시스템 바로가기")
    c_card1, c_card2 = st.columns(2)
    
    with c_card1:
        with st.container(border=True):
            st.markdown('<div class="equal-card-container">', unsafe_allow_html=True)
            st.markdown('<div class="title-link-container">', unsafe_allow_html=True)
            if st.button("📊 데이터 스마트 검증기 ➔", key="title_link_audit"):
                st.session_state.current_page = "AUDIT"
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            
            st.caption("학교 내부 원본 데이터 ↔ 대조 데이터 실시간 정합성 크로스체크")
            st.markdown("""
            * 대학 엑셀 시트 자동 로드 및 실시간 금액/항목 대조
            * 지능형 계정 매칭 엔진 & 1클릭 차액 오차 원인 진단
            * 엑셀형 대용량 스프레드시트 인라인 편집 및 매칭 영구 보존
            """)
            st.markdown('</div>', unsafe_allow_html=True)

    with c_card2:
        with st.container(border=True):
            st.markdown('<div class="equal-card-container">', unsafe_allow_html=True)
            st.markdown('<div class="title-link-container">', unsafe_allow_html=True)
            if st.button("🎁 기부금 관리 시스템 ➔", key="title_link_donation"):
                st.session_state.current_page = "DONATION_SELECT"
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            
            st.caption("대학 및 법인 기부금 수입·정기약정·원천별 지출·발급명세 통합 관리")
            st.markdown("""
            * **회계연도별 독립 관리** (연도별 분리 집계 및 정산)
            * **기부일자순 영수증 번호 수동 지정 부여 및 법정 서식 실시간 출력**[cite: 1]
            * 교직원 급여공제 및 정기 약정자 관리 & 1클릭 당월 수입 일괄 생성
            * 국세청 법정 기부금영수증 & 사용 용도별 집행 정산표 엑셀 다운로드
            """)
            st.markdown('</div>', unsafe_allow_html=True)

# ==========================================
# PAGE 2: 🎁 기부금 관리 - 회계 분리 선택 화면
# ==========================================
elif st.session_state.current_page == "DONATION_SELECT":
    st.markdown('<div class="main-app-title">🎁 기부금 관리 시스템 - 회계 선택</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-app-caption">대학 회계와 법인 회계는 회계연도 및 데이터가 철저히 분리 운영됩니다. 작업하실 <b>회계 제목을 클릭</b>해 주세요.</div>', unsafe_allow_html=True)

    e_col1, e_col2 = st.columns(2)
    with e_col1:
        with st.container(border=True):
            st.markdown('<div class="equal-card-container">', unsafe_allow_html=True)
            st.markdown('<div class="title-link-container">', unsafe_allow_html=True)
            if st.button("🏫 대학 회계 기부금 관리 ➔", key="title_link_univ"):
                st.session_state.selected_entity = "UNIVERSITY"
                st.session_state.current_page = "DONATION_WORKSPACE"
                st.session_state.editing_receipt_id = None
                st.session_state.editing_purpose_id = None
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            
            st.caption("대학(교비회계)으로 접수된 일반/지정/현물 기부금 전용")
            st.markdown("""
            * 회계연도별(3월~익년 2월) 기부금 수입 및 학생 장학/학과 지출 관리
            * 교직원 급여공제 정기기부 약정자 명단 등록 및 매월 일괄 수입 자동 생성
            * 예산과목 ➔ 대분류 ➔ 소분류 계층형 용도 분류 연동
            * 수입 등록·수정·삭제 관리 및 수입 합계 실시간 결산
            * 국세청 법정 기부영수증(코드 10) 및 용도별 정산표 엑셀 다운로드[cite: 1]
            """)
            st.markdown('</div>', unsafe_allow_html=True)

    with e_col2:
        with st.container(border=True):
            st.markdown('<div class="equal-card-container">', unsafe_allow_html=True)
            st.markdown('<div class="title-link-container">', unsafe_allow_html=True)
            if st.button("🏛️ 법인 회계 기부금 관리 ➔", key="title_link_found"):
                st.session_state.selected_entity = "FOUNDATION"
                st.session_state.current_page = "DONATION_WORKSPACE"
                st.session_state.editing_receipt_id = None
                st.session_state.editing_purpose_id = None
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            
            st.caption("학교법인으로 접수된 기부금 및 법정부담금 전출 특화 관리")
            st.markdown("""
            * 회계연도별(3월~익년 2월) 법인 발전기금 및 법인 지정기부금 독립 관리
            * 법인 전용 3단계 용도 분류 체계 관리 (발전기금, 법정부담금, 수익사업지원 등)
            * **법정부담금 전출용** 기부금 수입 및 학교 전출 지출 매핑 관리
            * 법인 세무 신고용 영수증 및 발급명세서 생성
            """)
            st.markdown('</div>', unsafe_allow_html=True)

# ==========================================
# PAGE 3: 🎁 기부금 관리 - 독립 작업 화면
# ==========================================
elif st.session_state.current_page == "DONATION_WORKSPACE":
    current_entity = st.session_state.selected_entity or "UNIVERSITY"
    entity_label = "🏫 대학 회계" if current_entity == "UNIVERSITY" else "🏛️ 법인 회계"
    
    top_c1, top_c2, top_c3 = st.columns([3, 1.8, 1.2])
    with top_c1:
        st.markdown(f'<div class="main-app-title">🎁 기부금 관리 시스템 [{entity_label}]</div>', unsafe_allow_html=True)
        st.markdown('<div class="main-app-caption">기부금 수입 등록·수정·삭제, 기준정보 환경설정, 지출 매핑 및 결산을 수행합니다.</div>', unsafe_allow_html=True)

    with top_c2:
        available_years = get_existing_fiscal_years(current_entity)
        if st.session_state.fiscal_year not in available_years:
            st.session_state.fiscal_year = available_years[0]

        sel_year = st.selectbox(
            "📅 작업 회계연도",
            available_years,
            index=available_years.index(st.session_state.fiscal_year),
            format_func=lambda y: f"{y} 회계연도"
        )
        if sel_year != st.session_state.fiscal_year:
            st.session_state.fiscal_year = sel_year
            st.session_state.editing_receipt_id = None
            st.session_state.editing_purpose_id = None
            st.rerun()

    with top_c3:
        st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 다른 회계로 전환", use_container_width=True):
            st.session_state.current_page = "DONATION_SELECT"
            st.session_state.editing_receipt_id = None
            st.session_state.editing_purpose_id = None
            st.rerun()

    current_year = st.session_state.fiscal_year

    with st.popover("➕ 새 회계연도 추가"):
        new_year_input = st.number_input("추가할 회계연도 입력 (4자리)", min_value=2000, max_value=2099, value=current_year + 1)
        if st.button("회계연도 추가 및 전환", use_container_width=True, type="primary"):
            st.session_state.fiscal_year = int(new_year_input)
            st.session_state.editing_receipt_id = None
            st.session_state.editing_purpose_id = None
            st.success(f"{new_year_input} 회계연도로 전환되었습니다.")
            st.rerun()

    conn = get_db_connection()
    receipts_df = pd.read_sql_query("""
        SELECT * FROM donation_receipts 
        WHERE entity_type = ? AND fiscal_year = ? 
        ORDER BY donation_date ASC, id ASC
    """, conn, params=(current_entity, current_year))
    
    expenses_df = pd.read_sql_query("""
        SELECT * FROM donation_expenses 
        WHERE entity_type = ? AND fiscal_year = ? 
        ORDER BY expense_date ASC, id ASC
    """, conn, params=(current_entity, current_year))

    pledges_df = pd.read_sql_query("""
        SELECT * FROM donation_pledges 
        WHERE entity_type = ?
        ORDER BY id ASC
    """, conn, params=(current_entity,))
    conn.close()

    purpose_tree = get_hierarchical_purposes(current_entity)
    entity_data = get_entity_info(current_entity)

    total_income = receipts_df['amount'].sum() if not receipts_df.empty else 0.0
    total_expense = expenses_df['amount'].sum() if not expenses_df.empty else 0.0
    balance = total_income - total_expense

    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"""<div class="kpi-card"><div style="color:#64748B; font-size:11.5px; font-weight:600;">{current_year}년 총 수입 합계</div><div class="kpi-val" style="color:#2563EB;">{total_income:,.0f} 원</div></div>""", unsafe_allow_html=True)
    k2.markdown(f"""<div class="kpi-card"><div style="color:#64748B; font-size:11.5px; font-weight:600;">{current_year}년 총 지출액</div><div class="kpi-val" style="color:#DC2626;">{total_expense:,.0f} 원</div></div>""", unsafe_allow_html=True)
    k3.markdown(f"""<div class="kpi-card"><div style="color:#64748B; font-size:11.5px; font-weight:600;">{current_year}년 집행 잔액</div><div class="kpi-val" style="color:#059669;">{balance:,.0f} 원</div></div>""", unsafe_allow_html=True)
    k4.markdown(f"""<div class="kpi-card"><div style="color:#64748B; font-size:11.5px; font-weight:600;">수입 등록 건수</div><div class="kpi-val" style="color:#0F172A;">{len(receipts_df)} 건</div></div>""", unsafe_allow_html=True)

    if current_entity == "FOUNDATION":
        stat_inc = receipts_df[receipts_df['is_statutory_transfer'] == 1]['amount'].sum() if not receipts_df.empty else 0.0
        stat_exp = expenses_df[expenses_df['is_statutory_transfer'] == 1]['amount'].sum() if not expenses_df.empty else 0.0
        st.markdown(f"""
        <div class="kpi-card" style="margin-top:14px; border-left:5px solid #7C3AED; background-color:#FAF5FF;">
            <div style="font-size:13px; font-weight:700; color:#6B21A8;">🏛️ [법인 {current_year}년] 법정부담금 전출 특화 관리 현황</div>
            <div style="font-size:14px; color:#1E293B; margin-top:4px;">
                전출용 수입: <b>{stat_inc:,.0f} 원</b> ↔ 학교 전출 지출: <b>{stat_exp:,.0f} 원</b> (정산 잔액: <b>{stat_inc - stat_exp:,.0f} 원</b>)
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    tab_manage, tab_stmt, tab_official, tab_config = st.tabs([
        "📥 기부금 관리", 
        "📊 사용 용도별 집행 정산표",
        "📑 기부영수증 발급",
        "⚙️ 환경설정"
    ])

    # ==========================================
    # TAB 1: 📥 기부금 관리
    # ==========================================
    with tab_manage:
        edit_row = None
        if st.session_state.editing_receipt_id is not None:
            matched_edit = receipts_df[receipts_df['id'] == st.session_state.editing_receipt_id]
            if not matched_edit.empty:
                edit_row = matched_edit.iloc[0]
            else:
                st.session_state.editing_receipt_id = None

        is_edit_mode = (edit_row is not None)
        expander_title = f"✏️ [{edit_row['donor_name']}] 님의 기부금 수입 내역 수정 중" if is_edit_mode else f"➕ 새 기부금 수입 등록 ({current_year} 회계연도)"

        with st.expander(expander_title, expanded=True):
            if is_edit_mode:
                st.info(f"💡 현재 **[{edit_row['donor_name']} (발급번호: {edit_row['receipt_no']})]** 님의 내역을 수정하고 있습니다.")

            st.markdown("##### 1. 기부자 기본 정보")
            d1, d2, d3, d4 = st.columns(4)
            main_opts = ["개인", "기업체", "단체및기관"]
            def_main_idx = main_opts.index(edit_row['donor_main_type']) if is_edit_mode and edit_row['donor_main_type'] in main_opts else 0
            with d1:
                d_main_type = st.selectbox("기부자 구분 (상위)", main_opts, index=def_main_idx, key=f"dmt_{current_year}_{is_edit_mode}")

            sub_opts = ["교직원", "일반인"] if d_main_type == "개인" else ([d_main_type])
            def_sub_idx = sub_opts.index(edit_row['donor_sub_type']) if is_edit_mode and edit_row['donor_sub_type'] in sub_opts else 0
            with d2:
                d_sub_type = st.selectbox("기부자 구분 (하위)", sub_opts, index=def_sub_idx, key=f"dst_{current_year}_{is_edit_mode}")
            with d3:
                donor_name = st.text_input("기부자 성명 / 법인명", value=edit_row['donor_name'] if is_edit_mode else "", key=f"dn_{current_year}_{is_edit_mode}", placeholder="예: 홍길동 또는 (주)회사명")
            with d4:
                raw_id_no = st.text_input("주민등록번호 / 사업자번호", value=decode_data(edit_row['id_number_cipher']) if (is_edit_mode and 'id_number_cipher' in edit_row and edit_row['id_number_cipher']) else (edit_row['id_number_masked'] if is_edit_mode else ""), placeholder="예: 900101-1234567", type="password", help="영수증 출력 시 공개/비공개 토글이 가능합니다.", key=f"rid_{current_year}_{is_edit_mode}")

            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

            st.markdown("##### 2. 기부 내역 및 회계 분류")
            
            amt_key = f"da_str_{current_year}_{is_edit_mode}"
            def format_amt_callback():
                val = st.session_state.get(amt_key, "0")
                num = parse_money(val)
                st.session_state[amt_key] = f"{num:,}"

            row2_1_c1, row2_1_c2 = st.columns(2)
            with row2_1_c1:
                def_date = datetime.strptime(edit_row['donation_date'], "%Y-%m-%d") if is_edit_mode and edit_row['donation_date'] else datetime.now()
                d_date = st.date_input("기부일자 (영수증발급일 자동 동기화)", def_date, key=f"d_date_{current_year}_{is_edit_mode}")
            with row2_1_c2:
                if amt_key not in st.session_state:
                    st.session_state[amt_key] = format_money(edit_row['amount']) if is_edit_mode else "0"
                d_amt_input = st.text_input("기부 금액 (원) - 숫자 입력 후 엔터", key=amt_key, on_change=format_amt_callback)
                d_amt = parse_money(d_amt_input)
                st.caption(f"✓ 실제 인식 금액: **{d_amt:,} 원**")

            h_c1, h_c2, h_c3 = st.columns([1.5, 2, 2.5])
            with h_c1:
                b_opts = ["일반기부금", "지정기부금", "현물기부금"]
                def_b_idx = b_opts.index(edit_row['budget_subject']) if is_edit_mode and edit_row['budget_subject'] in b_opts else 0
                budget_subj = st.selectbox("예산과목", b_opts, index=def_b_idx, key=f"bs_{current_year}_{is_edit_mode}")

            maj_map = purpose_tree.get(budget_subj, {})
            avail_majors = list(maj_map.keys()) or ["기본"]

            with h_c2:
                maj_idx = 0
                if is_edit_mode:
                    for idx, m_name in enumerate(avail_majors):
                        if m_name in edit_row['purpose']:
                            maj_idx = idx
                            break
                chosen_maj = st.selectbox("대분류", avail_majors, index=maj_idx, key=f"hier_maj_{budget_subj}_{is_edit_mode}")

            with h_c3:
                sub_candidates = maj_map.get(chosen_maj, []) + ["기타(직접입력)"]
                sub_idx = 0
                if is_edit_mode:
                    for idx, s_name in enumerate(sub_candidates):
                        if s_name != "기타(직접입력)" and s_name in edit_row['purpose']:
                            sub_idx = idx
                            break
                    else:
                        if edit_row['purpose']:
                            sub_idx = len(sub_candidates) - 1

                chosen_sub = st.selectbox("소분류", sub_candidates, index=sub_idx, key=f"hier_sub_{chosen_maj}_{is_edit_mode}")
                if chosen_sub == "기타(직접입력)":
                    def_custom_val = edit_row['purpose'] if is_edit_mode else ""
                    custom_sub_text = st.text_input("상세 소분류 직접 입력", value=def_custom_val, placeholder="예: 상세 목적 또는 기부내역", key=f"cust_sub_{is_edit_mode}")
                    final_purpose = f"{chosen_maj} - {custom_sub_text.strip()}" if custom_sub_text.strip() else chosen_maj
                else:
                    final_purpose = f"{chosen_maj} - {chosen_sub}"

            row2_3_c1, row2_3_c2 = st.columns(2)
            with row2_3_c1:
                def_code = edit_row['code'] if is_edit_mode else "10"
                d_code = st.text_input("구분 코드 (법정 서식)", value=def_code, key=f"dc_{current_year}_{is_edit_mode}")
            with row2_3_c2:
                t_opts = ["금전", "현물"]
                def_t_idx = t_opts.index(edit_row['donation_type']) if is_edit_mode and edit_row['donation_type'] in t_opts else (1 if budget_subj == "현물기부금" else 0)
                d_type = st.selectbox("내용 구분 (금전/현물)", t_opts, index=def_t_idx, key=f"dt_{current_year}_{is_edit_mode}")

            is_stat_chk = 0
            if current_entity == "FOUNDATION":
                default_checked = True if (is_edit_mode and edit_row['is_statutory_transfer'] == 1) or ("법정부담금" in final_purpose) else False
                is_stat = st.checkbox("📌 법정부담금 전출용 기부금 여부", value=default_checked, key=f"is_stat_{current_year}_{is_edit_mode}")
                is_stat_chk = 1 if is_stat else 0

            btn_col1, btn_col2 = st.columns([1.6, 8.4])
            with btn_col1:
                submit_label = "💾 수정 내용 저장하기" if is_edit_mode else "💾 기부금 수입 등록"
                submit_income = st.button(submit_label, type="primary", use_container_width=True)
            with btn_col2:
                if is_edit_mode:
                    if st.button("❌ 수정 취소 (신규 등록 복귀)", use_container_width=False):
                        st.session_state.editing_receipt_id = None
                        st.rerun()

            if submit_income:
                if donor_name.strip() and d_amt > 0:
                    masked_id = mask_id_number(raw_id_no)
                    stored_cipher_id = encode_data(raw_id_no.strip())
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    assigned_rec_no = edit_row['receipt_no'] if is_edit_mode else "미발급"
                    existing_addr = edit_row['donor_address'] if is_edit_mode else ""

                    conn = get_db_connection()
                    cursor = conn.cursor()

                    if is_edit_mode:
                        cursor.execute("""
                            UPDATE donation_receipts SET
                                donation_date = ?, budget_subject = ?, purpose = ?,
                                donor_main_type = ?, donor_sub_type = ?, donor_name = ?,
                                id_number_masked = ?, id_number_cipher = ?, donation_type = ?,
                                code = ?, amount = ?, receipt_date = ?, is_statutory_transfer = ?
                            WHERE id = ?
                        """, (
                            str(d_date), budget_subj, final_purpose.strip() or "일반",
                            d_main_type, d_sub_type, donor_name.strip(),
                            masked_id, stored_cipher_id, d_type,
                            d_code.strip(), float(d_amt), str(d_date), is_stat_chk,
                            int(edit_row['id'])
                        ))
                        cursor.execute("UPDATE donation_expenses SET donor_name = ? WHERE receipt_id = ?", (donor_name.strip(), int(edit_row['id'])))
                        conn.commit()
                        conn.close()
                        st.session_state.editing_receipt_id = None
                        st.success(f"[{donor_name}] 님의 기부금 내역이 수정되었습니다!")
                        st.rerun()
                    else:
                        cursor.execute("""
                            INSERT INTO donation_receipts (
                                entity_type, fiscal_year, donation_date, budget_subject, purpose,
                                donor_main_type, donor_sub_type, donor_name,
                                id_number_masked, id_number_cipher, donation_type,
                                code, amount, receipt_no, receipt_date, donor_address, is_statutory_transfer, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            current_entity, current_year, str(d_date), budget_subj, final_purpose.strip() or "일반",
                            d_main_type, d_sub_type, donor_name.strip(),
                            masked_id, stored_cipher_id, d_type,
                            d_code.strip(), float(d_amt), assigned_rec_no, str(d_date), existing_addr, is_stat_chk, now_str
                        ))
                        new_receipt_id = cursor.lastrowid
                        conn.commit()
                        conn.close()
                        
                        st.session_state.selected_receipt_id_for_expense = new_receipt_id
                        st.success(f"[{current_year}년 {donor_name}] 님의 기부금 ({d_amt:,.0f}원) 등록 완료!")
                        st.rerun()
                else:
                    st.warning("기부자 성명과 기부 금액을 올바르게 입력해 주세요.")

        st.markdown(f"##### 📋 [{current_year} 회계연도] 기부금 수입 대장 및 관리")
        
        view_filter_col1, view_filter_col2 = st.columns([2, 5])
        with view_filter_col1:
            month_options = ["전체 (연간 총괄)", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월", "1월 (익년)", "2월 (익년)"]
            selected_view_month = st.selectbox("📅 조회 기간 (월별/전체)", month_options, index=0, key=f"v_month_{current_year}")

        filtered_receipts_df = receipts_df.copy()
        if selected_view_month != "전체 (연간 총괄)":
            m_target = selected_view_month.split("월")[0].strip()
            target_m_int = int(m_target)
            filtered_receipts_df = receipts_df[receipts_df['donation_date'].apply(
                lambda d: datetime.strptime(str(d)[:10], "%Y-%m-%d").month == target_m_int if pd.notna(d) and len(str(d)) >= 10 else False
            )]

        filtered_income = filtered_receipts_df['amount'].sum() if not filtered_receipts_df.empty else 0.0

        st.markdown(f"""
        <div class="total-banner">
            <div>
                <span style="font-size:14px; font-weight:700; color:#1E3A8A;">📊 [{selected_view_month}] 수입 집계:</span>
                <span style="font-size:13.5px; color:#475569; margin-left:8px;">조회 건수: <b>{len(filtered_receipts_df)}</b> 건</span>
            </div>
            <div>
                <span style="font-size:15px; font-weight:700; color:#1D4ED8;">수입 합계: {filtered_income:,.0f} 원</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        exp_totals = {}
        if not expenses_df.empty:
            for r_id, grp in expenses_df.groupby('receipt_id'):
                exp_totals[r_id] = grp['amount'].sum()

        if not filtered_receipts_df.empty:
            table_rows = []
            seq_num = 1
            for _, r in filtered_receipts_df.iterrows():
                r_id = int(r['id'])
                orig_a = r['amount']
                used_a = exp_totals.get(r_id, 0.0)
                rem_a = orig_a - used_a
                table_rows.append({
                    "연번": str(seq_num),
                    "수입ID": r_id,
                    "발급번호": r['receipt_no'],
                    "기부일자": r['donation_date'],
                    "기부자명": r['donor_name'],
                    "식별번호": r['id_number_masked'],
                    "예산과목": r['budget_subject'],
                    "사용용도": r['purpose'],
                    "기부수입액": int(round(orig_a)),
                    "지출누계": int(round(used_a)),
                    "남은잔액": int(round(rem_a))
                })
                seq_num += 1

            sum_income_val = sum([row["기부수입액"] for row in table_rows])
            sum_exp_val = sum([row["지출누계"] for row in table_rows])
            sum_rem_val = sum([row["남은잔액"] for row in table_rows])

            table_rows.append({
                "연번": "합계",
                "수입ID": 0,
                "발급번호": "-",
                "기부일자": "-",
                "기부자명": f"{len(table_rows)}건 총계",
                "식별번호": "-",
                "예산과목": "-",
                "사용용도": "-",
                "기부수입액": sum_income_val,
                "지출누계": sum_exp_val,
                "남은잔액": sum_rem_val
            })

            summary_table_df = pd.DataFrame(table_rows)

            valid_receipt_ids = [r_id for r_id in summary_table_df['수입ID'].tolist() if r_id != 0]
            if st.session_state.selected_receipt_id_for_expense not in valid_receipt_ids and valid_receipt_ids:
                st.session_state.selected_receipt_id_for_expense = valid_receipt_ids[0]

            st.dataframe(
                summary_table_df.drop(columns=['수입ID']),
                use_container_width=True,
                height=280,
                hide_index=True,
                column_config={
                    "연번": st.column_config.TextColumn("연번", width=60),
                    "발급번호": st.column_config.TextColumn("발급번호", width=100),
                    "기부일자": st.column_config.TextColumn("기부일자", width=110),
                    "기부자명": st.column_config.TextColumn("기부자명", width=130),
                    "식별번호": st.column_config.TextColumn("식별번호", width=140),
                    "예산과목": st.column_config.TextColumn("예산과목", width=110),
                    "사용용도": st.column_config.TextColumn("사용용도", width=160),
                    "기부수입액": st.column_config.NumberColumn("기부수입액 (원)", format="%,d", width=130),
                    "지출누계": st.column_config.NumberColumn("지출누계 (원)", format="%,d", width=130),
                    "남은잔액": st.column_config.NumberColumn("남은잔액 (원)", format="%,d", width=130)
                }
            )

            ctrl_c1, ctrl_c2, ctrl_c3 = st.columns([4, 1.2, 1.2])
            with ctrl_c1:
                sel_r_id = st.selectbox(
                    f"👇 [{selected_view_month}] 지출 등록 또는 관리할 기부금 건 선택:",
                    valid_receipt_ids,
                    index=valid_receipt_ids.index(st.session_state.selected_receipt_id_for_expense) if st.session_state.selected_receipt_id_for_expense in valid_receipt_ids else 0,
                    format_func=lambda x: f"연번 {summary_table_df[summary_table_df['수입ID']==x]['연번'].values[0]} | [{summary_table_df[summary_table_df['수입ID']==x]['발급번호'].values[0]}] {summary_table_df[summary_table_df['수입ID']==x]['기부자명'].values[0]} 님 | 수입: {summary_table_df[summary_table_df['수입ID']==x]['기부수입액'].values[0]:,}원 (잔액: {summary_table_df[summary_table_df['수입ID']==x]['남은잔액'].values[0]:,}원)",
                    key=f"sel_r_{current_year}"
                )
                st.session_state.selected_receipt_id_for_expense = sel_r_id

            target_action_row = summary_table_df[summary_table_df['수입ID'] == sel_r_id].iloc[0]

            with ctrl_c2:
                st.markdown("<div style='height:25px;'></div>", unsafe_allow_html=True)
                if st.button("✏️ 이 내역 수정", use_container_width=True, help="선택한 내역을 상단 폼으로 불러와 수정합니다."):
                    st.session_state.editing_receipt_id = sel_r_id
                    st.rerun()

            with ctrl_c3:
                st.markdown("<div style='height:25px;'></div>", unsafe_allow_html=True)
                with st.popover(f"🗑️ 선택 건 삭제"):
                    st.markdown(f"**[{target_action_row['기부자명']}] 님의 수입 내역 삭제**")
                    st.caption(f"발급번호: {target_action_row['발급번호']} | 금액: {target_action_row['기부수입액']:,}원")
                    st.warning("⚠️ 삭제 시 연결된 지출 내역도 함께 삭제됩니다.")
                    if st.button("확인 및 삭제", key=f"confirm_del_rec_{sel_r_id}", type="primary", use_container_width=True):
                        delete_donation_receipt(sel_r_id)
                        st.session_state.selected_receipt_id_for_expense = None
                        if st.session_state.editing_receipt_id == sel_r_id:
                            st.session_state.editing_receipt_id = None
                        st.success("삭제되었습니다.")
                        st.rerun()

            curr_rem_amt = int(target_action_row['남은잔액'])

            st.markdown("---")
            st.markdown(f"#### 📤 [{current_year}년 {target_action_row['기부자명']} 님의 기부금] 에서 지출(수혜) 내용 등록")
            st.markdown(f"""
            <div class="sub-box">
                <b>선택된 기부금:</b> {target_action_row['기부자명']} 님 (발급번호: {target_action_row['발급번호']} / 사용용도: {target_action_row['사용용도']})<br>
                <b>기부 원본액:</b> {target_action_row['기부수입액']:,} 원 &nbsp;|&nbsp; 
                <b>현재 남은 집행 잔액:</b> <span style="color:#059669; font-weight:700;">{curr_rem_amt:,} 원</span>
            </div>
            """, unsafe_allow_html=True)

            with st.form(key=f"form_direct_expense_{current_year}_{sel_r_id}"):
                ex1, ex2 = st.columns(2)
                with ex1:
                    e_date = st.date_input("지출일자", datetime.now(), key=f"ed_{current_year}_{sel_r_id}")
                    e_beneficiary = st.text_input("수혜자 성명/기관", placeholder="예: 최OO 학생, 기계공학과 등", key=f"eb_{current_year}_{sel_r_id}")
                with ex2:
                    e_amt_str = st.text_input("지출 금액 (원) - 숫자 입력 후 엔터", value="0", key=f"ea_str_{current_year}_{sel_r_id}")
                    e_amt = parse_money(e_amt_str)
                    st.caption(f"✓ 실제 인식 지출액: **{e_amt:,} 원** (최대 잔액: {curr_rem_amt:,}원)")
                    e_content = st.text_input("수혜 내용 (지출 사유)", placeholder="예: 2026학년도 1학기 등록금 지원", key=f"ec_{current_year}_{sel_r_id}")

                is_stat_exp = 0
                if current_entity == "FOUNDATION":
                    is_s_e = st.checkbox("📌 법정부담금 전출 지출 여부", key=f"es_{current_year}_{sel_r_id}")
                    is_stat_exp = 1 if is_s_e else 0

                submit_exp = st.form_submit_button("💾 해당 기부금에서 지출 등록 및 차감", type="primary", use_container_width=True)

                if submit_exp:
                    if e_beneficiary.strip() and e_amt > 0:
                        if e_amt > curr_rem_amt:
                            st.error(f"지출 금액({e_amt:,}원)이 기부금 잔액({curr_rem_amt:,}원)을 초과할 수 없습니다.")
                        else:
                            conn = get_db_connection()
                            cursor = conn.cursor()
                            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            cursor.execute("""
                                INSERT INTO donation_expenses (
                                    entity_type, fiscal_year, receipt_id, donor_name, expense_date,
                                    beneficiary, content, amount, is_statutory_transfer, created_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                current_entity, current_year, sel_r_id, target_action_row['기부자명'],
                                str(e_date), e_beneficiary.strip(), e_content.strip(),
                                float(e_amt), is_stat_exp, now_str
                            ))
                            conn.commit()
                            conn.close()
                            st.success(f"[{target_action_row['기부자명']} 님의 기부금]에서 [{e_beneficiary} 님에게 {e_amt:,.0f}원 지출] 등록 완료!")
                            st.rerun()
                    else:
                        st.warning("수혜자와 지출 금액을 올바르게 입력해 주세요.")

            cur_linked_expenses = expenses_df[expenses_df['receipt_id'] == sel_r_id]
            if not cur_linked_expenses.empty:
                st.markdown(f"**📌 [{current_year}년] {target_action_row['기부자명']} 님의 기부금에서 지출된 내역 ({len(cur_linked_expenses)}건)**")
                disp_linked = cur_linked_expenses[['expense_date', 'beneficiary', 'content', 'amount']].copy()
                disp_linked.columns = ['지출일자', '수혜자', '수혜 내용(사유)', '지출금액(원)']
                st.dataframe(
                    disp_linked,
                    use_container_width=True,
                    height=180,
                    hide_index=True,
                    column_config={
                        "지출금액(원)": st.column_config.NumberColumn("지출금액 (원)", format="%,d")
                    }
                )
            else:
                st.caption(f"아직 {target_action_row['기부자명']} 님의 기부금에서 집행된 지출 내역이 없습니다.")
        else:
            st.info(f"{current_year} 회계연도에 등록된 기부금 수입이 없습니다. 상단에서 기부금을 먼저 등록해 주세요.")

    # ==========================================
    # TAB 2: 📊 사용 용도별 집행 정산표
    # ==========================================
    with tab_stmt:
        st.markdown(f"#### 📊 [{current_year} 회계연도] 사용 용도별 집행 정산표")
        st.caption(f"{current_year} 회계연도에 접수된 기부금의 용도별 총 수입, 지출, 잔액 및 집행률을 결산합니다.")

        inc_p = receipts_df.groupby('purpose')['amount'].sum().reset_index() if not receipts_df.empty else pd.DataFrame(columns=['purpose', 'amount'])
        
        if not expenses_df.empty and not receipts_df.empty:
            exp_merged = pd.merge(
                expenses_df[['receipt_id', 'amount']], 
                receipts_df[['id', 'purpose']], 
                left_on='receipt_id', 
                right_on='id', 
                how='left'
            )
            exp_p = exp_merged.groupby('purpose', as_index=False)['amount'].sum()
        else:
            exp_p = pd.DataFrame(columns=['purpose', 'amount'])

        statement_df = pd.merge(inc_p, exp_p, on='purpose', how='outer', suffixes=('_수입', '_지출')).fillna(0)
        if 'amount_수입' not in statement_df.columns: statement_df['amount_수입'] = 0.0
        if 'amount_지출' not in statement_df.columns: statement_df['amount_지출'] = 0.0

        statement_df['집행잔액'] = statement_df['amount_수입'] - statement_df['amount_지출']
        statement_df['집행률(%)'] = statement_df.apply(
            lambda row: round((row['amount_지출'] / row['amount_수입'] * 100), 1) if row['amount_수입'] > 0 else 0.0, 
            axis=1
        )
        statement_df = statement_df[['purpose', 'amount_수입', 'amount_지출', '집행잔액', '집행률(%)']]
        statement_df.columns = ['사용 용도', '수입 총액 (원)', '지출 총액 (원)', '집행 잔액 (원)', '집행률 (%)']

        st.dataframe(
            statement_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                '수입 총액 (원)': st.column_config.NumberColumn(format="%,d"),
                '지출 총액 (원)': st.column_config.NumberColumn(format="%,d"),
                '집행 잔액 (원)': st.column_config.NumberColumn(format="%,d"),
                '집행률 (%)': st.column_config.NumberColumn(format="%.1f%%")
            }
        )

        buf_stmt = io.BytesIO()
        with pd.ExcelWriter(buf_stmt, engine='openpyxl') as writer:
            statement_df.to_excel(writer, index=False, sheet_name=f"{current_year}년_용도별정산표")
        buf_stmt.seek(0)

        st.download_button(
            label=f"📥 [{entity_label} {current_year}년] 용도별 집행 정산표 (.xlsx) 다운로드",
            data=buf_stmt,
            file_name=f"용도별_집행정산표_{current_entity}_{current_year}년.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True
        )

    # ==========================================
    # TAB 3: 📑 기부영수증 발급 (별지 제63호의3서식 정밀 복제 & 다건 2단 구조 보정)
    # ==========================================
    with tab_official:
        st.markdown(f"#### 📑 [{current_year} 회계연도] 기부영수증 발급 (법인세법 시행규칙 별지 제63호의3서식)[cite: 1]")
        st.caption("기부자를 검색하여 선택하고 주소를 입력한 뒤, 우측에서 법정 영수증 서식을 인쇄하거나 PDF로 저장합니다.")

        if not receipts_df.empty:
            left_col, right_col = st.columns([1, 1.25], gap="large")

            with left_col:
                st.markdown("##### 1. 대상 검색 및 발급정보 설정")
                
                # 표 외부 상단 주소 입력 블록
                with st.container(border=True):
                    st.markdown("###### 🏠 기부자 주소(소재지) 입력[cite: 1]")
                    addr_in_col, addr_btn_col = st.columns([3.2, 1.3])
                    with addr_in_col:
                        target_donor_for_addr = st.selectbox(
                            "주소를 등록/변경할 기부자 선택",
                            sorted(list(receipts_df['donor_name'].unique())),
                            key=f"sel_donor_for_addr_{current_year}"
                        )
                        curr_saved_addr = receipts_df[receipts_df['donor_name'] == target_donor_for_addr]['donor_address'].iloc[0]
                        input_addr_val = st.text_input(
                            "주소 입력",
                            value=curr_saved_addr if curr_saved_addr else "",
                            placeholder="예: 서울특별시 종로구 세종대로 123",
                            key=f"in_addr_text_{target_donor_for_addr}"
                        )
                    with addr_btn_col:
                        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
                        if st.button("💾 주소 저장", type="primary", use_container_width=True):
                            conn = get_db_connection()
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE donation_receipts 
                                SET donor_address = ? 
                                WHERE donor_name = ? AND entity_type = ?
                            """, (input_addr_val.strip(), target_donor_for_addr, current_entity))
                            conn.commit()
                            conn.close()
                            st.success(f"[{target_donor_for_addr}] 님의 주소가 저장되었습니다!")
                            st.rerun()

                # 발급번호 부여 및 초기화
                b_assign_c1, b_assign_c2, b_assign_c3 = st.columns([1.5, 2, 1.8])
                with b_assign_c1:
                    default_start_no = f"{str(current_year)[-2:]}-01"
                    start_no_input = st.text_input("시작 발급번호", value=default_start_no, key=f"start_no_{current_year}")
                with b_assign_c2:
                    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
                    if st.button("✍️ 기부일자순 번호 부여", type="primary", use_container_width=True):
                        sorted_records = receipts_df.sort_values(by=['donation_date', 'id'], ascending=[True, True])
                        try:
                            prefix, start_seq_str = start_no_input.split("-")
                            start_seq = int(start_seq_str)
                        except Exception:
                            prefix = str(current_year)[-2:]
                            start_seq = 1

                        conn = get_db_connection()
                        cursor = conn.cursor()
                        for idx, (_, r_item) in enumerate(sorted_records.iterrows()):
                            new_no = f"{prefix}-{(start_seq + idx):02d}"
                            cursor.execute("UPDATE donation_receipts SET receipt_no = ? WHERE id = ?", (new_no, int(r_item['id'])))
                        conn.commit()
                        conn.close()
                        st.success(f"'{start_no_input}'부터 번호가 일괄 부여되었습니다!")
                        st.rerun()
                with b_assign_c3:
                    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
                    if st.button("🗑️ 번호 전체 초기화", use_container_width=True):
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("UPDATE donation_receipts SET receipt_no = '미발급' WHERE entity_type = ? AND fiscal_year = ?", (current_entity, current_year))
                        conn.commit()
                        conn.close()
                        st.success("발급번호가 모두 '미발급'으로 초기화되었습니다!")
                        st.rerun()

                search_q = st.text_input("🔍 기부자 성명 / 법인명 검색", placeholder="검색할 기부자명을 입력하세요...", key=f"search_donor_{current_year}")

                table_prep = receipts_df[['id', 'receipt_no', 'donation_date', 'donor_name', 'amount', 'donor_address']].copy()
                table_prep['선택'] = False
                table_prep['donor_address'] = table_prep['donor_address'].fillna('')
                table_prep.rename(columns={
                    'receipt_no': '발급번호',
                    'donation_date': '기부일자',
                    'donor_name': '기부자명',
                    'amount': '기부금액',
                    'donor_address': '주소(소재지)'
                }, inplace=True)

                if search_q.strip():
                    table_prep = table_prep[table_prep['기부자명'].str.contains(search_q.strip(), na=False)]

                if not table_prep.empty:
                    table_prep.loc[table_prep.index[0], '선택'] = True

                edited_receipt_table = st.data_editor(
                    table_prep[['선택', 'id', '발급번호', '기부일자', '기부자명', '기부금액', '주소(소재지)']],
                    use_container_width=True,
                    height=360,
                    hide_index=True,
                    key=f"editor_rec_{current_year}",
                    column_config={
                        "선택": st.column_config.CheckboxColumn("선택", width=60),
                        "id": None,
                        "발급번호": st.column_config.TextColumn("발급번호 (직접수정)", width=110),
                        "기부일자": st.column_config.TextColumn("기부일자", width=95, disabled=True),
                        "기부자명": st.column_config.TextColumn("기부자명", width=90, disabled=True),
                        "기부금액": st.column_config.NumberColumn("기부금액", format="%,d", width=100, disabled=True),
                        "주소(소재지)": st.column_config.TextColumn("주소(소재지)", width=180, disabled=True)
                    }
                )

                if st.button("💾 표에서 수정한 발급번호 저장", use_container_width=True):
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    for _, e_row in edited_receipt_table.iterrows():
                        cursor.execute("""
                            UPDATE donation_receipts 
                            SET receipt_no = ? 
                            WHERE id = ?
                        """, (str(e_row['발급번호']).strip(), int(e_row['id'])))
                    conn.commit()
                    conn.close()
                    st.success("발급번호가 저장되었습니다!")
                    st.rerun()

            # 우측: 법인세법 시행규칙 [별지 제63호의3서식] 100% 정밀 복제 뷰어 (2단 테이블 완벽 구현)
            with right_col:
                st.markdown("##### 2. 기부금 영수증 법정 서식 뷰어[cite: 1]")
                
                v_ctrl1, v_ctrl2 = st.columns([1.5, 1.5])
                with v_ctrl1:
                    show_unmasked_id = st.checkbox("👁️ 식별번호 전체 공개 (인쇄/제출용)", value=False, help="마스킹을 해제하고 실제 번호를 표시합니다.[cite: 1]")
                with v_ctrl2:
                    custom_receipt_date = st.date_input("📅 영수증 발급일자 선택", datetime.now(), key=f"custom_r_date_{current_year}")

                selected_rows = edited_receipt_table[edited_receipt_table['선택'] == True]

                if selected_rows.empty:
                    st.warning("👈 좌측 표에서 영수증을 출력할 기부자 건을 체크해 주세요.")
                else:
                    org_name = entity_data['org_name']
                    org_biz_no = entity_data['biz_no']
                    org_addr = entity_data['address']
                    org_law = entity_data['law_basis']

                    y_str, m_str, day_str = custom_receipt_date.year, custom_receipt_date.month, custom_receipt_date.day

                    full_printable_html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>기부금영수증_인쇄</title>
<style>
    body { font-family: 'Malgun Gothic', '맑은 고딕', sans-serif; background:#FFF; margin:0; padding:15px; color:#000; }
    .receipt-container { border: 2px solid #000; padding: 22px; margin-bottom: 25px; background: #FFF; page-break-after: always; }
    .receipt-header { text-align: center; border-bottom: 1.5px solid #000; padding-bottom: 8px; margin-bottom: 12px; }
    .receipt-title { font-size: 22px; font-weight: 800; letter-spacing: 5px; }
    .receipt-table { width: 100%; border-collapse: collapse; margin-bottom: 10px; font-size: 11px; background: #FFF; }
    .receipt-table th, .receipt-table td { border: 1px solid #000; padding: 5px 6px; background: #FFF; }
    .receipt-table th { text-align: center; font-weight: 600; }
    .stamp-box { display: inline-block; width: 65px; height: 65px; border: 1px dashed #94A3B8; vertical-align: middle; line-height: 65px; text-align: center; font-size: 10px; color: #64748B; margin-left: 8px; }
    @media print {
        .receipt-container { page-break-after: always; border: 2px solid #000; }
    }
</style>
</head>
<body>
"""

                    selected_receipt_records = receipts_df[receipts_df['id'].isin(selected_rows['id'].tolist())]
                    donor_groups = selected_receipt_records.groupby('donor_name')

                    for donor_k, group_df in donor_groups:
                        first_item = group_df.iloc[0]
                        total_donor_amt = group_df['amount'].sum()
                        
                        # 식별번호 복호화 검증 (해시값일 경우 마스킹 번호로 안전 대치)
                        if show_unmasked_id and first_item['id_number_cipher']:
                            candidate_id = decode_data(first_item['id_number_cipher'])
                            if len(candidate_id) == 64 and re.match(r'^[0-9a-fA-F]+$', candidate_id):
                                display_id = first_item['id_number_masked']
                            else:
                                display_id = candidate_id
                        else:
                            display_id = first_item['id_number_masked']

                        curr_addr = first_item['donor_address'] if first_item['donor_address'] else "-"
                        rep_rec_no = first_item['receipt_no']

                        # 법정 서식 2단 격자 완벽 일치 데이터 행 생성
                        donation_rows_html = ""
                        for _, d_row in group_df.iterrows():
                            is_goods = (d_row["donation_type"] == "현물")
                            item_name_val = d_row["purpose"] if is_goods else ""
                            item_desc_val = d_row["purpose"] if is_goods else ""
                            item_qty_val = ""
                            item_price_val = ""
                            row_amt_str = f"{int(d_row['amount']):,}"

                            donation_rows_html += (
                                f'<tr>'
                                f'<td rowspan="2" style="border:1px solid #000; padding:4px; text-align:center;">{d_row["code"]}</td>'
                                f'<td rowspan="2" style="border:1px solid #000; padding:4px; text-align:center;">{d_row["donation_type"]}</td>'
                                f'<td rowspan="2" style="border:1px solid #000; padding:4px; text-align:center;">{d_row["donation_date"]}</td>'
                                f'<td style="border:1px solid #000; padding:4px; text-align:center;">{item_name_val}</td>'
                                f'<td style="border:1px solid #000; padding:4px; text-align:center;">{item_desc_val}</td>'
                                f'<td rowspan="2" style="border:1px solid #000; padding:4px; text-align:right; font-weight:700;">{row_amt_str}</td>'
                                f'</tr>'
                                f'<tr>'
                                f'<td style="border:1px solid #000; padding:4px; text-align:center;">{item_qty_val}</td>'
                                f'<td style="border:1px solid #000; padding:4px; text-align:center;">{item_price_val}</td>'
                                f'</tr>'
                            )

                        card_html = (
f'<div class="receipt-container" style="background:#FFF; border:2px solid #000; padding:22px; margin-bottom:18px; font-family:sans-serif; color:#000;">'
f'<div style="font-size:10px; color:#475569; display:flex; justify-content:space-between; margin-bottom:4px;">'
f'<span>■ 법인세법 시행규칙 [별지 제63호의3서식] &lt;개정 2023.3.20.&gt;[cite: 1]</span>'
f'<span>(앞쪽)[cite: 1]</span>'
f'</div>'
f'<div style="margin-bottom:8px;">'
f'<table style="border-collapse:collapse; font-size:11px;">'
f'<tr>'
f'<th style="border:1px solid #000; padding:3px 8px; background:#FFF; font-weight:700;">일련번호[cite: 1]</th>'
f'<td style="border:1px solid #000; padding:3px 12px; background:#FFF; font-weight:800; font-family:monospace;">{rep_rec_no}</td>'
f'</tr>'
f'</table>'
f'</div>'
f'<div class="receipt-header" style="text-align:center; border-bottom:1.5px solid #000; padding-bottom:8px; margin-bottom:12px;">'
f'<div class="receipt-title" style="font-size:22px; font-weight:800; letter-spacing:5px;">기부금 영수증</div>[cite: 1]'
f'</div>'
f'<div style="font-size:12px; font-weight:700; margin:6px 0 3px 0;">● 기부자[cite: 1]</div>'
f'<table class="receipt-table" style="width:100%; border-collapse:collapse; margin-bottom:8px; font-size:11px; background:#FFF;">'
f'<tr>'
f'<th style="border:1px solid #000; background:#FFF; padding:5px; width:22%;">성명(법인명)[cite: 1]</th>'
f'<td style="border:1px solid #000; padding:5px; width:28%; text-align:center; font-weight:700;">{first_item["donor_name"]}</td>'
f'<th style="border:1px solid #000; background:#FFF; padding:5px; width:25%;">주민등록번호<br>(사업자등록번호)[cite: 1]</th>'
f'<td style="border:1px solid #000; padding:5px; width:25%; text-align:center; font-family:monospace; font-weight:600;">{display_id}</td>'
f'</tr>'
f'<tr>'
f'<th style="border:1px solid #000; background:#FFF; padding:5px;">주소(소재지)[cite: 1]</th>'
f'<td colspan="3" style="border:1px solid #000; padding:5px; text-align:center;">{curr_addr}</td>'
f'</tr>'
f'</table>'
f'<div style="font-size:12px; font-weight:700; margin:6px 0 3px 0;">● 기부금 단체[cite: 1]</div>'
f'<table class="receipt-table" style="width:100%; border-collapse:collapse; margin-bottom:4px; font-size:11px; background:#FFF;">'
f'<tr>'
f'<th style="border:1px solid #000; background:#FFF; padding:5px; width:22%;">단체명[cite: 1]</th>'
f'<td style="border:1px solid #000; padding:5px; width:28%; text-align:center; font-weight:600;">{org_name}</td>'
f'<th style="border:1px solid #000; background:#FFF; padding:5px; width:25%;">사업자등록번호(고유번호)[cite: 1]</th>'
f'<td style="border:1px solid #000; padding:5px; width:25%; text-align:center; font-family:monospace;">{org_biz_no}</td>'
f'</tr>'
f'<tr>'
f'<th style="border:1px solid #000; background:#FFF; padding:5px;">(지점명)[cite: 1]</th>'
f'<td style="border:1px solid #000; padding:5px; text-align:center;"></td>'
f'<th style="border:1px solid #000; background:#FFF; padding:5px;">(지점 사업자등록번호 등)[cite: 1]</th>'
f'<td style="border:1px solid #000; padding:5px; text-align:center;"></td>'
f'</tr>'
f'<tr>'
f'<th style="border:1px solid #000; background:#FFF; padding:5px;">소재지[cite: 1]</th>'
f'<td style="border:1px solid #000; padding:5px; text-align:center;">{org_addr}</td>'
f'<th style="border:1px solid #000; background:#FFF; padding:5px;">기부금공제대상 공익법인등 근거법령[cite: 1]</th>'
f'<td style="border:1px solid #000; padding:5px; text-align:center; font-size:10.5px;">{org_law}</td>'
f'</tr>'
f'<tr>'
f'<th style="border:1px solid #000; background:#FFF; padding:5px;">(지점 소재지)[cite: 1]</th>'
f'<td colspan="3" style="border:1px solid #000; padding:5px; text-align:center;"></td>'
f'</tr>'
f'</table>'
f'<div style="font-size:9.5px; color:#64748B; margin-bottom:8px;">* 기부금 단체의 지점(분사무소)이 기부받은 경우, 지점명 등을 추가로 기재할 수 있습니다.[cite: 1]</div>'
f'<div style="font-size:12px; font-weight:700; margin:6px 0 3px 0;">● 기부금 모집처(언론기관 등)[cite: 1]</div>'
f'<table class="receipt-table" style="width:100%; border-collapse:collapse; margin-bottom:8px; font-size:11px; background:#FFF;">'
f'<tr>'
f'<th style="border:1px solid #000; background:#FFF; padding:5px; width:22%;">단체명[cite: 1]</th>'
f'<td style="border:1px solid #000; padding:5px; width:28%; text-align:center;"></td>'
f'<th style="border:1px solid #000; background:#FFF; padding:5px; width:25%;">사업자등록번호[cite: 1]</th>'
f'<td style="border:1px solid #000; padding:5px; width:25%; text-align:center;"></td>'
f'</tr>'
f'<tr>'
f'<th style="border:1px solid #000; background:#FFF; padding:5px;">소재지[cite: 1]</th>'
f'<td colspan="3" style="border:1px solid #000; padding:5px; text-align:center;"></td>'
f'</tr>'
f'</table>'
f'<div style="font-size:12px; font-weight:700; margin:6px 0 3px 0;">● 기부내용[cite: 1]</div>'
f'<table class="receipt-table" style="width:100%; border-collapse:collapse; margin-bottom:8px; font-size:11px; background:#FFF;">'
f'<tr>'
f'<th rowspan="3" style="border:1px solid #000; background:#FFF; padding:4px; width:9%;">코드[cite: 1]</th>'
f'<th rowspan="3" style="border:1px solid #000; background:#FFF; padding:4px; width:13%;">구분<br>(금전 또는 현물)[cite: 1]</th>'
f'<th rowspan="3" style="border:1px solid #000; background:#FFF; padding:4px; width:15%;">연월일[cite: 1]</th>'
f'<th colspan="2" style="border:1px solid #000; background:#FFF; padding:4px;">내 &nbsp;&nbsp;&nbsp;&nbsp; 용[cite: 1]</th>'
f'<th rowspan="3" style="border:1px solid #000; background:#FFF; padding:4px; width:19%;">금액[cite: 1]</th>'
f'</tr>'
f'<tr>'
f'<th style="border:1px solid #000; background:#FFF; padding:4px; width:22%;">품명[cite: 1]</th>'
f'<th style="border:1px solid #000; background:#FFF; padding:4px; width:22%;">내용[cite: 1]</th>'
f'</tr>'
f'<tr>'
f'<th style="border:1px solid #000; background:#FFF; padding:4px;">수량[cite: 1]</th>'
f'<th style="border:1px solid #000; background:#FFF; padding:4px;">단가[cite: 1]</th>'
f'</tr>'
f'{donation_rows_html}'
f'<tr>'
f'<th colspan="3" style="border:1px solid #000; background:#FFF; padding:5px; text-align:center;">합 계 금 액[cite: 1]</th>'
f'<td colspan="2" style="border:1px solid #000; padding:5px; text-align:center;">-</td>'
f'<td style="border:1px solid #000; padding:5px; text-align:right; font-weight:800; font-size:12px;">{int(total_donor_amt):,}</td>'
f'</tr>'
f'</table>'
f'<div style="font-size:10.5px; margin-top:8px; text-align:justify; line-height:1.4;">'
f'「소득세법」 제34조, 「조세특례제한법」 제58조·제76조·제88조의4 및 「법인세법」 제24조에 따른 기부금을 위와 같이 기부하였음을 증명하여 주시기 바랍니다.[cite: 1]'
f'</div>'
f'<div style="margin-top:14px; text-align:right; font-size:11.5px;">'
f'<div>{y_str} 년 &nbsp;&nbsp;&nbsp;&nbsp; {m_str} 월 &nbsp;&nbsp;&nbsp;&nbsp; {day_str} 일[cite: 1]</div>'
f'<div style="margin-top:6px;">신청인 : &nbsp;&nbsp;<b>{first_item["donor_name"]}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; (서명 또는 인)[cite: 1]</div>'
f'</div>'
f'<div style="margin-top:14px; border-top:1.5px solid #000; padding-top:10px; text-align:center;">'
f'<div style="font-size:12px; font-weight:700;">위와 같이 기부금을 기부받았음을 증명합니다.[cite: 1]</div>'
f'<div style="font-size:12px; font-weight:600; margin:8px 0;">'
f'{y_str} 년 &nbsp;&nbsp;&nbsp;&nbsp; {m_str} 월 &nbsp;&nbsp;&nbsp;&nbsp; {day_str} 일[cite: 1]'
f'</div>'
f'<div style="display:flex; justify-content:center; align-items:center; margin-top:6px;">'
f'<span style="font-size:15px; font-weight:800;">기부금 수령인: &nbsp;&nbsp; {org_name}[cite: 1]</span>'
f'<div class="stamp-box" style="display:inline-block; width:65px; height:65px; border:1px dashed #94A3B8; vertical-align:middle; line-height:65px; text-align:center; font-size:10px; color:#64748B; margin-left:12px;">(인)[cite: 1]</div>'
f'</div>'
f'</div>'
f'<div style="font-size:9px; color:#64748B; text-align:right; margin-top:8px;">'
f'210mm×297mm[백상지 80g/㎡ 또는 중질지 80g/㎡][cite: 1]'
f'</div>'
f'</div>'
                        )
                        st.markdown(card_html, unsafe_allow_html=True)
                        full_printable_html += card_html

                    full_printable_html += """
</body>
</html>
"""
                    st.markdown("---")
                    
                    btn_col_p1, btn_col_p2 = st.columns(2)
                    with btn_col_p1:
                        st.download_button(
                            label=f"💾 선택 건 인쇄용 영수증(.html) 다운로드",
                            data=full_printable_html,
                            file_name=f"기부금영수증_{current_year}년_{len(donor_groups)}인.html",
                            mime="text/html",
                            type="primary",
                            use_container_width=True
                        )
                    with btn_col_p2:
                        st.components.v1.html(
                            f"""
                            <button onclick="parent.window.print()" style="width:100%; height:38px; background-color:#1E293B; color:#FFFFFF; border:none; border-radius:8px; font-weight:700; cursor:pointer;">
                                🖨️ 화면 바로 인쇄 (PDF 저장)
                            </button>
                            """,
                            height=45
                        )

            st.markdown("---")
            st.markdown("##### 📥 국세청 법정 기부자별 발급명세서 엑셀 다운로드")
            summary_donor = receipts_df.groupby(['donor_name', 'id_number_masked', 'code']).agg(
                건수=('amount', 'count'),
                총금액=('amount', 'sum')
            ).reset_index()
            summary_donor.columns = ['기부자 성명', '주민등록번호(마스킹)', '기부유형코드', '발급건수', '기부금액 합계']

            buf_donor = io.BytesIO()
            with pd.ExcelWriter(buf_donor, engine='openpyxl') as writer:
                summary_donor.to_excel(writer, index=False, sheet_name="기부자별발급명세서")
            buf_donor.seek(0)

            st.download_button(
                label=f"📥 [{current_year}년] 기부자별 발급명세서 (.xlsx) 다운로드",
                data=buf_donor,
                file_name=f"기부자별발급명세서_{current_entity}_{current_year}년.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )
        else:
            st.info(f"{current_year} 회계연도에 등록된 기부금 수입 내역이 없습니다.")

    # ==========================================
    # TAB 4: ⚙️ 환경설정
    # ==========================================
    with tab_config:
        st.markdown(f"#### ⚙️ [{entity_label}] 기준정보 환경설정 및 관리")
        st.caption("기부금 단체 발행처 정보, 예산과목별 기부 용도 체계 및 정기 약정자를 관리합니다.")

        g_c1, g_c2, g_c3 = st.columns(3)
        with g_c1:
            if st.button("🏛️ 기부금 단체 기본정보 설정", use_container_width=True, type="primary" if st.session_state.config_grid_menu == "ENTITY" else "secondary"):
                st.session_state.config_grid_menu = "ENTITY"
                st.rerun()
        with g_c2:
            if st.button("🏷️ 기부 용도 분류 체계 관리", use_container_width=True, type="primary" if st.session_state.config_grid_menu == "PURPOSE" else "secondary"):
                st.session_state.config_grid_menu = "PURPOSE"
                st.rerun()
        with g_c3:
            if st.button("📅 정기 기부(약정)자 관리", use_container_width=True, type="primary" if st.session_state.config_grid_menu == "PLEDGE" else "secondary"):
                st.session_state.config_grid_menu = "PLEDGE"
                st.rerun()

        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

        # 1. 🏛️ 기부금 단체 기본정보 설정
        if st.session_state.config_grid_menu == "ENTITY":
            st.markdown(f"##### 🏛️ [{entity_label}] 법정 영수증 발행 단체 정보 설정[cite: 1]")
            st.caption("여기서 저장된 정보는 영수증 출력 시 단체명, 사업자번호, 소재지, 근거법령 및 수령인 서명란에 영구 연동됩니다.[cite: 1]")

            with st.container(border=True):
                info_c1, info_c2 = st.columns(2)
                with info_c1:
                    new_org_name = st.text_input("단체명 (영수증 수령인명)[cite: 1]", value=entity_data['org_name'], key="set_org_name")
                    new_biz_no = st.text_input("사업자등록번호 (고유번호)[cite: 1]", value=entity_data['biz_no'], key="set_biz_no")
                with info_c2:
                    new_addr = st.text_input("단체 소재지 (주소)[cite: 1]", value=entity_data['address'], key="set_org_addr")
                    new_law = st.text_input("기부금공제대상 근거법령[cite: 1]", value=entity_data['law_basis'], key="set_org_law")

                if st.button("💾 기부금 단체 정보 영구 저장", type="primary", use_container_width=True):
                    update_entity_info(current_entity, new_org_name.strip(), new_biz_no.strip(), new_addr.strip(), new_law.strip())
                    st.success(f"[{entity_label}] 단체 정보가 안전하게 영구 저장되었습니다!")
                    st.rerun()

        # 2. 🏷️ 기부 용도 분류 체계 관리
        elif st.session_state.config_grid_menu == "PURPOSE":
            st.markdown("##### 🏷️ 기부 용도 분류 체계 등록 및 수정")

            conn = get_db_connection()
            purp_df = pd.read_sql_query("""
                SELECT id, budget_subject, major_category, sub_category, created_at FROM donation_purposes
                WHERE entity_type = ? ORDER BY budget_subject, major_category, sub_category
            """, conn, params=(current_entity,))
            conn.close()

            edit_p_row = None
            if st.session_state.editing_purpose_id is not None:
                matched_p = purp_df[purp_df['id'] == st.session_state.editing_purpose_id]
                if not matched_p.empty:
                    edit_p_row = matched_p.iloc[0]
                else:
                    st.session_state.editing_purpose_id = None

            is_edit_p_mode = (edit_p_row is not None)
            p_expander_title = f"✏️ 용도 분류 항목 수정 중: [{edit_p_row['budget_subject']} > {edit_p_row['major_category']} > {edit_p_row['sub_category']}]" if is_edit_p_mode else "➕ 새 용도 분류 항목 추가"

            with st.expander(p_expander_title, expanded=True):
                b_opts_list = ["일반기부금", "지정기부금", "현물기부금"]

                if is_edit_p_mode:
                    st.info(f"💡 현재 **[{edit_p_row['budget_subject']} > {edit_p_row['major_category']} > {edit_p_row['sub_category']}]** 항목을 수정 중입니다.")
                    u_b1, u_b2, u_b3 = st.columns(3)
                    with u_b1:
                        def_b_idx = b_opts_list.index(edit_p_row['budget_subject']) if edit_p_row['budget_subject'] in b_opts_list else 0
                        target_b = st.selectbox("최상위 예산과목", b_opts_list, index=def_b_idx, key="edit_purp_b")
                    with u_b2:
                        target_maj = st.text_input("대분류 명칭", value=edit_p_row['major_category'], key="edit_purp_maj")
                    with u_b3:
                        target_sub = st.text_input("소분류 명칭", value=edit_p_row['sub_category'], key="edit_purp_sub")

                    p_btn1, p_btn2 = st.columns([1.8, 8.2])
                    with p_btn1:
                        if st.button("💾 수정 내용 저장", type="primary", use_container_width=True):
                            if target_maj.strip() and target_sub.strip():
                                conn = get_db_connection()
                                cursor = conn.cursor()
                                cursor.execute("""
                                    UPDATE donation_purposes 
                                    SET budget_subject = ?, major_category = ?, sub_category = ?
                                    WHERE id = ?
                                """, (target_b, target_maj.strip(), target_sub.strip(), int(edit_p_row['id'])))
                                conn.commit()
                                conn.close()
                                st.session_state.editing_purpose_id = None
                                st.success("수정되었습니다.")
                                st.rerun()
                            else:
                                st.warning("대분류와 소분류 명칭을 모두 입력해 주세요.")
                    with p_btn2:
                        if st.button("❌ 수정 취소", use_container_width=False):
                            st.session_state.editing_purpose_id = None
                            st.rerun()

                else:
                    target_b = st.selectbox("1. 최상위 예산과목 선택", b_opts_list, key="add_new_budget_choice")
                    
                    sub_dict_for_b = purpose_tree.get(target_b, {})
                    existing_majors_in_b = list(sub_dict_for_b.keys())

                    maj_mode = st.radio("2. 대분류 선택 방식", ["기존 대분류 선택", "새 대분류 직접입력"], horizontal=True, key="maj_mode_hier")
                    
                    u_c1, u_c2 = st.columns(2)
                    with u_c1:
                        if maj_mode == "기존 대분류 선택" and existing_majors_in_b:
                            target_maj = st.selectbox("대분류", existing_majors_in_b, key="add_exist_maj_hier")
                        else:
                            target_maj = st.text_input("대분류", placeholder="예: 대학발전기금, 장학기금", key="add_new_maj_hier")
                    with u_c2:
                        target_sub = st.text_input("소분류", placeholder="예: 시설확충, 학과발전, 성적우수장학", key="add_new_sub_hier")

                    if st.button("💾 용도 분류 추가", type="primary", use_container_width=True):
                        if target_maj.strip() and target_sub.strip():
                            conn = get_db_connection()
                            cursor = conn.cursor()
                            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            cursor.execute("""
                                INSERT INTO donation_purposes (entity_type, budget_subject, major_category, sub_category, created_at)
                                VALUES (?, ?, ?, ?, ?)
                            """, (current_entity, target_b, target_maj.strip(), target_sub.strip(), now_str))
                            conn.commit()
                            conn.close()
                            st.success(f"[{target_b} > {target_maj.strip()} > {target_sub.strip()}] 분류가 추가되었습니다.")
                            st.rerun()
                        else:
                            st.warning("대분류와 소분류를 모두 입력해 주세요.")

            if not purp_df.empty:
                disp_purp = purp_df.copy()
                disp_purp['연번'] = range(1, len(disp_purp) + 1)
                st.dataframe(
                    disp_purp[['연번', 'budget_subject', 'major_category', 'sub_category', 'created_at']],
                    use_container_width=True,
                    height=240,
                    hide_index=True,
                    column_config={
                        "연번": st.column_config.NumberColumn("연번", width=60),
                        "budget_subject": st.column_config.TextColumn("예산과목", width=120),
                        "major_category": st.column_config.TextColumn("대분류", width=160),
                        "sub_category": st.column_config.TextColumn("소분류", width=200),
                        "created_at": st.column_config.TextColumn("등록일시", width=150)
                    }
                )

                del_c1, del_c2, del_c3 = st.columns([3.5, 1.2, 1.2])
                with del_c1:
                    sel_p_id = st.selectbox(
                        "관리할 분류 항목 선택",
                        purp_df['id'].tolist(),
                        format_func=lambda x: f"[{purp_df[purp_df['id']==x]['budget_subject'].values[0]}] {purp_df[purp_df['id']==x]['major_category'].values[0]} ➔ {purp_df[purp_df['id']==x]['sub_category'].values[0]}",
                        key="sel_purp_manage"
                    )
                with del_c2:
                    st.markdown("<div style='height:25px;'></div>", unsafe_allow_html=True)
                    if st.button("✏️ 이 항목 수정", use_container_width=True):
                        st.session_state.editing_purpose_id = sel_p_id
                        st.rerun()

                with del_c3:
                    st.markdown("<div style='height:25px;'></div>", unsafe_allow_html=True)
                    if st.button("🗑️ 선택 항목 삭제", type="secondary", use_container_width=True):
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM donation_purposes WHERE id = ?", (sel_p_id,))
                        conn.commit()
                        conn.close()
                        if st.session_state.editing_purpose_id == sel_p_id:
                            st.session_state.editing_purpose_id = None
                        st.success("해당 용도 분류가 삭제되었습니다.")
                        st.rerun()

        # 3. 📅 정기 기부(약정)자 관리
        else:
            st.markdown(f"##### 📅 [{entity_label}] 정기 기부(약정)자 명단 등록 및 당월 수입 일괄 생성")
            
            with st.expander("➕ 새 정기 기부(약정)자 등록", expanded=pledges_df.empty):
                st.markdown("##### 1. 기부자 기본 정보")
                pl_col1, pl_col2, pl_col3, pl_col4 = st.columns(4)
                with pl_col1:
                    pl_cat = st.selectbox("기부자 구분", ["교직원", "일반인", "기업/단체"], key="pl_cat_reg")
                with pl_col2:
                    meth_opts = ["급여공제", "직접입금"] if pl_cat == "교직원" else ["직접입금", "급여공제"]
                    pl_meth = st.selectbox("기부 방식", meth_opts, key="pl_meth_reg")
                with pl_col3:
                    pl_name = st.text_input("기부자명 (성명/법인명)", placeholder="예: 김교수, 이직원", key="pl_name_reg")
                with pl_col4:
                    pl_raw_id = st.text_input("주민등록번호 / 사업자번호", placeholder="예: 850315-1234567", type="password", help="마스킹 및 보관됩니다.", key="pl_id_reg")

                st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
                st.markdown("##### 2. 약정 금액 및 분납 조건")
                
                pl_tot_key = "pl_tot_str"
                pl_month_key = "pl_month_str"
                def format_pl_tot_callback():
                    val = st.session_state.get(pl_tot_key, "0")
                    num = parse_money(val)
                    st.session_state[pl_tot_key] = f"{num:,}"
                def format_pl_month_callback():
                    val = st.session_state.get(pl_month_key, "0")
                    num = parse_money(val)
                    st.session_state[pl_month_key] = f"{num:,}"

                pl_amt1, pl_amt2, pl_amt3 = st.columns(3)
                with pl_amt1:
                    if pl_tot_key not in st.session_state: st.session_state[pl_tot_key] = "0"
                    pl_tot_str = st.text_input("전체 약정액 (원) [선택] - 엔터", key=pl_tot_key, on_change=format_pl_tot_callback, help="정해진 총액 약정이 있는 경우 입력")
                    pl_tot = parse_money(pl_tot_str)
                    st.caption(f"✓ 전체 약정 인식: **{pl_tot:,} 원**")
                with pl_amt2:
                    pl_cnt = st.number_input("분납 횟수 (회)", min_value=0, max_value=240, value=0, help="0 입력 시 무기한 매월 정기 납부", key="pl_cnt_reg")
                    st.caption("0회: 무기한 정기 납부")
                with pl_amt3:
                    if pl_month_key not in st.session_state: st.session_state[pl_month_key] = "0"
                    pl_month_str = st.text_input("매월 약정액 (원) [필수] - 엔터", key=pl_month_key, on_change=format_pl_month_callback)
                    pl_month = parse_money(pl_month_str)
                    st.caption(f"✓ 매월 약정 인식: **{pl_month:,} 원**")

                st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
                st.markdown("##### 3. 기본 사용 용도 및 약정 상태")
                pl_st1, pl_st2 = st.columns([2, 1])
                with pl_st1:
                    all_sub_options = []
                    for b_name, majs in purpose_tree.items():
                        for m_name, subs in majs.items():
                            for s_item in subs:
                                all_sub_options.append(f"[{b_name}] {m_name} - {s_item}")
                    if not all_sub_options:
                        all_sub_options = ["대학발전기금" if current_entity == "UNIVERSITY" else "발전기금"]
                    all_sub_options.append("기타(직접입력)")

                    pl_purp_sel = st.selectbox("기본 사용 용도", all_sub_options, key="pl_purp_sel")
                    if pl_purp_sel == "기타(직접입력)":
                        pl_final_purpose = st.text_input("기타 상세 용도 직접 입력", placeholder="예: 지정 장학금", key="pl_purp_cust")
                    else:
                        pl_final_purpose = pl_purp_sel
                with pl_st2:
                    pl_status = st.selectbox("약정 상태", ["진행중", "일시중지", "약정종료"], key="pl_status_reg")

                if st.button("💾 정기 기부(약정)자 등록", type="primary", use_container_width=True):
                    if pl_name.strip() and pl_month > 0:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        cursor.execute("""
                            INSERT INTO donation_pledges (
                                entity_type, donor_category, payment_method, donor_name,
                                id_number_masked, id_number_cipher, total_pledge_amt, installment_count,
                                monthly_amt, default_purpose, status, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            current_entity, pl_cat, pl_meth, pl_name.strip(),
                            mask_id_number(pl_raw_id), encode_data(pl_raw_id.strip()),
                            float(pl_tot), int(pl_cnt), float(pl_month),
                            pl_final_purpose.strip() or "일반", pl_status, now_str
                        ))
                        conn.commit()
                        conn.close()
                        st.success(f"[{pl_name}] 님의 매월 {pl_month:,}원 정기 약정이 등록되었습니다!")
                        st.rerun()
                    else:
                        st.warning("기부자명과 매월 약정액을 정확히 입력해 주세요.")

            st.markdown("---")
            st.markdown(f"##### ⚡ [{current_year} 회계연도] 당월 정기 기부금(급여공제분) 일괄 수입 생성")
            
            active_pledges = pledges_df[pledges_df['status'] == '진행중'].copy() if not pledges_df.empty else pd.DataFrame()

            if not active_pledges.empty:
                bat_c0, bat_c1, bat_c2, bat_c3 = st.columns([1.5, 2, 2, 2])
                with bat_c0:
                    current_month = datetime.now().month
                    chosen_month = st.selectbox(
                        "생성 대상 월",
                        range(1, 13),
                        index=current_month - 1,
                        format_func=lambda m: f"{m}월분",
                        key="batch_chosen_month"
                    )
                with bat_c1:
                    try:
                        def_batch_d = date(current_year, chosen_month, 25)
                    except Exception:
                        def_batch_d = date(current_year, chosen_month, 28)
                    batch_date = st.date_input(f"{chosen_month}월 기부(급여)일자", def_batch_d, key=f"batch_donation_date_{chosen_month}")
                with bat_c2:
                    batch_filter = st.selectbox("대상 구분 필터", ["전체 진행중 약정자", "교직원만", "직접입금자만"], key="batch_filter")
                with bat_c3:
                    batch_budget = st.selectbox("일괄 적용 예산과목", ["일반기부금", "지정기부금"], key="batch_budget")

                filtered_pledges = active_pledges
                if batch_filter == "교직원만":
                    filtered_pledges = active_pledges[active_pledges['donor_category'] == '교직원']
                elif batch_filter == "직접입금자만":
                    filtered_pledges = active_pledges[active_pledges['payment_method'] == '직접입금']

                st.markdown(f"""
                <div class="total-banner">
                    <div>
                        <span style="font-size:14px; font-weight:700; color:#1E3A8A;">📋 [{chosen_month}월분] 생성 대상 집계:</span>
                        <span style="font-size:13.5px; color:#475569; margin-left:8px;">총 <b>{len(filtered_pledges)}</b> 명 선택됨</span>
                    </div>
                    <div>
                        <span style="font-size:15px; font-weight:700; color:#1D4ED8;">{chosen_month}월 일괄 수입 예정액: {filtered_pledges['monthly_amt'].sum():,.0f} 원</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                disp_p_df = filtered_pledges[['donor_name', 'donor_category', 'payment_method', 'monthly_amt', 'default_purpose', 'id_number_masked']].copy()
                disp_p_df.columns = ['기부자명', '기부자 구분', '기부방식', f'{chosen_month}월공제액(원)', '사용용도', '식별번호']
                st.dataframe(
                    disp_p_df,
                    use_container_width=True,
                    height=200,
                    hide_index=True,
                    column_config={
                        f"{chosen_month}월공제액(원)": st.column_config.NumberColumn(format="%,d")
                    }
                )

                if st.button(f"🚀 위 {len(filtered_pledges)}명 [{chosen_month}월분] 기부금 수입으로 일괄 생성 확정", type="primary", use_container_width=True):
                    if not filtered_pledges.empty:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        created_count = 0
                        total_batch_amt = filtered_pledges['monthly_amt'].sum()
                        for idx, (_, row) in enumerate(filtered_pledges.iterrows()):
                            d_main = "개인" if row['donor_category'] in ["교직원", "일반인"] else "기업체"
                            d_sub = row['donor_category']
                            is_stat_val = 1 if (current_entity == "FOUNDATION" and "법정부담금" in row['default_purpose']) else 0

                            cursor.execute("""
                                INSERT INTO donation_receipts (
                                    entity_type, fiscal_year, donation_date, budget_subject, purpose,
                                    donor_main_type, donor_sub_type, donor_name,
                                    id_number_masked, id_number_cipher, donation_type,
                                    code, amount, receipt_no, receipt_date, donor_address, is_statutory_transfer, created_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                current_entity, current_year, str(batch_date), batch_budget, row['default_purpose'],
                                d_main, d_sub, row['donor_name'],
                                row['id_number_masked'], row['id_number_cipher'], "금전",
                                "10", float(row['monthly_amt']), "미발급", str(batch_date), "", is_stat_val, now_str
                            ))
                            created_count += 1

                        conn.commit()
                        conn.close()
                        show_batch_success_modal(chosen_month, created_count, total_batch_amt, current_year)
                    else:
                        st.warning("선택된 대상자가 없습니다.")
            else:
                st.info("현재 등록된 '진행중' 약정자가 없습니다. 상단에서 약정자를 먼저 등록해 주세요.")

            st.markdown("---")
            st.markdown("##### 📋 전체 정기 기부(약정)자 명단 대장")
            if not pledges_df.empty:
                pledge_table = pledges_df.copy()
                pledge_table['연번'] = range(1, len(pledge_table) + 1)
                st.dataframe(
                    pledge_table[['연번', 'donor_name', 'donor_category', 'payment_method', 'total_pledge_amt', 'installment_count', 'monthly_amt', 'default_purpose', 'status']],
                    use_container_width=True,
                    height=220,
                    hide_index=True,
                    column_config={
                        "연번": st.column_config.NumberColumn(width=60),
                        "donor_name": st.column_config.TextColumn("기부자명", width=110),
                        "donor_category": st.column_config.TextColumn("기부자 구분", width=100),
                        "payment_method": st.column_config.TextColumn("기부방식", width=90),
                        "total_pledge_amt": st.column_config.NumberColumn("전체약정액 (원)", format="%,d", width=120),
                        "installment_count": st.column_config.NumberColumn("분납횟수", width=80),
                        "monthly_amt": st.column_config.NumberColumn("매월약정액 (원)", format="%,d", width=120),
                        "default_purpose": st.column_config.TextColumn("기본용도", width=140),
                        "status": st.column_config.TextColumn("상태", width=80)
                    }
                )

                pl_ctrl1, pl_ctrl2, pl_ctrl3 = st.columns([3, 1.5, 1.5])
                with pl_ctrl1:
                    sel_pledge_id = st.selectbox(
                        "약정 상태 변경 대상 선택",
                        pledges_df['id'].tolist(),
                        format_func=lambda x: f"[{pledges_df[pledges_df['id']==x]['donor_category'].values[0]}] {pledges_df[pledges_df['id']==x]['donor_name'].values[0]} 님 (월 {pledges_df[pledges_df['id']==x]['monthly_amt'].values[0]:,.0f}원 / 현재: {pledges_df[pledges_df['id']==x]['status'].values[0]})",
                        key="sel_pl_action"
                    )
                with pl_ctrl2:
                    new_st = st.selectbox("변경할 상태", ["진행중", "일시중지", "약정종료"], key="new_st_choice")
                    if st.button("상태 갱신", use_container_width=True):
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("UPDATE donation_pledges SET status = ? WHERE id = ?", (new_st, sel_pledge_id))
                        conn.commit()
                        conn.close()
                        st.success("약정 상태가 변경되었습니다.")
                        st.rerun()
                with pl_ctrl3:
                    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
                    if st.button("🗑️ 약정자 삭제", type="secondary", use_container_width=True):
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM donation_pledges WHERE id = ?", (sel_pledge_id,))
                        conn.commit()
                        conn.close()
                        st.success("약정자가 삭제되었습니다.")
                        st.rerun()
            else:
                st.caption("등록된 약정자가 없습니다.")

# ==========================================
# PAGE 4: 📊 데이터 스마트 검증기
# ==========================================
elif st.session_state.current_page == "AUDIT":
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
                VALUES (?, '기준 데이터', '대조 데이터', '{}', ?)
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
                "left_label": row[0] or "기준 데이터",
                "right_label": row[1] or "대조 데이터",
                "source_raw_blob": row[2],
                "target_raw_blob": row[3],
                "source_sheet_name": row[4],
                "target_sheet_name": row[5],
                "settings": settings
            }
        return {"left_label": "기준 데이터", "right_label": "대조 데이터", "source_raw_blob": None, "target_raw_blob": None, "source_sheet_name": None, "target_sheet_name": None, "settings": {}}

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

    projects_df = get_projects()
    with st.sidebar:
        st.markdown("#### 📂 대조 프로젝트 목록")
        with st.expander("➕ 새 프로젝트 추가", expanded=False):
            new_proj_name = st.text_input("새 프로젝트명", placeholder="예: 2026 원본대조 1차", key="new_proj_input_side")
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
    st.markdown(f'<div class="main-app-caption">📌 현재 프로젝트: <b>{selected_project_name}</b> | 두 원본 데이터 시트를 자유롭게 선택해 상호 대조·검증합니다.</div>', unsafe_allow_html=True)

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
            f"{left_label_input} 금액": int(round(s_val)),
            f"매칭 {right_label_input} 항목명": sel_match,
            f"{right_label_input} 금액": int(round(t_val)),
            "차액": int(round(diff)),
            "매칭유형": st_text
        })
    res_df = pd.DataFrame(matched_rows)

    border_c = "#059669" if abs(grand_diff) < 1 else "#DC2626"
    diff_txt = "총계 완벽 일치 (0원)" if abs(grand_diff) < 1 else f"총계 차액: {grand_diff:+,.0f} 원"
    st.markdown(f"""
    <div class="kpi-card" style="margin-bottom: 16px; border-left: 5px solid {border_c};">
        <div style="font-size: 13px; font-weight: 600; color: #64748B;">데이터 대조 정합성 현황 (공식 총계 행 기준)</div>
        <div style="font-size: 16px; font-weight: 700; color: #0F172A; margin-top: 4px;">
            {left_label_input} 총계: <b style="color:#1E40AF;">{official_s_total:,.0f} 원</b> ↔ 
            {right_label_input} 총계: <b style="color:#6D28D9;">{official_t_total:,.0f} 원</b> 
            &nbsp;<span style="color:{border_c}; font-size:15px;">[ {diff_txt} ]</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

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
            f"{left_label_input} 금액": st.column_config.NumberColumn(f"{left_label_input} 금액 (원)", format="%,d", width=135, disabled=True),
            t_col_title: st.column_config.SelectboxColumn(f"매칭 {right_label_input} 항목명 (더블클릭)", options=target_options, required=True, width=210),
            f"{right_label_input} 금액": st.column_config.NumberColumn(f"{right_label_input} 금액 (원)", format="%,d", width=135, disabled=True),
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
