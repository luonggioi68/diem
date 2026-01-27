import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

# --- 1. CẤU HÌNH & KẾT NỐI ---
st.set_page_config(page_title="Hệ Thống Tra Cứu Điểm", page_icon="🔥", layout="wide")

def init_firebase():
    if not firebase_admin._apps:
        try:
            key_dict = dict(st.secrets["firebase"])
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(key_dict)
            firebase_admin.initialize_app(cred)
        except Exception as e:
            st.error(f"Lỗi kết nối: {e}")
            st.stop()
    return firestore.client()

# --- 2. HÀM XỬ LÝ FILE ĐA NĂNG (ROBUST) ---
def safe_str(val):
    if pd.isna(val) or str(val).lower() in ['nan', 'none', '']: return ""
    s = str(val).strip()
    if s.endswith('.0'): s = s[:-2]
    return s

def load_excel_robust(file):
    """Hàm đọc file bất chấp định dạng (XLS, XLSX, HTML, CSV)"""
    try:
        # Cách 1: Đọc chuẩn Excel (XLS/XLSX)
        return pd.read_excel(file, sheet_name=None)
    except:
        try:
            # Cách 2: Đọc dạng HTML (Thường gặp ở file xuất từ VnEdu/SMAS)
            file.seek(0)
            dfs = pd.read_html(file)
            # Chuyển list df thành dict để giống cấu trúc sheet
            return {f"Sheet {i+1}": df for i, df in enumerate(dfs)}
        except:
            try:
                # Cách 3: Đọc dạng CSV/Text
                file.seek(0)
                df = pd.read_csv(file)
                return {"Sheet 1": df}
            except Exception as e:
                st.error(f"Không thể đọc file {file.name}. Lỗi: {e}")
                return None

def upload_to_firebase(db, file, sem, cls, type_file):
    count = 0
    try:
        # Dùng hàm đọc thông minh
        xls_data = load_excel_robust(file)
        if not xls_data: return 0

        batch = db.batch()
        batch_count = 0
        
        # Xử lý từng Sheet (hoặc từng bảng)
        for sheet_name, df in xls_data.items():
            if any(x in str(sheet_name).lower() for x in ["hướng dẫn", "bìa"]): continue
            
            # Chuẩn hóa tên cột (xóa khoảng trắng thừa)
            df.columns = df.columns.astype(str).str.strip()
            
            # Tìm dòng header chứa 'Mã học sinh'
            h_idx = -1
            for i, row in df.iterrows():
                # Chuyển row thành chuỗi để tìm kiếm
                if row.astype(str).str.contains("Mã học sinh", case=False).any():
                    h_idx = i; break
            
            if h_idx != -1:
                # Reset header
                df.columns = df.iloc[h_idx].astype(str).str.strip()
                df = df.iloc[h_idx+1:]
                
                # Tìm cột quan trọng
                cols = df.columns.tolist()
                idx_ma = next((i for i, c in enumerate(cols) if "Mã học sinh" in c), -1)
                
                if idx_ma != -1:
                    for _, row in df.iterrows():
                        ma_hs = safe_str(row.iloc[idx_ma])
                        if len(ma_hs) > 3:
                            # --- 1. UPLOAD ĐIỂM ---
                            if type_file == 'score':
                                # Cập nhật thông tin HS (Dùng merge để không mất active)
                                try:
                                    ten_hs = safe_str(row.iloc[idx_ma-2]) # Tên thường trước Mã 2 cột
                                    ref_st = db.collection('students').document(ma_hs)
                                    doc_snap = ref_st.get()
                                    
                                    st_data = {'id': ma_hs, 'name': ten_hs, 'cls': cls}
                                    if not doc_snap.exists: st_data['active'] = 0 # Mới thì chưa kích hoạt
                                    
                                    batch.set(ref_st, st_data, merge=True)
                                except: pass

                                # Lưu điểm
                                def g(off): 
                                    try: return safe_str(row.iloc[idx_ma+off])
                                    except: return ""
                                
                                tx = "  ".join([g(k) for k in range(1,10) if g(k)])
                                # Tạo ID ngắn gọn hơn
                                safe_sub = str(sheet_name).replace("/", "-").strip()
                                doc_id = f"{ma_hs}_{sem}_{safe_sub}"
                                
                                ref_sc = db.collection('scores').document(doc_id)
                                batch.set(ref_sc, {
                                    'id': ma_hs, 'sub': safe_sub, 'sem': sem, 'cls': cls,
                                    'tx': tx, 'gk': g(16), 'ck': g(26), 'tb': g(27), 
                                    'cn': (g(28) if sem=='HK2' else "")
                                })

                            # --- 2. UPLOAD TỔNG KẾT ---
                            elif type_file == 'summary':
                                doc_id = f"{ma_hs}_{sem}_summary"
                                ref_sum = db.collection('summary').document(doc_id)
                                batch.set(ref_sum, {
                                    'id': ma_hs, 'sem': sem, 'cls': cls,
                                    'ht': safe_str(row.get('Học tập')), 
                                    'rl': safe_str(row.get('Rèn luyện')),
                                    'v': safe_str(row.get('Vắng')), 
                                    'dh': safe_str(row.get('Danh hiệu')),
                                    'kq': safe_str(row.get('Kết quả'))
                                })
                            
                            count += 1
                            batch_count += 1
                            if batch_count >= 300: # Firebase giới hạn 500
                                batch.commit(); batch = db.batch(); batch_count = 0
        
        batch.commit() # Commit phần dư
            
    except Exception as e:
        st.error(f"Lỗi xử lý: {e}")
        print(e)
    return count

