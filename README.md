# **ZLG CAN 測試工具 (Streamlit Edition)**

這是一款基於 Streamlit 開發的專業 CAN/CANFD 測試工具，專為 ZLG USBCANFD-200U/100U 硬體設計。支援 DBC 載入、即時監控、訊號動態調節以及高精度的週期性發送。

## **🚀 核心功能**

* **智慧型型別偵測**：自動識別 DBC 訊號為整數或浮點數，動態調整滑桿精度。  
* **異步週期發送**：獨立的發送引擎，支援 10ms \- 5000ms 週期，且不影響 UI 操作流暢度。  
* **高密度 UI**：v1.9.x 採用 0.8rem 極致緊湊佈局，適合單螢幕查看大量訊號。  
* **日誌管理**：自動清理機制（上限 9999 條），確保長時間測試不卡頓。

## **🛠️ 環境準備**

### **1\. 軟體需求**

* Python 3.9 或更高版本  
* ZLG SDK 驅動程式（必須安裝官方提供的硬體驅動）

### **2\. 資料夾結構**

請確保專案根目錄下存在 zlg 資料夾，並包含以下對應平台的 SDK 檔案：

* **Windows**: zlgcan.dll, usbcanfd.dll 等相關依賴。  
* **Linux**: libzlgcan.so 相關函式庫。

## **💻 部署方式**

### **方案一：本地環境 (Windows / Linux)**

最適合開發與即時硬體偵錯的模式。

1. **複製專案**  
   git clone \[https://github.com/aaron-swhuang/can-link.git\](https://github.com/aaron-swhuang/can-link.git)  
   cd can-link

2. **建立虛擬環境**  
   python \-m venv venv  
   \# Windows 啟動:  
   .\\venv\\Scripts\\activate  
   \# Linux 啟動:  
   source venv/bin/activate

3. **安裝依賴**  
   pip install \-r streamlit cantools pandas

4. **啟動程式**  
   streamlit run main.py

### **方案二：Docker 容器化部署**

適合測試環境一致化，或是在具備 USB 穿透功能的 Linux 伺服器上運行。

1. **建立 Docker 映像檔**  
   docker build \-t can-link-app .

2. **啟動容器 (需掛載 USB 設備)**  
   \# Linux 下建議使用 \--privileged 以存取硬體  
   docker run \-d \-p 8501:8501 \--privileged \-v /dev/bus/usb:/dev/bus/usb can-link-app

## **📂 SDK 檔案說明 (zlg 資料夾)**

為了讓 Python 成功調用 SDK，請根據作業系統放置以下檔案於 ./zlg/ 內：

| 平台 | 必備檔案 | 說明 |
| :---- | :---- | :---- |
| **Windows** | zlgcan.py, zlgcan.dll, Kernel.dll | 需確保 Python 位元數 (64-bit) 與 DLL 一致 |
| **Linux** | zlgcan.py, libzlgcan.so | 需配置 LD\_LIBRARY\_PATH 或放在 /usr/lib |
