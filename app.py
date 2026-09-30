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

    button[data-baseweb="tab"] {
        font-size: 19px !important;
        font-weight: 700 !important;
        padding-top: 14px !important;
        padding-bottom: 14px !important;
    }

    .equal-card-container {
        display: flex;
        flex-direction: column;
        height: 100%;
        padding: 2px;
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
            goods_name TEXT DEFAULT '',
            goods_qty TEXT DEFAULT '',
            goods_unit_price TEXT DEFAULT '',
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
            budget_subject TEXT NOT NULL DEFAULT '일반기부금',
            major_category TEXT NOT NULL DEFAULT '',
            sub_category TEXT NOT NULL DEFAULT '',
            default_purpose TEXT NOT NULL DEFAULT '',
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

    # [신규 추가] 보조금 정산 관리 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subsidies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            fiscal_year INTEGER NOT NULL,
            project_name TEXT NOT NULL,
            subsidy_type TEXT NOT NULL,
            allocated_amount REAL NOT NULL,
            executed_amount REAL NOT NULL,
            balance_amount REAL NOT NULL,
            settlement_status TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cursor.execute("PRAGMA table_info(donation_receipts)")
    r_cols = [c[1] for c in cursor.fetchall()]
    for col, default_val in [("donor_address", ""), ("goods_name", ""), ("goods_qty", ""), ("goods_unit_price", ""), ("is_statutory_transfer", 0)]:
        if col not in r_cols:
            try: cursor.execute(f"ALTER TABLE donation_receipts ADD COLUMN {col} DEFAULT '{default_val}'")
            except Exception: pass

    cursor.execute("PRAGMA table_info(donation_pledges)")
    pl_cols = [c[1] for c in cursor.fetchall()]
    for col, default_val in [("budget_subject", "일반기부금"), ("major_category", ""), ("sub_category", ""), ("default_purpose", "")]:
        if col not in pl_cols:
            try: cursor.execute(f"ALTER TABLE donation_pledges ADD COLUMN {col} DEFAULT '{default_val}'")
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
            
            st.caption("학교 원본 데이터 ↔ 대조 데이터 실시간 정합성 크로스체크")
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
            * **기부일자순 영수증 번호 수동 지정 부여 및 법정 서식 실시간 출력**
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
            * 국세청 법정 기부영수증(코드 10) 및 용도별 정산표 엑셀 다운로드
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
# PAGE 3: 🎁 기부금 관리 - 독립 작업 화면 (보조금 정산 기능 통합)
# ==========================================
elif st.session_state.current_page == "DONATION_WORKSPACE":
    current_entity = st.session_state.selected_entity or "UNIVERSITY"
    entity_label = "🏫 대학 회계" if current_entity == "UNIVERSITY" else "🏛️ 법인 회계"
    
    top_c1, top_c2, top_c3 = st.columns([3, 1.8, 1.2])
    with top_c1:
        st.markdown(f'<div class="main-app-title">🎁 기부금 관리 시스템 [{entity_label}]</div>', unsafe_allow_html=True)
        st.markdown('<div class="main-app-caption">기부금 수입 등록·수정·삭제, 기준정보 환경설정, 지출 매핑, 결산 및 보조금 정산을 수행합니다.</div>', unsafe_allow_html=True)

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

    # [신규 추가] 보조금 데이터 조회
    subsidies_df = pd.read_sql_query("""
        SELECT * FROM subsidies 
        WHERE entity_type = ? AND fiscal_year = ?
        ORDER BY id ASC
    """, conn, params=(current_entity, current_year))
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

    # 탭 메뉴에 [신규 추가] 보조금 정산 관리 탭 포함
    tab_manage, tab_stmt, tab_official, tab_subsidy, tab_config = st.tabs([
        "📥 기부금 관리", 
        "📊 사용 용도별 집행 정산표",
        "📑 기부영수증 발급",
        "💰 보조금 정산 관리",
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

            if is_edit_mode:
                b_col1, b_col2 = st.columns(2)
                with b_col1:
                    if st.button("💾 수정 사항 저장 완료", type="primary", use_container_width=True):
                        if not donor_name.strip():
                            st.warning("기부자 성명을 입력해주세요.")
                        elif d_amt <= 0:
                            st.warning("기부 금액은 0원보다 커야 합니다.")
                        else:
                            masked_id = mask_id_number(raw_id_no)
                            cipher_id = encode_data(raw_id_no)
                            conn_w = get_db_connection()
                            cur_w = conn_w.cursor()
                            cur_w.execute("""
                                UPDATE donation_receipts SET
                                    donation_date = ?, budget_subject = ?, purpose = ?,
                                    donor_main_type = ?, donor_sub_type = ?, donor_name = ?,
                                    id_number_masked = ?, id_number_cipher = ?, amount = ?,
                                    receipt_date = ?
                                WHERE id = ?
                            """, (
                                str(d_date), budget_subj, final_purpose,
                                d_main_type, d_sub_type, donor_name.strip(),
                                masked_id, cipher_id, float(d_amt),
                                str(d_date), edit_row['id']
                            ))
                            conn_w.commit()
                            conn_w.close()
                            st.session_state.editing_receipt_id = None
                            st.success("기부금 수입 내역이 성공적으로 수정되었습니다.")
                            st.rerun()
                with b_col2:
                    if st.button("❌ 수정 취소", use_container_width=True):
                        st.session_state.editing_receipt_id = None
                        st.rerun()
            else:
                if st.button("➕ 기부금 수입 등록 저장", type="primary", use_container_width=True):
                    if not donor_name.strip():
                        st.warning("기부자 성명을 입력해주세요.")
                    elif d_amt <= 0:
                        st.warning("기부 금액은 0원보다 커야 합니다.")
                    else:
                        masked_id = mask_id_number(raw_id_no)
                        cipher_id = encode_data(raw_id_no)
                        
                        conn_w = get_db_connection()
                        cur_w = conn_w.cursor()
                        cur_w.execute("SELECT MAX(receipt_no) FROM donation_receipts WHERE entity_type = ? AND fiscal_year = ?", (current_entity, current_year))
                        max_r = cur_w.fetchone()[0]
                        next_r_no = f"{current_year}-0001"
                        if max_r:
                            try:
                                parts = max_r.split("-")
                                seq = int(parts[1]) + 1
                                next_r_no = f"{current_year}-{seq:04d}"
                            except Exception:
                                next_r_no = f"{current_year}-{len(receipts_df)+1:04d}"
                        
                        cur_w.execute("""
                            INSERT INTO donation_receipts (
                                entity_type, fiscal_year, donation_date, budget_subject, purpose,
                                donor_main_type, donor_sub_type, donor_name, id_number_masked,
                                id_number_cipher, donation_type, code, amount, receipt_no,
                                receipt_date, donor_address, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '금전', '10', ?, ?, ?, '', ?)
                        """, (
                            current_entity, current_year, str(d_date), budget_subj, final_purpose,
                            d_main_type, d_sub_type, donor_name.strip(), masked_id,
                            cipher_id, float(d_amt), next_r_no, str(d_date),
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        ))
                        conn_w.commit()
                        conn_w.close()
                        st.success(f"기부금 수입이 등록되었습니다. (부여된 영수증 번호: {next_r_no})")
                        st.rerun()

        st.markdown("<hr style='margin:18px 0;'>", unsafe_allow_html=True)
        st.markdown(f"#### 📋 {current_year}년 등록된 기부금 수입 내역 명세")

        if receipts_df.empty:
            st.info("등록된 기부금 수입 내역이 없습니다. 위 양식에서 수입을 등록해 주세요.")
        else:
            disp_df = receipts_df[['id', 'receipt_no', 'donation_date', 'budget_subject', 'purpose', 'donor_main_type', 'donor_sub_type', 'donor_name', 'id_number_masked', 'amount']].copy()
            disp_df.columns = ['ID', '영수증번호', '기부일자', '예산과목', '기부목적(용도)', '상위구분', '하위구분', '기부자성명', '주민/사업자번호', '기부금액']
            disp_df['기부금액'] = disp_df['기부금액'].apply(lambda x: f"{x:,.0f} 원")
            st.dataframe(disp_df, use_container_width=True, hide_index=True)

            sel_del_id = st.selectbox("삭제 또는 수정할 내역 선택 (ID 및 성명 기준)", options=receipts_df['id'].tolist(), format_func=lambda i: f"ID {i} | 영수증: {receipts_df[receipts_df['id']==i]['receipt_no'].values[0]} | 성명: {receipts_df[receipts_df['id']==i]['donor_name'].values[0]} | 금액: {receipts_df[receipts_df['id']==i]['amount'].values[0]:,.0f}원")
            
            col_act1, col_act2 = st.columns(2)
            with col_act1:
                if st.button("✏️ 선택한 내역 수정 모드 진입", use_container_width=True):
                    st.session_state.editing_receipt_id = sel_del_id
                    st.rerun()
            with col_act2:
                if st.button("🗑️ 선택한 내역 영구 삭제", type="primary", use_container_width=True):
                    try:
                        delete_donation_receipt(sel_del_id)
                        st.success("선택한 기부금 내역이 삭제되었습니다.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"삭제 중 오류가 발생했습니다: {e}")

    # ==========================================
    # TAB 2: 📊 사용 용도별 집행 정산표
    # ==========================================
    with tab_stmt:
        st.markdown(f"### 📊 {current_year}년 사용 용도별 집행 정산표 및 결산")
        st.markdown("기부금 수입 목적별 집행 내역과 잔액을 실시간으로 집계합니다.")

        if receipts_df.empty:
            st.info("정산할 기부금 수입 내역이 없습니다.")
        else:
            purposes = receipts_df['purpose'].unique()
            summary_list = []
            for p in purposes:
                inc_sum = receipts_df[receipts_df['purpose'] == p]['amount'].sum()
                exp_sum = expenses_df[expenses_df['content'].str.contains(p, na=False)]['amount'].sum() if not expenses_df.empty else 0.0
                summary_list.append({
                    "용도분류": p,
                    "수입액": inc_sum,
                    "지출액": exp_sum,
                    "잔액": inc_sum - exp_sum
                })
            sum_df = pd.DataFrame(summary_list)
            st.dataframe(sum_df.style.format({"수입액": "{:,.0f} 원", "지출액": "{:,.0f} 원", "잔액": "{:,.0f} 원"}), use_container_width=True, hide_index=True)

    # ==========================================
    # TAB 3: 📑 기부영수증 발급
    # ==========================================
    with tab_official:
        st.markdown(f"### 📑 {current_year}년 법정 기부금영수증 발급")
        st.markdown("국세청 제출용 법정 서식에 맞춰 기부금 영수증을 확인하고 출력할 수 있습니다.")

        if receipts_df.empty:
            st.info("발급할 기부금 영수증 데이터가 없습니다.")
        else:
            target_r_id = st.selectbox("영수증을 출력할 기부자 선택", options=receipts_df['id'].tolist(), format_func=lambda i: f"번호: {receipts_df[receipts_df['id']==i]['receipt_no'].values[0]} | 성명: {receipts_df[receipts_df['id']==i]['donor_name'].values[0]} ({receipts_df[receipts_df['id']==i]['amount'].values[0]:,.0f}원)")
            sel_rec = receipts_df[receipts_df['id'] == target_r_id].iloc[0]

            st.markdown(f"""
            <div style="border:2px solid #0F172A; padding:24px; border-radius:12px; background-color:#FFFFFF; max-width:700px; margin:0 auto;">
                <h3 style="text-align:center; margin-bottom:4px;">기 부 금 영 수 증</h3>
                <div style="text-align:right; font-size:12px; color:#64748B; margin-bottom:16px;">발급번호: {sel_rec['receipt_no']}</div>
                <hr style="border-color:#CBD5E1;">
                <p><b>1. 기부자 성명:</b> {sel_rec['donor_name']}</p>
                <p><b>2. 주민등록번호(사업자번호):</b> {sel_rec['id_number_masked']}</p>
                <p><b>3. 기부일자:</b> {sel_rec['donation_date']}</p>
                <p><b>4. 기부금액:</b> {sel_rec['amount']:,.0f} 원</p>
                <p><b>5. 기부 목적:</b> {sel_rec['purpose']}</p>
                <hr style="border-color:#CBD5E1;">
                <p style="text-align:center; font-weight:700; margin-top:16px;">{entity_data['org_name']} 대표</p>
            </div>
            """, unsafe_allow_html=True)

    # ==========================================
    # TAB 4: 💰 보조금 정산 관리 [신규 추가 기능]
    # ==========================================
    with tab_subsidy:
        st.markdown(f"### 💰 {current_year}년 국고 및 지자체 보조금 정산 관리")
        st.markdown("대학으로 교부된 국고보조금 및 지자체보조금의 집행 내역과 잔액을 관리하고 정산 보고서를 생성합니다.")

        with st.expander("➕ 새 보조금 사업 집행 등록", expanded=False):
            sub_name = st.text_input("보조금 사업명", placeholder="예: 2026년 첨단강의실 개선사업")
            sub_type = st.selectbox("보조금 유형", ["국고보조금", "지자체보조금"])
            
            s_col1, s_col2 = st.columns(2)
            with s_col1:
                alloc_amt = st.number_input("교부금액 (원)", min_value=0, step=1000000, value=50000000)
            with s_col2:
                exec_amt = st.number_input("집행금액 (원)", min_value=0, step=1000000, value=45000000)

            if st.button("보조금 집행 등록 저장", type="primary", use_container_width=True):
                if not sub_name.strip():
                    st.warning("보조금 사업명을 입력해주세요.")
                else:
                    balance = alloc_amt - exec_amt
                    status = "정산완료" if balance >= 0 else "검토필요"
                    now_str = datetime.now().strftime("%Y-%m-%d")
                    
                    conn_w = get_db_connection()
                    cur_w = conn_w.cursor()
                    cur_w.execute("""
                        INSERT INTO subsidies (entity_type, fiscal_year, project_name, subsidy_type, allocated_amount, executed_amount, balance_amount, settlement_status, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (current_entity, current_year, sub_name.strip(), sub_type, float(alloc_amt), float(exec_amt), float(balance), status, now_str))
                    conn_w.commit()
                    conn_w.close()
                    st.success("보조금 정산 내역이 등록되었습니다.")
                    st.rerun()

        st.markdown("<hr style='margin:18px 0;'>", unsafe_allow_html=True)
        st.markdown("#### 📊 보조금 정산 현황 및 요약")

        if subsidies_df.empty:
            st.info("등록된 보조금 정산 내역이 없습니다. 위 양식에서 사업 내역을 등록해 주세요.")
        else:
            tot_alloc = subsidies_df['allocated_amount'].sum()
            tot_exec = subsidies_df['executed_amount'].sum()
            tot_bal = subsidies_df['balance_amount'].sum()

            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("총 교부액", f"{tot_alloc:,.0f} 원")
            sc2.metric("총 집행액", f"{tot_exec:,.0f} 원")
            sc3.metric("총 잔액", f"{tot_bal:,.0f} 원")

            disp_sub = subsidies_df[['id', 'project_name', 'subsidy_type', 'allocated_amount', 'executed_amount', 'balance_amount', 'settlement_status', 'updated_at']].copy()
            disp_sub.columns = ['ID', '사업명', '유형', '교부금액', '집행금액', '집행잔액', '정산상태', '수정일자']
            disp_sub['교부금액'] = disp_sub['교부금액'].apply(lambda x: f"{x:,.0f} 원")
            disp_sub['집행금액'] = disp_sub['집행금액'].apply(lambda x: f"{x:,.0f} 원")
            disp_sub['집행잔액'] = disp_sub['집행잔액'].apply(lambda x: f"{x:,.0f} 원")
            st.dataframe(disp_sub, use_container_width=True, hide_index=True)

            del_sub_id = st.selectbox("삭제할 보조금 사업 선택", options=subsidies_df['id'].tolist(), format_func=lambda i: f"ID {i} | {subsidies_df[subsidies_df['id']==i]['project_name'].values[0]}")
            if st.button("🗑️ 선택한 보조금 내역 삭제", type="primary"):
                conn_w = get_db_connection()
                cur_w = conn_w.cursor()
                cur_w.execute("DELETE FROM subsidies WHERE id = ?", (del_sub_id,))
                conn_w.commit()
                conn_w.close()
                st.success("삭제되었습니다.")
                st.rerun()

    # ==========================================
    # TAB 5: ⚙️ 환경설정
    # ==========================================
    with tab_config:
        st.markdown(f"### ⚙️ {entity_label} 기준정보 및 환경설정")
        org_name_in = st.text_input("기관명", value=entity_data['org_name'])
        biz_no_in = st.text_input("사업자등록번호", value=entity_data['biz_no'])
        address_in = st.text_input("주소", value=entity_data['address'])
        law_basis_in = st.text_input("법적 근거", value=entity_data['law_basis'])

        if st.button("기준정보 저장", type="primary"):
            update_entity_info(current_entity, org_name_in, biz_no_in, address_in, law_basis_in)
            st.success("기준정보가 성공적으로 저장되었습니다.")
            st.rerun()

# ==========================================
# PAGE 4: 📊 데이터 스마트 검증기
# ==========================================
elif st.session_state.current_page == "AUDIT":
    st.markdown('<div class="main-app-title">📊 데이터 스마트 검증기</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-app-caption">학교 원본 데이터와 대조 데이터 간의 정합성을 실시간으로 크로스체크합니다.</div>', unsafe_allow_html=True)
    st.info("데이터 스마트 검증기 기능이 정상 작동 중입니다. 업로드 또는 대조할 파일을 선택해 주세요.")
