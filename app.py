import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

# --- 1. CẤU HÌNH & DANH SÁCH NĂM ---
st.set_page_config(page_title="Hồ Sơ Học Tập Số", page_icon="🎓", layout="wide")

YEAR_LIST = [f"{y}-{y+1}" for y in range(2023, 2030)]

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

# --- 2. CSS GIAO DIỆN (MOBILE FIRST) ---
st.markdown("""
<style>
    /* Ẩn râu ria */
    #MainMenu, header, footer, .stAppDeployButton {display: none !important;}
    [data-testid="stSidebar"] {display: none;}
    .block-container {padding: 0.5rem 0.5rem 2rem 0.5rem !important;}
    
    /* Header */
    .main-header {
        background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
        padding: 15px; border-radius: 12px; color: white; 
        text-align: center; font-weight: 700; font-size: 20px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.2); margin-bottom: 15px;
        text-transform: uppercase; letter-spacing: 1px;
    }
    
    /* Report Card */
    .report-card {
        background: white; padding: 15px; border: 1px solid #ddd;
        border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); 
        margin-bottom: 15px; color: #333; position: relative;
    }
    .year-tag {
        position: absolute; top: 10px; right: 10px;
        background: #e3f2fd; color: #1565c0; padding: 4px 8px;
        border-radius: 6px; font-size: 12px; font-weight: bold;
    }
    
    /* Grid Tổng kết */
    .summary-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-top: 15px; }
    .summary-item { background: #f8f9fa; padding: 10px; border-radius: 8px; border-left: 4px solid #2c5364; text-align: center; }
    .summary-val { font-size: 15px; font-weight: bold; color: #333; margin-top: 2px; display:block;}
    
    /* Table & Button */
    .stTable { font-size: 13px; }
    div[data-testid="stTable"] td { padding: 8px 2px !important; }
    .stButton>button { width: 100%; border-radius: 10px; height: 48px; font-weight: bold; }
    
    /* Admin Zone */
    .admin-zone { border: 1px dashed #ccc; padding: 15px; border-radius: 10px; background: #fdfdfd; margin-top: 20px;}
    .config-box { background: #e8f5e9; padding: 10px; border-radius: 8px; border: 1px solid #c8e6c9; margin-bottom: 15px; text-align: center;}
</style>
""", unsafe_allow_html=True)

# --- 3. HÀM XỬ LÝ DATABASE ---
def safe_str(val):
    if pd.isna(val) or str(val).lower() in ['nan', 'none', '']: return ""
    s = str(val).strip()
    if s.endswith('.0'): s = s[:-2]
    return s

def load_excel_robust(file):
    try: return pd.read_excel(file, sheet_name=None)
    except:
        try: file.seek(0); dfs = pd.read_html(file); return {f"Sheet {i+1}": df for i, df in enumerate(dfs)}
        except: return None

# --- CONFIG YEAR ---
def get_current_year_config(db):
    try:
        doc = db.collection('system_config').document('settings').get()
        if doc.exists: return doc.to_dict().get('default_year', '2024-2025')
    except: pass
    return '2024-2025'

def set_current_year_config(db, year):
    db.collection('system_config').document('settings').set({'default_year': year}, merge=True)

def delete_data_year(db, collection, year, cls, sem=None):
    cnt = 0
    try:
        ref = db.collection(collection)
        query = ref.where('year', '==', year)
        if cls != "Tất cả": query = query.where('cls', '==', cls)
        if sem: query = query.where('sem', '==', sem)
        
        batch = db.batch(); b_cnt = 0
        for doc in query.stream():
            batch.delete(doc.reference)
            b_cnt += 1; cnt += 1
            if b_cnt >= 400: batch.commit(); batch = db.batch(); b_cnt = 0
        if b_cnt > 0: batch.commit()
    except Exception as e: st.error(f"Lỗi xóa: {e}")
    return cnt

