import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date
from zoneinfo import ZoneInfo
from math import radians, sin, cos, sqrt, asin
from streamlit_js_eval import get_geolocation
import cv2
import numpy as np
import pandas as pd
import io
import time
import random
from gspread.exceptions import APIError

# ================== CONFIG ==================
st.set_page_config(page_title="ระบบลงเวลาและจัดการวันลา", layout="wide")

# ================== HEADER STYLE ==================
st.markdown("""
<style>
.header-main {color:#1976D2;font-size:2.4rem;font-weight:700}
.header-section-1 {color:#D32F2F;font-size:1.8rem;font-weight:600}
.header-section-2 {color:#FFD700;font-size:1.8rem;font-weight:600}
.header-section-3 {color:#2E7D32;font-size:1.8rem;font-weight:600}
.header-section-4 {color:#7B1FA2;font-size:1.8rem;font-weight:600}
</style>
""", unsafe_allow_html=True)

SHEET_ID = "1VJZJq_kF0w_PMFU4JSHYyX9ZgG5U4PCp5uOVSHVnFNI"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"

# ================== GOOGLE CONNECTION ==================
@st.cache_resource
def init_connection():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["gcp_service_account"], scope
    )
    return gspread.authorize(creds)

client = init_connection()
sheet = client.open_by_key(SHEET_ID)

log_ws = sheet.worksheet("Logs")
settings_ws = sheet.worksheet("Settings")
logs2_ws = sheet.worksheet("Logs2")
logs4_ws = sheet.worksheet("Logs4")
logs5_ws = sheet.worksheet("Logs5")

# ================== DATA CACHE ==================
@st.cache_data(ttl=60) # ลด TTL เพื่อให้ข้อมูลอัปเดตบ่อยขึ้นแต่ไม่โหลด API หนักเกินไป
def load_settings():
    return settings_ws.get_all_values()

@st.cache_data(ttl=300)
def load_logs2():
    return logs2_ws.get_all_records()

@st.cache_data(ttl=300)
def load_logs4():
    return logs4_ws.get_all_records()

@st.cache_data(ttl=300)
def load_logs5():
    return logs5_ws.get_all_records()

# ================== SESSION STATE ==================
if "init" not in st.session_state:
    st.session_state.update({
        "init": True,
        "qr_value": None,
        "saved": False,
        "shift": None,
        "note": "",
        "leave_start": date.today(),
        "leave_end": date.today()
    })

# ================== HELPER ==================
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Report")
    return output.getvalue()

