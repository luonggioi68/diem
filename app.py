st.write("--- ĐANG KIỂM TRA KẾT NỐI ---")
try:
    # 1. Thử đọc Secrets
    test_key = st.secrets["firebase"]
    st.success(f"✅ Đã đọc được Secrets! Project ID: {test_key.get('project_id')}")
    
    # 2. Thử tạo credentials
    key_dict = dict(test_key)
    key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
    cred = credentials.Certificate(key_dict)
    st.success("✅ Chứng chỉ bảo mật hợp lệ!")
    
    # 3. Thử kết nối
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    st.success("✅ KẾT NỐI FIREBASE THÀNH CÔNG!")
    
except Exception as e:
    st.error("❌ LỖI KẾT NỐI:")
    st.code(str(e)) # Nó sẽ hiện chi tiết lỗi là gì
    st.stop() # Dừng chương trình để thầy đọc lỗi
