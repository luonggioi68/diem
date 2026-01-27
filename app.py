import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
import json

# --- 1. CẤU HÌNH & KẾT NỐI FIREBASE ---
st.set_page_config(page_title="Hệ Thống Tra Cứu Điểm (Firebase)", page_icon="🔥", layout="wide")

# Hàm kết nối Firebase an toàn
def init_firebase():
    # Kiểm tra xem đã kết nối chưa để tránh lỗi init lại
    if not firebase_admin._apps:
        # Lấy thông tin từ Streamlit Secrets (An toàn nhất)
        key_dict = json.loads(st.secrets["textkey"])
        cred = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(cred)
    return firestore.client()

# --- 2. CSS GIAO DIỆN ---
st.markdown("""
<style>
    [data-testid="stSidebar"] {display: none;}
    .main-header {
        background: linear-gradient(135deg, #FF8C00 0%, #FF0080 100%);
        padding: 20px; border-radius: 12px; color: white; text-align: center;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1); margin-bottom: 25px;
    }
    .report-card {
        background: white; padding: 25px; border: 2px solid #eee;
        border-radius: 12px; box-shadow: 0 5px 15px rgba(0,0,0,0.05);
    }
    .school-name { color: #cc0000; font-weight: 900; font-size: 20px; text-transform: uppercase; text-align: center;}
    .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 15px; margin-top: 20px; }
    .summary-item { background: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 4px solid #FF8C00; text-align: center; }
    .summary-val { font-size: 18px; font-weight: bold; color: #333; margin-top: 5px; display:block;}
</style>
""", unsafe_allow_html=True)

# --- 3. XỬ LÝ FILE EXCEL ---
def safe_str(val):
    if pd.isna(val) or str(val).lower() in ['nan', 'none', '']: return ""
    s = str(val).strip()
    if s.endswith('.0'): s = s[:-2]
    return s

# Hàm upload lên Firebase
def upload_to_firebase(db, file, sem, cls, type_file):
    # type_file: 'score' (điểm) hoặc 'summary' (tổng kết)
    count = 0
    try:
        if type_file == 'score':
            xls = pd.read_excel(file, sheet_name=None)
            for sheet_name, df in xls.items():
                if "hướng dẫn" in sheet_name.lower(): continue
                
                # Tìm header
                h_idx = -1
                for i, row in df.iterrows():
                    if row.astype(str).str.contains("Mã học sinh", case=False).any():
                        h_idx = i; break
                
                if h_idx != -1:
                    df.columns = df.iloc[h_idx]; df = df.iloc[h_idx+1:]
                    cols = df.columns.tolist()
                    idx_ma = next((i for i, c in enumerate(cols) if "Mã học sinh" in str(c)), -1)
                    
                    if idx_ma != -1:
                        batch = db.batch() # Dùng batch để ghi nhanh
                        for _, row in df.iterrows():
                            ma_hs = safe_str(row.iloc[idx_ma])
                            if len(ma_hs) > 3:
                                # Lấy tên HS để cập nhật bảng students
                                try: 
                                    ten_hs = safe_str(row.iloc[idx_ma-2])
                                    # Lưu thông tin HS
                                    ref_st = db.collection('students').document(ma_hs)
                                    batch.set(ref_st, {'id': ma_hs, 'name': ten_hs, 'cls': cls, 'active': 1}, merge=True)
                                except: pass

                                # Lưu điểm
                                def g(off): 
                                    try: return safe_str(row.iloc[idx_ma+off])
                                    except: return ""
                                
                                tx = "  ".join([g(k) for k in range(1,10) if g(k)])
                                doc_id = f"{ma_hs}_{sem}_{sheet_name.strip()}" # ID duy nhất
                                
                                ref_sc = db.collection('scores').document(doc_id)
                                batch.set(ref_sc, {
                                    'id': ma_hs, 'sub': sheet_name.strip(), 'sem': sem, 'cls': cls,
                                    'tx': tx, 'gk': g(16), 'ck': g(26), 'tb': g(27), 
                                    'cn': (g(28) if sem=='HK2' else "")
                                })
                                count += 1
                                if count % 400 == 0: # Firebase giới hạn batch 500
                                    batch.commit()
                                    batch = db.batch()
                        batch.commit() # Commit phần còn lại

        elif type_file == 'summary':
            df = pd.read_excel(file) if file.name.endswith(('xlsx','xls')) else pd.read_csv(file)
            if 'Mã học sinh' not in df.columns:
                for i, row in df.iterrows():
                    if row.astype(str).str.contains("Mã học sinh").any():
                        df.columns = df.iloc[i]; df = df.iloc[i+1:]; break
            df.columns = df.columns.str.strip()
            
            batch = db.batch()
            for _, row in df.iterrows():
                ma = safe_str(row.get('Mã học sinh'))
                if len(ma) > 3:
                    doc_id = f"{ma}_{sem}_summary"
                    ref_sum = db.collection('summary').document(doc_id)
                    batch.set(ref_sum, {
                        'id': ma, 'sem': sem, 'cls': cls,
                        'ht': safe_str(row.get('Học tập')), 'rl': safe_str(row.get('Rèn luyện')),
                        'v': safe_str(row.get('Vắng')), 'dh': safe_str(row.get('Danh hiệu')),
                        'kq': safe_str(row.get('Kết quả'))
                    })
                    count += 1
            batch.commit()
            
    except Exception as e:
        st.error(f"Lỗi: {e}")
    return count