def haversine(lat1, lon1, lat2, lon2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    a = sin((lat2 - lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2 - lon1)/2)**2
    return 6371000 * 2 * asin(sqrt(a))

def get_employee_setting(name):
    data = load_settings()
    if not data:
        return None
    header, rows = data[0], data[1:]
    try:
        i_name = header.index("ชื่อพนักงาน")
        i_lat = header.index("Latitude")
        i_lon = header.index("Longitude")
        i_rad = header.index("Radius")
        for r in rows:
            if str(r[i_name]).strip() == str(name).strip():
                return float(r[i_lat]), float(r[i_lon]), float(r[i_rad])
    except:
        return None

def decode_qr(img):
    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(img)
    return data.strip() if data else None

# ปรับปรุง: รองรับการบันทึกพร้อมกัน 500 คนด้วย Exponential Backoff + Jitter
def safe_append(ws, row, retry=10):
    for i in range(retry):
        try:
            ws.append_rows([row], value_input_option="USER_ENTERED")
            return True
        except Exception as e:
            if i == retry - 1:
                return False
            # รอแบบสุ่มเพื่อเลี่ยงการชนกัน (Wait 1-3, 2-4, 4-6... seconds)
            wait_time = (2 ** i) + random.uniform(0.1, 1.0)
            time.sleep(wait_time)
    return False

# ================== HEADER ==================
c1, c2 = st.columns([8,2])
with c1:
    st.markdown('<div class="header-main">🎫 Time Attendance</div>', unsafe_allow_html=True)
with c2:
    st.link_button("📊 Database (HR)", SHEET_URL, use_container_width=True)

# ================== SECTION 1 ==================
st.markdown('<div class="header-section-1">📝 บันทึกเวลาเข้า-ออก,ลา</div>', unsafe_allow_html=True)
action = st.radio("เลือกประเภทรายการ", ["เข้า","ออก","ลางาน"], horizontal=True)

settings_data = load_settings()
shifts = []
if settings_data:
    header, rows = settings_data[0], settings_data[1:]
    if "Shift" in header:
        s = header.index("Shift")
        shifts = sorted({r[s] for r in rows if len(r) > s and r[s]})

c1, c2 = st.columns(2)
with c1:
    st.session_state.shift = st.selectbox("🕒 กะ", shifts) if shifts else st.text_input("🕒 กะ")
with c2:
    st.session_state.note = st.text_input("📝 หมายเหตุ")

if action == "ลางาน":
    c1, c2 = st.columns(2)
    st.session_state.leave_start = c1.date_input("เริ่มลา", st.session_state.leave_start)
    st.session_state.leave_end = c2.date_input("สิ้นสุด", st.session_state.leave_end)

# ปรับปรุง: ป้องกัน KeyError จากการดึงพิกัด (GPS)
lat, lon = None, None
if action != "ลางาน":
    loc = get_geolocation()
    if loc and "coords" in loc:
        lat = loc["coords"]["latitude"]
        lon = loc["coords"]["longitude"]
    else:
        st.warning("⚠️ กรุณาเปิด GPS และรอนะบบดึงตำแหน่ง (หากมีป๊อปอัพให้กด Allow หรืออนุญาต)")
        st.stop()

if not st.session_state.qr_value:
    img = st.camera_input("📷 สแกน QR CODE จากบัตรพนักงาน")
    if img:
        qr = decode_qr(cv2.imdecode(np.frombuffer(img.getvalue(), np.uint8), cv2.IMREAD_COLOR))
        if qr:
            st.session_state.qr_value = qr
            st.rerun()
else:
    emp = st.session_state.qr_value
    st.success(f"👤 {emp}")

    emp_set = get_employee_setting(emp)
    if not emp_set:
        st.error("ไม่พบข้อมูลพนักงานในระบบ")
        st.stop()

    if not st.session_state.saved and st.button("✅ ยืนยันบันทึกข้อมูล"):
        with st.spinner("กำลังเชื่อมต่อฐานข้อมูล... กรุณาอย่าปิดหน้าจอ"):
            now = datetime.now(ZoneInfo("Asia/Bangkok"))
            dist, status = "", "ปกติ"

            if action != "ลางาน":
                dist = int(haversine(lat, lon, emp_set[0], emp_set[1]))
                status = "ปกติ" if dist <= emp_set[2] else "นอกพื้นที่"

            row = [
                now.strftime("%d/%m/%Y %H:%M:%S"),
                emp,
                st.session_state.shift,
                action,
                dist,
                status,
                f"{lat},{lon}" if lat else "",
                st.session_state.note,
                st.session_state.leave_start.strftime("%d/%m/%Y") if action=="ลางาน" else "",
                st.session_state.leave_end.strftime("%d/%m/%Y") if action=="ลางาน" else ""
            ]

            if safe_append(log_ws, row):
                st.session_state.saved = True
                # ปรับปรุง: ไม่ใช้ st.cache_data.clear() พร่ำเพรื่อเพื่อลดภาระ API ตอนคนใช้เยอะ
                st.balloons()
                st.success("บันทึกข้อมูลเรียบร้อยแล้ว!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ บันทึกไม่สำเร็จเนื่องจากมีผู้ใช้งานจำนวนมาก กรุณากดปุ่ม 'บันทึก' อีกครั้ง")

    if st.session_state.saved and st.button("➡️ บันทึกรายการถัดไป"):
        st.session_state.qr_value = None
        st.session_state.saved = False
        st.rerun()

# ================== SECTION 2 ==================
st.divider()
st.markdown('<div class="header-section-2">🔍 ตรวจสอบวันลาคงเหลือ</div>', unsafe_allow_html=True)

with st.expander("📊 ยอดคงเหลือ"):
    df2 = pd.DataFrame(load_logs2())
    if df2.empty:
        st.info("ไม่มีข้อมูล")
    else:
        f_company = st.text_input("🏢 บริษัท")
        f_emp = st.text_input("🆔 รหัสพนักงาน")

        if f_company and "บริษัท" in df2.columns:
            df2 = df2[df2["บริษัท"].fillna("").astype(str).str.contains(f_company, case=False)]

        if f_emp and "รหัสพนักงาน" in df2.columns:
            df2 = df2[df2["รหัสพนักงาน"].fillna("").astype(str).str.contains(f_emp, case=False)]

        if df2.empty:
            st.warning("ไม่พบข้อมูลตามเงื่อนไขที่ค้นหา")
        else:
            st.dataframe(df2, use_container_width=True)
            st.download_button("📥 Excel", to_excel(df2), "leave_balance.xlsx")

# ================== SECTION 3 ==================
st.divider()
st.markdown('<div class="header-section-3">📋 รายละเอียดการลา</div>', unsafe_allow_html=True)

with st.expander("🔎 ค้นหา"):
    df4 = pd.DataFrame(load_logs4())
    if df4.empty:
        st.info("ไม่มีข้อมูล")
    else:
        if "วันที่" in df4.columns:
            df4["วันที่_dt"] = pd.to_datetime(df4["วันที่"], dayfirst=True, errors="coerce")
        else:
            df4["วันที่_dt"] = pd.NaT

        start = st.date_input("ตั้งแต่", value=None)
        end = st.date_input("ถึง", value=None)
        emp_name = st.text_input("ชื่อพนักงาน", key="search_name")

        if start:
            df4 = df4[df4["วันที่_dt"].dt.date >= start]
        if end:
            df4 = df4[df4["วันที่_dt"].dt.date <= end]
        if emp_name and "ชื่อพนักงาน" in df4.columns:
            df4 = df4[df4["ชื่อพนักงาน"].fillna("").astype(str).str.contains(emp_name, case=False)]

        if df4.empty:
            st.warning("ไม่พบข้อมูลตามเงื่อนไขที่ค้นหา")
        else:
            st.dataframe(df4, use_container_width=True)
            st.download_button("📥 Excel", to_excel(df4), "leave_history.xlsx")

# ================== SECTION 4 ==================
st.divider()
st.markdown('<div class="header-section-4">🕒 วันหยุดประจำปี</div>', unsafe_allow_html=True)

with st.expander("📊 แสดงข้อมูลทั้งหมด", expanded=True):
    df5 = pd.DataFrame(load_logs5())
    if df5.empty:
        st.info("ไม่พบข้อมูล")
    else:
        search_val = st.text_input("🔍 ค้นหาข้อมูลวันหยุด")
        if search_val:
            df5 = df5[df5.apply(
                lambda r: r.fillna("").astype(str).str.contains(search_val, case=False).any(),
                axis=1
            )]

        if df5.empty:
            st.warning("ไม่พบข้อมูลตามคำค้นหา")
        else:
            st.dataframe(df5, use_container_width=True)
            st.download_button("📥 Excel", to_excel(df5), "logs5.xlsx")
