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
import streamlit as st
import cantools
import pandas as pd

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
        ZCAN_TYPE_CAN, ZCAN_TYPE_CANFD = 0, 1
        ZCAN_USBCANFD_200U, ZCAN_USBCANFD_100U = 41, 42
        ZLG_SDK_AVAILABLE = True
except Exception as e:
    print(f"[警告] SDK 導入失敗: {e}")

# --- 4. 日誌機制配置 (重要：保留 Logger) ---
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
    logger.info("系統正在釋放 ZLG 硬體資源...")
    print("\n[系統] 正在釋放 ZLG 硬體資源...")
atexit.register(cleanup_resources)

# --- 5. 頁面配置與樣式 ---
st.set_page_config(page_title="ZLG CAN 測試工具", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
    html, body, [class*="css"] { font-size: 0.8rem !important; }
    .stDeployButton, [data-testid="stAppDeployButton"] { display: none !important; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container { padding-top: 3.1rem !important; }
    .app-header { background: linear-gradient(90deg, #1e293b 0%, #334155 100%); padding: 6px 15px; border-radius: 5px; color: white; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid #3b82f6; }
    .status-indicator { display: flex; align-items: center; gap: 5px; font-size: 0.7rem; }
    .dot { height: 7px; width: 7px; border-radius: 50%; display: inline-block; }
    .dot-online { background-color: #4ade80; box-shadow: 0 0 5px #4ade80; animation: blink 2s infinite; }
    .dot-active { background-color: #f59e0b; box-shadow: 0 0 8px #f59e0b; animation: blink 0.5s infinite; }
    .dot-offline { background-color: #94a3b8; }
    @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
    .section-title { font-size: 0.8rem; font-weight: 600; color: #475569; margin-bottom: 5px; padding-left: 5px; border-left: 4px solid #3b82f6; }
    .status-bar { position: fixed; bottom: 0; left: 0; width: 100%; height: 20px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; z-index: 9999; display: flex; align-items: center; padding: 0 20px; font-size: 0.6rem; color: #64748b; }
    .stSelectbox, .stNumberInput { margin-bottom: -12px !important; transition: opacity 0.2s; }
</style>
""", unsafe_allow_html=True)

# --- 6. 輔助功能 ---
@st.cache_resource
def get_zcan_instance():
    if not ZLG_SDK_AVAILABLE: return None
    logger.info("建立 ZCAN SDK 實例...")
    with zlg_env(): return ZCAN()

def safe_float(val, default=0.0):
    if val is None: return float(default)
    try: return float(val.value) if hasattr(val, 'value') else float(val)
    except: return float(default)

# --- 7. 初始化 Session State ---
default_states = {
    'connected': False, 'log_data': [], 'db': None, 'last_dbc_hash': None,
    'added_messages': [], 'focused_msg_idx': None, 'sig_values': {}, 'sig_meta': {},
    'is_monitoring': False, 'is_cyclic': False, 'cycle_ms': 100,
    'd_handle': None, 'c_handle': None, 'can_type': 1, 'hw_info_str': ""
}
for k, v in default_states.items():
    if k not in st.session_state: st.session_state[k] = v

def toggle_connection(hw_type_name):
    if not st.session_state.connected:
        if ZLG_SDK_AVAILABLE:
            temp_handle = INVALID_DEVICE_HANDLE
            try:
                zcanlib = get_zcan_instance()
                dev_type = ZCAN_USBCANFD_200U if "200U" in hw_type_name else ZCAN_USBCANFD_100U
                with zlg_env():
                    logger.info(f"啟動硬體連線 (Type: {dev_type})...")
                    temp_handle = zcanlib.OpenDevice(dev_type, 0, 0)
                    if temp_handle == INVALID_DEVICE_HANDLE:
                        logger.error("OpenDevice 失敗"); st.error("❌ 設備可能被佔用"); return
                    if st.session_state.can_type == 1 and CANFD_START_FUNC:
                        chn_handle = CANFD_START_FUNC(zcanlib, temp_handle, 0)
                        if chn_handle == 0: raise Exception("canfd_start 失敗")
                        st.session_state.c_handle = chn_handle
                    else:
                        config = ZCAN_CHANNEL_INIT_CONFIG()
                        config.can_type = 0
                        chn_handle = zcanlib.InitCAN(temp_handle, 0, config)
                        if chn_handle == 0 or zcanlib.StartCAN(chn_handle) != 1: raise Exception("啟動失敗")
                        st.session_state.c_handle = chn_handle
                    try:
                        st.session_state.hw_info_str = str(zcanlib.GetDeviceInf(temp_handle))
                    except: st.session_state.hw_info_str = "資訊讀取失敗"
                    st.session_state.d_handle, st.session_state.connected = temp_handle, True
                    st.toast("✅ 連線成功")
            except Exception as e:
                logger.error(f"連線異常: {e}"); st.error(f"連線失敗: {e}")
                if temp_handle != INVALID_DEVICE_HANDLE:
                    with zlg_env(): zcanlib.CloseDevice(temp_handle)
    else:
        if st.session_state.d_handle:
            with zlg_env(): get_zcan_instance().CloseDevice(st.session_state.d_handle)
        st.session_state.connected, st.session_state.d_handle, st.session_state.c_handle = False, None, None
        st.session_state.is_monitoring = st.session_state.is_cyclic = False; st.toast("🔌 已中斷連線")

def send_can_message(msg_id, data):
    success, status_code = True, "1"
    if st.session_state.connected and st.session_state.c_handle is not None and ZLG_SDK_AVAILABLE:
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
                if ret != 1: success, status_code = False, f"Err:{ret}"
        except Exception as e:
            logger.error(f"發送異常 ID {hex(msg_id)}: {e}")
            success, status_code = False, "EXCP"
    else: success, status_code = False, "OFFLINE"
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    hex_data = " ".join(f"{b:02X}" for b in data)
    st.session_state.log_data.insert(0, {"方向": "TX", "時間": timestamp, "ID": hex(msg_id).upper(), "數據": hex_data, "狀態": "OK" if success else status_code})
    if len(st.session_state.log_data) > 9999: st.session_state.log_data = st.session_state.log_data[:9999]
    return success

def poll_reception():
    if not st.session_state.connected or st.session_state.c_handle is None: return
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
                    hex_data = " ".join(f"{msgs[i].frame.data[j]:02X}" for j in range(msgs[i].frame.data_dlc))
                    st.session_state.log_data.insert(0, {"方向": "RX", "時間": datetime.now().strftime("%H:%M:%S.%f")[:-3], "ID": hex(msgs[i].frame.can_id).upper(), "數據": hex_data, "狀態": "OK"})
            if len(st.session_state.log_data) > 9999: st.session_state.log_data = st.session_state.log_data[:9999]

# --- 8. UI 渲染 ---
with st.sidebar:
    st.subheader("🛠️ 硬體設定")
    hw_choice = st.selectbox("設備型號", ["USBCANFD_200U", "USBCANFD_100U"])
    st.session_state.can_type = st.radio("模式", [0, 1], format_func=lambda x: "CAN" if x == 0 else "CANFD", index=1, horizontal=True)
    conn_btn_label = "🔌 斷開連線" if st.session_state.connected else "⚡ 啟動硬體連線"
    if st.button(conn_btn_label, use_container_width=True, type="primary" if st.session_state.connected else "secondary"):
        toggle_connection(hw_choice); st.rerun()
    st.divider()
    if st.session_state.connected:
        with st.expander("🗂️ 設備資訊詳情"):
            st.code(st.session_state.hw_info_str or "正在讀取...", language="text")
    st.divider()
    st.session_state.is_monitoring = st.toggle("📡 匯流排監控", value=st.session_state.is_monitoring, disabled=not st.session_state.connected)
    uploaded_dbc = st.file_uploader("載入 DBC", type=["dbc"], label_visibility="collapsed")
    if uploaded_dbc:
        file_bytes = uploaded_dbc.getvalue()
        file_hash = binascii.crc32(file_bytes)
        if st.session_state.last_dbc_hash != file_hash:
            try:
                st.session_state.db = cantools.database.load_string(file_bytes.decode('utf-8'))
                st.session_state.last_dbc_hash, st.session_state.sig_meta = file_hash, {}
                st.success("DBC 載入成功"); logger.info("DBC 檔案載入成功")
            except Exception as e:
                logger.error(f"DBC 解析失敗: {e}")
                st.error("解析失敗")

# 主畫面標頭
status_dot = "dot-active" if st.session_state.is_cyclic else ("dot-online" if st.session_state.connected else "dot-offline")
status_text = ("CYCLIC SENDING" if st.session_state.is_cyclic else "ONLINE") if st.session_state.connected else "OFFLINE"
st.markdown(f'<div class="app-header"><div>🚗 ZLG CAN 測試工具 v1.9.5</div><div class="status-indicator"><span class="dot {status_dot}"></span>{status_text}</div></div>', unsafe_allow_html=True)

if st.session_state.db is None:
    st.warning("👋 請先從側邊欄載入 DBC 檔案。")
else:
    # --- 1. 發送控制區 ---
    main_cols = st.columns([2, 1, 1, 1])
    main_cols[0].markdown('<p class="section-title">報文與發送控制</p>', unsafe_allow_html=True)
    m_name, m_obj = None, None
    if st.session_state.focused_msg_idx is not None:
        m_name = st.session_state.added_messages[st.session_state.focused_msg_idx]
        m_obj = st.session_state.db.get_message_by_name(m_name)
    if st.session_state.is_cyclic:
        if main_cols[1].button("🛑 停止發送", use_container_width=True, type="primary"):
            st.session_state.is_cyclic = False; st.rerun()
    else:
        if main_cols[1].button(f"🚀 單次發送" if not m_obj else f"🚀 [0x{m_obj.frame_id:03X}]", use_container_width=True, type="primary", disabled=not st.session_state.connected or m_obj is None):
            current_payload = st.session_state.sig_values.get(m_name, {})
            try:
                full_sigs = {s.name: safe_float(s.initial, safe_float(s.minimum, 0.0)) for s in m_obj.signals}
                full_sigs.update(current_payload); send_can_message(m_obj.frame_id, m_obj.encode(full_sigs))
            except Exception as e: st.error(f"發送失敗: {e}")
    st.session_state.is_cyclic = main_cols[2].toggle("🔁 週期模式", value=st.session_state.is_cyclic, disabled=not st.session_state.connected or m_obj is None)
    st.session_state.cycle_ms = main_cols[3].number_input("ms", 10, 5000, st.session_state.cycle_ms, 10, label_visibility="collapsed")

    # --- 2. 報文管理 ---
    item_cols = st.columns([3, 1, 2])
    all_msgs_map = {f"{m.name} [0x{m.frame_id:03X}] ({m.frame_id})": m.name for m in st.session_state.db.messages}
    target_display = item_cols[0].selectbox("選取報文", list(all_msgs_map.keys()), label_visibility="collapsed")
    if item_cols[1].button("➕ 添加", use_container_width=True):
        if all_msgs_map[target_display] not in st.session_state.added_messages:
            st.session_state.added_messages.append(all_msgs_map[target_display]); st.rerun()
    with st.container(border=True):
        if not st.session_state.added_messages:
            st.info("清單為空，請從上方選取報文。")
        else:
            list_cols = st.columns(len(st.session_state.added_messages) + 1)
            for idx, msg_name in enumerate(st.session_state.added_messages):
                m_obj_tmp = st.session_state.db.get_message_by_name(msg_name)
                if list_cols[idx].button(f"{msg_name} [0x{m_obj_tmp.frame_id:03X}]", use_container_width=True, type="primary" if st.session_state.focused_msg_idx == idx else "secondary"):
                    st.session_state.focused_msg_idx = idx; st.rerun()
            if list_cols[-1].button("🗑️"):
                st.session_state.added_messages, st.session_state.focused_msg_idx = [], None; st.rerun()
    st.divider()

    # --- 3. 週期發送引擎 ---
    @st.fragment(run_every=st.session_state.cycle_ms/1000.0 if st.session_state.is_cyclic else None)
    def render_cyclic_engine(m_name_local):
        if st.session_state.is_cyclic and m_name_local:
            m_obj_cyclic = st.session_state.db.get_message_by_name(m_name_local)
            payload = st.session_state.sig_values.get(m_name_local, {})
            try:
                full_sigs = {s.name: safe_float(s.initial, safe_float(s.minimum, 0.0)) for s in m_obj_cyclic.signals}
                full_sigs.update(payload)
                send_can_message(m_obj_cyclic.frame_id, m_obj_cyclic.encode(full_sigs))
            except: pass

    # --- 4. 訊號控制局部片段 ---
    @st.fragment
    def render_signal_console(focused_name):
        focused_obj = st.session_state.db.get_message_by_name(focused_name)
        st.markdown(f'<p class="section-title">詳細訊號控制: {focused_name} [0x{focused_obj.frame_id:03X}]</p>', unsafe_allow_html=True)
        if focused_name not in st.session_state.sig_values:
            st.session_state.sig_values[focused_name] = {s.name: safe_float(s.initial, safe_float(s.minimum, 0.0)) for s in focused_obj.signals}
        if focused_name not in st.session_state.sig_meta:
            st.session_state.sig_meta[focused_name] = {}
            for s in focused_obj.signals:
                is_int = (not s.is_float) and (s.scale == 1) and (float(s.offset).is_integer())
                min_v, max_v = safe_float(s.minimum, 0), safe_float(s.maximum, 100)
                st.session_state.sig_meta[focused_name][s.name] = {"is_int": is_int, "min": int(min_v) if is_int else float(min_v), "max": int(max_v) if is_int else float(max_v), "step": 1 if is_int else None}
        def sync_val(key, m_name, s_name):
            if key in st.session_state: st.session_state.sig_values[m_name][s_name] = st.session_state[key]
        col_ratios = [0.5, 3, 1.5, 3.5, 0.5]
        h_cols = st.columns(col_ratios)
        h_cols[0].caption("No."); h_cols[1].caption("訊號名稱"); h_cols[2].caption("數值輸入"); h_cols[3].caption("列舉選擇"); h_cols[4].caption("註釋")
        with st.container(height=450):
            for i, sig in enumerate(focused_obj.signals, 1):
                meta = st.session_state.sig_meta[focused_name][sig.name]
                row_cols = st.columns(col_ratios)
                row_cols[0].markdown(f"<p style='text-align:center; color:#94a3b8; padding-top:5px;'>{i}</p>", unsafe_allow_html=True)
                row_cols[1].markdown(f"**{sig.name}**")
                raw_val = st.session_state.sig_values[focused_name].get(sig.name, 0.0)
                cur_val = int(raw_val) if meta["is_int"] else float(raw_val)
                k_num, k_sel = f"num_{focused_name}_{sig.name}", f"sel_{focused_name}_{sig.name}"
                row_cols[2].number_input(f"I_{sig.name}", meta["min"], meta["max"], cur_val, step=meta["step"], label_visibility="collapsed", key=k_num, on_change=sync_val, args=(k_num, focused_name, sig.name))
                if sig.choices:
                    choice_labels = {v: f"{v}: {str(k)}" for v, k in sig.choices.items()}
                    sorted_vals = sorted(choice_labels.keys())
                    c_idx = sorted_vals.index(int(cur_val)) if int(cur_val) in sorted_vals else 0
                    row_cols[3].selectbox(f"C_{sig.name}", sorted_vals, index=c_idx, format_func=lambda x: choice_labels.get(x, str(x)), label_visibility="collapsed", key=k_sel, on_change=sync_val, args=(k_sel, focused_name, sig.name))
                else: row_cols[3].selectbox(f"NA_{sig.name}", ["-"], disabled=True, label_visibility="collapsed", key=f"na_{focused_name}_{sig.name}")
                if sig.comment:
                    with row_cols[4].popover("ℹ️", use_container_width=True): st.write(sig.comment)
                else: row_cols[4].markdown('<p style="text-align:center; color:#cbd5e1;">-</p>', unsafe_allow_html=True)

    if st.session_state.focused_msg_idx is not None:
        render_signal_console(m_name)
        render_cyclic_engine(m_name)

    # --- 5. 監控日誌 ---
    @st.fragment(run_every=0.3 if (st.session_state.is_monitoring or st.session_state.is_cyclic) else None)
    def render_monitor_log():
        if st.session_state.is_monitoring: poll_reception()
        with st.expander("📊 匯流排監控日誌", expanded=True):
            st.dataframe(pd.DataFrame(st.session_state.log_data), use_container_width=True, hide_index=True, height=250)
            if st.button("🗑️ 清空日誌", use_container_width=True):
                st.session_state.log_data = []; st.rerun()
    render_monitor_log()

st.markdown(f'<div class="status-bar"><span>📦 Version: v1.9.5 (Optimized)</span><span style="margin-left:auto;">📂 Log: {log_filename}</span></div>', unsafe_allow_html=True)