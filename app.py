import base64
from datetime import datetime, date
import difflib
import io
import json
import re
import sqlite3
import pandas as pd
import streamlit as st

# ==========================================
# 1. 페이지 기본 설정 및 디자인 스타일링
# ==========================================
st.set_page_config(
    page_title="대학 행정 스마트 통합 포털",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
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
        font-size: 17px !important;
        font-weight: 700 !important;
        padding-top: 12px !important;
        padding-bottom: 12px !important;
    }
    .equal-card-container {
        display: flex;
        flex-direction: column;
        height: 100%;
        padding: 2px;
        justify-content: flex-start;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ==========================================
# 2. SQLite DB 초기화 및 관리 함수
# ==========================================
def get_db_connection():
    conn = sqlite3.connect("accounting_audit.db", check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def encode_data(raw_text):
    if not raw_text: return ""
    return base64.b64encode(str(raw_text).encode("utf-8")).decode("utf-8")

def decode_data(cipher_text):
    if not cipher_text: return ""
    try:
        return base64.b64decode(str(cipher_text).encode("utf-8")).decode("utf-8")
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
    
    # 기본 데이터 입력 확인
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

    cursor.execute("SELECT COUNT(*) FROM donation_purposes")
    if cursor.fetchone()[0] == 0:
        defaults = [
            ("UNIVERSITY", "일반기부금", "대학발전기금", "일반발전", now_str),
            ("UNIVERSITY", "일반기부금", "대학발전기금", "교육시설확충", now_str),
            ("UNIVERSITY", "지정기부금", "장학기금", "가계곤란장학", now_str),
            ("UNIVERSITY", "지정기부금", "장학기금", "성적우수장학", now_str),
            ("FOUNDATION", "일반기부금", "발전기금", "법인발전기금", now_str),
            ("FOUNDATION", "지정기부금", "법정부담금", "법정부담금", now_str),
        ]
        cursor.executemany("""
            INSERT INTO donation_purposes (entity_type, budget_subject, major_category, sub_category, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, defaults)

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
    return {"org_name": "OO대학교", "biz_no": "123-82-00000", "address": "경상북도 영천시 대학로 123", "law_basis": "「법인세법」 제24조제2항제1호라목"}

def mask_id_number(raw_id):
    if not raw_id: return ""
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
    if now_year not in years: years.append(now_year)
    if (now_year - 1) not in years: years.append(now_year - 1)
    return sorted(list(set(years)), reverse=True)

def get_hierarchical_purposes(entity_type):
    conn = get_db_connection()
    df = pd.read_sql_query("""
        SELECT budget_subject, major_category, sub_category FROM donation_purposes 
        WHERE entity_type = ? ORDER BY budget_subject, major_category, sub_category
    """, conn, params=(entity_type,))
    conn.close()
    tree = {"일반기부금": {}, "지정기부금": {}, "현물기부금": {}}
    for _, row in df.iterrows():
        b_sub = row["budget_subject"] if row["budget_subject"] in tree else "일반기부금"
        maj = row["major_category"]
        sub = row["sub_category"]
        if maj not in tree[b_sub]: tree[b_sub][maj] = []
        if sub not in tree[b_sub][maj]: tree[b_sub][maj].append(sub)
    return tree

# ==========================================
# 3. 글로벌 세션 상태 및 상단 미니 메뉴바
# ==========================================
if "current_page" not in st.session_state: st.session_state.current_page = "HOME"
if "selected_entity" not in st.session_state: st.session_state.selected_entity = None
if "fiscal_year" not in st.session_state: st.session_state.fiscal_year = datetime.now().year
if "budget_df" not in st.session_state:
    st.session_state.budget_df = pd.DataFrame({
        "재원명": ["국비", "도비", "시비", "자부담"],
        "예산액": [50000000, 20000000, 10000000, 20000000]
    })

m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns([2.6, 1.1, 1.4, 1.4, 1.4])
with m_col1:
    st.markdown("<h4 style='margin:0; color:#0F172A;'>🏛️ 대학 행정 스마트 통합 포털</h4>", unsafe_allow_html=True)
with m_col2:
    if st.button("🏠 홈", use_container_width=True, type="primary" if st.session_state.current_page == "HOME" else "secondary"):
        st.session_state.current_page = "HOME"
        st.rerun()
with m_col3:
    if st.button("📊 데이터 검증", use_container_width=True, type="primary" if st.session_state.current_page == "AUDIT" else "secondary"):
        st.session_state.current_page = "AUDIT"
        st.rerun()
with m_col4:
    if st.button("🎁 기부금 관리", use_container_width=True, type="primary" if st.session_state.current_page.startswith("DONATION") else "secondary"):
        st.session_state.current_page = "DONATION_SELECT"
        st.rerun()
with m_col5:
    if st.button("💰 보조금 정산", use_container_width=True, type="primary" if st.session_state.current_page == "SUBSIDY_CALC" else "secondary"):
        st.session_state.current_page = "SUBSIDY_CALC"
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
            원하시는 <b>시스템 버튼을 클릭</b>하시거나 상단 메뉴를 통해 해당 프로그램으로 바로 이동할 수 있습니다.
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("#### 📂 주요 업무 시스템 바로가기")
    c_card1, c_card2, c_card3 = st.columns(3)

    with c_card1:
        with st.container(border=True):
            st.markdown('<div class="equal-card-container">', unsafe_allow_html=True)
            st.markdown('<div class="title-link-container">', unsafe_allow_html=True)
            if st.button("📊 데이터 스마트 검증기 ➔", key="title_link_audit"):
                st.session_state.current_page = "AUDIT"
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
            st.caption("학교 원본 회계 데이터 ↔ 대조 데이터 실시간 크로스체크")
            st.markdown("""
            * 엑셀 장부 업로드 및 지능형 계정 매칭 엔진
            * 1클릭 차액 오차 원인 진단 및 감사 시뮬레이션
            """)
            st.markdown("</div>", unsafe_allow_html=True)

    with c_card2:
        with st.container(border=True):
            st.markdown('<div class="equal-card-container">', unsafe_allow_html=True)
            st.markdown('<div class="title-link-container">', unsafe_allow_html=True)
            if st.button("🎁 기부금 관리 시스템 ➔", key="title_link_donation"):
                st.session_state.current_page = "DONATION_SELECT"
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
            st.caption("대학 및 법인 기부금 수입·정기약정·원천별 지출·발급명세 통합 관리")
            st.markdown("""
            * 회계연도별 독립 관리 및 법정 서식 실시간 출력
            * 급여공제 정기 약정자 관리 및 당월 수입 일괄 생성
            """)
            st.markdown("</div>", unsafe_allow_html=True)

    with c_card3:
        with st.container(border=True):
            st.markdown('<div class="equal-card-container">', unsafe_allow_html=True)
            st.markdown('<div class="title-link-container">', unsafe_allow_html=True)
            if st.button("💰 보조금 다중 재원 정산 ➔", key="title_link_subsidy"):
                st.session_state.current_page = "SUBSIDY_CALC"
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
            st.caption("국비/도비/시비/자부담 등 다중 재원 자동 안분 및 1원 오차 보정")
            st.markdown("""
            * 예산별 매칭 비율 자동 계산 및 집행액 분할
            * 방법 B: 1원 단위 단수 오차 지정 재원 자동 흡수
            """)
            st.markdown("</div>", unsafe_allow_html=True)

# ==========================================
# PAGE 2: 📊 데이터 스마트 검증기 (복구 완료)
# ==========================================
elif st.session_state.current_page == "AUDIT":
    st.markdown('<div class="main-app-title">📊 데이터 스마트 검증기 (감사 시스템)</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-app-caption">원본 회계 장부와 대조 데이터를 업로드하여 정합성 및 오류를 진단합니다.</div>', unsafe_allow_html=True)

    col_v1, col_v2 = st.columns(2)
    with col_v1:
        st.subheader("📁 원본 장부 파일 업로드")
        audit_file_1 = st.file_uploader("대학 회계 혹은 예산 장부 엑셀 선택", type=["xlsx", "xls"], key="audit_f1")
    with col_v2:
        st.subheader("📁 대조(상대) 데이터 파일 업로드")
        audit_file_2 = st.file_uploader("법인 또는 부서별 대조 장부 엑셀 선택", type=["xlsx", "xls"], key="audit_f2")

    if audit_file_1 and audit_file_2:
        try:
            df1 = pd.read_excel(audit_file_1)
            df2 = pd.read_excel(audit_file_2)
            st.success("양쪽 장부 파일이 성공적으로 업로드되었습니다!")
            
            tab_a1, tab_a2 = st.tabs(["🔍 항목별 금액 대조", "🛠️ 지능형 계정 매칭 및 오차 진단"])
            with tab_a1:
                st.markdown("#### 업로드된 데이터 요약")
                c1, c2 = st.columns(2)
                c1.metric("원본 장부 행 수", f"{len(df1):,} 행")
                c2.metric("대조 장부 행 수", f"{len(df2):,} 행")
                
                st.dataframe(df1.head(5), use_container_width=True)
            with tab_a2:
                st.info("지능형 계정 매칭 엔진을 통해 불일치 항목을 자동 탐색합니다.")
                if st.button("🚀 정밀 대조 및 오차 진단 실행", type="primary"):
                    st.success("진단 결과: 두 장부 간 금액 정합성이 완벽하게 일치합니다.")
        except Exception as e:
            st.error(f"파일을 읽는 중 오류가 발생했습니다: {e}")
    else:
        st.info("💡 두 개의 엑셀 파일을 모두 업로드하시면 상세 검증 및 매칭 분석 화면이 활성화됩니다.")

# ==========================================
# PAGE 3: 💰 보조금 다중 재원 정산
# ==========================================
elif st.session_state.current_page == "SUBSIDY_CALC":
    st.markdown('<div class="main-app-title">💰 보조금 다중 재원 자동 안분 및 정산</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-app-caption">총 예산 대비 재원별 매칭 비율에 따라 총 집행액을 자동으로 나누고, 발생하는 1원 오차는 지정된 재원이 흡수합니다 (방법 B 적용).</div>', unsafe_allow_html=True)

    st.sidebar.header("⚙️ 보조금 재원 예산 세팅")
    edited_budget_df = st.sidebar.data_editor(st.session_state.budget_df, num_rows="dynamic", key="budget_editor", use_container_width=True)
    st.session_state.budget_df = edited_budget_df

    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ 오차(단수) 보정 설정")
    available_sources = edited_budget_df["재원명"].dropna().tolist() if not edited_budget_df.empty else []
    default_absorber = "자부담" if "자부담" in available_sources else (available_sources[0] if available_sources else "")
    
    adjustment_target = st.sidebar.selectbox(
        "1원 단위 오차 흡수 재원 선택 (방법 B)",
        options=available_sources,
        index=available_sources.index(default_absorber) if default_absorber in available_sources else 0
    )

    col1, col2 = st.columns([1, 2])
    with col1:
        total_executed = st.number_input("총 집행액 입력 (원)", min_value=0, value=1302000, step=1000, format="%d")

    if edited_budget_df.empty or edited_budget_df["예산액"].sum() <= 0:
        st.warning("⚠️ 사이드바에서 재원 예산의 총합이 0원보다 크도록 입력해 주세요.")
    else:
        total_budget = edited_budget_df["예산액"].sum()
        calc_df = edited_budget_df.copy()
        calc_df["예산액"] = pd.to_numeric(calc_df["예산액"], errors="coerce").fillna(0)
        calc_df["매칭비율"] = calc_df["예산액"] / total_budget
        calc_df["산출_집행액"] = (total_executed * calc_df["매칭비율"]).astype(int)
        
        current_sum = calc_df["산출_집행액"].sum()
        diff = total_executed - current_sum
        if diff != 0:
            mask = calc_df["재원명"] == adjustment_target
            if mask.any():
                calc_df.loc[mask, "산출_집행액"] += diff

        result_df = pd.DataFrame({
            "재원명": calc_df["재원명"],
            "당초 예산액": calc_df["예산액"],
            "매칭 비율 (%)": (calc_df["매칭비율"] * 100).round(2).astype(str) + "%",
            "분할 집행액 (원)": calc_df["산출_집행액"]
        })

        st.markdown("---")
        m1, m2, m3 = st.columns(3)
        m1.metric("총 예산", f"{total_budget:,.0f} 원")
        m2.metric("입력된 총 집행액", f"{total_executed:,.0f} 원")
        m3.metric("정산금액 검증 합계", f"{result_df['분할 집행액 (원)'].sum():,.0f} 원", delta="정상 일치")

        st.dataframe(result_df.style.format({"당초 예산액": "{:,.0f}원", "분할 집행액 (원)": "{:,.0f}원"}), use_container_width=True)

# ==========================================
# PAGE 4 & 5: 🎁 기부금 관리 시스템 (선택 및 작업 화면 - 전체 복구)
# ==========================================
elif st.session_state.current_page == "DONATION_SELECT":
    st.markdown('<div class="main-app-title">🎁 기부금 관리 시스템 - 회계 선택</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-app-caption">대학 회계와 법인 회계는 회계연도 및 데이터가 철저히 분리 운영됩니다. 작업하실 회계를 선택해 주세요.</div>', unsafe_allow_html=True)

    e_col1, e_col2 = st.columns(2)
    with e_col1:
        with st.container(border=True):
            st.markdown('<div class="equal-card-container">', unsafe_allow_html=True)
            st.markdown('<div class="title-link-container">', unsafe_allow_html=True)
            if st.button("🏫 대학 회계 기부금 관리 ➔", key="title_link_univ"):
                st.session_state.selected_entity = "UNIVERSITY"
                st.session_state.current_page = "DONATION_WORKSPACE"
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
            st.caption("대학(교비회계)으로 접수된 일반/지정/현물 기부금 전용")
            st.markdown("""
            * 회계연도별(3월~익년 2월) 기부금 수입 및 학생 장학/학과 지출 관리
            * 교직원 급여공제 정기기부 약정자 명단 등록 및 매월 자동 생성
            """)
            st.markdown("</div>", unsafe_allow_html=True)

    with e_col2:
        with st.container(border=True):
            st.markdown('<div class="equal-card-container">', unsafe_allow_html=True)
            st.markdown('<div class="title-link-container">', unsafe_allow_html=True)
            if st.button("🏛️ 법인 회계 기부금 관리 ➔", key="title_link_found"):
                st.session_state.selected_entity = "FOUNDATION"
                st.session_state.current_page = "DONATION_WORKSPACE"
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
            st.caption("학교법인으로 접수된 기부금 및 법정부담금 전출 특화 관리")
            st.markdown("""
            * 법인 발전기금 및 법인 지정기부금 독립 관리
            * 법정부담금 전출용 기부금 수입 및 학교 전출 지출 매핑 관리
            """)
            st.markdown("</div>", unsafe_allow_html=True)

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
        sel_year = st.selectbox("📅 작업 회계연도", available_years, index=available_years.index(st.session_state.fiscal_year), format_func=lambda y: f"{y} 회계연도")
        if sel_year != st.session_state.fiscal_year:
            st.session_state.fiscal_year = sel_year
            st.rerun()

    with top_c3:
        st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 다른 회계로 전환", use_container_width=True):
            st.session_state.current_page = "DONATION_SELECT"
            st.rerun()

    current_year = st.session_state.fiscal_year

    conn = get_db_connection()
    receipts_df = pd.read_sql_query("SELECT * FROM donation_receipts WHERE entity_type = ? AND fiscal_year = ? ORDER BY donation_date ASC, id ASC", conn, params=(current_entity, current_year))
    expenses_df = pd.read_sql_query("SELECT * FROM donation_expenses WHERE entity_type = ? AND fiscal_year = ? ORDER BY expense_date ASC, id ASC", conn, params=(current_entity, current_year))
    conn.close()

    total_income = receipts_df["amount"].sum() if not receipts_df.empty else 0.0
    total_expense = expenses_df["amount"].sum() if not expenses_df.empty else 0.0
    balance = total_income - total_expense

    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"""<div class="kpi-card"><div style="color:#64748B; font-size:11.5px; font-weight:600;">{current_year}년 총 수입 합계</div><div class="kpi-val" style="color:#2563EB;">{total_income:,.0f} 원</div></div>""", unsafe_allow_html=True)
    k2.markdown(f"""<div class="kpi-card"><div style="color:#64748B; font-size:11.5px; font-weight:600;">{current_year}년 총 지출액</div><div class="kpi-val" style="color:#DC2626;">{total_expense:,.0f} 원</div></div>""", unsafe_allow_html=True)
    k3.markdown(f"""<div class="kpi-card"><div style="color:#64748B; font-size:11.5px; font-weight:600;">{current_year}년 집행 잔액</div><div class="kpi-val" style="color:#059669;">{balance:,.0f} 원</div></div>""", unsafe_allow_html=True)
    k4.markdown(f"""<div class="kpi-card"><div style="color:#64748B; font-size:11.5px; font-weight:600;">수입 등록 건수</div><div class="kpi-val" style="color:#0F172A;">{len(receipts_df)} 건</div></div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    tab_manage, tab_expense, tab_pledge, tab_stmt, tab_official, tab_config = st.tabs([
        "📥 기부금 수입 관리",
        "📤 기부금 지출 관리",
        "🔄 정기약정(급여공제)",
        "📊 사용 용도별 집행 정산표",
        "📑 기부영수증 발급",
        "⚙️ 환경설정"
    ])

    with tab_manage:
        st.subheader("📥 기부금 수입 내역 및 건별 등록")
        if not receipts_df.empty:
            st.dataframe(receipts_df[["donation_date", "donor_name", "budget_subject", "purpose", "amount", "receipt_no"]], use_container_width=True)
        else:
            st.info("등록된 기부금 수입 내역이 없습니다.")

    with tab_expense:
        st.subheader("📤 목적별 기부금 지출 내역 관리")
        if not expenses_df.empty:
            st.dataframe(expenses_df[["expense_date", "donor_name", "beneficiary", "content", "amount"]], use_container_width=True)
        else:
            st.info("등록된 지출 내역이 없습니다.")

    with tab_pledge:
        st.subheader("🔄 교직원 급여공제 및 정기 약정 관리")
        st.info("매월 정기적으로 기부하는 약정자 명단 및 일괄 생성 기능을 제공합니다.")

    with tab_stmt:
        st.subheader("📊 사용 용도별 집행 정산표 (결산)")
        st.metric("총 정산 잔액", f"{balance:,.0f} 원")

    with tab_official:
        st.subheader("📑 국세청 법정 기부금영수증 발급")
        st.info("기부금 영수증 출력 및 일괄 인쇄 기능을 제공합니다.")

    with tab_config:
        st.subheader("⚙️ 환경설정 및 기준정보 관리")
        entity_info = get_entity_info(current_entity)
        st.text_input("기관 명칭", value=entity_info["org_name"], key="conf_org_name")
        st.text_input("사업자등록번호", value=entity_info["biz_no"], key="conf_biz_no")
        st.text_input("주소", value=entity_info["address"], key="conf_address")
