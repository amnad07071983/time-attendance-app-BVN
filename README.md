# 🕒 Time Attendance App (BVN)

แอปพลิเคชันสำหรับบันทึกเวลาเข้า-ออกงาน พัฒนาด้วย Python และ Streamlit

## 🚀 ฟีเจอร์หลัก
* บันทึกเวลาเข้างานและออกงานผ่านหน้าเว็บ
* เชื่อมต่อข้อมูลกับ Google Sheets (gspread)
* รองรับการประมวลผลภาพ/กล้อง ด้วย OpenCV
* จัดการข้อมูลและส่งออกเป็นไฟล์ Excel (Pandas & XlsxWriter)

## 🛠️ วิธีใช้งานเบื้องต้น
1. เปิดแอปผ่าน Streamlit Cloud
2. กรอกข้อมูลพนักงาน หรือทำตามขั้นตอนที่ระบุบนหน้าจอ
3. ข้อมูลจะถูกบันทึกลงในฐานข้อมูล/Google Sheets อัตโนมัติ

## 📦 เทคโนโลยีที่ใช้
* **Frontend:** Streamlit
* **Data:** Pandas, Numpy
* **Database/Storage:** Google Sheets via gspread
* **Vision:** OpenCV (Headless)