def upload_firebase(db, file, year, sem, cls, type_file):
    count = 0
    try:
        batch = db.batch(); b_cnt = 0
        
        if type_file == 'score':
            data = load_excel_robust(file)
            if not data: return 0
            for sname, df in data.items():
                if any(x in str(sname).lower() for x in ["hướng dẫn", "bìa"]): continue
                h_idx = -1
                for i, row in df.iterrows():
                    if row.astype(str).str.contains("Mã học sinh", case=False).any(): h_idx = i; break
                if h_idx != -1:
                    df.columns = df.iloc[h_idx]; df = df.iloc[h_idx+1:]
                    cols = df.columns.tolist()
                    idx_ma = next((i for i,c in enumerate(cols) if "Mã học sinh" in str(c)), -1)
                    if idx_ma != -1:
                        for _, row in df.iterrows():
                            ma = safe_str(row.iloc[idx_ma])
                            if len(ma) > 3:
                                try:
                                    ten = safe_str(row.iloc[idx_ma-2])
                                    doc_st_id = f"{ma}_{year}"
                                    ref_st = db.collection('students').document(doc_st_id)
                                    snap = ref_st.get()
                                    st_data = {'id': ma, 'name': ten, 'cls': cls, 'year': year}
                                    if not snap.exists: st_data['active'] = 0
                                    batch.set(ref_st, st_data, merge=True)
                                except: pass

                                def g(o): 
                                    try: return safe_str(row.iloc[idx_ma+o])
                                    except: return ""
                                sub = str(sname).strip().replace("/", "-")
                                doc_id = f"{ma}_{year}_{sem}_{sub}"
                                batch.set(db.collection('scores').document(doc_id), {
                                    'id': ma, 'year': year, 'sem': sem, 'cls': cls, 'sub': sub,
                                    'tx': "  ".join([g(k) for k in range(1,10) if g(k)]),
                                    'gk': g(16), 'ck': g(26), 'tb': g(27), 
                                    'cn': (g(28) if sem=='HK2' else "")
                                })
                                count += 1; b_cnt += 1
                                if b_cnt >= 300: batch.commit(); batch = db.batch(); b_cnt = 0
            batch.commit()
        elif type_file == 'summary':
            try: df = pd.read_excel(file)
            except: df = pd.read_csv(file)
            if 'Mã học sinh' not in df.columns:
                for i, r in df.iterrows():
                    if r.astype(str).str.contains("Mã học sinh").any(): df.columns = df.iloc[i]; df = df.iloc[i+1:]; break
            df.columns = df.columns.str.strip()
            has_loai = 'Loại TK' in df.columns
            for _, row in df.iterrows():
                ma = safe_str(row.get('Mã học sinh'))
                if len(ma) > 3:
                    cur_sem = sem
                    if has_loai:
                        v = safe_str(row.get('Loại TK')).upper()
                        if '1' in v: cur_sem = 'HK1'
                        elif '2' in v: cur_sem = 'HK2'
                        elif 'CN' in v or 'NAM' in v: cur_sem = 'CN'
                    doc_id = f"{ma}_{year}_{cur_sem}_sum"
                    batch.set(db.collection('summary').document(doc_id), {
                        'id': ma, 'year': year, 'sem': cur_sem, 'cls': cls,
                        'ht': safe_str(row.get('Học tập')), 'rl': safe_str(row.get('Rèn luyện')),
                        'v': safe_str(row.get('Vắng')), 'dh': safe_str(row.get('Danh hiệu')),
                        'kq': safe_str(row.get('Kết quả'))
                    })
                    count += 1; b_cnt += 1
                    if b_cnt >= 300: batch.commit(); batch = db.batch(); b_cnt = 0
            batch.commit()
    except Exception as e: st.error(f"Lỗi: {e}")
    return count

