import streamlit as st
import json

st.write("Đang kiểm tra kết nối...")

try:
    # Thử đọc key
    key_info = json.loads(st.secrets["textkey"])
    st.success("✅ Đã đọc được Key bảo mật!")
    st.write("Project ID:", key_info.get("project_id"))
    
    # Thử import thư viện
    import firebase_admin
    st.success("✅ Đã cài đặt thư viện firebase-admin!")
    
except Exception as e:
    st.error("❌ CÓ LỖI XẢY RA:")
    st.code(str(e))
