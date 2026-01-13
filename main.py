import streamlit as st
import cantools
import binascii
from datetime import datetime
import pandas as pd
import time

# --- 頁面配置 ---
st.set_page_config(
    page_title="ZLG CAN 測試工具",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 核心 CSS：極致緊湊佈局與狀態列 ---
st.markdown("""
    <style>
    /* 1. 隱藏不必要元素，保留側邊欄按鈕 */
    .stDeployButton, [data-testid="stAppDeployButton"] { display: none !important; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* 2. 縮減頂部留白，讓內容往上移 */
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 0rem !important;
    }
    header[data-testid="stHeader"] {
        background-color: rgba(0,0,0,0) !important;
        pointer-events: none;
    }
    header[data-testid="stHeader"] button {
        pointer-events: auto;
    }

    /* 3. 自定義 App Header 樣式 */
    .app-header {
        background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 100%);
        padding: 15px 25px;
        border-radius: 10px;
        color: white;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .header-title { font-size: 1.5rem; font-weight: 700; margin: 0; }
    .header-info { font-size: 0.9rem; opacity: 0.9; }

    /* 4. 標準底部狀態列 */
    .status-bar {
        position: fixed;
        bottom: 0;
        left: 0;
        width: 100%;
        height: 30px;
        background-color: #f8fafc;
        border-top: 1px solid #e2e8f0;
        z-index: 9999;
        display: flex;
        align-items: center;
        padding: 0 20px;
        font-size: 0.75rem;
        color: #64748b;
    }
    
    /* 5. 修復代碼顯示樣式 */
    code {
        color: #e83e8c !important;
        background-color: #f1f5f9 !important;
        padding: 2px 5px !important;
        border-radius: 4px !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- 初始化 Session State ---
if 'connected' not in st.session_state:
    st.session_state.connected = False
if 'log_data' not in st.session_state:
    st.session_state.log_data = []
if 'db' not in st.session_state:
    st.session_state.db = None

# --- 功能函數 ---
def toggle_connection():
    st.session_state.connected = not st.session_state.connected
    if st.session_state.connected:
        st.toast("✅ 已連線至 ZLG 設備")
    else:
        st.toast("🔌 設備已中斷連線")

def send_can_message(msg_id, data):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    hex_data = " ".join(f"{b:02X}" for b in data)
    st.session_state.log_data.insert(0, {
        "時間": timestamp,
        "ID": hex(msg_id).upper(),
        "長度": len(data),
        "數據 (Hex)": hex_data
    })
    st.toast(f"🚀 已發送: {hex(msg_id).upper()}")

# --- 側邊欄：配置區 ---
with st.sidebar:
    st.subheader("🛠️ 硬體與檔案配置")
    
    st.markdown("### 硬體設定")
    dev_type = st.selectbox("設備類型", ["USBCAN-2E-U", "USBCAN-I", "USBCAN-II"])
    baudrate = st.selectbox("波特率", ["500K", "250K", "1000K", "125K"])
    
    if st.button("🔌 中斷連線" if st.session_state.connected else "⚡ 啟動連線", use_container_width=True, type="primary" if not st.session_state.connected else "secondary"):
        toggle_connection()
    
    st.divider()
    st.markdown("### 資料庫設定")
    uploaded_dbc = st.file_uploader("上傳 DBC 檔案", type=["dbc"])
    if uploaded_dbc:
        try:
            st.session_state.db = cantools.database.load_string(uploaded_dbc.getvalue().decode('utf-8'))
            st.success("DBC 載入成功")
        except:
            st.error("DBC 解析錯誤")

# --- 主畫面：標頭區 (Header) ---
# 建立一個整合標頭
dbc_status = "已載入" if st.session_state.db else "未載入"
conn_status = "ONLINE" if st.session_state.connected else "OFFLINE"
conn_color = "#4ade80" if st.session_state.connected else "#94a3b8"

st.markdown(f"""
    <div class="app-header">
        <div class="header-title">🚗 車機訊號模擬器 <span style="font-size: 0.8rem; font-weight: normal; opacity: 0.7;">v1.0.7</span></div>
        <div class="header-info" style="text-align: right;">
            <div>狀態: <span style="color: {conn_color}; font-weight: bold;">{conn_status}</span> | 設備: {dev_type}</div>
            <div>DBC: {dbc_status}</div>
        </div>
    </div>
""", unsafe_allow_html=True)

# --- 主畫面：操作區 ---
if st.session_state.db is None:
    st.info("👋 歡迎使用！請從側邊欄上傳 DBC 檔案以開始模擬測試。")
else:
    col_ctrl, col_view = st.columns([1.2, 0.8], gap="large")

    with col_ctrl:
        st.subheader("🎯 訊號調整")
        msg_list = [m.name for m in st.session_state.db.messages]
        target_name = st.selectbox("選擇報文 (Message)", msg_list)
        target_msg = st.session_state.db.get_message_by_name(target_name)
        
        st.caption(f"ID: {hex(target_msg.frame_id).upper()} | DLC: {target_msg.length} bytes")
        
        input_sigs = {}
        with st.container(border=True):
            for sig in target_msg.signals:
                min_v = float(sig.minimum) if sig.minimum is not None else 0.0
                max_v = float(sig.maximum) if sig.maximum is not None else 100.0
                init_v = float(sig.initial) if sig.initial is not None else min_v
                
                input_sigs[sig.name] = st.slider(
                    f"{sig.name} ({sig.unit if sig.unit else '-'})",
                    min_v, max_v, init_v,
                    key=f"s_{target_name}_{sig.name}"
                )

        if st.button("🚀 立即發送", use_container_width=True, disabled=not st.session_state.connected):
            try:
                encoded = target_msg.encode(input_sigs)
                send_can_message(target_msg.frame_id, encoded)
            except Exception as e:
                st.error(f"編碼失敗: {e}")

    with col_view:
        st.subheader("📡 發送預覽")
        try:
            raw = target_msg.encode(input_sigs)
            hex_str = "  ".join(f"{b:02X}" for b in raw)
        except:
            hex_str = "00 00 00 00 00 00 00 00"

        st.markdown(f"""
            <div style="background-color: #f8fafc; padding: 25px; border-radius: 12px; text-align: center; border: 1px solid #e2e8f0;">
                <p style="margin: 0; font-size: 0.75rem; color: #64748b; font-weight: bold;">RAW HEX DATA</p>
                <h2 style="margin: 15px 0; font-family: 'Courier New', monospace; color: #2563eb; letter-spacing: 2px;">{hex_str}</h2>
            </div>
        """, unsafe_allow_html=True)
        
        with st.expander("詳細資料結構 (JSON)", expanded=True):
            st.json({"Message": target_name, "Signals": input_sigs})

    st.divider()
    st.subheader("📊 系統監控")
    t_log, t_stats = st.tabs(["📋 歷史日誌", "📈 統計數據"])
    with t_log:
        if st.session_state.log_data:
            df = pd.DataFrame(st.session_state.log_data)
            st.dataframe(df, use_container_width=True, height=250)
            if st.button("🗑️ 清除所有日誌"):
                st.session_state.log_data = []
                st.rerun()
        else:
            st.caption("目前無傳輸紀錄...")
    with t_stats:
        c1, c2, c3 = st.columns(3)
        c1.metric("總發送次數", len(st.session_state.log_data))
        c2.metric("通訊錯誤", "0")
        c3.metric("硬體狀態", "Online" if st.session_state.connected else "Offline")

# --- 視窗底部的 Status Bar ---
st.markdown(f"""
    <div class="status-bar">
        <span style="margin-right: 20px;">📦 <b>Version:</b> v1.0.7</span>
        <span style="margin-right: 20px;">🌐 <b>Host:</b> localhost:8501</span>
        <span style="margin-right: 20px;">⚡ <b>Status:</b> {'Connected' if st.session_state.connected else 'Disconnected'}</span>
        <span style="margin-left: auto;">🕒 Last Sync: {datetime.now().strftime("%H:%M:%S")}</span>
    </div>
""", unsafe_allow_html=True)