# --- 4. ADMIN UI ---
def view_admin(db):
    st.markdown('<div class="main-header">🛠️ QUẢN TRỊ VIÊN</div>', unsafe_allow_html=True)
    if st.button("Đăng xuất"): st.session_state.page = 'login'; st.rerun()
    
    if st.text_input("Mật khẩu:", type="password") == "admin123":
        current_db_year = get_current_year_config(db)
        
        st.markdown(f"""<div class="config-box"><b>Năm học đang kích hoạt: {current_db_year}</b></div>""", unsafe_allow_html=True)
        col_y1, col_y2 = st.columns([2, 1])
        year_sel = col_y1.selectbox("📅 Năm làm việc:", YEAR_LIST, index=YEAR_LIST.index(current_db_year) if current_db_year in YEAR_LIST else 0)
        if col_y2.button("📌 Đặt làm Mặc định"):
            set_current_year_config(db, year_sel)
            st.success(f"Đã đặt {year_sel} làm mặc định!"); st.rerun()

        st.markdown("---")
        t1, t2, t3 = st.tabs(["UPLOADER", "KÍCH HOẠT", "XÓA DỮ LIỆU"])
        
        with t1:
            st.caption(f"Upload vào năm: **{year_sel}**")
            cls = st.selectbox("Lớp:", [f"Lớp {i}" for i in range(6, 13)])
            c1, c2 = st.columns(2)
            f1 = c1.file_uploader(f"Điểm HK1 {cls}", key="f1")
            f2 = c1.file_uploader(f"Điểm HK2 {cls}", key="f2")
            tk = st.file_uploader(f"Tổng Kết {cls}", key="tk")
            
            if st.button("LƯU DỮ LIỆU", type="primary"):
                with st.spinner(f"Đang xử lý {year_sel}..."):
                    c = 0
                    if f1: c += upload_firebase(db, f1, year_sel, "HK1", cls, 'score')
                    if f2: c += upload_firebase(db, f2, year_sel, "HK2", cls, 'score')
                    if tk: c += upload_firebase(db, tk, year_sel, "HK1", cls, 'summary')
                    st.success(f"Đã lưu {c} bản ghi.")

        with t2:
            flt = st.selectbox("Lọc Lớp:", ["Tất cả"] + [f"Lớp {i}" for i in range(6, 13)])
            ref = db.collection('students').where('year', '==', year_sel)
            if flt != "Tất cả": ref = ref.where('cls', '==', flt)
            
            docs = list(ref.stream())
            data = [{"id_doc": d.id, **d.to_dict()} for d in docs]
            
            if data:
                df = pd.DataFrame(data)
                if 'active' not in df.columns: df['active'] = 0
                df['active'] = df['active'].apply(lambda x: bool(x))
                
                # --- THÊM SỐ THỨ TỰ (STT) VÀO ADMIN ---
                # Sắp xếp theo lớp và tên để STT đẹp hơn
                df = df.sort_values(by=['cls', 'name'])
                df.insert(0, 'STT', range(1, len(df) + 1))
                
                edited = st.data_editor(df[['active', 'STT', 'id', 'name', 'cls']], 
                                      column_config={
                                          "active": st.column_config.CheckboxColumn("Kích hoạt", default=False),
                                          "STT": st.column_config.NumberColumn("STT", width="small", disabled=True),
                                          "id": st.column_config.TextColumn("Mã HS", disabled=True),
                                          "name": st.column_config.TextColumn("Họ tên", disabled=True),
                                          "cls": st.column_config.TextColumn("Lớp", disabled=True)
                                      },
                                      hide_index=True, use_container_width=True)
                
                if st.button("LƯU TRẠNG THÁI"):
                    batch = db.batch(); b_cnt = 0
                    for i, r in edited.iterrows():
                        doc_key = f"{r['id']}_{year_sel}"
                        batch.update(db.collection('students').document(doc_key), {'active': 1 if r['active'] else 0})
                        b_cnt += 1
                        if b_cnt >= 300: batch.commit(); batch = db.batch(); b_cnt = 0
                    batch.commit()
                    st.success("Đã lưu!")
            else: st.warning(f"Chưa có dữ liệu năm {year_sel}.")

        with t3:
            st.warning(f"Đang xóa dữ liệu năm: {year_sel}")
            del_cls = st.selectbox("Lớp xóa:", ["Tất cả"] + [f"Lớp {i}" for i in range(6, 13)], key="del")
            c1, c2 = st.columns(2)
            with c1:
                d_hk1 = st.checkbox("Xóa Điểm HK1")
                d_hk2 = st.checkbox("Xóa Điểm HK2")
            with c2:
                d_thk1 = st.checkbox("Xóa TK HK1")
                d_thk2 = st.checkbox("Xóa TK HK2/CN")
            d_all = st.checkbox("Xóa Tài khoản HS (Reset năm)")
            
            if st.button("🚨 THỰC HIỆN XÓA", type="primary"):
                with st.spinner("Deleting..."):
                    if d_hk1: delete_data_year(db, 'scores', year_sel, del_cls, 'HK1')
                    if d_hk2: delete_data_year(db, 'scores', year_sel, del_cls, 'HK2')
                    if d_thk1: delete_data_year(db, 'summary', year_sel, del_cls, 'HK1')
                    if d_thk2: 
                        delete_data_year(db, 'summary', year_sel, del_cls, 'HK2')
                        delete_data_year(db, 'summary', year_sel, del_cls, 'CN')
                    if d_all: delete_data_year(db, 'students', year_sel, del_cls)
                    st.success("Đã xóa xong!")

