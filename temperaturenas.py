import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import io
import re
from PIL import Image
import paramiko
import requests
import time
import subprocess

st.header("NAS System Dashboard", divider="rainbow")

base = "http://192.168.11.228:5000/webapi"
wifi = st.secrets["secrets"]["wifiname"]
wifipassword=st.secrets["secrets"]["wifipasswd"]

def connect_to_wifi(wifi, wifipassword):
    command = f'netsh wlan connect name ="{wifi}" ssid="{wifi}"keymaterial="{wifipassword}"'
    try:
        output = subprocess.run(command,capture_output=True,shell=True,text=True)
        if "Connection request was commpleted successfully" in output.stdout:
            print(f"connected successfully to {wifi}")
        else:
            print(f"Failed to connect.Error:{output.stdout.strip()}")
    except Exception as e:
        print(f"An error occred: {e}")
connect_to_wifi(f"{wifi}",f"{wifipassword}")


@st.cache_data(ttl=30)
def get_sid():
    try:
        login = requests.get(f"{base}/auth.cgi", params={
                "api":"SYNO.API.Auth",
                "version": 6,
                "method": "login",
                "account": st.secrets["secrets"]["DB_USERNAME"],
                "passwd": st.secrets["secrets"]["DB_PASSWORD"],
                "session": "FileStation",
                "format" : "sid"
            }, timeout=10)
    except requests.exceptions.ConnectionError:
        st.error("Could not connect to the NAS. Check that QuickConnect is enabled and your QuickConnect ID is correct.")
        return None
    except requests.exceptions.Timeout:
        st.error("Connection timed out. The NAS may be offline or unreachable.")
        return None

    if login.status_code != 200:
        st.error(f"Server returned HTTP {login.status_code}. Response: {login.text[:300]}")
        return None

    if not login.text.strip():
        st.error("Server returned an empty response. QuickConnect may not be reaching your NAS — check that it's online and QuickConnect is enabled in DSM.")
        return None

    try:
        data = login.json()
    except requests.exceptions.JSONDecodeError:
        st.error(f"Server returned non-JSON response. Raw response: {login.text[:300]}")
        return None

    if not data.get("success"):
        st.error(f"Login failed: {data.get('error')}")
        return None
    return data["data"]["sid"]
def get_system_info(sid):
    resp = requests.get(f"{base}/entry.cgi", params={
        "api": "SYNO.Core.System",
        "version": 1,
        "method": "info",
        "_sid": sid
    })
    return resp.json()
def get_storage_info(sid):
    resp = requests.get(f"{base}/entry.cgi", params= {
        "api": "SYNO.Storage.CGI.Storage",
        "version": 1,
        "method":"load_info",
        "_sid": sid
        })
    return resp.json()
def get_utilization(sid):
    resp = requests.get(f"{base}/entry.cgi", params={
        "api":"SYNO.Core.System.Utilization",
        "version": 1,
        "method":"get",
        "_sid":sid
    })
    return resp.json()

sid = get_sid()

if sid:
    sys_info=get_system_info(sid)
    storage_info= get_storage_info(sid)
    util_info = get_utilization(sid)
    if sys_info.get("success"):
        data = sys_info["data"]
        col1,col2,col3 = st.columns(3)
        col1.metric("Models",data.get("model","N/A"))
        col2.metric("CPU_Temp",f"{data.get("sys_temp","N/A")}°C")
        col3.metric("System Status",data.get("sys_status","N/A"))

        with st.expander("Full system info(raw)"):
            st.json(data)
    else:
        st.error(f"System info failed:{sys_info.get('error')}")
    
    if util_info.get("success"):
        util = util_info["data"]
        st.subheader("CPU and Memory")
        col1,col2,col3 = st.columns(3)
        if "cpu" in util:
            col1.metric("CPU usage", f"{util['cpu'].get('user_load', 'N/A')}%")
        if "memory" in util:
            col2.metric("Memory Usage", f"{util['memory'].get('real_usage', 'N/A')}%")

        with st.expander("Full utilization info (raw)"):
            st.json(util)
        
    else:
        st.warning(f"Utilization info failed: {util_info.get('error')}")
    if storage_info.get("success"):
        st.subheader("Storage Volumes")

        def bytes_to_human(b):
            try:
                b = int(b)
            except (TypeError, ValueError):
                return "N/A"
            if b >= 1_099_511_627_776:  # 1 TB
                return f"{b / 1_099_511_627_776:.2f} TB"
            elif b >= 1_073_741_824:  # 1 GB
                return f"{b / 1_073_741_824:.2f} GB"
            elif b >= 1_048_576:  # 1 MB
                return f"{b / 1_048_576:.2f} MB"
            return f"{b} B"

        volumes = storage_info["data"].get("volumes", [])
        if not volumes:
            st.warning("No volumes found in storage info.")
        else:
            for vol in volumes:
                vol_id = vol.get("id") or vol.get("volume_path") or "Unknown Volume"
                status = vol.get("status", "N/A")

                # Synology DSM uses 'size' dict OR top-level used_size/total_size
                size_block = vol.get("size", {})
                used  = vol.get("used_size")  or size_block.get("used")
                total = vol.get("total_size") or size_block.get("total")
                free  = vol.get("free_size")  or size_block.get("avail")

                st.write(f"**{vol_id}** — Status: `{status}`")

                col1, col2, col3 = st.columns(3)
                col1.metric("Total", bytes_to_human(total))
                col2.metric("Used",  bytes_to_human(used))
                col3.metric("Free",  bytes_to_human((int(total) - int(used)) if total and used else free))

                if used and total:
                    try:
                        pct = round(int(used) / int(total) * 100, 1)
                        st.progress(pct / 100, text=f"{pct}% used")
                    except (ValueError, ZeroDivisionError):
                        pass

                st.divider()

        with st.expander("Full storage info (raw)"):
            st.json(storage_info["data"])
    else:
        st.error(f"Storage info failed: {storage_info.get('error')}")
else:
    st.stop()

time.sleep(30)
st.rerun()



