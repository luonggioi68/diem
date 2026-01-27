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

# --- 2. CSS GIAO DIỆN (ĐÃ DỌN DẸP SẠCH SẼ) ---
st.markdown("""
<style>
    /* 1. Ẩn Menu (3 chấm) và Header mặc định */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    [data-testid="stToolbar"] {visibility: hidden;}
    
    /* 2. Ẩn Footer (Made with Streamlit) */
    footer {visibility: hidden;}
    
    /* 3. Ẩn Sidebar (Menu trái) */
    [data-testid="stSidebar"] {display: none;}
    
    /* 4. Đẩy nội dung lên sát mép trên (Bỏ khoảng trắng thừa) */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
    }
    
    /* 5. Trang trí lại Header của mình cho đẹp */
    .main-header {
        background: linear-gradient(135deg, #FF8C00 0%, #FF0080 100%);
        padding: 15px; 
        border-radius: 12px; 
        color: white; 
        text-align: center;
        box-shadow: 0 4px 10px rgba(0,0,0,0.1); 
        margin-bottom: 20px;
    }
    
    /* 6. Khung phiếu điểm */
    .report-card {
        background: white; 
        padding: 20px; 
        border: 2px solid #eee;
        border-radius: 12px; 
        box-shadow: 0 5px 15px rgba(0,0,0,0.05); 
        color: #333;
    }
    .school-name { 
        color: #cc0000; 
        font-weight: 900; 
        font-size: 18px; 
        text-transform: uppercase; 
        text-align: center;
    }
    
    /* 7. Grid Tổng kết */
    .summary-grid { 
        display: grid; 
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); 
        gap: 10px; 
        margin-top: 20px; 
    }
    .summary-item { 
        background: #f8f9fa; 
        padding: 10px; 
        border-radius: 8px; 
        border-left: 4px solid #FF8C00; 
        text-align: center; 
    }
    .summary-val { 
        font-size: 16px; 
        font-weight: bold; 
        color: #333; 
        margin-top: 5px; 
        display:block;
    }
    
    /* 8. Tinh chỉnh bảng */
    .stTable { font-size: 14px; }
    
    /* 9. Nút bấm đẹp hơn */
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 45px;
        font-weight: bold;
    }
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

# --- HÀM XÓA DỮ LIỆU (NÂNG CẤP: LỌC THEO KỲ) ---
def delete_data_granular(db, collection_name, cls, sem=None):
    """
    Xóa dữ liệu chi tiết.
    - collection_name: 'scores' hoặc 'summary' hoặc 'students'
    - cls: Lớp
    - sem: 'HK1', 'HK2', 'CN' (Nếu None thì xóa hết của lớp đó - dùng cho students)
    """
    deleted_count = 0
    try:
        ref = db.collection(collection_name)
        
        # Tạo query cơ bản theo Lớp
        if cls == "Tất cả":
            query = ref
        else:
            query = ref.where('cls', '==', cls)
            
        # Nếu có chỉ định kỳ thì lọc thêm kỳ
        if sem:
            query = query.where('sem', '==', sem)
            
        docs = query.stream()
        
        batch = db.batch()
        batch_count = 0
        
        for doc in docs:
            batch.delete(doc.reference)
            batch_count += 1
            deleted_count += 1
            
            if batch_count >= 400:
                batch.commit()
                batch = db.batch()
                batch_count = 0
        
        if batch_count > 0:
            batch.commit()
            
    except Exception as e:
        st.error(f"Lỗi khi xóa {collection_name}: {e}")
    return deleted_count

# --- HÀM UPLOAD (GIỮ NGUYÊN) ---
def upload_to_firebase(db, file, sem_default, cls, type_file):
    count = 0
    try:
        batch = db.batch()
        batch_count = 0
        
        if type_file == 'score':
            xls_data = load_excel_robust(file)
            if not xls_data: return 0
            
            for sheet_name, df in xls_data.items():
                if any(x in str(sheet_name).lower() for x in ["hướng dẫn", "bìa"]): continue
                h_idx = -1
                for i, row in df.iterrows():
                    if row.astype(str).str.contains("Mã học sinh", case=False).any():
                        h_idx = i; break
                
                if h_idx != -1:
                    df.columns = df.iloc[h_idx]
                    df = df.iloc[h_idx+1:]
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
                    if row.astype(str).str.contains("Mã học sinh").any():
                        df.columns = df.iloc[i]; df = df.iloc[i+1:]; break
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
                        elif 'CN' in val_loai or 'CẢ NĂM' in val_loai or 'NAM' in val_loai: current_sem = 'CN'
                    
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
    except Exception as e:
        st.error(f"Lỗi: {e}"); print(e)
    return count

# --- 4. GIAO DIỆN ADMIN ---
def view_admin(db):
    st.markdown('<div class="main-header">🛠️ QUẢN TRỊ VIÊN</div>', unsafe_allow_html=True)
    if st.button("Đăng xuất"): st.session_state.page = 'login'; st.rerun()
    
    if st.text_input("Mật khẩu:", type="password") == "admin123":
        t1, t2, t3 = st.tabs(["📤 UPLOAD DỮ LIỆU", "✅ KÍCH HOẠT", "🗑️ QUẢN LÝ XÓA"])
        
        # TAB 1: UPLOAD
        with t1:
            cls = st.selectbox("Chọn Lớp:", [f"Lớp {i}" for i in range(6, 13)])
            c1, c2 = st.columns(2)
            f1 = c1.file_uploader(f"Điểm HK1 {cls}", key="f1")
            f2 = c1.file_uploader(f"Điểm HK2 {cls}", key="f2")
            tk = st.file_uploader(f"File Tổng Kết {cls} (HK1, HK2, CN)", key="tk_all")
            
            if st.button("LƯU LÊN CLOUD", type="primary"):
                with st.spinner("Đang đồng bộ..."):
                    cnt = 0
                    if f1: cnt += upload_to_firebase(db, f1, "HK1", cls, 'score')
                    if f2: cnt += upload_to_firebase(db, f2, "HK2", cls, 'score')
                    if tk: cnt += upload_to_firebase(db, tk, "HK1", cls, 'summary') 
                    st.success(f"Xong! {cnt} bản ghi.")

        # TAB 2: KÍCH HOẠT
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
                                      disabled=['id', 'name', 'cls'], hide_index=True, height=500)
                if st.button("LƯU TRẠNG THÁI"):
                    batch = db.batch(); b_cnt = 0
                    for _, r in edited.iterrows():
                        batch.update(db.collection('students').document(r['id']), {'active': 1 if r['active'] else 0})
                        b_cnt += 1
                        if b_cnt >= 300: batch.commit(); batch = db.batch(); b_cnt = 0
                    batch.commit()
                    st.success("Đã lưu!")
            else: st.warning("Chưa có dữ liệu.")

        # TAB 3: XÓA DỮ LIỆU (NÂNG CẤP CHI TIẾT)
        with t3:
            st.warning("⚠️ Chú ý: Dữ liệu đã xóa sẽ không thể khôi phục!")
            
            # Chọn lớp
            cls_del = st.selectbox("1. Chọn Lớp cần xóa:", ["Tất cả"] + [f"Lớp {i}" for i in range(6, 13)], key="del_cls")
            
            c_d1, c_d2, c_d3 = st.columns(3)
            
            # Cột 1: Xóa Điểm Chi Tiết
            with c_d1:
                st.markdown('<div class="del-section"><div class="del-title">1. BẢNG ĐIỂM CHI TIẾT</div>', unsafe_allow_html=True)
                d_sc_hk1 = st.checkbox(f"Xóa Điểm HK1 ({cls_del})")
                d_sc_hk2 = st.checkbox(f"Xóa Điểm HK2 ({cls_del})")
                st.markdown('</div>', unsafe_allow_html=True)

            # Cột 2: Xóa Tổng Kết
            with c_d2:
                st.markdown('<div class="del-section"><div class="del-title">2. TỔNG KẾT & HẠNH KIỂM</div>', unsafe_allow_html=True)
                d_sum_hk1 = st.checkbox(f"Xóa TK HK1 ({cls_del})")
                d_sum_hk2 = st.checkbox(f"Xóa TK HK2 ({cls_del})")
                d_sum_cn = st.checkbox(f"Xóa TK Cả Năm ({cls_del})")
                st.markdown('</div>', unsafe_allow_html=True)

            # Cột 3: Xóa Học Sinh
            with c_d3:
                st.markdown('<div class="del-section"><div class="del-title">3. TÀI KHOẢN HỌC SINH</div>', unsafe_allow_html=True)
                d_student = st.checkbox(f"Xóa Danh sách HS ({cls_del})")
                st.caption("Lưu ý: Xóa HS sẽ xóa luôn quyền đăng nhập.")
                st.markdown('</div>', unsafe_allow_html=True)
            
            st.write("")
            if st.button("🚨 THỰC HIỆN XÓA", type="primary"):
                if not any([d_sc_hk1, d_sc_hk2, d_sum_hk1, d_sum_hk2, d_sum_cn, d_student]):
                    st.error("Bạn chưa chọn mục nào để xóa!")
                else:
                    with st.spinner("Đang xóa dữ liệu..."):
                        log = []
                        # Xóa điểm
                        if d_sc_hk1: 
                            n = delete_data_granular(db, 'scores', cls_del, 'HK1')
                            log.append(f"Xóa {n} điểm HK1")
                        if d_sc_hk2: 
                            n = delete_data_granular(db, 'scores', cls_del, 'HK2')
                            log.append(f"Xóa {n} điểm HK2")
                        
                        # Xóa tổng kết
                        if d_sum_hk1: 
                            n = delete_data_granular(db, 'summary', cls_del, 'HK1')
                            log.append(f"Xóa {n} TK HK1")
                        if d_sum_hk2: 
                            n = delete_data_granular(db, 'summary', cls_del, 'HK2')
                            log.append(f"Xóa {n} TK HK2")
                        if d_sum_cn: 
                            n = delete_data_granular(db, 'summary', cls_del, 'CN')
                            log.append(f"Xóa {n} TK Cả Năm")
                            
                        # Xóa học sinh
                        if d_student:
                            n = delete_data_granular(db, 'students', cls_del, None)
                            log.append(f"Xóa {n} Tài khoản HS")
                            
                        st.success(" | ".join(log))

# --- 5. GIAO DIỆN HỌC SINH ---
def view_student(db):
    c1, c2 = st.columns([8, 1])
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
        
        st.markdown(f"""
        <div class="report-card">
            <div class="school-name">TRƯỜNG THCS & THPT TUY ĐỨC</div>
            <div style="text-align:center; color:#FF8C00; font-weight:bold; margin-bottom:10px;">PHIẾU LIÊN LẠC ĐIỆN TỬ</div>
            <div style="text-align:center"><b>Học sinh:</b> {u.get('name')} | <b>Mã:</b> {u.get('id')} | <b>Lớp:</b> {u.get('cls')}</div>
        </div>
        """, unsafe_allow_html=True)
        
        ky = st.radio("Kỳ:", ["HK1", "HK2 & Cả năm"], horizontal=True)
        sem = "HK1" if ky == "HK1" else "HK2"
        
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
            
            renames = {'sub': 'Môn', 'tx': 'ĐĐG TX', 'gk': 'GK', 'ck': 'CK', 'tb': 'TBM', 'cn': 'CN'}
            cols = ['STT', 'Môn', 'ĐĐG TX', 'GK', 'CK', 'TBM']
            if sem == 'HK2': cols.append('CN')
            st.table(df.rename(columns=renames)[cols].set_index('STT'))
        else: st.info("Chưa có điểm môn học.")
        
        tk = db.collection('summary').document(f"{u['id']}_{sem}_summary").get()
        tk_data = tk.to_dict() if tk.exists else {}
        tk_cn = db.collection('summary').document(f"{u['id']}_CN_summary").get()
        tk_cn_data = tk_cn.to_dict() if tk_cn.exists else {}
        
        def card(l, v): return f'<div class="summary-item"><small>{l}</small><div class="summary-val">{v if v else "-"}</div></div>'
        
        st.markdown(f"##### 🏆 TỔNG KẾT {ky.upper()}")
        if tk_data:
            html = '<div class="summary-grid">'
            html += card("Học tập", tk_data.get('ht')) + card("Rèn luyện", tk_data.get('rl')) 
            html += card("Vắng", tk_data.get('v')) + card("Danh hiệu", tk_data.get('dh'))
            html += '</div>'
            st.markdown(html, unsafe_allow_html=True)
        else: st.caption("Chưa có dữ liệu.")

        if sem == 'HK2':
            st.markdown("---")
            st.markdown(f"##### 🚩 KẾT QUẢ CẢ NĂM")
            if tk_cn_data:
                html = '<div class="summary-grid">'
                html += card("Học tập CN", tk_cn_data.get('ht'))
                html += card("Rèn luyện CN", tk_cn_data.get('rl'))
                html += card("Danh hiệu CN", tk_cn_data.get('dh'))
                html += f'<div class="summary-item" style="border-color:red"><small>KẾT QUẢ</small><div class="summary-val" style="color:red">{tk_cn_data.get("kq")}</div></div>'
                html += '</div>'
                st.markdown(html, unsafe_allow_html=True)
            else: st.caption("Chưa có kết quả cả năm.")

# --- MAIN ---
if __name__ == "__main__":
    if 'page' not in st.session_state: st.session_state.page = 'login'
    try:
        db = init_firebase()
        if st.session_state.page == 'admin': view_admin(db)
        else: view_student(db)
    except Exception as e:
        st.error("Lỗi hệ thống."); print(e)

