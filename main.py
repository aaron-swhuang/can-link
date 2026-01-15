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
    print(f"[警告] SDK 導入失敗: {e}")

import streamlit as st
import cantools
import pandas as pd

# --- 4. 日誌機制配置 (Debug Log 核心 - 永不刪除) ---
log_dir = os.path.join(current_dir, "log")
if not os.path.exists(log_dir): os.makedirs(log_dir)
log_filename = datetime.now().strftime("%Y-%m-%d") + ".log"
log_filepath = os.path.join(log_dir, log_filename)
logger = logging.getLogger("ZLG_CAN_TOOL")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(log_filepath, encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
    logger.addHandler(fh)

def cleanup_resources():
    print("\n[系統] 偵測到程式退出，正在釋放 ZLG 硬體資源...")
atexit.register(cleanup_resources)

# --- 5. 頁面配置與樣式 (進一步縮小字體級距) ---
st.set_page_config(page_title="ZLG CAN 測試工具", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
    /* 全域字體大小再次調降一級 (0.8rem) */
    html, body, [class*="css"] { font-size: 0.8rem !important; }
    .stDeployButton, [data-testid="stAppDeployButton"] { display: none !important; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    /* 微調頂部間距確保 Rerun Bar 與 Header 比例協調 */
    .block-container { padding-top: 3.1rem !important; }
    .app-header { background: linear-gradient(90deg, #1e293b 0%, #334155 100%); padding: 6px 15px; border-radius: 5px; color: white; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid #3b82f6; }
    .status-indicator { display: flex; align-items: center; gap: 5px; font-size: 0.7rem; }
    .dot { height: 7px; width: 7px; border-radius: 50%; display: inline-block; }
    .dot-online { background-color: #4ade80; box-shadow: 0 0 5px #4ade80; animation: blink 2s infinite; }
    .dot-offline { background-color: #94a3b8; }
    @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
    .section-title { font-size: 0.8rem; font-weight: 600; color: #475569; margin-bottom: 5px; padding-left: 5px; border-left: 4px solid #3b82f6; }
    .status-bar { position: fixed; bottom: 0; left: 0; width: 100%; height: 20px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; z-index: 9999; display: flex; align-items: center; padding: 0 20px; font-size: 0.6rem; color: #64748b; }
    /* 極致壓縮表單元件間距 */
    .stSelectbox, .stNumberInput, .stSlider { margin-bottom: -12px !important; }
    [data-testid="stExpander"] { margin-bottom: 5px !important; }
</style>
""", unsafe_allow_html=True)

# --- 6. 硬體與輔助功能 ---
@st.cache_resource
def get_zcan_instance():
    if not ZLG_SDK_AVAILABLE: return None
    logger.info("正在建立 ZCAN 類別實例...")
    with zlg_env(): return ZCAN()

def safe_float(val, default=0.0):
    if val is None: return float(default)
    try: return float(val.value) if hasattr(val, 'value') else float(val)
    except: return float(default)

# --- 7. 初始化 Session State ---
if 'connected' not in st.session_state: st.session_state.connected = False
if 'log_data' not in st.session_state: st.session_state.log_data = []
if 'db' not in st.session_state: st.session_state.db = None
if 'added_messages' not in st.session_state: st.session_state.added_messages = []
if 'focused_msg_idx' not in st.session_state: st.session_state.focused_msg_idx = None
if 'sig_values' not in st.session_state: st.session_state.sig_values = {}
if 'is_monitoring' not in st.session_state: st.session_state.is_monitoring = False
if 'd_handle' not in st.session_state: st.session_state.d_handle = None
if 'c_handle' not in st.session_state: st.session_state.c_handle = None
if 'can_type' not in st.session_state: st.session_state.can_type = 1
if 'hw_info_str' not in st.session_state: st.session_state.hw_info_str = ""

def toggle_connection(hw_type_name):
    """連線/斷開邏輯，包含詳細 Debug Log"""
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
                        logger.error("OpenDevice 失敗：回傳 INVALID_DEVICE_HANDLE")
                        st.error("❌ 開啟失敗：設備可能被佔用或未插入"); return
                    logger.info(f"OpenDevice 成功, Device Handle: {temp_handle}")
                    if st.session_state.can_type == 1 and CANFD_START_FUNC:
                        logger.info("執行 CANFD 啟動流程...")
                        chn_handle = CANFD_START_FUNC(zcanlib, temp_handle, 0)
                        if chn_handle == 0:
                            logger.error("canfd_start 失敗")
                            raise Exception("canfd_start 失敗")
                        st.session_state.c_handle = chn_handle
                    else:
                        logger.info("執行傳統 CAN 啟動流程...")
                        config = ZCAN_CHANNEL_INIT_CONFIG()
                        config.can_type = 0
                        chn_handle = zcanlib.InitCAN(temp_handle, 0, config)
                        if chn_handle == 0 or zcanlib.StartCAN(chn_handle) != 1:
                            raise Exception("啟動失敗")
                        st.session_state.c_handle = chn_handle
                    try:
                        info = zcanlib.GetDeviceInf(temp_handle)
                        st.session_state.hw_info_str = str(info)
                        logger.info(f"設備資訊獲取成功: {info}")
                    except:
                        st.session_state.hw_info_str = "資訊讀取失敗"
                    st.session_state.d_handle = temp_handle
                    st.session_state.connected = True
                    st.toast("✅ 連線成功")
                    print(f"連線成功: Device={temp_handle}")
            except Exception as e:
                logger.error(f"連線異常: {e}")
                logger.error(traceback.format_exc())
                st.error(f"連線失敗: {e}")
                if temp_handle != INVALID_DEVICE_HANDLE:
                    with zlg_env(): zcanlib.CloseDevice(temp_handle)
    else:
        if st.session_state.d_handle:
            logger.info(f"正在關閉設備 Handle: {st.session_state.d_handle}")
            with zlg_env(): get_zcan_instance().CloseDevice(st.session_state.d_handle)
        st.session_state.connected, st.session_state.d_handle, st.session_state.c_handle = False, None, None
        st.session_state.is_monitoring = False
        st.toast("🔌 已中斷連線")

def send_can_message(msg_id, data, silent=False):
    success = True
    status_code = "1"
    if st.session_state.connected and st.session_state.c_handle and ZLG_SDK_AVAILABLE:
        try:
            zcanlib = get_zcan_instance()
            with zlg_env():
                if st.session_state.can_type == 1:
                    t_data = ZCAN_TransmitFD_Data()
                    t_data.frame.can_id, t_data.frame.len = msg_id, len(data)
                    t_data.frame.eff, t_data.frame.fdf, t_data.frame.brs = (1 if msg_id > 0x7FF else 0), 1, 1
                    for i, b in enumerate(data): t_data.frame.data[i] = b
                    ret = zcanlib.TransmitFD(st.session_state.c_handle, t_data, 1)
                else:
                    t_data = ZCAN_Transmit_Data()
                    t_data.frame.can_id, t_data.frame.can_dlc = msg_id, len(data)
                    t_data.frame.eff = 1 if msg_id > 0x7FF else 0
                    for i, b in enumerate(data): t_data.frame.data[i] = b
                    ret = zcanlib.Transmit(st.session_state.c_handle, t_data, 1)
                if ret != 1:
                    success, status_code = False, f"Err:{ret}"
                    logger.error(f"TX 失敗 ID: {hex(msg_id)}, SDK: {ret}")
        except Exception as e:
            success, status_code = False, "EXCP"
            logger.error(f"TX 發生異常: {e}")
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

# --- 8. UI 渲染流程 ---
with st.sidebar:
    st.subheader("🛠️ 硬體設定")
    hw_choice = st.selectbox("設備型號", ["USBCANFD_200U", "USBCANFD_100U"])
    st.session_state.can_type = st.radio("模式", [0, 1], format_func=lambda x: "CAN" if x == 0 else "CANFD", index=1, horizontal=True)
    conn_btn_label = "🔌 斷開連線" if st.session_state.connected else "⚡ 啟動硬體連線"
    if st.button(conn_btn_label, use_container_width=True, type="primary" if st.session_state.connected else "secondary"):
        toggle_connection(hw_choice); st.rerun()
    st.divider()
    if not st.session_state.connected:
        st.button("🗂️ 設備詳情 (請先連線)", use_container_width=True, disabled=True)
    else:
        with st.expander("🗂️ 設備資訊詳情", expanded=False):
            st.code(st.session_state.hw_info_str if st.session_state.hw_info_str else "正在讀取...", language="text")
    st.divider()
    st.session_state.is_monitoring = st.toggle("📡 監控模式", value=st.session_state.is_monitoring, disabled=not st.session_state.connected)
    uploaded_dbc = st.file_uploader("載入 DBC", type=["dbc"], label_visibility="collapsed")
    if uploaded_dbc:
        try:
            st.session_state.db = cantools.database.load_string(uploaded_dbc.getvalue().decode('utf-8'))
            st.success("DBC 載入成功"); logger.info("使用者載入了新的 DBC 檔案")
        except Exception as e:
            st.error("解析失敗"); logger.error(f"DBC 解析失敗: {e}")

# 主畫面標頭
status_dot = "dot-online" if st.session_state.connected else "dot-offline"
st.markdown(f'<div class="app-header"><div>🚗 ZLG CAN 測試工具 v1.8.1</div><div class="status-indicator"><span class="dot {status_dot}"></span>{"ONLINE" if st.session_state.connected else "OFFLINE"}</div></div>', unsafe_allow_html=True)

if st.session_state.db is None:
    st.warning("👋 請先從側邊欄載入 DBC 檔案。")
else:
    # --- 1. 頂層發送按鈕區 ---
    main_cols = st.columns([3, 1])
    with main_cols[0]:
        st.markdown('<p class="section-title">報文與發送控制</p>', unsafe_allow_html=True)
    with main_cols[1]:
        btn_label = "🚀 發送報文"
        if st.session_state.focused_msg_idx is not None:
            m_name = st.session_state.added_messages[st.session_state.focused_msg_idx]
            m_obj = st.session_state.db.get_message_by_name(m_name)
            btn_label = f"🚀 發送 [0x{m_obj.frame_id:03X}]"
        if st.button(btn_label, use_container_width=True, type="primary", disabled=not st.session_state.connected or st.session_state.focused_msg_idx is None):
            current_payload = st.session_state.sig_values.get(m_name, {})
            try:
                full_sigs = {s.name: safe_float(s.initial, safe_float(s.minimum, 0.0)) for s in m_obj.signals}
                full_sigs.update(current_payload)
                send_can_message(m_obj.frame_id, m_obj.encode(full_sigs))
            except Exception as e:
                st.error(f"發送失敗: {e}"); logger.error(f"發送編碼異常: {e}")

    # --- 2. 報文添加與列表區 ---
    item_cols = st.columns([3, 1, 2])
    with item_cols[0]:
        all_msgs_map = {f"{m.name} [0x{m.frame_id:03X}] ({m.frame_id})": m.name for m in st.session_state.db.messages}
        target_display_to_add = st.selectbox("選取報文 (ID)", list(all_msgs_map.keys()), label_visibility="collapsed")
        target_name_to_add = all_msgs_map[target_display_to_add]
    with item_cols[1]:
        if st.button("➕ 添加到清單", use_container_width=True):
            if target_name_to_add not in st.session_state.added_messages:
                st.session_state.added_messages.append(target_name_to_add); st.rerun()
    with st.container(border=True):
        if not st.session_state.added_messages:
            st.info("清單為空，請從上方選取報文。")
        else:
            list_cols = st.columns(len(st.session_state.added_messages) + 1)
            for idx, msg_name in enumerate(st.session_state.added_messages):
                is_active = (st.session_state.focused_msg_idx == idx)
                m_obj_tmp = st.session_state.db.get_message_by_name(msg_name)
                btn_display = f"{msg_name} [0x{m_obj_tmp.frame_id:03X}]"
                if list_cols[idx].button(btn_display, use_container_width=True, type="primary" if is_active else "secondary"):
                    st.session_state.focused_msg_idx = idx; st.rerun()
            if list_cols[-1].button("🗑️", help="清空"):
                st.session_state.added_messages, st.session_state.focused_msg_idx = [], None; st.rerun()

    st.divider()

    # --- 3. 詳細訊號控制區 ---
    if st.session_state.focused_msg_idx is not None:
        focused_name = st.session_state.added_messages[st.session_state.focused_msg_idx]
        focused_obj = st.session_state.db.get_message_by_name(focused_name)
        st.markdown(f'<p class="section-title">詳細訊號控制: {focused_name} [0x{focused_obj.frame_id:03X}] ({focused_obj.frame_id})</p>', unsafe_allow_html=True)
        if focused_name not in st.session_state.sig_values:
            st.session_state.sig_values[focused_name] = {s.name: safe_float(s.initial, safe_float(s.minimum, 0.0)) for s in focused_obj.signals}

        def sync_signal_value(source_key, msg_name, sig_name):
            if source_key in st.session_state:
                st.session_state.sig_values[msg_name][sig_name] = st.session_state[source_key]

        col_ratios = [0.5, 2, 3, 1, 2.5, 0.5]
        h_cols = st.columns(col_ratios)
        h_cols[0].caption("No.")
        h_cols[1].caption("訊號名稱")
        h_cols[2].caption("滑桿調節")
        h_cols[3].caption("數值輸入")
        h_cols[4].caption("列舉選擇")
        h_cols[5].caption("註釋")

        with st.container(height=500):
            for i, sig in enumerate(focused_obj.signals, 1):
                row_cols = st.columns(col_ratios)
                row_cols[0].markdown(f"<p style='text-align:center; color:#94a3b8; padding-top:5px;'>{i}</p>", unsafe_allow_html=True)
                row_cols[1].markdown(f"**{sig.name}**")
                cur_val = st.session_state.sig_values[focused_name].get(sig.name, 0.0)
                s_min, s_max = float(safe_float(sig.minimum, 0)), float(safe_float(sig.maximum, 100))
                k_sld, k_num, k_sel = f"sld_{focused_name}_{sig.name}", f"num_{focused_name}_{sig.name}", f"sel_{focused_name}_{sig.name}"
                row_cols[2].slider(f"S_{sig.name}", s_min, s_max, float(cur_val), label_visibility="collapsed", key=k_sld, on_change=sync_signal_value, args=(k_sld, focused_name, sig.name))
                row_cols[3].number_input(f"I_{sig.name}", s_min, s_max, float(cur_val), label_visibility="collapsed", key=k_num, on_change=sync_signal_value, args=(k_num, focused_name, sig.name))
                if sig.choices:
                    choice_labels = {v: f"{v}: {str(k)}" for v, k in sig.choices.items()}
                    sorted_vals = sorted(choice_labels.keys())
                    try: current_idx = sorted_vals.index(int(cur_val))
                    except: current_idx = 0
                    row_cols[4].selectbox(f"C_{sig.name}", sorted_vals, index=current_idx, format_func=lambda x: choice_labels.get(x, str(x)), label_visibility="collapsed", key=k_sel, on_change=sync_signal_value, args=(k_sel, focused_name, sig.name))
                else:
                    row_cols[4].selectbox(f"NA_{sig.name}", ["-"], disabled=True, label_visibility="collapsed", key=f"na_{focused_name}_{sig.name}")
                if sig.comment:
                    with row_cols[5].popover("ℹ️", use_container_width=True):
                        st.markdown("**訊號說明：**")
                        st.write(sig.comment)
                else:
                    row_cols[5].markdown('<p style="text-align:center; color:#cbd5e1;">-</p>', unsafe_allow_html=True)

    st.divider()
    with st.expander("📊 匯流排監控日誌", expanded=True):
        log_placeholder = st.empty()
        if st.button("🗑️ 清空日誌", use_container_width=True):
            st.session_state.log_data = []; st.rerun()

# --- 9. 監控與刷新 ---
if st.session_state.is_monitoring:
    poll_reception()
    log_placeholder.dataframe(pd.DataFrame(st.session_state.log_data), use_container_width=True, hide_index=True, height=300)
    time.sleep(0.1); st.rerun()
else:
    if st.session_state.log_data:
        log_placeholder.dataframe(pd.DataFrame(st.session_state.log_data), use_container_width=True, hide_index=True, height=300)

st.markdown(f'<div class="status-bar"><span>📦 Version: v1.8.1 (Ultra Compact)</span><span style="margin-left:auto;">📂 Log: {log_filename}</span></div>', unsafe_allow_html=True)