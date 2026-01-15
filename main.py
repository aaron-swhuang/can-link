import os
import sys
import time
import platform
import logging
import binascii
import traceback
import atexit
from datetime import datetime
from ctypes import *
from contextlib import contextmanager

# --- 1. 全局路徑與環境初始化 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
zlg_folder_path = os.path.normpath(os.path.join(current_dir, "zlg"))

if os.path.exists(zlg_folder_path):
    if zlg_folder_path not in sys.path:
        sys.path.insert(0, zlg_folder_path)
    if platform.system() == "Windows":
        try:
            os.add_dll_directory(zlg_folder_path)
        except:
            pass

# --- 2. 核心環境保護器 ---
@contextmanager
def zlg_env():
    """上下文管理器：確保在執行 ZLG 相關代碼時，工作目錄正確切換至 zlg 資料夾"""
    _old_cwd = os.getcwd()
    try:
        os.chdir(zlg_folder_path)
        yield
    finally:
        os.chdir(_old_cwd)

# --- 3. 頂層導入 ZLG SDK ---
ZLG_SDK_AVAILABLE = False
import_error_msg = ""
try:
    with zlg_env():
        import zlgcan
        ZCAN = zlgcan.ZCAN
        ZCAN_Transmit_Data = zlgcan.ZCAN_Transmit_Data
        ZCAN_TransmitFD_Data = getattr(zlgcan, 'ZCAN_TransmitFD_Data', None)
        ZCAN_Receive_Data = getattr(zlgcan, 'ZCAN_Receive_Data', None)
        ZCAN_ReceiveFD_Data = getattr(zlgcan, 'ZCAN_ReceiveFD_Data', None)
        ZCAN_CHANNEL_INIT_CONFIG = zlgcan.ZCAN_CHANNEL_INIT_CONFIG
        INVALID_DEVICE_HANDLE = getattr(zlgcan, 'INVALID_DEVICE_HANDLE', 0)
        CANFD_START_FUNC = getattr(zlgcan, 'canfd_start', None)
        ZCAN_TYPE_CAN = 0
        ZCAN_TYPE_CANFD = 1
        ZCAN_USBCANFD_200U = 41
        ZCAN_USBCANFD_100U = 42
        ZLG_SDK_AVAILABLE = True
except Exception as e:
    import_error_msg = str(e)

import streamlit as st
import cantools
import pandas as pd

# --- 4. 日誌機制配置 ---
log_dir = os.path.join(current_dir, "log")
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

log_filename = datetime.now().strftime("%Y-%m-%d") + ".log"
log_filepath = os.path.join(log_dir, log_filename)