# --- 3. GIAO DIỆN ADMIN ---
def view_admin(db):
    st.title("🛠️ QUẢN TRỊ (FIREBASE)")
    if st.button("Đăng xuất"): st.session_state.page = 'login'; st.rerun()
    
    if st.text_input("Mật khẩu:", type="password") == "admin123":
        t1, t2 = st.tabs(["UPLOAD DỮ LIỆU", "KÍCH HOẠT"])
        
        with t1:
            cls = st.selectbox("Chọn Lớp:", [f"Lớp {i}" for i in range(6, 13)])
            c1, c2 = st.columns(2)
            f1 = c1.file_uploader(f"Điểm HK1 {cls}", key="f1")
            f2 = c1.file_uploader(f"Điểm HK2 {cls}", key="f2")
            tk1 = c2.file_uploader(f"TK HK1", key="t1")
            tk2 = c2.file_uploader(f"TK HK2", key="t2")
            tk3 = c2.file_uploader(f"TK CN", key="t3")
            
            if st.button("LƯU DỮ LIỆU", type="primary"):
                with st.spinner("Đang xử lý..."):
                    cnt = 0
                    if f1: cnt += upload_to_firebase(db, f1, "HK1", cls, 'score')
                    if f2: cnt += upload_to_firebase(db, f2, "HK2", cls, 'score')
                    if tk1: cnt += upload_to_firebase(db, tk1, "HK1", cls, 'summary')
                    if tk2: cnt += upload_to_firebase(db, tk2, "HK2", cls, 'summary')
                    if tk3: cnt += upload_to_firebase(db, tk3, "CN", cls, 'summary')
                    st.success(f"Xong! {cnt} bản ghi.")

        with t2:
            st.info("Tick chọn 'Active' để mở quyền xem điểm.")
            flt = st.selectbox("Lọc Lớp:", ["Tất cả"] + [f"Lớp {i}" for i in range(6, 13)])
            
            ref = db.collection('students')
            docs = ref.where('cls', '==', flt).stream() if flt != "Tất cả" else ref.stream()
            
            users = [{"id": d.id, **d.to_dict()} for d in docs]
            if users:
                df = pd.DataFrame(users)
                # Đảm bảo có cột active
                if 'active' not in df.columns: df['active'] = 0
                df['active'] = df['active'].apply(lambda x: True if x==1 else False)
                
                edited = st.data_editor(df[['active', 'id', 'name', 'cls']], 
                                      column_config={"active": st.column_config.CheckboxColumn("Active", default=False)},
                                      disabled=['id', 'name', 'cls'], hide_index=True, height=500)
                
                if st.button("LƯU TRẠNG THÁI"):
                    batch = db.batch(); b_cnt = 0
                    for _, r in edited.iterrows():
                        batch.update(db.collection('students').document(r['id']), {'active': 1 if r['active'] else 0})
                        b_cnt += 1
                        if b_cnt >= 300: batch.commit(); batch = db.batch(); b_cnt = 0
                    batch.commit()
                    st.success("Đã lưu!")
            else:
                st.warning("Chưa có dữ liệu.")

# --- 4. GIAO DIỆN HỌC SINH ---
def view_student(db):
    c1, c2 = st.columns([8,1])
    c1.markdown("### 🔥 TRA CỨU ĐIỂM")
    if c2.button("⚙️"): st.session_state.page = 'admin'; st.rerun()

    if 'user' not in st.session_state:
        mid = st.text_input("Mã Học Sinh:").strip()
        if st.button("Xem", type="primary"):
            doc = db.collection('students').document(mid).get()
            if not doc.exists: st.error("Sai mã")
            elif doc.to_dict().get('active') != 1: st.warning("Chưa kích hoạt")
            else: st.session_state.user = doc.to_dict(); st.rerun()
    else:
        u = st.session_state.user
        if st.button("⬅️ Quay lại"): del st.session_state.user; st.rerun()
        
        st.markdown(f"**Học sinh:** {u.get('name')} | **Lớp:** {u.get('cls')}")
        ky = st.radio("Kỳ:", ["HK1", "HK2 & Cả năm"], horizontal=True)
        sem = "HK1" if ky == "HK1" else "HK2"
        
        # Lấy điểm
        docs = db.collection('scores').where('id', '==', u['id']).where('sem', '==', sem).stream()
        data = [d.to_dict() for d in docs]
        
        if data:
            df = pd.DataFrame(data)
            renames = {'sub': 'Môn', 'tx': 'ĐĐG TX', 'gk': 'GK', 'ck': 'CK', 'tb': 'TBM', 'cn': 'CN'}
            cols = ['Môn', 'ĐĐG TX', 'GK', 'CK', 'TBM']
            if sem == 'HK2': cols.append('CN')
            st.table(df.rename(columns=renames)[cols])
        else: st.info("Chưa có điểm.")
        
        # Lấy TK
        tk = db.collection('summary').document(f"{u['id']}_{sem}_summary").get()
        if tk.exists:
            d = tk.to_dict()
            st.info(f"🏆 **TỔNG KẾT {sem}:** HL: {d.get('ht')} | HK: {d.get('rl')} | Danh hiệu: {d.get('dh')}")
            
        if sem == 'HK2':
            tkcn = db.collection('summary').document(f"{u['id']}_CN_summary").get()
            if tkcn.exists:
                d = tkcn.to_dict()
                st.warning(f"🚩 **CẢ NĂM:** HL: {d.get('ht')} | HK: {d.get('rl')} | KẾT QUẢ: {d.get('kq')}")

# --- MAIN ---
if __name__ == "__main__":
    if 'page' not in st.session_state: st.session_state.page = 'login'
    try:
        db = init_firebase()
        if st.session_state.page == 'admin': view_admin(db)
        else: view_student(db)
    except Exception as e:
        st.error("Chưa cấu hình Secrets hoặc lỗi mạng.")
        print(e)
