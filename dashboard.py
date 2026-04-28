import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="JobBot Dashboard",
    page_icon="🎯",
    layout="wide"
)

# Hide Streamlit default UI
st.markdown("""
<style>
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 0 !important; }
</style>
""", unsafe_allow_html=True)

# Read the HTML file and render it
with open("jobbot-dashboard.html", "r", encoding="utf-8") as f:
    html_content = f.read()

components.html(html_content, height=1000, scrolling=True)