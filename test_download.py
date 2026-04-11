import streamlit as st
import io

st.write("Test Download Button UUID Bug")

# Test 1: Plain bytes
b1 = b"Hello, World - Bytes!"
st.download_button("Test Bytes", data=b1, file_name="test_bytes.txt", mime="text/plain", key="btn1")

# Test 2: BytesIO
b2 = b"Hello, World - BytesIO!"
bio = io.BytesIO(b2)
st.download_button("Test BytesIO", data=bio, file_name="test_bytesio.txt", mime="text/plain", key="btn2")

# Test 3: PDF Bytes
b3 = b"%PDF-1.4\n%EOF"
st.download_button("Test PDF Bytes", data=b3, file_name="test_pdf.pdf", mime="application/pdf", key="btn3")

# Test 4: Dynamic Name
name = "MyReport_123.pdf"
st.download_button("Test Dynamic Name", data=b3, file_name=name, mime="application/pdf", key="btn4")
