import re
import unicodedata
import streamlit as st
import pandas as pd
import os
import sys
import base64
import time
import datetime
import smtplib
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from PIL import Image
import base64
from PIL import Image
import io
#=============================================================================
# CHÈN VÀO ĐÂY: Hàm xử lý xóa dấu và khoảng trắng
def clean_username(input_string):
    if not input_string:
        return ""
    username = input_string.lower().replace('đ', 'd')
    username = unicodedata.normalize('NFKD', username)
    username = re.sub(r'[\u0300-\u036f]', '', username)
    return re.sub(r'[^a-z0-9]', '', username)
#=============================================================================
#========================================================================================================
    # MÃ HÓA ẢNH THÀNH STRINH =============================================================================
    def convert_image_to_base64(uploaded_file):
        """Chuyển đổi file ảnh được upload từ st.file_uploader thành chuỗi Base64"""
        if uploaded_file is not None:
            try:
                image = Image.open(uploaded_file)
                # Tự động chuyển đổi sang hệ màu RGB nếu ảnh gốc là PNG (hệ màu RGBA có độ trong suốt)
                if image.mode in ("RGBA", "P"):
                    image = image.convert("RGB")
            
                # Nén ảnh xuống chất lượng 50% để chuỗi không quá dài (Tránh vượt giới hạn ký tự 1 ô của Google Sheet)
                buffered = io.BytesIO()
                image.save(buffered, format="JPEG", quality=50) 
            
                img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
                return img_str
            except Exception as e:
                st.error(f"❌ Lỗi khi xử lý nén hình ảnh: {e}")
                return ""
        return ""
# ============================================================================
# 1. CẤU HÌNH TRANG WEB (PHẢI LÀ LỆNH STREAMLIT ĐẦU TIÊN TRONG FILE CODE)
# ============================================================================
icon_source = "logo_cty.jpg" if os.path.exists("logo_cty.jpg") else "🏢"
st.set_page_config(
    page_title="Đại Sơn ME group Project",
    page_icon=icon_source,
    layout="wide"
)

# === CẤU HÌNH HỆ THỐNG GOOGLE SHEET MULTI-TENANT (CÁCH 2) =====================
SPREADSHEET_ID = '1-cspxHW8eQR-6BVL6BzSGO_BZTtZh_P4SfB2ymunh3g' 
FIXED_COLUMNS = ["Công ty", "ID", "Công trình", "Tình trạng", "Tiến độ (%)", "Người phụ trách", "Cập nhật cuối", "Ảnh", "Miêu tả"]

# Tạo thư mục 'image' lưu ảnh local nếu chưa tồn tại
IMAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "image")
if not os.path.exists(IMAGE_DIR):
    os.makedirs(IMAGE_DIR)

# ============================================================================
# ĐỊNH DẠNG VÀ TẢI DỮ LIỆU TỪ GOOGLE SHEET (GỘP CHUNG 1 WORKSHEET)
# ============================================================================
def load_data_from_sheets():
    """Hàm tải toàn bộ dữ liệu từ 1 tab duy nhất và tiến hành lọc theo Code Pandas"""
    try:
        import gspread
        import pandas as pd
        import os
        import streamlit as st
        import json
        
        # --- CẤU HÌNH KẾT NỐI BẢO MẬT CHỐNG LỖI ASN.1 EXTRA DATA ---
        try:
            if "gspread_json" in st.secrets:
                raw_json_str = st.secrets["gspread_json"]
                # Phân tách chuỗi json sang từ điển Python tạm thời
                creds_dict = json.loads(raw_json_str, strict=False)
                # Thay thế ký tự chuỗi \n ẩn thành ký tự xuống dòng thực tế cho mã PEM của Google
                if "private_key" in creds_dict:
                    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
                gc = gspread.service_account_from_dict(creds_dict)
            else:
                current_dir = os.path.dirname(os.path.abspath(__file__))
                credentials_path = os.path.join(current_dir, 'credentials.json')
                gc = gspread.service_account(filename=credentials_path)
        except Exception as auth_err:
            st.error(f"❌ Lỗi xác thực tài khoản kết nối Google Sheet: {auth_err}")
            return False
        # -----------------------------------------------------------------

        sh = gc.open_by_key(SPREADSHEET_ID)
        
        # Luôn đọc từ 1 tab duy nhất cố định tên là datacongtrinh
        try:
            worksheet = sh.worksheet("datacongtrinh")
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sh.add_worksheet(title="datacongtrinh", rows="1000", cols="15")
            worksheet.append_row(FIXED_COLUMNS)
        
        all_values = worksheet.get_all_values()
        
        if len(all_values) > 1:
            data_rows = all_values[1:] 
            max_cols = len(FIXED_COLUMNS)
            clean_data = []
            for r in data_rows:
                if len(r) < max_cols:
                    r = r + [""] * (max_cols - len(r))
                clean_data.append(r[:max_cols])
            
            df_all = pd.DataFrame(clean_data, columns=FIXED_COLUMNS)
            
            # Ép kiểu dữ liệu tiến độ thành số nguyên an toàn
            df_all["Tiến độ (%)"] = df_all["Tiến độ (%)"].astype(str).str.strip()
            df_all["Tiến độ (%)"] = df_all["Tiến độ (%)"].str.replace("%", "", regex=False).str.strip()
            df_all["Tiến độ (%)"] = pd.to_numeric(df_all["Tiến độ (%)"], errors='coerce').fillna(0).astype(int)
            
            # Lưu toàn bộ dữ liệu gốc vào bộ nhớ tạm hệ thống
            st.session_state["all_projects_raw"] = df_all
            
            # TIẾN HÀNH LỌC DỮ LIỆU THEO PHÂN QUYỀN USER ĐĂNG NHẬP
            user_info = st.session_state['user_info']
            if user_info["company"] == "ALL_COMPANIES":
                df_filtered = df_all.copy()
            else:
                df_filtered = df_all[df_all["Công ty"] == user_info["company"]].copy()
                
            df_filtered = df_filtered.sort_values(by="ID", ascending=True).reset_index(drop=True)
            st.session_state["projects"] = df_filtered
            return True
        else:
            st.session_state["all_projects_raw"] = pd.DataFrame(columns=FIXED_COLUMNS)
            st.session_state["projects"] = pd.DataFrame(columns=FIXED_COLUMNS)
            return True
            
    except Exception as e:
        st.error(f"❌ Lỗi tự động đồng bộ gspread: {e}")
        if "projects" not in st.session_state:
            st.session_state["projects"] = pd.DataFrame(columns=FIXED_COLUMNS)
        return False


