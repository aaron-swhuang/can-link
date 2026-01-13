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

# --- 核心 CSS ---
st.markdown("""
    <style>
    .stDeployButton, [data-testid="stAppDeployButton"] { display: none !important; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    .block-container {
        padding-top: 3.5rem !important;
        padding-bottom: 2rem !important;
        padding-left: 3rem !important;
        padding-right: 3rem !important;
    }
    header[data-testid="stHeader"] {
        background-color: rgba(0,0,0,0) !important;
        pointer-events: none;
        height: 3.5rem !important;
    }
    header[data-testid="stHeader"] button {
        pointer-events: auto;
    }
    .app-header {
        background: linear-gradient(90deg, #0f172a 0%, #1e3a8a 100%);
        padding: 15px 25px;
        border-radius: 10px;
        color: white;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        position: relative;
        z-index: 10;
    }
    .header-title { font-size: 1.5rem; font-weight: 700; margin: 0; }
    .header-info { font-size: 0.85rem; opacity: 0.9; line-height: 1.4; }
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
    code {
        color: #e83e8c !important;
        background-color: #f1f5f9 !important;
        padding: 2px 5px !important;
        border-radius: 4px !important;
    }
    .signal-comment {
        font-size: 0.8rem;
        color: #64748b;
        font-style: italic;
        margin-top: -10px;
        margin-bottom: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# --- 工具函式 ---
def safe_float(val, default=0.0):
    if val is None:
        return float(default)
    try:
        if hasattr(val, 'value'):
            return float(val.value)
        return float(val)
    except (TypeError, ValueError):
        return float(default)

# --- 1. 測試引擎模組 ---
def execute_signal_sweep(db, msg_name, sig_name, start_val, end_val, step, interval_ms, progress_callback):
    try:
        msg = db.get_message_by_name(msg_name)
        current_sigs = {s.name: safe_float(s.initial, 0.0) for s in msg.signals}
        direction = 1 if end_val >= start_val else -1
        step = abs(step) * direction
        if step == 0: return False
        steps = int(abs(end_val - start_val) / abs(step)) + 1
        for i in range(steps):
            if not st.session_state.is_testing:
                break
            curr_val = start_val + (i * step)
            if direction == 1: curr_val = min(curr_val, end_val)
            else: curr_val = max(curr_val, end_val)
            current_sigs[sig_name] = curr_val
            encoded = msg.encode(current_sigs)
            send_can_message(msg.frame_id, encoded, silent=True)
            progress_callback(curr_val, i / max(1, (steps - 1)))
            time.sleep(interval_ms / 1000.0)
        return True
    except Exception as e:
        st.error(f"執行錯誤: {e}")
        return False

# --- 2. 初始化 ---
if 'connected' not in st.session_state:
    st.session_state.connected = False
if 'log_data' not in st.session_state:
    st.session_state.log_data = []
if 'db' not in st.session_state:
    st.session_state.db = None
if 'is_testing' not in st.session_state:
    st.session_state.is_testing = False

def toggle_connection():
    st.session_state.connected = not st.session_state.connected
    st.toast("✅ 連線成功" if st.session_state.connected else "🔌 已中斷")

def send_can_message(msg_id, data, silent=False):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    hex_data = " ".join(f"{b:02X}" for b in data)
    st.session_state.log_data.insert(0, {
        "時間": timestamp, "ID": hex(msg_id).upper(), "長度": len(data), "數據 (Hex)": hex_data
    })
    if not silent:
        st.toast(f"🚀 發送: {hex(msg_id).upper()}")

# --- 3. UI 介面 ---
with st.sidebar:
    st.subheader("🛠️ 配置中心")
    dev_type = st.selectbox("選擇設備", ["USBCAN-2E-U", "USBCAN-I"], key="hw_type")
    if st.button("🔌 中斷連線" if st.session_state.connected else "⚡ 啟動連線", use_container_width=True):
        toggle_connection()
    st.divider()
    st.markdown("### 載入資料庫")
    uploaded_dbc = st.file_uploader("選擇 DBC 檔案", type=["dbc"])
    if uploaded_dbc:
        content = uploaded_dbc.getvalue()
        success_load = False
        for encoding in ['utf-8', 'cp1252', 'gb2312', 'latin-1']:
            try:
                decoded_text = content.decode(encoding)
                st.session_state.db = cantools.database.load_string(decoded_text)
                st.success(f"DBC 載入成功 (編碼: {encoding})")
                success_load = True
                break
            except: continue
        if not success_load:
            st.error(f"DBC 解析失敗。")

# --- 主標頭 ---
dbc_status = "READY" if st.session_state.db else "EMPTY"
conn_status = "ONLINE" if st.session_state.connected else "OFFLINE"
conn_color = "#4ade80" if st.session_state.connected else "#94a3b8"
st.markdown(f"""
    <div class="app-header">
        <div class="header-title">🚗 車機訊號模擬器 <span style="font-size: 0.8rem; font-weight: normal; opacity: 0.7;">v1.1.5</span></div>
        <div class="header-info">
            <div>狀態: <span style="color: {conn_color}; font-weight: bold;">{conn_status}</span> | 設備: {dev_type}</div>
            <div style="text-align: right;">資料庫: {dbc_status}</div>
        </div>
    </div>
""", unsafe_allow_html=True)

if st.session_state.db is None:
    st.warning("👋 歡迎！請先在左側邊欄上傳 DBC 檔案以啟用功能。")
else:
    tab_manual, tab_auto = st.tabs(["🎮 手動操作", "🚀 自動化模組"])
    msg_list = [m.name for m in st.session_state.db.messages]
    with tab_manual:
        st.info("💡 手動模擬：調整滑桿發送單次訊號。")
        sel_msg_name = st.selectbox("選擇報文 (Message)", msg_list, key="manual_sel")
        msg_obj = st.session_state.db.get_message_by_name(sel_msg_name)
        if msg_obj.comment:
            st.caption(f"📝 報文說明: {msg_obj.comment}")
        input_sigs = {}
        with st.container(border=True):
            for sig in msg_obj.signals:
                is_integer = (not sig.is_float) and (sig.scale == 1) and (float(sig.offset).is_integer())
                if is_integer:
                    s_min = int(safe_float(sig.minimum, 0))
                    s_max = int(safe_float(sig.maximum, 100))
                    s_init = int(safe_float(sig.initial, s_min))
                    step = 1
                else:
                    s_min = float(safe_float(sig.minimum, 0.0))
                    s_max = float(safe_float(sig.maximum, 100.0))
                    s_init = float(safe_float(sig.initial, s_min))
                    step = None
                s_init = max(min(s_init, s_max), s_min)
                input_sigs[sig.name] = st.slider(
                    f"{sig.name} ({sig.unit or '-'})",
                    s_min, s_max, s_init,
                    step=step,
                    key=f"manual_s_{sel_msg_name}_{sig.name}",
                    help=sig.comment if sig.comment else "無詳細說明"
                )
                if sig.comment:
                    st.markdown(f'<p class="signal-comment">└─ {sig.comment}</p>', unsafe_allow_html=True)
        if st.button("🚀 發送單次訊息", use_container_width=True, disabled=not st.session_state.connected):
            try:
                encoded = msg_obj.encode(input_sigs)
                send_can_message(msg_obj.frame_id, encoded)
            except Exception as e:
                st.error(f"編碼失敗: {e}")
    with tab_auto:
        st.subheader("📋 自動化測試套件")
        with st.expander("🛠️ 訊號映射設定 (Signal Mapping)", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                target_msg_name = st.selectbox("目標報文", msg_list, key="auto_msg")
                msg_obj_auto = st.session_state.db.get_message_by_name(target_msg_name)
                if msg_obj_auto.comment:
                    st.caption(f"📝 {msg_obj_auto.comment}")
            with col2:
                target_sig_name = st.selectbox("目標訊號", [s.name for s in msg_obj_auto.signals], key="auto_sig")
                target_sig_obj = msg_obj_auto.get_signal_by_name(target_sig_name)
                if target_sig_obj.comment:
                    st.caption(f"📝 {target_sig_obj.comment}")
        st.divider()
        st.markdown(f"#### ⚡ 訊號掃掠測試：{target_sig_name}")
        is_int_auto = (not target_sig_obj.is_float) and (target_sig_obj.scale == 1)
        def_min = int(safe_float(target_sig_obj.minimum, 0)) if is_int_auto else safe_float(target_sig_obj.minimum, 0.0)
        def_max = int(safe_float(target_sig_obj.maximum, 100)) if is_int_auto else safe_float(target_sig_obj.maximum, 100.0)
        def_step = 1 if is_int_auto else 1.0
        c_p1, c_p2, c_p3, c_p4 = st.columns(4)
        start_v = c_p1.number_input("起始值", value=def_min)
        end_v = c_p2.number_input("結束值", value=def_max)
        step_v = c_p3.number_input("步進", value=def_step)
        freq_v = c_p4.number_input("間隔 (ms)", value=50)
        if not st.session_state.is_testing:
            if st.button("▶️ 執行測試", use_container_width=True, type="primary", disabled=not st.session_state.connected):
                st.session_state.is_testing = True
                st.rerun()
        else:
            if st.button("⏹️ 強制停止", use_container_width=True):
                st.session_state.is_testing = False
                st.rerun()
            st.info(f"測試執行中...")
            p_bar = st.progress(0)
            status_placeholder = st.empty()
            def ui_callback(val, progress):
                p_bar.progress(progress)
                val_str = f"{int(val)}" if is_int_auto else f"{val:.2f}"
                status_placeholder.metric("當前物理值", f"{val_str} {target_sig_obj.unit or ''}")
            success = execute_signal_sweep(
                st.session_state.db, target_msg_name, target_sig_name,
                start_v, end_v, step_v, freq_v, ui_callback
            )
            if success:
                st.session_state.is_testing = False
                st.success("✅ 測試執行完畢")
                st.balloons()
    st.divider()
    with st.expander("📊 傳輸紀錄 (Log)", expanded=False):
        if st.session_state.log_data:
            st.dataframe(pd.DataFrame(st.session_state.log_data), use_container_width=True)
            if st.button("🗑️ 清空日誌"):
                st.session_state.log_data = []
                st.rerun()
        else:
            st.caption("無數據...")

# --- 狀態列 ---
st.markdown(f"""
    <div class="status-bar">
        <span>📦 Version: v1.1.5 (Standard Layout)</span>
        <span style="margin-left: 20px;">🌐 Host: localhost:8501</span>
        <span style="margin-left: auto;">🕒 {datetime.now().strftime("%H:%M:%S")}</span>
    </div>
""", unsafe_allow_html=True)