# --- 4. GIAO DIỆN ADMIN ---
def view_admin(db):
    st.markdown('<div class="main-header">🛠️ QUẢN TRỊ VIÊN (FIREBASE)</div>', unsafe_allow_html=True)
    if st.button("⬅️ Thoát"): st.session_state.page = 'login'; st.rerun()
    
    if st.text_input("Mật khẩu:", type="password") == "admin123":
        cls = st.selectbox("Chọn Lớp:", [f"Lớp {i}" for i in range(6, 13)])
        
        c1, c2 = st.columns(2)
        f1 = c1.file_uploader(f"Điểm HK1 {cls}", key="f1")
        f2 = c1.file_uploader(f"Điểm HK2 {cls}", key="f2")
        t1 = c2.file_uploader(f"TK HK1 {cls}", key="t1")
        t2 = c2.file_uploader(f"TK HK2 {cls}", key="t2")
        t3 = c2.file_uploader(f"TK Cả Năm {cls}", key="t3")
        
        if st.button("LƯU LÊN DATABASE (CLOUD)", type="primary"):
            with st.spinner("Đang đẩy dữ liệu lên mây..."):
                cnt = 0
                if f1: cnt += upload_to_firebase(db, f1, "HK1", cls, 'score')
                if f2: cnt += upload_to_firebase(db, f2, "HK2", cls, 'score')
                if t1: cnt += upload_to_firebase(db, t1, "HK1", cls, 'summary')
                if t2: cnt += upload_to_firebase(db, t2, "HK2", cls, 'summary')
                if t3: cnt += upload_to_firebase(db, t3, "CN", cls, 'summary')
                st.success(f"Xong! Đã cập nhật {cnt} bản ghi lên hệ thống.")