def append_to_sheet(row_data):
    try:
        import gspread
        import os
        import streamlit as st
        import json
        
        # --- CẤU HÌNH KẾT NỐI BẢO MẬT CHỐNG LỖI ASN.1 EXTRA DATA ---
        if "gspread_json" in st.secrets:
            raw_json_str = st.secrets["gspread_json"]
            creds_dict = json.loads(raw_json_str, strict=False)
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            gc = gspread.service_account_from_dict(creds_dict)
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            credentials_path = os.path.join(current_dir, 'credentials.json')
            gc = gspread.service_account(filename=credentials_path)
        # --------------------------------------------------------

        sh = gc.open_by_key(SPREADSHEET_ID) 
        worksheet = sh.worksheet("datacongtrinh")
        worksheet.append_row(row_data)
        return True 
        
    except Exception as e:
        print(f"Lỗi đồng bộ chi tiết: {e}") 
        return False

# ============================================================================
# CẤU HÌNH GỬI EMAIL SMTP (THAY THÔNG TIN CỦA BẠN VÀO ĐÂY)
# ============================================================================
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
ADMIN_EMAIL = "daisonpublic@gmail.com"  # Email nhận thông tin duyệt OTP

# TÀI KHOẢN GỬI (Gmail gửi và Mật khẩu ứng dụng 16 ký tự)
SENDER_EMAIL = "daisonpublic@gmail.com" 
SENDER_PASSWORD = "lrhz klln yfxo exad" 

# Biến bổ sung (Đảm bảo đã khai báo SPREADSHEET_ID ở đầu file của bạn)
# SPREADSHEET_ID = "ID_SHEET_CỦA_BẠN"

# Khởi tạo từ điển chứa tài khoản mặc định
DATA_USERS = {
    "admin": {"password": "123456", "company": "ALL_COMPANIES", "role": "Tổng Quản Trị"}
}

# --- 2 HÀM PHỤ TRỢ ĐỌC/GHI TÀI KHOẢN CLOUD XUỐNG TAB datauser ---
def load_users_from_sheets():
    """Tải dữ liệu tài khoản từ Tab datauser trên Google Sheet nạp vào ứng dụng"""
    global DATA_USERS
    
    if 'DATA_USERS' not in globals() or not isinstance(DATA_USERS, dict):
        DATA_USERS = {
            "admin": {"password": "123456", "company": "ALL_COMPANIES", "role": "Tổng Quản Trị"}
        }
        
    try:
        import gspread
        import os
        import streamlit as st
        import json
        
        try:
            if "gspread_json" in st.secrets:
                raw_json_str = st.secrets["gspread_json"]
                creds_dict = json.loads(raw_json_str, strict=False)
                if "private_key" in creds_dict:
                    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
                gc = gspread.service_account_from_dict(creds_dict)
            else:
                current_dir = os.path.dirname(os.path.abspath(__file__))
                credentials_path = os.path.join(current_dir, 'credentials.json')
                gc = gspread.service_account(filename=credentials_path)
        except Exception as auth_err:
            st.error(f"❌ Lỗi xác thực tài khoản kết nối Google Sheet: {auth_err}")
            return

        try:
            sh = gc.open_by_key(SPREADSHEET_ID)
        except gspread.exceptions.APIError as api_err:
            st.error(f"❌ Lỗi API Google Sheets (Chưa Share quyền Editor cho email dịch vụ): {api_err}")
            return
        except Exception as sheet_err:
            st.error(f"❌ Không thể tìm thấy file Sheet hoặc ID cấu hình sai: {sheet_err}")
            return
        
        try:
            worksheet = sh.worksheet("datauser")
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sh.add_worksheet(title="datauser", rows="500", cols="4")
            worksheet.append_row(["Tài khoản", "Mật khẩu", "Công ty", "Quyền hạn"])
            
        all_values = worksheet.get_all_values()
        
        # CHỈNH SỬA QUYẾT ĐỊNH: Bóc tách chính xác từng cột 0, 1, 2, 3 của mảng Google Sheet
        if all_values and len(all_values) > 1:
            for row in all_values[1:]:
                if row and len(row) >= 4:
                    u = str(row[0]).strip()  # Cột A: Tài khoản (Vị trí 0)
                    p = str(row[1]).strip()  # Cột B: Mật khẩu (Vị trí 1)
                    c = str(row[2]).strip()  # Cột C: Công ty (Vị trí 2)
                    r = str(row[3]).strip()  # Cột D: Quyền hạn (Vị trí 3)
                    if u:
                        DATA_USERS[u] = {"password": p, "company": c, "role": r}
        else:
            DATA_USERS["admin"] = {"password": "123456", "company": "ALL_COMPANIES", "role": "Tổng Quản Trị"}
            
    except Exception as e:
        st.error(f"⚠️ Hệ thống gặp lỗi xử lý dữ liệu bảng tính: {str(e)}")

def save_user_to_sheets(username, password, company, role, phone):
    """Ghi trực tiếp tài khoản mới được kích hoạt OTP thành công xuống Google Sheet vĩnh viễn"""
    try:
        import gspread
        import os
        import streamlit as st
        import json
        
        # --- CẤU HÌNH KẾT NỐI BẢO MẬT CHỐNG LỖI ASN.1 EXTRA DATA ---
        if "gspread_json" in st.secrets:
            raw_json_str = st.secrets["gspread_json"]
            creds_dict = json.loads(raw_json_str, strict=False)
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            gc = gspread.service_account_from_dict(creds_dict)
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            credentials_path = os.path.join(current_dir, 'credentials.json')
            gc = gspread.service_account(filename=credentials_path)
        # --------------------------------------------------------

        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheet = sh.worksheet("datauser")
        
        worksheet.append_row([username, password, company, role, phone])
        return True
    except Exception as e:
        st.error(f"❌ Lỗi ghi tài khoản vào Google Sheet: {e}")
        return False
#================================================================================================================
# LẤY ẢNH TỪ ĐOẠN MÃ HÓA STRING
def display_base64_image(base64_string):
    """Giải mã chuỗi Base64 từ Google Sheet và hiển thị lên Streamlit"""
    if base64_string and str(base64_string).strip() != "":
        # Streamlit hỗ trợ hiển thị trực tiếp chuỗi Base64 qua cấu trúc data URI
        st.image(f"data:image/jpeg;base64,{base64_string}", use_container_width=True)
#================================================================================================================

