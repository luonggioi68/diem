import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

# --- 1. CẤU HÌNH & KẾT NỐI FIREBASE ---
st.set_page_config(page_title="Hệ Thống Tra Cứu Điểm", page_icon="🔥", layout="wide")

def init_firebase():
    if not firebase_admin._apps:
        try:
            key_dict = dict(st.secrets["firebase"])
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(key_dict)
            firebase_admin.initialize_app(cred)
        except Exception as e:
            st.error(f"Lỗi kết nối Firebase: {e}")
            st.stop()
    return firestore.client()

# --- 2. CSS GIAO DIỆN (CLEAN MOBILE VERSION) ---
st.markdown("""
<style>
    /* 1. ẨN CÁC THÀNH PHẦN MẶC ĐỊNH CỦA STREAMLIT */
    #MainMenu {visibility: hidden; display: none;} /* Ẩn 3 chấm */
    header {visibility: hidden; display: none;} /* Ẩn thanh trên cùng */
    footer {visibility: hidden; display: none;} /* Ẩn dòng Made with Streamlit */
    .stAppDeployButton {display: none;} /* Ẩn nút Deploy/Manage lơ lửng */
    [data-testid="stToolbar"] {visibility: hidden; display: none;} /* Ẩn thanh công cụ */
    [data-testid="stSidebar"] {display: none;} /* Ẩn sidebar */
    
    /* 2. CĂN CHỈNH LỀ CHO ĐIỆN THOẠI (SÁT VIỀN) */
    .block-container {
        padding-top: 0.5rem !important; /* Sát mép trên */
        padding-bottom: 1rem !important; /* Sát mép dưới */
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }
    
    /* 3. HEADER CỦA APP */
    .main-header {
        background: linear-gradient(to right, #007bff, #0056b3);
        padding: 15px; 
        border-radius: 10px; 
        color: white; 
        text-align: center !important;
        font-weight: 700;
        font-size: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); 
        margin-bottom: 15px;
        text-transform: uppercase;
    }
    
    /* 4. KHUNG KẾT QUẢ */
    .report-card {
        background: white; padding: 15px; 
        border: 1px solid #ddd;
        border-radius: 10px; 
        box-shadow: 0 2px 8px rgba(0,0,0,0.05); 
        margin-bottom: 15px;
    }
    .school-name { 
        color: #cc0000; font-weight: 900; font-size: 15px; 
        text-transform: uppercase; text-align: center; margin-bottom: 5px;
    }
    
    /* 5. GRID TỔNG KẾT (2 CỘT) */
    .summary-grid { 
        display: grid; grid-template-columns: repeat(2, 1fr); 
        gap: 8px; margin-top: 15px; 
    }
    .summary-item { 
        background: #f1f3f5; padding: 10px; border-radius: 8px; 
        border-left: 3px solid #007bff; text-align: center; 
    }
    .summary-val { font-size: 15px; font-weight: bold; color: #333; margin-top: 2px; display:block;}
    
    /* 6. NÚT BẤM (TO, DỄ BẤM TRÊN MOBILE) */
    .stButton>button {
        width: 100% !important;
        border-radius: 10px;
        height: 48px; /* Chiều cao chuẩn ngón tay */
        font-weight: bold;
        font-size: 16px;
        border: none;
        box-shadow: 0 2px 4px rgba(0,0,0,0.15);
    }
    
    /* 7. NÚT ADMIN Ở CUỐI (TÁCH BIỆT) */
    .admin-btn-zone {
        margin-top: 40px;
        padding-top: 20px;
        border-top: 1px dashed #ccc;
        text-align: center;
        margin-bottom: 0px; /* Bỏ khoảng trắng dưới cùng */
    }
    
    /* Tinh chỉnh bảng điểm cho mobile */
    .stTable { font-size: 13px; }
    div[data-testid="stTable"] td { padding: 8px 4px !important; } /* Thu nhỏ padding ô */
</style>
""", unsafe_allow_html=True)

# --- 3. HÀM XỬ LÝ DỮ LIỆU ---
def safe_str(val):
    if pd.isna(val) or str(val).lower() in ['nan', 'none', '']: return ""
    s = str(val).strip()
    if s.endswith('.0'): s = s[:-2]
    return s

def load_excel_robust(file):
    try: return pd.read_excel(file, sheet_name=None)
    except:
        try:
            file.seek(0); dfs = pd.read_html(file)
            return {f"Sheet {i+1}": df for i, df in enumerate(dfs)}
        except: return None