logger = logging.getLogger("ZLG_CAN_TOOL")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(log_filepath, encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
    logger.addHandler(fh)

# --- 5. 資源清理機制 ---
def cleanup_resources():
    """當進程結束時釋放硬體"""
    print("\n[系統] 正在關閉 Python 進程，檢查硬體資源釋放狀態...")
atexit.register(cleanup_resources)

# --- 6. 頁面配置與樣式 ---
st.set_page_config(page_title="ZLG CAN 測試工具", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
    .stDeployButton, [data-testid="stAppDeployButton"] { display: none !important; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container { padding-top: 3.5rem !important; padding-bottom: 2rem !important; padding-left: 3rem !important; padding-right: 3rem !important; }
    .app-header { background: linear-gradient(90deg, #0f172a 0%, #1e3a8a 100%); padding: 15px 25px; border-radius: 10px; color: white; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
    .status-indicator { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 0.9rem; }
    .dot { height: 10px; width: 10px; border-radius: 50%; display: inline-block; }
    .dot-online { background-color: #4ade80; box-shadow: 0 0 8px #4ade80; animation: blink 2s infinite; }
    .dot-offline { background-color: #94a3b8; }
    @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
    .status-bar { position: fixed; bottom: 0; left: 0; width: 100%; height: 30px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; z-index: 9999; display: flex; align-items: center; padding: 0 20px; font-size: 0.75rem; color: #64748b; }
</style>
""", unsafe_allow_html=True)

# --- 7. 硬體管理 ---
@st.cache_resource
def get_zcan_instance():
    if not ZLG_SDK_AVAILABLE: return None
    logger.info("正在建立 ZCAN 類別實例...")
    with zlg_env(): return ZCAN()

def safe_float(val, default=0.0):
    if val is None: return float(default)
    try: return float(val.value) if hasattr(val, 'value') else float(val)
    except: return float(default)

# --- 8. Session State 初始化 ---
if 'connected' not in st.session_state: st.session_state.connected = False
if 'log_data' not in st.session_state: st.session_state.log_data = []
if 'db' not in st.session_state: st.session_state.db = None
if 'is_testing' not in st.session_state: st.session_state.is_testing = False
if 'is_monitoring' not in st.session_state: st.session_state.is_monitoring = False
if 'd_handle' not in st.session_state: st.session_state.d_handle = None
if 'c_handle' not in st.session_state: st.session_state.c_handle = None
if 'can_type' not in st.session_state: st.session_state.can_type = 1
if 'hw_info_str' not in st.session_state: st.session_state.hw_info_str = ""

def toggle_connection(hw_type_name):
    """連線/斷開邏輯"""
    if not st.session_state.connected:
        if ZLG_SDK_AVAILABLE:
            temp_handle = INVALID_DEVICE_HANDLE
            try:
                zcanlib = get_zcan_instance()
                dev_type = ZCAN_USBCANFD_200U if "200U" in hw_type_name else ZCAN_USBCANFD_100U
                with zlg_env():
                    logger.info(f"嘗試開啟設備 (Type: {dev_type})...")
                    temp_handle = zcanlib.OpenDevice(dev_type, 0, 0)
                    if temp_handle == INVALID_DEVICE_HANDLE:
                        logger.error("OpenDevice 失敗")
                        st.error("❌ 開啟失敗：設備可能被佔用"); return
                    logger.info(f"OpenDevice 成功, Handle: {temp_handle}")
                    if st.session_state.can_type == 1 and CANFD_START_FUNC:
                        logger.info("執行 CANFD 啟動流程...")
                        chn_handle = CANFD_START_FUNC(zcanlib, temp_handle, 0)
                        if chn_handle == 0: raise Exception("canfd_start 失敗")
                        st.session_state.c_handle = chn_handle
                    else:
                        logger.info("執行傳統 CAN 啟動流程...")
                        config = ZCAN_CHANNEL_INIT_CONFIG()
                        config.can_type = 0
                        chn_handle = zcanlib.InitCAN(temp_handle, 0, config)
                        if chn_handle == 0 or zcanlib.StartCAN(chn_handle) != 1: raise Exception("啟動失敗")
                        st.session_state.c_handle = chn_handle
                    try:
                        info = zcanlib.GetDeviceInf(temp_handle)
                        st.session_state.hw_info_str = str(info)
                    except: st.session_state.hw_info_str = "資訊讀取失敗"
                    st.session_state.d_handle = temp_handle
                    st.session_state.connected = True
                    st.toast("✅ 硬體連線成功")
            except Exception as e:
                logger.error(f"連線異常: {e}")
                st.error(f"連線失敗: {e}")
                if temp_handle != INVALID_DEVICE_HANDLE:
                    with zlg_env(): zcanlib.CloseDevice(temp_handle)
        else:
            st.session_state.connected = True
    else:
        if st.session_state.d_handle:
            with zlg_env(): get_zcan_instance().CloseDevice(st.session_state.d_handle)
        st.session_state.connected = False
        st.session_state.d_handle = None
        st.session_state.c_handle = None
        st.session_state.is_monitoring = False
        st.toast("🔌 已斷開連線")

def send_can_message(msg_id, data, silent=False):
    success = True
    status_code = "1"
    if st.session_state.connected and st.session_state.c_handle and ZLG_SDK_AVAILABLE:
        try:
            zcanlib = get_zcan_instance()
            with zlg_env():
                if st.session_state.can_type == 1:
                    t_data = ZCAN_TransmitFD_Data()
                    t_data.frame.can_id = msg_id
                    t_data.frame.len = len(data)
                    t_data.frame.eff = 1 if msg_id > 0x7FF else 0
                    t_data.frame.fdf = 1
                    t_data.frame.brs = 1
                    for i, b in enumerate(data): t_data.frame.data[i] = b
                    ret = zcanlib.TransmitFD(st.session_state.c_handle, t_data, 1)
                else:
                    t_data = ZCAN_Transmit_Data()
                    t_data.frame.can_id = msg_id
                    t_data.frame.can_dlc = len(data)
                    t_data.frame.eff = 1 if msg_id > 0x7FF else 0
                    for i, b in enumerate(data): t_data.frame.data[i] = b
                    ret = zcanlib.Transmit(st.session_state.c_handle, t_data, 1)
                if ret != 1:
                    success, status_code = False, f"Err:{ret}"
                    logger.error(f"TX 失敗 ID: {hex(msg_id)}, SDK: {ret}")
        except Exception as e:
            success, status_code = False, "EXCP"
            logger.error(f"TX 異常: {e}")
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    hex_data = " ".join(f"{b:02X}" for b in data)
    st.session_state.log_data.insert(0, {"方向": "TX", "時間": timestamp, "ID": hex(msg_id).upper(), "數據": hex_data, "狀態": "OK" if success else status_code})
    return success

def poll_reception():
    if not st.session_state.connected or not st.session_state.c_handle: return
    zcanlib = get_zcan_instance()
    with zlg_env():
        rcv_type = ZCAN_TYPE_CANFD if st.session_state.can_type == 1 else ZCAN_TYPE_CAN
        rcv_num = zcanlib.GetReceiveNum(st.session_state.c_handle, rcv_type)
        if rcv_num > 0:
            if st.session_state.can_type == 1:
                msgs, actual = zcanlib.ReceiveFD(st.session_state.c_handle, rcv_num)
                for i in range(actual):
                    hex_data = " ".join(f"{msgs[i].frame.data[j]:02X}" for j in range(msgs[i].frame.len))
                    st.session_state.log_data.insert(0, {"方向": "RX", "時間": datetime.now().strftime("%H:%M:%S.%f")[:-3], "ID": hex(msgs[i].frame.can_id).upper(), "數據": hex_data, "狀態": "OK"})
            else:
                msgs, actual = zcanlib.Receive(st.session_state.c_handle, rcv_num)
                for i in range(actual):
                    hex_data = " ".join(f"{msgs[i].frame.data[j]:02X}" for j in range(msgs[i].frame.can_dlc))
                    st.session_state.log_data.insert(0, {"方向": "RX", "時間": datetime.now().strftime("%H:%M:%S.%f")[:-3], "ID": hex(msgs[i].frame.can_id).upper(), "數據": hex_data, "狀態": "OK"})
            if len(st.session_state.log_data) > 200: st.session_state.log_data = st.session_state.log_data[:200]

# --- 9. UI 渲染 ---
with st.sidebar:
    st.subheader("🛠️ 硬體配置")
    hw_choice = st.selectbox("設備型號", ["USBCANFD_200U", "USBCANFD_100U"])
    st.session_state.can_type = st.radio("通訊模式", [0, 1], format_func=lambda x: "Classic CAN" if x == 0 else "CANFD", index=1, horizontal=True)
    if st.button("🔌 斷開連線" if st.session_state.connected else "⚡ 啟動硬體連線", use_container_width=True, type="primary" if st.session_state.connected else "secondary"):
        toggle_connection(hw_choice); st.rerun()
    st.divider()
    st.session_state.is_monitoring = st.toggle("📡 監控模式", value=st.session_state.is_monitoring, disabled=not st.session_state.connected or st.session_state.is_testing)
    uploaded_dbc = st.file_uploader("載入 DBC 檔案", type=["dbc"], label_visibility="collapsed")
    if uploaded_dbc:
        try:
            st.session_state.db = cantools.database.load_string(uploaded_dbc.getvalue().decode('utf-8'))
            st.success("DBC 載入成功")
        except: st.error("DBC 解析失敗")

status_dot = "dot-online" if st.session_state.connected else "dot-offline"
st.markdown(f'<div class="app-header"><div>🚗 ZLG CAN 測試工具 v1.5.9</div><div class="status-indicator"><span class="dot {status_dot}"></span>{"ONLINE" if st.session_state.connected else "OFFLINE"}</div></div>', unsafe_allow_html=True)

if st.session_state.db is None:
    st.warning("👋 請先載入 DBC 檔案以開始操作。")
else:
    tab1, tab2 = st.tabs(["🎮 手動控制", "🚀 自動化測試"])
    msg_list = [m.name for m in st.session_state.db.messages]
    with tab1:
        sel_msg = st.selectbox("選擇報文", msg_list)
        msg_obj = st.session_state.db.get_message_by_name(sel_msg)
        input_sigs = {}
        with st.container(border=True):
            for sig in msg_obj.signals:
                s_min, s_max = float(safe_float(sig.minimum, 0)), float(safe_float(sig.maximum, 100))
                s_init = max(min(safe_float(sig.initial, s_min), s_max), s_min)
                input_sigs[sig.name] = st.slider(f"{sig.name}", s_min, s_max, s_init)
        if st.button("🚀 發送數據", use_container_width=True, disabled=not st.session_state.connected):
            try: send_can_message(msg_obj.frame_id, msg_obj.encode(input_sigs))
            except Exception as e: st.error(f"編碼失敗: {e}")
    with tab2:
        st.subheader("🚀 訊號掃掠測試")
        c1, c2 = st.columns(2)
        t_msg_name = c1.selectbox("目標報文", msg_list, key="a_m")
        t_msg = st.session_state.db.get_message_by_name(t_msg_name)
        t_sig_name = c2.selectbox("目標訊號", [s.name for s in t_msg.signals])
        t_sig = t_msg.get_signal_by_name(t_sig_name)
        col_p1, col_p2, col_p3, col_p4 = st.columns(4)
        start_v = col_p1.number_input("起始值", value=float(safe_float(t_sig.minimum, 0)))
        end_v = col_p2.number_input("結束值", value=float(safe_float(t_sig.maximum, 100)))
        step_v = col_p3.number_input("步進值", value=1.0)
        freq_v = col_p4.number_input("間隔(ms)", value=50)
        if not st.session_state.is_testing:
            if st.button("▶️ 啟動掃掠測試", use_container_width=True, type="primary", disabled=not st.session_state.connected):
                st.session_state.is_testing = True; st.rerun()
        else:
            st.button("⏹️ 停止測試", on_click=lambda: st.session_state.update({"is_testing": False}))
            p_bar, metric_val, log_view = st.progress(0), st.empty(), st.empty()
            curr_sigs = {s.name: safe_float(s.initial, safe_float(s.minimum, 0.0)) for s in t_msg.signals}
            steps = int(abs(end_v - start_v) / (abs(step_v) or 1)) + 1
            for i in range(steps):
                if not st.session_state.is_testing: break
                val = start_v + (i * step_v * (1 if end_v >= start_v else -1))
                curr_sigs[t_sig_name] = val
                try:
                    tx_ok = send_can_message(t_msg.frame_id, t_msg.encode(curr_sigs), silent=True)
                    p_bar.progress(i / (steps - 1))
                    metric_val.metric(f"發送: {t_sig_name}", f"{val:.2f}", delta="OK" if tx_ok else "FAIL")
                    log_view.dataframe(pd.DataFrame(st.session_state.log_data), use_container_width=True, hide_index=True)
                except Exception as e: st.error(f"測試錯誤: {e}"); break
                time.sleep(freq_v / 1000.0)
            st.session_state.is_testing = False; st.rerun()
    with st.expander("📊 監控日誌詳情", expanded=True):
        log_placeholder = st.empty()
        if st.button("🗑️ 清空日誌紀錄"): st.session_state.log_data = []; st.rerun()

# --- 10. 監控循環與 UI 同步 ---
if st.session_state.is_monitoring and not st.session_state.is_testing:
    poll_reception()
    log_placeholder.dataframe(pd.DataFrame(st.session_state.log_data), use_container_width=True, hide_index=True)
    time.sleep(0.1); st.rerun()
else:
    if st.session_state.log_data:
        log_placeholder.dataframe(pd.DataFrame(st.session_state.log_data), use_container_width=True, hide_index=True)

st.markdown(f'<div class="status-bar"><span>📦 Version: v1.5.9 (Code Cleaned)</span><span style="margin-left:auto;">📂 Log: {log_filename}</span></div>', unsafe_allow_html=True)