def send_otp_to_admin(company_name, username, password, otp_code, phone):
    """Hàm tự động gửi thông tin đăng ký và mã OTP về email Admin để duyệt"""
    server = None
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = ADMIN_EMAIL
        msg['Subject'] = f"🔑 [YÊU CẦU ACTIVE] Dự án Đại Sơn ME - {company_name}"

        body = f"""
        <h3>Hệ thống ghi nhận yêu cầu kích hoạt phần mềm mới:</h3>
        <p><b>🏢 Công ty:</b> {company_name}</p>
        <p><b>👤 Tài khoản đăng ký:</b> {username}</p>
        <p><b>🔒 Mật khẩu:</b> {password}</p>
        <p><b>📞 Số điện thoại liên hệ:</b> <a href="tel:{phone}">{phone}</a></p>
        <hr/>
        <p style='font-size: 18px; color: red;'><b>🔥 MÃ OTP ACTIVE CỦA LẦN NÀY LÀ: <span style='font-size: 24px;'>{otp_code}</span></b></p>
        <p><i>Vui lòng gọi điện hoặc nhắn tin theo SĐT trên để xác minh kích hoạt nếu họ đã thanh toán hoặc được cấp phép sử dụng!</i></p>
        """
        msg.attach(MIMEText(body, 'html', 'utf-8'))

        # Sử dụng khối kết nối bảo mật chuẩn mã hóa TLS
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, ADMIN_EMAIL, msg.as_string())
        return True
    except Exception as e:
        st.error(f"❌ Lỗi gửi email hệ thống: {e}")
        return False
    finally:
        # Đảm bảo đóng kết nối SMTP an toàn để tránh bị Google chặn IP ngầm
        if server:
            try:
                server.quit()
            except:
                pass
#===============================================================================    
# Kích hoạt quét danh sách user cloud ngay khi mở app
load_users_from_sheets()
#===============================================================================

# ============================================================================
# 2. KHỞI TẠO VÀ XỬ LÝ ĐĂNG NHẬP / ĐĂNG KÝ CÓ OTP KÍCH HOẠT
# ============================================================================
import random

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user_info'] = None
if 'reg_otp' not in st.session_state:
    st.session_state['reg_otp'] = None
if 'pending_user' not in st.session_state:
    st.session_state['pending_user'] = None

if not st.session_state['logged_in']:
    if os.path.exists("logo_cty.jpg"):
        st.image("logo_cty.jpg", width=200) 
    else:
        st.title("🏢")

    st.subheader("G7ĐS PROJECT MANAGER - HỆ THỐNG QUẢN LÝ DỰ ÁN")
    
    tab_login, tab_register = st.tabs(["🔒 Đăng Nhập Hệ Thống", "📝 Đăng Ký Tài Khoản Mới"])
    
    # --- TAB ĐĂNG NHẬP ---
    with tab_login:
        user = st.text_input("Tài khoản:", key="login_user")
        password = st.text_input("Mật khẩu:", type="password", key="login_pass")
        
        if st.button("Đăng nhập", type="primary", key="btn_login"):
            user_clean = user.strip().lower()
            if user_clean in DATA_USERS and DATA_USERS[user_clean]["password"] == password:
                st.session_state['logged_in'] = True
                st.session_state['user_info'] = {
                    "username": user_clean,
                    "company": DATA_USERS[user_clean]["company"],
                    "role": DATA_USERS[user_clean]["role"]
                }
                st.success("Đăng nhập thành công!")
                st.rerun() 
            else:
                st.error("Sai tài khoản hoặc mật khẩu! (Hoặc tài khoản chưa được phê duyệt)")

    # --- TAB ĐĂNG KÝ & XIN MÃ OTP ACTIVE CHỐNG DÙNG CHÙA ---
    with tab_register:
        if st.session_state['reg_otp'] is None:
            st.warning("⚠️ Tài khoản sau khi đăng ký sẽ bị Khóa. Bạn phải liên hệ Admin để nhận mã OTP kích hoạt sử dụng.")
            
            # SỬ DỤNG ST.FORM ĐỂ KHÓA DỮ LIỆU KHÔNG BỊ XOÁ KHI GÕ CHỮ
            with st.form(key="registration_form"):
                reg_company = st.text_input("Nhập Mã Công Ty của bạn:", key="reg_company_box").strip().upper()
                reg_user_raw = st.text_input("Tạo tài khoản đăng nhập (Hệ thống tự động xóa dấu):", key="reg_user_box").strip()
                reg_pass = st.text_input("Tạo mật khẩu đăng nhập:", type="password", key="reg_pass_box").strip()
                reg_phone = st.text_input("Nhập Số Điện Thoại (để liên hệ kích hoạt):", key="reg_phone_box").strip()
                
                # Nút bấm bắt buộc phải là st.form_submit_button khi nằm trong Form
                submit_reg = st.form_submit_button("🚀 Gửi yêu cầu cấp mã OTP Kích Hoạt", type="primary")
            
            # Xử lý làm sạch tên đăng nhập sau khi submit form
            if 'clean_username' in globals() or 'clean_username' in locals():
                reg_user = clean_username(reg_user_raw)
            else:
                import re
                reg_user = re.sub(r'[^a-zA-Z0-9]', '', reg_user_raw).lower()
                
            if submit_reg:
                # Kiểm tra dữ liệu sau khi bấm nút submit
                if not reg_company or not reg_user or not reg_pass or not reg_phone:
                    st.error("❌ Vui lòng điền đầy đủ Mã công ty, Tài khoản, Mật khẩu và Số điện thoại!")
                elif len(reg_phone) < 10 or not reg_phone.isdigit():
                    st.error("❌ Số điện thoại không hợp lệ! Vui lòng nhập đúng số điện thoại từ 10 chữ số.")
                elif reg_user in DATA_USERS:
                    st.error("❌ Tài khoản này đã tồn tại trên hệ thống dữ liệu!")
                else:
                    otp_generated = str(random.randint(100000, 999999))
                    
                    with st.spinner("Đang gửi thông tin đăng ký về Email Admin để lấy mã duyệt..."):
                        if send_otp_to_admin(reg_company, reg_user, reg_pass, otp_generated, reg_phone):
                            st.session_state['reg_otp'] = otp_generated
                            st.session_state['pending_user'] = {
                                "user": reg_user,
                                "password": reg_pass,
                                "company": reg_company,
                                "role": "Quản lý",
                                "phone": reg_phone
                            }
                            st.success(f"🚀 Yêu cầu đã gửi thành công tới Admin! Vui lòng liên hệ bộ phận kỹ thuật qua SĐT {reg_phone} để nhận mã OTP kích hoạt.")
                            st.rerun()
                        else:
                            st.error("❌ Lỗi gửi Email xác thực. Vui lòng kiểm tra lại trạng thái hoạt động của tài khoản xuantrucxala@gmail.com!")
        else:
            # GIAO DIỆN NHẬP MÃ XÁC THỰC OTP GIỮ NGUYÊN KHÔNG ĐỔI
            st.warning(f"🔒 Hệ thống đang chờ mã OTP kích hoạt cho tài khoản `{st.session_state['pending_user']['user']}`")
            input_otp = st.text_input("Nhập mã OTP kích hoạt (Gồm 6 số từ Email Admin):", key="reg_otp_box").strip()
            
            col_active, col_cancel = st.columns(2)
            with col_active:
                if st.button("✅ Xác Nhận Kích Hoạt Phần Mềm", type="primary", key="btn_otp_confirm"):
                    if input_otp == st.session_state['reg_otp']:
                        u_data = st.session_state['pending_user']
                        
                        with st.spinner("Đang kích hoạt và đồng bộ tài khoản bản quyền lên Cloud..."):
                            if save_user_to_sheets(u_data['user'], u_data['password'], u_data['company'], u_data['role'], u_data['phone']):
                                DATA_USERS[u_data['user']] = {
                                    "password": u_data['password'],
                                    "company": u_data['company'],
                                    "role": u_data['role'],
                                    "phone": u_data['phone']
                                }
                                st.success("🎉 Kích hoạt bản quyền thành công! Hiện tại bạn đã có thể quay lại tab Đăng nhập để sử dụng phần mềm.")
                                st.session_state['reg_otp'] = None
                                st.session_state['pending_user'] = None
                            else:
                                st.error("❌ Không thể đồng bộ tài khoản lên Google Sheet. Vui lòng kiểm tra kết nối API Sheet!")
                    else:
                        st.error("❌ Mã OTP kích hoạt không chính xác! Vui lòng kiểm tra lại.")
                        
            with col_cancel:
                if st.button("❌ Hủy bỏ lượt đăng ký này", key="btn_reg_cancel"):
                    st.session_state['reg_otp'] = None
                    st.session_state['pending_user'] = None
                    st.rerun()

