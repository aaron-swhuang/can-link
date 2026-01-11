import streamlit as st
import cantools
import binascii
from datetime import datetime
import pandas as pd

# --- 頁面配置 ---
st.set_page_config(
    page_title="ZLG CAN 測試工具",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 核心 CSS：打造標準視窗狀態列 ---
st.markdown("""
    <style>
    /* 1. 基礎 UI 清理 */
    .stDeployButton {display:none;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header[data-testid="stHeader"] {background-color: rgba(0,0,0,0); z-index: 0;}

    /* 2. 標準狀態列 (Status Bar) 樣式 */
    .status-bar {
        position: fixed;
        bottom: 0;
        left: 0;
        width: 100%;
        height: 30px;
        background-color: #f0f2f6;
        border-top: 1px solid #dcdfe6;
        z-index: 9999;
        display: flex;
        align-items: center;
        padding: 0 20px;
        font-size: 0.8rem;
        color: #5e6d82;
        font-family: sans-serif;
    }
    
    /* 3. 主內容區微調，避免被 30px 狀態列擋住最後一行 */
    .stApp {
        margin-bottom: 40px;
    }
    
    /* 4. 修復滑桿與代碼顯示樣式 */
    code {
        color: #e83e8c !important;
        background-color: #f8f9fa !important;
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

# --- 側邊欄：控制面板 ---
with st.sidebar:
    st.title("⚙️ 控制面板")
    
    # 設備狀態簡潔顯示
    s_color = "green" if st.session_state.connected else "gray"
    s_icon = "🟢" if st.session_state.connected else "⚪"
    st.markdown(f"""
        <div style="padding: 10px; border-radius: 5px; border: 1px solid #eee; background-color: #fff; margin-bottom: 15px;">
            <span style="color: {s_color}; font-weight: bold;">{s_icon} {'設備連線中' if st.session_state.connected else '未連接'}</span>
        </div>
    """, unsafe_allow_html=True)
    
    st.subheader("硬體連線")
    dev_type = st.selectbox("設備類型", ["USBCAN-2E-U", "USBCAN-I", "USBCAN-II"])
    baudrate = st.selectbox("波特率", ["500K", "250K", "1000K", "125K"])
    
    if st.button("🔌 中斷連線" if st.session_state.connected else "⚡ 啟動連線", use_container_width=True, type="primary" if not st.session_state.connected else "secondary"):
        toggle_connection()
    
    st.divider()
    uploaded_dbc = st.file_uploader("上傳 DBC 檔案", type=["dbc"])
    if uploaded_dbc:
        try:
            st.session_state.db = cantools.database.load_string(uploaded_dbc.getvalue().decode('utf-8'))
            st.success("DBC 載入成功")
        except:
            st.error("DBC 解析錯誤")

# --- 主畫面：操作區 ---
st.title("🚗 車機訊號模擬器")

if st.session_state.db is None:
    st.info("👋 歡迎！請先在上傳 DBC 檔案以開始模擬。")
else:
    # 建立操作與預覽區塊
    col_ctrl, col_view = st.columns([1.2, 0.8], gap="large")

    with col_ctrl:
        st.subheader("🎯 訊號調整")
        msg_list = [m.name for m in st.session_state.db.messages]
        target_name = st.selectbox("選擇報文 (Message)", msg_list)
        target_msg = st.session_state.db.get_message_by_name(target_name)
        
        st.caption(f"ID: {hex(target_msg.frame_id).upper()} | DLC: {target_msg.length}")
        
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
            <div style="background-color: #f0f2f6; padding: 20px; border-radius: 10px; text-align: center;">
                <p style="margin: 0; font-size: 0.8rem; color: #666;">RAW HEX DATA</p>
                <h2 style="margin: 10px 0; font-family: monospace; color: #007bff;">{hex_str}</h2>
            </div>
        """, unsafe_allow_html=True)
        
        with st.expander("詳細結構", expanded=True):
            st.json({"Message": target_name, "Signals": input_sigs})

    # --- 日誌區塊：回到主捲動區域，不再固定擋路 ---
    st.divider()
    st.subheader("📊 系統監控")
    t_log, t_stats = st.tabs(["📋 歷史日誌", "📈 統計數據"])
    with t_log:
        if st.session_state.log_data:
            df = pd.DataFrame(st.session_state.log_data)
            st.dataframe(df, use_container_width=True, height=300)
            if st.button("🗑️ 清除所有日誌"):
                st.session_state.log_data = []
                st.rerun()
        else:
            st.caption("暫無歷史數據...")
    with t_stats:
        c1, c2, c3 = st.columns(3)
        c1.metric("總發送", len(st.session_state.log_data))
        c2.metric("錯誤", "0")
        c3.metric("狀態", "Ready")

# --- 視窗底部的 Status Bar ---
st.markdown(f"""
    <div class="status-bar">
        <span style="margin-right: 20px;"><b>Version:</b> v1.0.7</span>
        <span style="margin-right: 20px;"><b>Port:</b> 8501</span>
        <span style="margin-right: 20px;"><b>Device:</b> {dev_type if st.session_state.connected else 'None'}</span>
        <span style="margin-left: auto;">Last Update: {datetime.now().strftime("%H:%M:%S")}</span>
    </div>
""", unsafe_allow_html=True)