# --- 5. HỌC SINH UI ---
def view_student(db):
   
    st.markdown('<div class="main-header">TRA CỨU ĐIỂM - HỒ SƠ HỌC TẬP SỐ <br> Trường PT DTNT THCS&THPT Tuy Đức</div>', unsafe_allow_html=True)
    default_year = get_current_year_config(db)

    if 'user' not in st.session_state:
        try: idx = YEAR_LIST.index(default_year)
        except: idx = 0
        year_login = st.selectbox("Năm học:", YEAR_LIST, index=idx)
        mid = st.text_input("Mã Học Sinh:", placeholder="VD: 2411...").strip()
        
        if st.button("TRA CỨU", type="primary", use_container_width=True):
            doc_key = f"{mid}_{year_login}"
            doc = db.collection('students').document(doc_key).get()
            if not doc.exists: st.error(f"Không tìm thấy dữ liệu năm {year_login}!Liên hệ admin zalo: 0383477162 để đăng kí tài khoản, Cân nhắc phí thu 15k/năm học")
            elif doc.to_dict().get('active') != 1: st.warning(f"Chưa kích hoạt năm {year_login}.Liên hệ admin zalo: 0383477162 để kích hoạt tài khoản, Cân nhắc phí thu 15k/năm học")
            else:
                st.session_state.user = doc.to_dict()
                st.session_state.year_view = year_login
                st.rerun()
    else:
        u = st.session_state.user
        year_view = st.session_state.year_view
        
        st.markdown(f"""
        <div class="report-card">
            <span class="year-tag">{year_view}</span>
            <div style="text-align:center; font-weight:bold; color:#2c5364; font-size:16px;">
                {u.get('name')}
            </div>
            <div style="text-align:center; font-size:14px;">
                Mã: {u.get('id')} | Lớp: {u.get('cls')}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        ky = st.radio("", ["Học kỳ 1", "Học kỳ 2 & Cả năm"], horizontal=True)
        sem = "HK1" if "1" in ky else "HK2"
        
        docs = db.collection('scores').where('id', '==', u['id']).where('year', '==', year_view).where('sem', '==', sem).stream()
        data = [d.to_dict() for d in docs]
        
        if data:
            df = pd.DataFrame(data)
            
            # --- LOGIC SẮP XẾP MÔN HỌC ---
            def sort_priority(row):
                s = str(row['sub']).lower()
                
                # 1. Môn ưu tiên hàng đầu
                if 'toán' in s: return 0
                if 'văn' in s or 'ngữ văn' in s: return 1
                if 'anh' in s or 'ngoại ngữ' in s: return 2
                
                # 2. Phát hiện môn Đánh giá (Đ/CĐ)
                # Dựa vào tên môn học thường gặp
                eval_subs = ['thể chất', 'gdtc', 'quốc phòng', 'gdqp', 'trải nghiệm', 'hđtn', 'địa phương', 'nghệ thuật', 'âm nhạc', 'mỹ thuật']
                if any(x in s for x in eval_subs): return 20 # Đẩy xuống cuối
                
                # 3. Các môn còn lại (Lý, Hóa, Sinh, Sử, Địa...)
                return 10 
            
            df['priority'] = df.apply(sort_priority, axis=1)
            # Sắp xếp theo Priority tăng dần -> sau đó theo Tên môn
            df = df.sort_values(by=['priority', 'sub'])
            
            # Đánh STT
            df['STT'] = range(1, len(df)+1)
            
            rn = {'sub': 'Môn', 'tx': 'TX', 'gk': 'GK', 'ck': 'CK', 'tb': 'TB', 'cn': 'CN'}
            cols = ['STT', 'Môn', 'TX', 'GK', 'CK', 'TB']
            if sem == 'HK2': cols.append('CN')
            st.table(df.rename(columns=rn)[cols].set_index('STT'))
        else: st.info("Chưa có điểm.")
        
        doc_tk = f"{u['id']}_{year_view}_{sem}_sum"
        tk = db.collection('summary').document(doc_tk).get()
        tk_d = tk.to_dict() if tk.exists else {}
        
        def card(l, v): return f'<div class="summary-item"><small>{l}</small><div class="summary-val">{v if v else "-"}</div></div>'
        st.markdown(f"**TỔNG KẾT {sem}**")
        if tk_d: st.markdown(f"""<div class="summary-grid">{card('Học lực', tk_d.get('ht'))}{card('Hạnh kiểm', tk_d.get('rl'))}{card('Vắng', tk_d.get('v'))}{card('Danh hiệu', tk_d.get('dh'))}</div>""", unsafe_allow_html=True)
        
        if sem == 'HK2':
            doc_cn = f"{u['id']}_{year_view}_CN_sum"
            cn = db.collection('summary').document(doc_cn).get()
            cn_d = cn.to_dict() if cn.exists else {}
            if cn_d:
                st.markdown("---")
                st.markdown("**CẢ NĂM**")
                st.markdown(f"""<div class="summary-grid">{card('Học lực', cn_d.get('ht'))}{card('Hạnh kiểm', cn_d.get('rl'))}{card('Danh hiệu', cn_d.get('dh'))}<div class="summary-item" style="border-color:red; background:#fff5f5"><small style="color:red">KẾT QUẢ</small><div class="summary-val" style="color:red">{cn_d.get('kq')}</div></div></div>""", unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        if c1.button("🔙 Đổi Năm"): del st.session_state.user; st.rerun()
        if c2.button("Thoát"): del st.session_state.user; st.rerun()

    st.markdown('<div class="admin-zone" style="text-align:center; border:none; margin-top:50px;">', unsafe_allow_html=True)
    if st.button("⚙️", key="adm_btn"): st.session_state.page = 'admin'; st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    if 'page' not in st.session_state: st.session_state.page = 'login'
    try:
        db = init_firebase()
        if st.session_state.page == 'admin': view_admin(db)
        else: view_student(db)
    except Exception as e: st.error("Lỗi hệ thống."); print(e)