# --- HÀM XÓA DỮ LIỆU ---
def delete_data_granular(db, collection_name, cls, sem=None):
    deleted_count = 0
    try:
        ref = db.collection(collection_name)
        if cls == "Tất cả": query = ref
        else: query = ref.where('cls', '==', cls)
        if sem: query = query.where('sem', '==', sem)
        
        docs = query.stream()
        batch = db.batch(); batch_count = 0
        for doc in docs:
            batch.delete(doc.reference)
            batch_count += 1; deleted_count += 1
            if batch_count >= 400: batch.commit(); batch = db.batch(); batch_count = 0
        if batch_count > 0: batch.commit()
    except Exception as e: st.error(f"Lỗi: {e}")
    return deleted_count

# --- HÀM UPLOAD ---
def upload_to_firebase(db, file, sem_default, cls, type_file):
    count = 0
    try:
        batch = db.batch(); batch_count = 0
        if type_file == 'score':
            xls_data = load_excel_robust(file)
            if not xls_data: return 0
            for sheet_name, df in xls_data.items():
                if any(x in str(sheet_name).lower() for x in ["hướng dẫn", "bìa"]): continue
                h_idx = -1
                for i, row in df.iterrows():
                    if row.astype(str).str.contains("Mã học sinh", case=False).any(): h_idx = i; break
                if h_idx != -1:
                    df.columns = df.iloc[h_idx]; df = df.iloc[h_idx+1:]
                    cols = df.columns.tolist()
                    idx_ma = next((i for i, c in enumerate(cols) if "Mã học sinh" in str(c)), -1)
                    if idx_ma != -1:
                        for _, row in df.iterrows():
                            ma_hs = safe_str(row.iloc[idx_ma])
                            if len(ma_hs) > 3:
                                try: 
                                    ten_hs = safe_str(row.iloc[idx_ma-2])
                                    ref_st = db.collection('students').document(ma_hs)
                                    doc_snap = ref_st.get()
                                    st_data = {'id': ma_hs, 'name': ten_hs, 'cls': cls}
                                    if not doc_snap.exists: st_data['active'] = 0
                                    batch.set(ref_st, st_data, merge=True)
                                except: pass
                                def g(off): 
                                    try: return safe_str(row.iloc[idx_ma+off])
                                    except: return ""
                                tx = "  ".join([g(k) for k in range(1,10) if g(k)])
                                safe_sub = str(sheet_name).strip().replace("/", "-")
                                doc_id = f"{ma_hs}_{sem_default}_{safe_sub}"
                                ref_sc = db.collection('scores').document(doc_id)
                                batch.set(ref_sc, {
                                    'id': ma_hs, 'sub': safe_sub, 'sem': sem_default, 'cls': cls,
                                    'tx': tx, 'gk': g(16), 'ck': g(26), 'tb': g(27), 
                                    'cn': (g(28) if sem_default=='HK2' else "")
                                })
                                count += 1; batch_count += 1
                                if batch_count >= 300: batch.commit(); batch = db.batch(); batch_count = 0
            batch.commit()
        elif type_file == 'summary':
            try: df = pd.read_excel(file)
            except: df = pd.read_csv(file)
            if 'Mã học sinh' not in df.columns:
                for i, row in df.iterrows():
                    if row.astype(str).str.contains("Mã học sinh").any(): df.columns = df.iloc[i]; df = df.iloc[i+1:]; break
            df.columns = df.columns.str.strip()
            has_loai_tk = 'Loại TK' in df.columns
            for _, row in df.iterrows():
                ma = safe_str(row.get('Mã học sinh'))
                if len(ma) > 3:
                    current_sem = sem_default
                    if has_loai_tk:
                        val_loai = safe_str(row.get('Loại TK')).upper()
                        if 'HK1' in val_loai or '1' in val_loai: current_sem = 'HK1'
                        elif 'HK2' in val_loai or '2' in val_loai: current_sem = 'HK2'
                        elif 'CN' in val_loai or 'CẢ NĂM' in val_loai: current_sem = 'CN'
                    doc_id = f"{ma}_{current_sem}_summary"
                    ref_sum = db.collection('summary').document(doc_id)
                    batch.set(ref_sum, {
                        'id': ma, 'sem': current_sem, 'cls': cls,
                        'ht': safe_str(row.get('Học tập')), 'rl': safe_str(row.get('Rèn luyện')),
                        'v': safe_str(row.get('Vắng')), 'dh': safe_str(row.get('Danh hiệu')),
                        'kq': safe_str(row.get('Kết quả'))
                    })
                    count += 1; batch_count += 1
                    if batch_count >= 300: batch.commit(); batch = db.batch(); batch_count = 0
            batch.commit()
    except Exception as e: st.error(f"Lỗi: {e}")
    return count