# ============================================================================
# 3. NẾU ĐÃ ĐĂNG NHẬP THÀNH CÔNG (GIAO DIỆN CHÍNH)
# ============================================================================
else:
    user_info = st.session_state['user_info']
    
    # Thiết lập đường dẫn tệp sao lưu cục bộ
    MAIN_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_FILE = os.path.join(MAIN_DIR, f"backup_data_all.csv")

    # Đọc dữ liệu tập trung từ Google Sheet
    if "projects" not in st.session_state:
       load_data_from_sheets() 

    # Giao diện chính
    st.title("🏗️ HỆ THỐNG QUẢN LÝ & BÁO CÁO CÔNG TRÌNH ONLINE")
    
    # Thanh điều hướng Sidebar hiển thị thông tin phân quyền
    st.sidebar.markdown(f"### 🏢 **{user_info['company'] if user_info['company'] != 'ALL_COMPANIES' else 'ADMIN ĐẠI SƠN MANAGER PROJECT'}**")
    st.sidebar.markdown(f"👤 Tài khoản: `{user_info['username']}`")
    st.sidebar.markdown(f"💼 Quyền hạn: `{user_info['role']}`")
    
    if st.sidebar.button("Đăng xuất", type="secondary"):
        st.session_state['logged_in'] = False
        st.session_state['user_info'] = None
        if "projects" in st.session_state: del st.session_state["projects"]
        if "all_projects_raw" in st.session_state: del st.session_state["all_projects_raw"]
        st.rerun()
        
    st.sidebar.write("---")
    
    LOGO_PATH = os.path.join(MAIN_DIR, "assets", "logo cty.jpg")
    if os.path.exists(LOGO_PATH):
        st.sidebar.image(LOGO_PATH, width='stretch')
    else:
        st.sidebar.title("🏢 QUẢN LÝ DỰ ÁN")
    st.sidebar.write("---")  
    
    menu = st.sidebar.radio(
        "MENU CHỨC NĂNG",
        ["📊 Tổng Quan Tiến Độ", "📝 Báo Cáo & Cập Nhật", "➕ Thêm Công trình Mới"],
    )

    col_refresh, _ = st.columns([1, 4])
    with col_refresh:
        if st.button("🔄 Đồng bộ dữ liệu"):
            st.cache_data.clear()
            load_data_from_sheets()
            st.success("Đã đồng bộ!")
            st.rerun()
    st.markdown("---")
    # ============================================================================================
    # CHỨC NĂNG 1: TỔNG QUAN TIẾN ĐỘ & HIỂN THỊ
    # ============================================================================================
    if menu == "📊 Tổng Quan Tiến Độ":
        st.subheader(f"Danh sách các công trình đang thi công - {user_info['company']}")
        
        if "projects" in st.session_state and st.session_state["projects"].empty:
            st.info("Hệ thống chưa có dữ liệu công trình nào của công ty bạn. Vui lòng thêm mới!")
        else:
            # 1. LẤY DỮ LIỆU GỐC TỪ SESSION STATE
            df_raw = st.session_state["projects"].copy()

            # Làm sạch dữ liệu chuỗi trống để tránh lỗi gộp nhóm
            for col in ["Miêu tả", "Ảnh"]:
                if col in df_raw.columns:
                    df_raw[col] = df_raw[col].astype(str).apply(
                        lambda x: "" if x.strip().lower() in ["nan", "", "none", "null"] else x.strip()
                    )
                else:
                    df_raw[col] = ""

            # 2. XỬ LÝ GỘP NHÓM (GROUPBY) THEO ID (BẢN VÁ SỬA LỖI HIỂN THỊ HÌNH ẢNH TUYỆT ĐỐI)
            df_raw = df_raw.reset_index() 
            
            # Hàm gộp ảnh: CHỈ LẤY CHUỖI BASE64 HỢP LỆ, LOẠI BỎ 100% CHUỖI TRỐNG HOẶC RÁC HỆ THỐNG
            def join_images(series):
                valid_imgs = []
                for img_str in series:
                    img_clean = str(img_str).strip()
                    # Loại bỏ các giá trị rác hoặc rỗng trước khi gộp
                    if img_clean and img_clean.lower() not in ["none", "nan", "", "null"] and len(img_clean) > 100:
                        # Nếu chuỗi cũ lỡ có tiền tố thì lọc bỏ, chỉ lấy phần base64 thô
                        if "base64," in img_clean:
                            img_clean = img_clean.split("base64,")[-1]
                        if img_clean not in valid_imgs:
                            valid_imgs.append(img_clean)
                return ",".join(valid_imgs) if valid_imgs else ""

            # Hàm gộp miêu tả: Giữ nguyên khối văn bản sạch, không trùng lặp
            def join_descriptions(series):
                seen_blocks = set()
                valid_blocks = []
                for d in series:
                    txt = str(d).strip()
                    if not txt or txt.lower() in ["nan", "none", "null", ""] or txt.startswith("data:image"):
                        continue
                    normalized_txt = " ".join(txt.split())
                    if normalized_txt and normalized_txt not in seen_blocks:
                        seen_blocks.add(normalized_txt)
                        valid_blocks.append(txt)
                return " [SPLIT_DATE] ".join(valid_blocks) if valid_blocks else ""

            # Thực hiện Gom nhóm theo ID công trình
            df_display = df_raw.groupby("ID").agg({
                "Công ty": "last",          
                "Công trình": "last",      
                "Tình trạng": "last",      
                "Tiến độ (%)": "last",     
                "Người phụ trách": "last", 
                "Cập nhật cuối": "last",   
                "Miêu tả": join_descriptions, 
                "Ảnh": join_images          # Gom toàn bộ chuỗi ảnh sạch về phân tách bởi dấu phẩy
            }).reset_index()

            # SỬA TRIỆT ĐỂ LỖI 🔄0: Lấy chính xác CHUỖI TEXT THUẦN TÚY (String) của bức ảnh đầu tiên làm ảnh đại diện
            df_table = df_display.copy()
            def get_avatar_image(x):
                val = str(x).strip()
                if not val or val.lower() in ["none", "nan", ""]:
                    return ""
                parts = [p.strip() for p in val.split(",") if p.strip()]
                # Thêm tiền tố chuẩn cho ImageColumn của st.dataframe
                return f"data:image/jpeg;base64,{parts[0]}" if parts else ""

            df_table["Ảnh"] = df_table["Ảnh"].apply(get_avatar_image)

            show_columns = ["ID", "Công trình", "Tình trạng", "Tiến độ (%)", "Người phụ trách", "Cập nhật cuối", "Miêu tả", "Ảnh"]
            valid_columns = [col for col in show_columns if col in df_table.columns]

            # Hiển thị bảng tổng hợp duy nhất 1 hàng sạch sẽ lên màn hình
            st.dataframe(
                df_table[valid_columns],
                width='stretch',
                hide_index=True,
                column_config={
                    "Ảnh": st.column_config.ImageColumn("Ảnh đại diện", help="Ảnh chụp thực tế mới nhất từ công trường"),
                    "Miêu tả": st.column_config.Column("Lịch sử nhật ký công trường", width="large"),
                },
            )
            
            # --- KHU VỰC XEM CHI TIẾT BÁO CÁO CÔNG TRƯỜNG (HIỂN THỊ ĐẦY ĐỦ TẤT CẢ ẢNH ĐÃ GÔM) ---
            # --- KHU VỰC XEM CHI TIẾT BÁO CÁO CÔNG TRƯỜNG ---
            st.markdown("### 🔍 Chi tiết báo cáo công trường")
        
            for idx, row in df_display.iterrows():
                with st.expander(f"🚧 [{row['ID']}] {row['Công trình']} (Tiến độ: {row['Tiến độ (%)']}%)"):
                    col_left, col_right = st.columns([3, 2]) # Tăng tỷ lệ cột chữ rộng hơn để hiển thị nhật ký thoáng đãng
                
                    with col_left:
                        st.markdown(f"**Trạng thái mới nhất:** `{row['Tình trạng']}`")
                        st.markdown(f"**Người phụ trách mới nhất:** {row['Người phụ trách']}")
                        st.markdown(f"**Cập nhật cuối:** {row['Cập nhật cuối']}")
                        st.markdown("**📋 Nhật ký tiến độ theo từng ngày:**")
                    
                        txt_mieu_ta = str(row["Miêu tả"]).strip()
                        if txt_mieu_ta:
                            # Tách các ngày báo cáo cũ dựa trên ký tự phân tách " | "
                            parts_desc = [p.strip() for p in txt_mieu_ta.split(" | ") if p.strip()]
                            
                            for part_desc in parts_desc:
                                # Tạo một hộp màu xám/xanh bo góc chuyên nghiệp độc lập cho từng ngày báo cáo
                                with st.container(border=True):
                                    # Kiểm tra xem trong chuỗi có định dạng ngày (ví dụ "1. Ngày" hoặc chứa dấu hai chấm) hay không
                                    if ":" in part_desc:
                                        # Tách tiêu đề ngày và nội dung chi tiết để làm nổi bật dòng thời gian
                                        tieu_de, noi_dung = part_desc.split(":", 1)
                                        st.markdown(f"**📅 {tieu_de.strip()}:**")
                                        st.markdown(noi_dung.strip())
                                    else:
                                        st.markdown(part_desc)
                        else:
                            st.caption("*(Chưa có nội dung miêu tả chi tiết)*")
                    
                    with col_right:
                        raw_anh = str(row["Ảnh"]).strip()
                        
                        if raw_anh and raw_anh.lower() not in ["none", "nan", ""]:
                            # Tách các chuỗi base64 đơn lẻ ra từ dấu phẩy
                            img_list = [img.strip() for img in raw_anh.split(",") if img.strip() and len(img.strip()) > 100]
                            
                            if img_list:
                                st.markdown(f"**📸 Bộ sưu tập ảnh thực tế ({len(img_list)} ảnh):**")
                                sub_cols = st.columns(2)
                                for i, single_img in enumerate(img_list):
                                    with sub_cols[i % 2]:
                                        try:
                                            # Nếu chuỗi chưa có tiền tố html data, tự động thêm vào để st.image đọc được
                                            if not single_img.startswith("data:image"):
                                                full_base64_str = f"data:image/jpeg;base64,{single_img}"
                                            else:
                                                full_base64_str = single_img
                                                
                                            st.image(full_base64_str, use_container_width=True)
                                        except Exception:
                                            st.caption("⚠️ File ảnh lỗi không thể hiển thị")
                            else:
                                st.caption("*(Chưa có ảnh thực tế hợp lệ)*")
                        else:
                            st.caption("*(Chưa có ảnh thực tế)*")

            # --- BIỂU ĐỒ TIẾN ĐỘ THỰC TẾ (BẢN SỬA LỖI HIỂN THỊ THIẾU CỘT) ---
        st.markdown("---")
        st.subheader("Biểu đồ tiến độ thực tế (%)")
        
        if not st.session_state["projects"].empty:
            try:
                import plotly.express as px
                
                # 1. Tạo một bản sao dữ liệu để làm sạch, tránh ảnh hưởng đến bảng gốc
                df_chart = st.session_state["projects"].copy()
                
                # 2. Làm sạch dữ liệu: Xóa khoảng trắng ở tên công trình, ép tiến độ về dạng số thực (float)
                df_chart["Công trình"] = df_chart["Công trình"].astype(str).str.strip()
                
                # Loại bỏ ký tự % nếu người dùng vô tình nhập vào sheet, chuyển chuỗi trống thành 0
                df_chart["Tiến độ (%)"] = (
                    df_chart["Tiến độ (%)"]
                    .astype(str)
                    .str.replace("%", "")
                    .str.strip()
                )
                df_chart["Tiến độ (%)"] = pd.to_numeric(df_chart["Tiến độ (%)"], errors="coerce").fillna(0)
                
                # 3. Vẽ biểu đồ cột bằng Plotly Express để đảm bảo hiển thị ĐẦY ĐỦ các công trình
                fig = px.bar(
                    df_chart, 
                    x="Công trình", 
                    y="Tiến độ (%)",
                    text="Tiến độ (%)",  # Hiển thị số % trực tiếp trên đầu cột cho dễ nhìn
                    labels={"Tiến độ (%)": "Tiến độ thực tế (%)", "Công trình": "Tên công trình"},
                    template="plotly_white"
                )
                
                # 4. Định dạng hiển thị cột màu xanh chuẩn và hiển thị số % rõ ràng
                fig.update_traces(
                    marker_color="#1f77b4", 
                    texttemplate="%{text}%", 
                    textposition="outside"
                )
                
                # Ép trục X nhận diện từng công trình độc lập (không bị gộp hoặc bỏ sót công trình sau)
                fig.update_layout(
                    xaxis_type="category", 
                    yaxis_range=[0, 105], # Giới hạn trục Y từ 0 đến 105% để không bị tràn số
                    margin=dict(l=20, r=20, t=20, b=20)
                )
                
                # 5. Hiển thị biểu đồ lên giao diện Streamlit
                st.plotly_chart(fig, use_container_width=True)
                
            except Exception as chart_err:
                # Phương án dự phòng bằng st.bar_chart gốc nếu máy bạn chưa cài plotly
                # nhưng đã được làm sạch dữ liệu để sửa lỗi hiển thị
                df_backup = st.session_state["projects"].copy()
                df_backup["Tiến độ (%)"] = pd.to_numeric(df_backup["Tiến độ (%)"], errors='coerce').fillna(0)
                st.bar_chart(
                    data=df_backup, 
                    x="Công trình", 
                    y="Tiến độ (%)", 
                    color="#1f77b4"
                )
        else:
            st.info("💡 Chưa có dữ liệu công trình để hiển thị biểu đồ!")
    
    # ===================================================================================================================
    # CHỨC NĂNG 2: BÁO CÁO & CẬP NHẬT (LƯU ẢNH & ĐỒNG BỘ SHEET TỔNG)
    # ===================================================================================================================
    elif menu == "📝 Báo Cáo & Cập Nhật":
        st.subheader("Cập nhật tình trạng & Tải ảnh công trình")
        
        project_list = st.session_state["projects"]["Công trình"].tolist()
        if not project_list:
            st.warning("Hiện chưa có Công trình nào khả dụng để báo cáo. Hãy thêm mới!")
        else:
            selected_task = st.selectbox("Chọn công trình muốn báo cáo:", project_list)
            
            # 🟢 KHAI BÁO BIẾN ĐỂ SỬA LỖI: Tìm index thực tế dựa trên bảng dữ liệu thô tổng hợp (Bảng chưa lọc)
            raw_task_idx = st.session_state["all_projects_raw"][st.session_state["all_projects_raw"]["Công trình"] == selected_task].index[0]
            current_row = st.session_state["all_projects_raw"].loc[raw_task_idx]
            
            current_desc = str(current_row["Miêu tả"]).strip() if "Miêu tả" in current_row and not pd.isna(current_row["Miêu tả"]) else ""
            if current_desc.lower() == "nan": 
                current_desc = ""
                
            with st.form("report_form"):
                col1, col2 = st.columns(2)
                with col1:
                    status_options = ["Chưa bắt đầu", "Đang thực hiện", "Tạm dừng", "Hoàn thành"]
                    status = st.selectbox("Tình trạng hiện tại:", status_options, index=status_options.index(current_row["Tình trạng"]))
                    progress = st.slider("Tiến độ đạt được (%)", min_value=0, max_value=100, value=int(current_row["Tiến độ (%)"]))

                with col2:
                    staff = st.text_input("Người báo cáo:", value=current_row["Người phụ trách"])
                    uploaded_files = st.file_uploader("Tải lên ảnh thực tế từ công trường:", type=["jpg", "png", "jpeg"], accept_multiple_files=True)

                    if not pd.isna(current_row["Ảnh"]) and str(current_row["Ảnh"]).strip():
                        st.write("📸 **Hình ảnh công trường hiện tại:**")
                        img_list = [img.strip() for img in str(current_row["Ảnh"]).split(",") if img.strip()]
                        cols = st.columns(min(len(img_list), 3))
                        for i, img_item in enumerate(img_list):
                            with cols[i % 3]:
                                # CHỈNH SỬA TỐI ƯU HIỂN THỊ: Tự động phân tách hiển thị cả ảnh mã hóa Base64 online lẫn ảnh folder Local
                                if img_item.startswith("data:image"):
                                    st.image(img_item, width=120)
                                else:
                                    full_path_test = os.path.join(MAIN_DIR, img_item)
                                    if os.path.exists(full_path_test):
                                        st.image(full_path_test, width=120)
                                    else:
                                        st.caption(f"Ảnh Local cũ")
                                
                description = st.text_area("Miêu tả chi tiết tình hình công trường / Ghi chú:", value=current_desc)
                submitted = st.form_submit_button("Cập nhật báo cáo")
                
                if submitted:
                    current_images = [] # Sửa lỗi định nghĩa biến hệ thống
                    today_str = pd.Timestamp.now().strftime("%Y-%m-%d")
                    so_luong_thanh_cong = 0
                    
                    try:
                        import gspread
                        import json
                        if "gspread_json" in st.secrets:
                            raw_json_str = st.secrets["gspread_json"]
                            creds_dict = json.loads(raw_json_str, strict=False)
                            if "private_key" in creds_dict:
                                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
                            gc = gspread.service_account_from_dict(creds_dict)
                        else:
                            current_dir = os.path.dirname(os.path.abspath(__file__))
                            credentials_path = os.path.join(current_dir, 'credentials.json')
                            gc = gspread.service_account(filename=credentials_path)
                            
                        sh = gc.open_by_key(SPREADSHEET_ID)
                        worksheet = sh.worksheet("datacongtrinh")
                    except Exception as sheet_conn_err:
                        st.error(f"❌ Thất bại khi kết nối Google Sheets: {sheet_conn_err}")
                        st.stop()

                    # ============================================================================
                    # TRƯỜNG HỢP 1: NGƯỜI DÙNG CÓ UP ẢNH -> TÁCH MỖI ẢNH THÀNH 1 DÒNG BÁO CÁO MỚI
                    # ============================================================================
                    if uploaded_files:
                        with st.spinner("Đang xử lý nén sâu và bóc tách dòng báo cáo kèm ảnh..."):
                            import base64
                            from PIL import Image
                            import io

                            for u_file in uploaded_files:
                                try:
                                    # --- ĐỌC VÀ NÉN SÂU ẢNH ---
                                    image = Image.open(u_file)
                                    if image.mode in ("RGBA", "P"):
                                        image = image.convert("RGB")

                                    # Ép kích thước về 400px giúp ảnh siêu nhẹ, không vượt giới hạn ký tự Google Sheet
                                    max_size = 400
                                    if image.width > max_size or image.height > max_size:
                                        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

                                    buffered = io.BytesIO()
                                    image.save(buffered, format="JPEG", quality=30) # Chất lượng nén 30% lý tưởng
                                    
                                    # CHỈ LẤY CHUỖI THÔ (Không chèn text "data:image" ở đây để tránh trùng lặp)
                                    encoded_img = base64.b64encode(buffered.getvalue()).decode("utf-8")

                                    # --- ĐÓNG GÓI MẢNG DỮ LIỆU ĐẦY ĐỦ 9 CỘT ---
                                    new_row_values = [
                                        str(current_row["Công ty"]), 
                                        str(current_row["ID"]),
                                        str(selected_task), 
                                        str(status), 
                                        int(progress),
                                        str(staff).strip(), 
                                        str(today_str), 
                                        str(encoded_img),  # Lưu chuỗi Base64 thô sạch sẽ vào cột H
                                        str(description).strip()
                                    ]

                                    # --- ĐẨY LÊN GOOGLE SHEET ---
                                    worksheet.append_row(new_row_values)
                                    so_luong_thanh_cong += 1

                                except Exception as e:
                                    st.error(f"❌ Lỗi xử lý mã hóa hình ảnh {u_file.name}: {e}")
                                    
                            if so_luong_thanh_cong > 0:
                                st.success(f"🎉 Đã đồng bộ thành công {so_luong_thanh_cong} hình ảnh (chia tách thành các dòng nhật ký độc lập) lên Google Sheets!")
                                load_data_from_sheets()
                                st.rerun()

                    # ============================================================================
                    # TRƯỜNG HỢP 2: KHÔNG UP ẢNH -> GHI ĐÈ BÁO CÁO CHỮ LÊN DÒNG CŨ NHƯ TRƯỚC ĐÂY
                    # ============================================================================
                    else:
                        with st.spinner("Đang cập nhật báo cáo tiến độ..."):
                            try:
                                sheet_row_idx = int(raw_task_idx) + 2 
                                updated_row_values = [
                                    str(current_row["Công ty"]), 
                                    str(current_row["ID"]),
                                    str(selected_task), 
                                    str(status), 
                                    int(progress),
                                    str(staff).strip(), 
                                    str(today_str), 
                                    str(current_row["Ảnh"]), # Giữ nguyên chuỗi ảnh cũ trong sheet
                                    str(description).strip()
                                ]
                                worksheet.update(f"A{sheet_row_idx}:I{sheet_row_idx}", [updated_row_values])
                                st.success("🎉 Cập nhật báo cáo tiến độ thành công!")
                                load_data_from_sheets()
                                st.rerun()
                            except Exception as sheet_err:
                                st.error(f"❌ Lỗi đồng bộ dữ liệu báo cáo chữ: {sheet_err}")

                    # Gom tất cả các link ảnh thành chuỗi văn bản cách nhau bởi dấu phẩy
                    final_img_str = ",".join(current_images) if current_images else "None"
                    today_str = pd.Timestamp.now().strftime("%Y-%m-%d")
                    
                    # ============================================================================
                    # ĐỒNG BỘ DỮ LIỆU LÊN GOOGLE SHEET
                    # ============================================================================
                    try:
                        import gspread
                        import json
                        
                        try:
                            if "gspread_json" in st.secrets:
                                raw_json_str = st.secrets["gspread_json"]
                                creds_dict = json.loads(raw_json_str, strict=False)
                                if "private_key" in creds_dict:
                                    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
                                gc = gspread.service_account_from_dict(creds_dict)
                            else:
                                current_dir = os.path.dirname(os.path.abspath(__file__))
                                credentials_path = os.path.join(current_dir, 'credentials.json')
                                gc = gspread.service_account(filename=credentials_path)
                        except Exception as secret_err:
                            gc = gspread.service_account(filename=os.path.join(MAIN_DIR, 'credentials.json'))
                            
                        sh = gc.open_by_key(SPREADSHEET_ID)
                        worksheet = sh.worksheet("datacongtrinh")
                        
                        # Định vị dòng chính xác trên Sheet tổng (+2)
                        sheet_row_idx = int(raw_task_idx) + 2 
                        
                        updated_row_values = [
                            str(current_row["Công ty"]), 
                            str(current_row["ID"]),
                            str(selected_task), 
                            str(status), 
                            int(progress),
                            str(staff).strip(), 
                            str(today_str), 
                            str(final_img_str), 
                            str(description).strip()
                        ]
                        
                        worksheet.update(f"A{sheet_row_idx}:I{sheet_row_idx}", [updated_row_values])
                        st.success("🎉 Cập nhật báo cáo tiến độ và hình ảnh lên Google Sheets thành công!")
                        load_data_from_sheets()
                        st.rerun()
                    except Exception as sheet_err:
                        st.error(f"❌ Lỗi đồng bộ dữ liệu báo cáo lên Google Sheet: {sheet_err}")
    
    # ================================================================================================================
    # CHỨC NĂNG 3: THÊM HẠNG MỤC MỚI (HOÀN THIỆN ĐA CÔNG TY)
    # ================================================================================================================
    elif menu == "➕ Thêm Công trình Mới":
        st.subheader(f"Thêm công trình thi công mới - Không gian {user_info['company']}")

        with st.form("add_project_form"):
            col1, col2 = st.columns(2)

            with col1:
                new_id = st.text_input("Mã công trình (Ví dụ: DA03):").strip()
                new_name = st.text_input("Tên công trình thi công:").strip()
                new_status = st.selectbox(
                    "Trạng thái ban đầu:",
                    ["Chưa bắt đầu", "Đang thực hiện", "Tạm dừng"],
                )

            with col2:
                new_progress = st.slider(
                    "Tiến độ ban đầu (%)", min_value=0, max_value=100, value=0
                )
                new_staff = st.text_input("Người phụ trách chính:", value=user_info['username']).strip()

            submitted = st.form_submit_button("Thêm mới công trình", type="primary")

            if submitted:
                # 1. Kiểm tra nghiêm ngặt dữ liệu đầu vào
                if not new_id or not new_name or not new_staff:
                    st.error("❌ Vui lòng điền đầy đủ tất cả các trường thông tin!")
                elif new_id in st.session_state["projects"]["ID"].astype(str).values:
                    st.error("❌ Mã công trình này đã tồn tại trong hệ thống của bạn! Vui lòng nhập mã khác.")
                else:
                    current_time = pd.Timestamp.now().strftime("%Y-%m-%d")

                    # 2. Định dạng mảng dữ liệu chuẩn xác tuyệt đối 9 cột đồng bộ từ cột A đến cột I
                    row_to_sheets = [
                        str(user_info['company']),  # Cột A: Mã Công ty
                        str(new_id),                # Cột B: ID dự án
                        str(new_name),              # Cột C: Tên Công trình
                        str(new_status),            # Cột D: Tình trạng hiện tại
                        int(new_progress),          # Cột E: Tiến độ (%)
                        str(new_staff),             # Cột F: Người phụ trách
                        str(current_time),          # Cột G: Cập nhật cuối
                        "None",                     # Cột H: Chuỗi ảnh mã hóa Base64
                        ""                          # Cột I: Miêu tả ghi chú
                    ]

                    # 3. Tiến hành kết nối trực tiếp và ghi đè an toàn lên Cloud Google Sheets thông qua Secrets
                    try:
                        import gspread
                        import json
                        
                        with st.spinner("Đang đồng bộ dữ liệu công trình lên Cloud..."):
                            # --- ĐỒNG BỘ CẤU HÌNH KẾT NỐI BẢO MẬT CHỐNG LỖI ASN.1 EXTRA DATA ---
                            if "gspread_json" in st.secrets:
                                raw_json_str = st.secrets["gspread_json"]
                                creds_dict = json.loads(raw_json_str, strict=False)
                                if "private_key" in creds_dict:
                                    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
                                gc = gspread.service_account_from_dict(creds_dict)
                            else:
                                current_dir = os.path.dirname(os.path.abspath(__file__))
                                credentials_path = os.path.join(current_dir, 'credentials.json')
                                gc = gspread.service_account(filename=credentials_path)
                            # -----------------------------------------------------------------
                            
                            sh = gc.open_by_key(SPREADSHEET_ID)
                            worksheet = sh.worksheet("datacongtrinh")
                            
                            # Ghi hàng dữ liệu chuẩn hóa 9 cột xuống Google Sheet tổng
                            worksheet.append_row(row_to_sheets)
                            
                        st.success(f"🎉 Đã thêm thành công và sao lưu lên Google Sheet: {new_name}")
                        
                        # Gọi hàm reload để nạp mảng dữ liệu mới từ Cloud về bộ nhớ RAM của ứng dụng
                        load_data_from_sheets()
                        st.rerun()
                        
                    except Exception as sheet_err:
                        # Phương án dự phòng lưu tạm xuống file CSV cục bộ nếu mạng yếu hoặc lỗi API gspread
                        st.warning(f"⚠️ Lỗi kết nối Google Sheet ({sheet_err}). Chương trình tiến hành sao lưu vào bộ nhớ tạm local máy tính.")
                        
                        # Tạo cấu trúc từ điển khớp dữ liệu
                        new_data = {
                            "Công ty": user_info['company'],
                            "ID": new_id,
                            "Công trình": new_name,
                            "Tình trạng": new_status,
                            "Tiến độ (%)": new_progress,
                            "Người phụ trách": new_staff,
                            "Cập nhật cuối": current_time,
                            "Ảnh": "None",
                            "Miêu tả": ""
                        }
                        
                        st.session_state["projects"] = pd.concat(
                            [st.session_state["projects"], pd.DataFrame([new_data])],
                            ignore_index=True,
                        )
                        
                        try:
                            st.session_state["projects"].to_csv(DATA_FILE, index=False, encoding="utf-8-sig")
                            st.success(f"✅ Đã lưu tạm thành công công trình vào file nội bộ: {new_name}")
                            st.rerun()
                        except Exception as csv_error:
                            st.error(f"❌ Lỗi nghiêm trọng: Hệ thống không thể ghi dữ liệu cục bộ! Chi tiết: {csv_error}")