# --- 5. GIAO DIỆN HỌC SINH ---
def view_student(db):
    c1, c2 = st.columns([8, 1])
    c1.markdown("### 🔥 TRA CỨU ĐIỂM (ONLINE)")
    if c2.button("⚙️"): st.session_state.page = 'admin'; st.rerun()

    if 'user' not in st.session_state:
        mid = st.text_input("Nhập Mã Học Sinh (Ví dụ: 2411...):").strip()
        if st.button("Xem Điểm", type="primary"):
            # Tìm trong Collection Students
            docs = db.collection('students').where('id', '==', mid).stream()
            u = None
            for doc in docs: u = doc.to_dict()
            
            if not u: st.error("Mã không đúng")
            elif u.get('active') == 0: st.warning("Chưa kích hoạt")
            else: st.session_state.user = u; st.rerun()
    else:
        u = st.session_state.user
        if st.button("⬅️ Tra cứu khác"): del st.session_state.user; st.rerun()
        
        st.markdown(f"""
        <div class="report-card">
            <div class="school-name">TRƯỜNG THCS & THPT TUY ĐỨC</div>
            <div style="text-align:center; color:#FF8C00; font-weight:bold; margin-bottom:10px;">KẾT QUẢ HỌC TẬP</div>
            <div><b>Học sinh:</b> {u['name']} | <b>Mã:</b> {u['id']} | <b>Lớp:</b> {u['cls']}</div>
        </div>
        """, unsafe_allow_html=True)
        
        ky = st.radio("Chọn:", ["Học kỳ 1", "Học kỳ 2 & Cả năm"], horizontal=True)
        sem = "HK1" if ky == "Học kỳ 1" else "HK2"
        
        # Lấy điểm từ Firebase
        docs = db.collection('scores').where('id', '==', u['id']).where('sem', '==', sem).stream()
        data = [d.to_dict() for d in docs]
        
        if data:
            df = pd.DataFrame(data)
            # Sắp xếp và đổi tên cột
            cols = {'sub': 'Môn', 'tx': 'ĐĐG TX', 'gk': 'Giữa Kỳ', 'ck': 'Cuối Kỳ', 'tb': 'TBM'}
            if sem == 'HK2': cols['cn'] = 'Cả Năm'
            
            df = df.rename(columns=cols)
            show_cols = ['Môn', 'ĐĐG TX', 'Giữa Kỳ', 'Cuối Kỳ', 'TBM']
            if sem == 'HK2': show_cols.append('Cả Năm')
            
            st.table(df[show_cols])
        else:
            st.info("Chưa có điểm.")
            
        # Lấy tổng kết
        tk_doc = db.collection('summary').document(f"{u['id']}_{sem}_summary").get()
        tk = tk_doc.to_dict() if tk_doc.exists else None
        
        tk_cn_doc = db.collection('summary').document(f"{u['id']}_CN_summary").get()
        tk_cn = tk_cn_doc.to_dict() if tk_cn_doc.exists else None
        
        def card(l, v): return f'<div class="summary-item"><small>{l}</small><div class="summary-val">{v}</div></div>'
        
        if tk:
            st.markdown(f"##### 🏆 TỔNG KẾT {ky.upper()}")
            html = '<div class="summary-grid">'
            html += card("Học tập", tk['ht']) + card("Rèn luyện", tk['rl']) + card("Vắng", tk['v']) + card("Danh hiệu", tk['dh'])
            html += '</div>'
            st.markdown(html, unsafe_allow_html=True)
            
        if sem == 'HK2' and tk_cn:
            st.markdown("---")
            st.markdown(f"##### 🚩 CẢ NĂM")
            html = '<div class="summary-grid">'
            html += card("Học tập", tk_cn['ht']) + card("Rèn luyện", tk_cn['rl']) + card("Danh hiệu", tk_cn['dh'])
            html += f'<div class="summary-item" style="border-color:red"><small>KẾT QUẢ</small><div class="summary-val" style="color:red">{tk_cn["kq"]}</div></div>'
            html += '</div>'
            st.markdown(html, unsafe_allow_html=True)

# --- 6. MAIN ---
if __name__ == "__main__":
    if 'page' not in st.session_state: st.session_state.page = 'login'
    
    # Kết nối DB
    try:
        db = init_firebase()
        if st.session_state.page == 'admin': view_admin(db)
        else: view_student(db)
    except Exception as e:
        st.error("⚠️ Chưa cấu hình Secrets! Vui lòng làm bước 4.")
        st.expander("Chi tiết lỗi").write(e)