# --- 4. GIAO DIỆN ADMIN (GIỮ NGUYÊN) ---
def view_admin(db):
    st.markdown('<div class="main-header">🛠️ QUẢN TRỊ VIÊN</div>', unsafe_allow_html=True)
    if st.button("Đăng xuất"): st.session_state.page = 'login'; st.rerun()
    
    if st.text_input("Mật khẩu:", type="password") == "admin123":
        t1, t2, t3 = st.tabs(["UPLOAD DỮ LIỆU", "KÍCH HOẠT", "QUẢN LÝ XÓA"])
        
        with t1:
            cls = st.selectbox("Chọn Lớp:", [f"Lớp {i}" for i in range(6, 13)])
            c1, c2 = st.columns(2)
            f1 = c1.file_uploader(f"Điểm HK1 {cls}", key="f1")
            f2 = c1.file_uploader(f"Điểm HK2 {cls}", key="f2")
            tk = st.file_uploader(f"File Tổng Kết {cls}", key="tk")
            
            if st.button("LƯU LÊN CLOUD", type="primary", use_container_width=True):
                with st.spinner("Đang đồng bộ..."):
                    cnt = 0
                    if f1: cnt += upload_to_firebase(db, f1, "HK1", cls, 'score')
                    if f2: cnt += upload_to_firebase(db, f2, "HK2", cls, 'score')
                    if tk: cnt += upload_to_firebase(db, tk, "HK1", cls, 'summary') 
                    st.success(f"Xong! {cnt} bản ghi.")

        with t2:
            st.info("Tick 'Active' để mở quyền xem điểm.")
            flt = st.selectbox("Lọc Lớp:", ["Tất cả"] + [f"Lớp {i}" for i in range(6, 13)])
            ref = db.collection('students')
            docs = ref.where('cls', '==', flt).stream() if flt != "Tất cả" else ref.stream()
            data = [{"id": d.id, **d.to_dict()} for d in docs]
            if data:
                df = pd.DataFrame(data)
                if 'active' not in df.columns: df['active'] = 0
                df['active'] = df['active'].apply(lambda x: True if x==1 else False)
                edited = st.data_editor(df[['active', 'id', 'name', 'cls']], 
                                      column_config={"active": st.column_config.CheckboxColumn("Active", default=False)},
                                      disabled=['id', 'name', 'cls'], hide_index=True, use_container_width=True)
                if st.button("LƯU TRẠNG THÁI", use_container_width=True):
                    batch = db.batch(); b_cnt = 0
                    for _, r in edited.iterrows():
                        batch.update(db.collection('students').document(r['id']), {'active': 1 if r['active'] else 0})
                        b_cnt += 1
                        if b_cnt >= 300: batch.commit(); batch = db.batch(); b_cnt = 0
                    batch.commit()
                    st.success("Đã lưu!")
            else: st.warning("Chưa có dữ liệu.")

        with t3:
            st.warning("⚠️ Chú ý: Dữ liệu đã xóa sẽ không thể khôi phục!")
            cls_del = st.selectbox("Chọn Lớp cần xóa:", ["Tất cả"] + [f"Lớp {i}" for i in range(6, 13)], key="del_cls")
            
            c_d1, c_d2 = st.columns(2)
            with c_d1:
                d_sc_hk1 = st.checkbox(f"Xóa Điểm HK1")
                d_sc_hk2 = st.checkbox(f"Xóa Điểm HK2")
            with c_d2:
                d_sum_hk1 = st.checkbox(f"Xóa TK HK1")
                d_sum_hk2 = st.checkbox(f"Xóa TK HK2")
                d_sum_cn = st.checkbox(f"Xóa TK Cả Năm")
            
            d_student = st.checkbox(f"Xóa Danh sách HS ({cls_del})")
            
            if st.button("🚨 THỰC HIỆN XÓA", type="primary", use_container_width=True):
                if not any([d_sc_hk1, d_sc_hk2, d_sum_hk1, d_sum_hk2, d_sum_cn, d_student]):
                    st.error("Chưa chọn mục để xóa!")
                else:
                    with st.spinner("Đang xóa..."):
                        if d_sc_hk1: delete_data_granular(db, 'scores', cls_del, 'HK1')
                        if d_sc_hk2: delete_data_granular(db, 'scores', cls_del, 'HK2')
                        if d_sum_hk1: delete_data_granular(db, 'summary', cls_del, 'HK1')
                        if d_sum_hk2: delete_data_granular(db, 'summary', cls_del, 'HK2')
                        if d_sum_cn: delete_data_granular(db, 'summary', cls_del, 'CN')
                        if d_student: delete_data_granular(db, 'students', cls_del, None)
                        st.success("Đã xóa xong!")