# ============================================================================
# CHÂN TRANG (KHỐI LỆNH ĐƯỢC ĐƯA RA NGOÀI NHÁNH ĐĂNG NHẬP ĐỂ LUÔN HIỂN THỊ)
# ============================================================================
logo_path = "logo_cty.jpg"
logo_base64 = ""

# Kiểm tra xem file logo có tồn tại trong thư mục code không
if os.path.exists(logo_path):
    with open(logo_path, "rb") as image_file:
        # Mã hóa ảnh sang Base64 text để nhúng trực tiếp vào thẻ HTML
        logo_base64 = base64.b64encode(image_file.read()).decode('utf-8')

# Tạo thẻ img HTML nếu chuyển đổi thành công
if logo_base64:
    logo_html = f'<img src="data:image/jpeg;base64,{logo_base64}" style="height: 30px; vertical-align: middle; margin-right: 10px; border-radius: 4px;">'
else:
    # Nếu không tìm thấy file logo_cty.jpg, tự động dùng tạm emoji tòa nhà để không bị trống trang
    logo_html = '🏢 '

# Đưa chữ chạy cùng LOGO công ty vào chân trang web công nghệ HTML Marquee
st.markdown(
    f"""
    <div style="background-color: #f0f2f6; padding: 10px; border-radius: 5px; margin-top: 30px;">
        <marquee behavior="scroll" direction="left" scrollamount="6" style="font-size: 24px; font-weight: bold; color: #ff4b4b; font-family: sans-serif;">
            {logo_html}Đại Sơn ME group - Đồng hành cùng mọi công trình!
        </marquee>
    </div>
    """, 
    unsafe_allow_html=True
)
        
        