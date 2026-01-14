import os
import sys
import time
import platform
import logging
import binascii
import traceback
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
        ZCAN_CHANNEL_INIT_CONFIG = zlgcan.ZCAN_CHANNEL_INIT_CONFIG
        INVALID_DEVICE_HANDLE = getattr(zlgcan, 'INVALID_DEVICE_HANDLE', 0)
        # 根據您的測試代碼導入輔助函式
        CANFD_START_FUNC = getattr(zlgcan, 'canfd_start', None)

        ZCAN_USBCANFD_200U = 41
        ZCAN_USBCANFD_100U = 42
        ZLG_SDK_AVAILABLE = True
except Exception as e:
    import_error_msg = str(e)

import streamlit as st
import cantools
import pandas as pd

# --- 4. 日誌機制 ---
log_dir = os.path.join(current_dir, "log")
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

log_filepath = os.path.join(log_dir, datetime.now().strftime("%Y-%m-%d") + ".log")
logger = logging.getLogger("ZLG_CAN_TOOL")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(log_filepath, encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
    logger.addHandler(fh)

# --- 5. 頁面配置與 CSS ---
st.set_page_config(page_title="ZLG CAN 測試工具", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
    .stDeployButton, [data-testid="stAppDeployButton"] { display: none !important; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container { padding-top: 3.5rem !important; padding-bottom: 2rem !important; padding-left: 3rem !important; padding-right: 3rem !important; }
    header[data-testid="stHeader"] { background-color: rgba(0,0,0,0) !important; pointer-events: none; }
    header[data-testid="stHeader"] button { pointer-events: auto; }
    .app-header { background: linear-gradient(90deg, #0f172a 0%, #1e3a8a 100%); padding: 15px 25px; border-radius: 10px; color: white; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
    .status-indicator { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 0.9rem; }
    .dot { height: 10px; width: 10px; border-radius: 50%; display: inline-block; }
    .dot-online { background-color: #4ade80; box-shadow: 0 0 8px #4ade80; animation: blink 2s infinite; }
    .dot-offline { background-color: #94a3b8; }
    @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
    .status-bar { position: fixed; bottom: 0; left: 0; width: 100%; height: 30px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; z-index: 9999; display: flex; align-items: center; padding: 0 20px; font-size: 0.75rem; color: #64748b; }
</style>
""", unsafe_allow_html=True)

# --- 6. 硬體管理 ---
@st.cache_resource
def get_zcan_instance():
    if not ZLG_SDK_AVAILABLE: return None
    with zlg_env():
        return ZCAN()

def safe_float(val, default=0.0):
    if val is None: return float(default)
    try: return float(val.value) if hasattr(val, 'value') else float(val)
    except: return float(default)

# --- 7. 初始化 Session State ---
if 'connected' not in st.session_state: st.session_state.connected = False
if 'log_data' not in st.session_state: st.session_state.log_data = []
if 'db' not in st.session_state: st.session_state.db = None
if 'is_testing' not in st.session_state: st.session_state.is_testing = False
if 'd_handle' not in st.session_state: st.session_state.d_handle = None
if 'c_handle' not in st.session_state: st.session_state.c_handle = None
if 'can_type' not in st.session_state: st.session_state.can_type = 1
if 'hw_info_str' not in st.session_state: st.session_state.hw_info_str = ""

def toggle_connection(hw_type_name):
    if not st.session_state.connected:
        if ZLG_SDK_AVAILABLE:
            temp_handle = INVALID_DEVICE_HANDLE
            try:
                zcanlib = get_zcan_instance()
                dev_type = ZCAN_USBCANFD_200U if "200U" in hw_type_name else ZCAN_USBCANFD_100U

                with zlg_env():
                    # 步驟 1: 開啟設備
                    logger.info(f"OpenDevice (Type: {dev_type})...")
                    temp_handle = zcanlib.OpenDevice(dev_type, 0, 0)
                    if temp_handle == INVALID_DEVICE_HANDLE:
                        st.error("❌ 開啟硬體失敗！請檢查 USB 與連線狀態。")
                        return

                    # 步驟 2: 啟動通道 (採用您的測試代碼邏輯)
                    logger.info("正在使用 canfd_start 啟動通道...")
                    if st.session_state.can_type == 1 and CANFD_START_FUNC:
                        # 使用 zlgcan.py 內建的輔助函式
                        # 注意：zlgcan 模組內的函式通常需要傳入 lib 實例和設備控制代碼
                        chn_handle = CANFD_START_FUNC(zcanlib, temp_handle, 0)
                        if chn_handle == 0:
                            raise Exception("canfd_start 失敗，請確認設備支援 FD 模式。")
                        st.session_state.c_handle = chn_handle
                        logger.info(f"CANFD 通道啟動成功, Channel Handle: {chn_handle}")
                    else:
                        # 傳統模式 fallback
                        config = ZCAN_CHANNEL_INIT_CONFIG()
                        config.can_type = 0
                        chn_handle = zcanlib.InitCAN(temp_handle, 0, config)
                        if chn_handle == 0 or zcanlib.StartCAN(chn_handle) != 1:
                            raise Exception("傳統 CAN 通道啟動失敗。")
                        st.session_state.c_handle = chn_handle

                    # 步驟 3: 獲取資訊
                    try:
                        info = zcanlib.GetDeviceInf(temp_handle)
                        st.session_state.hw_info_str = str(info)
                    except:
                        st.session_state.hw_info_str = "資訊讀取失敗"

                    st.session_state.d_handle = temp_handle
                    st.session_state.connected = True
                    st.toast("✅ 連線成功")

            except Exception as e:
                logger.error(f"連線異常: {e}")
                st.error(f"連線異常: {e}")
                if temp_handle != INVALID_DEVICE_HANDLE:
                    with zlg_env(): zcanlib.CloseDevice(temp_handle)
        else:
            st.session_state.connected = True
    else:
        # 斷開連線
        if st.session_state.d_handle and ZLG_SDK_AVAILABLE:
            with zlg_env(): get_zcan_instance().CloseDevice(st.session_state.d_handle)
        st.session_state.connected = False
        st.session_state.d_handle = None
        st.session_state.c_handle = None
        st.toast("🔌 已斷開")

def force_release_hardware():
    if ZLG_SDK_AVAILABLE:
        try:
            zcanlib = get_zcan_instance()
            if st.session_state.d_handle:
                with zlg_env(): zcanlib.CloseDevice(st.session_state.d_handle)
            st.session_state.connected = False
            st.session_state.d_handle = None
            st.session_state.c_handle = None
            st.success("✅ 硬體控制權已強制釋放。")
        except Exception as e:
            st.error(f"釋放失敗: {e}")

def send_can_message(msg_id, data, silent=False):
    send_success = True
    status_code = "1"
    if st.session_state.connected and st.session_state.c_handle and ZLG_SDK_AVAILABLE:
        try:
            zcanlib = get_zcan_instance()
            is_eff = 1 if msg_id > 0x7FF else 0
            with zlg_env():
                if st.session_state.can_type == 1 and ZCAN_TransmitFD_Data:
                    # --- CANFD 發送模式 ---
                    t_data = ZCAN_TransmitFD_Data()
                    t_data.frame.can_id = msg_id
                    t_data.frame.len = len(data)
                    t_data.frame.eff = is_eff
                    t_data.frame.fdf = 1
                    t_data.frame.brs = 1 # 對齊您的測試代碼：開啟加速
                    t_data.transmit_type = 0
                    for i, b in enumerate(data):
                        if i < 64: t_data.frame.data[i] = b
                    ret = zcanlib.TransmitFD(st.session_state.c_handle, t_data, 1)
                else:
                    # --- 傳統 CAN 發送模式 ---
                    t_data = ZCAN_Transmit_Data()
                    t_data.frame.can_id = msg_id
                    t_data.frame.can_dlc = len(data)
                    t_data.frame.eff = is_eff
                    t_data.transmit_type = 0
                    for i, b in enumerate(data):
                        if i < 8: t_data.frame.data[i] = b
                    ret = zcanlib.Transmit(st.session_state.c_handle, t_data, 1)

                if ret != 1:
                    send_success = False
                    status_code = f"Err:{ret}"
        except Exception as e:
            send_success = False
            status_code = "EXCP"
            logger.error(f"發送異常: {e}")

    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    hex_data = " ".join(f"{b:02X}" for b in data)
    st.session_state.log_data.insert(0, {
        "時間": timestamp, "ID": hex(msg_id).upper(), "數據": hex_data, "狀態": "OK" if send_success else status_code
    })
    if not send_success and not silent:
        st.error(f"發送失敗 (ID: {hex(msg_id).upper()})，代碼: {status_code}")

# --- 8. UI 介面 ---
with st.sidebar:
    st.subheader("🛠️ 硬體配置")
    hw_choice = st.selectbox("設備型號", ["USBCANFD_200U", "USBCANFD_100U"])
    st.session_state.can_type = st.radio("通訊模式", [0, 1], format_func=lambda x: "Classic CAN" if x == 0 else "CANFD", index=1, horizontal=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("⚡ 啟動連線", use_container_width=True, disabled=st.session_state.connected):
            toggle_connection(hw_choice)
            st.rerun()
    with col2:
        if st.button("🔌 斷開連線", use_container_width=True, disabled=not st.session_state.connected):
            toggle_connection(hw_choice)
            st.rerun()

    st.divider()
    if st.button("🚨 強制釋放硬體", type="secondary", use_container_width=True):
        force_release_hardware()

    if st.session_state.connected and st.session_state.hw_info_str:
        with st.expander("🗂️ 設備資訊", expanded=True):
            st.code(st.session_state.hw_info_str, language="text")
    st.divider()
    uploaded_dbc = st.file_uploader("載入 DBC", type=["dbc"], label_visibility="collapsed")
    if uploaded_dbc:
        content = uploaded_dbc.getvalue()
        for enc in ['utf-8', 'cp1252', 'gb2312']:
            try:
                st.session_state.db = cantools.database.load_string(content.decode(enc))
                st.success("DBC 已就緒"); break
            except: continue

# --- 主畫面 ---
status_dot = "dot-online" if st.session_state.connected else "dot-offline"
st.markdown(f'<div class="app-header"><div class="header-title">🚗 ZLG CAN 測試工具 <span style="font-size: 0.8rem; opacity: 0.7;">v1.5.2</span></div><div class="status-indicator"><span class="dot {status_dot}"></span>{"ONLINE" if st.session_state.connected else "OFFLINE"}</div></div>', unsafe_allow_html=True)

if st.session_state.db is None:
    st.warning("👋 請先載入 DBC 檔案。")
else:
    tab1, tab2 = st.tabs(["🎮 手動控制", "🚀 自動化測試"])
    msg_list = [m.name for m in st.session_state.db.messages]
    with tab1:
        sel_msg = st.selectbox("選擇報文", msg_list)
        msg_obj = st.session_state.db.get_message_by_name(sel_msg)
        input_sigs = {}
        with st.container(border=True):
            for sig in msg_obj.signals:
                is_int = (not sig.is_float) and (sig.scale == 1)
                s_min = int(safe_float(sig.minimum, 0)) if is_int else float(safe_float(sig.minimum, 0.0))
                s_max = int(safe_float(sig.maximum, 100)) if is_int else float(safe_float(sig.maximum, 100.0))
                s_init = max(min(safe_float(sig.initial, s_min), s_max), s_min)
                input_sigs[sig.name] = st.slider(f"{sig.name} ({sig.unit or '-'})", s_min, s_max, int(s_init) if is_int else s_init, step=1 if is_int else None)
        if st.button("🚀 發送數據", use_container_width=True, disabled=not st.session_state.connected):
            try:
                encoded = msg_obj.encode(input_sigs)
                send_can_message(msg_obj.frame_id, encoded)
            except Exception as e: st.error(f"編碼失敗: {e}")
    with tab2:
        st.subheader("🚀 訊號掃掠測試")
        c1, c2 = st.columns(2)
        with c1: t_msg = st.selectbox("目標報文", msg_list, key="a_m")
        with c2: t_sig = st.selectbox("目標訊號", [s.name for s in st.session_state.db.get_message_by_name(t_msg).signals])
        t_obj = st.session_state.db.get_message_by_name(t_msg).get_signal_by_name(t_sig)
        c_p1, c_p2, c_p3, c_p4 = st.columns(4)
        start_v = c_p1.number_input("起始", value=float(safe_float(t_obj.minimum, 0)))
        end_v = c_p2.number_input("結束", value=float(safe_float(t_obj.maximum, 100)))
        step_v = c_p3.number_input("步進", value=1.0)
        freq_v = c_p4.number_input("間隔(ms)", value=50)
        if not st.session_state.is_testing:
            if st.button("▶️ 啟動測試", use_container_width=True, type="primary"):
                st.session_state.is_testing = True; st.rerun()
        else:
            if st.button("⏹️ 停止測試", use_container_width=True):
                st.session_state.is_testing = False; st.rerun()
    with st.expander("📊 傳輸紀錄", expanded=False):
        if st.session_state.log_data:
            st.dataframe(pd.DataFrame(st.session_state.log_data), use_container_width=True, hide_index=True)
            if st.button("🗑️ 清空紀錄"): st.session_state.log_data = []; st.rerun()

# --- 狀態列 ---
st.markdown(f'<div class="status-bar"><span>📦 Version: v1.5.2 (canfd_start Alignment)</span><span style="margin-left: auto;">🕒 {datetime.now().strftime("%H:%M:%S")}</span></div>', unsafe_allow_html=True)