# --- 5. GIAO DIỆN HỌC SINH (MOBILE) ---
def view_student(db):
    # Tiêu đề căn giữa, to rõ
    st.markdown('<div class="main-header">🔥 TRA CỨU ĐIỂM TUY ĐỨC SCHOOL</div>', unsafe_allow_html=True)

    if 'user' not in st.session_state:
        # Form nhập liệu
        mid = st.text_input("Nhập Mã Học Sinh:", placeholder="Ví dụ: 2411...").strip()
        
        # Nút bấm Full Width
        if st.button("TRA CỨU NGAY", type="primary", use_container_width=True):
            doc = db.collection('students').document(mid).get()
            if not doc.exists: st.error("Sai mã học sinh!")
            elif doc.to_dict().get('active') != 1: st.warning("Tài khoản chưa được kích hoạt.")
            else: st.session_state.user = doc.to_dict(); st.rerun()
    else:
        u = st.session_state.user
        
        st.markdown(f"""
        <div class="report-card">
            <div class="school-name">TRƯỜNG THCS & THPT TUY ĐỨC</div>
            <div style="text-align:center; margin-top:10px;">
                <div style="font-size:18px; font-weight:bold; color:#0056b3;">{u.get('name')}</div>
                <div>Mã: {u.get('id')} | Lớp: {u.get('cls')}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        ky = st.radio("Chọn kỳ:", ["HK1", "HK2 & Cả năm"], horizontal=True)
        sem = "HK1" if ky == "HK1" else "HK2"
        
        # Lấy điểm
        docs = db.collection('scores').where('id', '==', u['id']).where('sem', '==', sem).stream()
        data = [d.to_dict() for d in docs]
        
        if data:
            df = pd.DataFrame(data)
            def sort_priority(s):
                s = str(s).lower()
                if 'toán' in s: return 0
                if 'văn' in s or 'ngữ văn' in s: return 1
                if 'anh' in s or 'ngoại ngữ' in s: return 2
                return 3
            df['priority'] = df['sub'].apply(sort_priority)
            df = df.sort_values(by=['priority', 'sub'])
            df['STT'] = range(1, len(df) + 1)
            
            renames = {'sub': 'Môn', 'tx': 'TX', 'gk': 'GK', 'ck': 'CK', 'tb': 'TB', 'cn': 'CN'}
            cols = ['STT', 'Môn', 'TX', 'GK', 'CK', 'TB']
            if sem == 'HK2': cols.append('CN')
            st.table(df.rename(columns=renames)[cols].set_index('STT'))
        else: st.info("Chưa có điểm.")
        
        # Lấy TK
        tk = db.collection('summary').document(f"{u['id']}_{sem}_summary").get()
        tk_d = tk.to_dict() if tk.exists else {}
        tk_cn = db.collection('summary').document(f"{u['id']}_CN_summary").get()
        tk_cn_d = tk_cn.to_dict() if tk_cn.exists else {}
        
        def card(l, v): return f'<div class="summary-item"><small>{l}</small><div class="summary-val">{v if v else "-"}</div></div>'
        
        st.markdown(f"**TỔNG KẾT {ky.upper()}**")
        if tk_d:
            st.markdown(f"""
            <div class="summary-grid">
                {card("Học tập", tk_d.get('ht'))}
                {card("Rèn luyện", tk_d.get('rl'))}
                {card("Vắng", tk_d.get('v'))}
                {card("Danh hiệu", tk_d.get('dh'))}
            </div>
            """, unsafe_allow_html=True)
        
        if sem == 'HK2' and tk_cn_d:
            st.markdown("---")
            st.markdown("**KẾT QUẢ CẢ NĂM**")
            st.markdown(f"""
            <div class="summary-grid">
                {card("Học tập CN", tk_cn_d.get('ht'))}
                {card("Rèn luyện CN", tk_cn_d.get('rl'))}
                {card("Danh hiệu CN", tk_cn_d.get('dh'))}
                <div class="summary-item" style="border-left: 4px solid #dc3545; background: #fff5f5;">
                    <small style="color:#dc3545">KẾT QUẢ</small>
                    <div class="summary-val" style="color:#dc3545">{tk_cn_d.get("kq")}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        if st.button("⬅️ TRA CỨU KHÁC", use_container_width=True): 
            del st.session_state.user; st.rerun()

    # Nút Admin ở cuối trang (Footer)
    st.markdown('<div class="admin-btn-zone">', unsafe_allow_html=True)
    if st.button("⚙️ Admin", type="secondary"): 
        st.session_state.page = 'admin'; st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# --- MAIN ---
if __name__ == "__main__":
    if 'page' not in st.session_state: st.session_state.page = 'login'
    try:
        db = init_firebase()
        if st.session_state.page == 'admin': view_admin(db)
        else: view_student(db)
    except Exception as e:
        st.error("Lỗi hệ thống."); print(e)



