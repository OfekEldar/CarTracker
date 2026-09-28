import json
import time
import pandas as pd
import paho.mqtt.client as mqtt
import streamlit as st

# ================= Page Config =================
st.set_page_config(
    page_title="Triton Tracker & Control",
    page_icon="🚗",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ================= Default Parking Location =================
DEFAULT_PARKING_LAT = 32.085300  
DEFAULT_PARKING_LON = 34.781800  

# ================= Security & Login =================
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🔒 Enter Password to access tracker:", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("🔒 Enter Password to access tracker:", type="password", on_change=password_entered, key="password")
        st.error("❌ Incorrect Password")
        return False
    return True

if not check_password():
    st.stop()

# ================= System & MQTT Settings =================
MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 1883
CMD_TOPIC = "ofek/cmd10"
STATUS_TOPIC = "ofek/status"

# ================= Initialize Session State =================
if "relay_state" not in st.session_state:
    st.session_state.relay_state = "UNKNOWN"
    
if "last_gps" not in st.session_state or st.session_state.last_gps is None:
    st.session_state.last_gps = {
        "lat": DEFAULT_PARKING_LAT,
        "lon": DEFAULT_PARKING_LON,
        "maps_url": f"https://www.google.com/maps/search/?api=1&query={DEFAULT_PARKING_LAT},{DEFAULT_PARKING_LON}",
        "is_default": True
    }
    
if "last_update" not in st.session_state:
    st.session_state.last_update = "No data yet"
if "gps_status" not in st.session_state:
    st.session_state.gps_status = "WAITING"

# ================= Thread-Safe Shared State =================
@st.cache_resource
def get_shared_state():
    return {"raw_message": None, "is_new": False}

shared_state = get_shared_state()

# ================= MQTT Functions =================
def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        client.subscribe(STATUS_TOPIC)
        print(f"[MQTT] Connected & Subscribed to {STATUS_TOPIC}")

def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8").strip()
    print(f"[MQTT IN] {payload}")
    
    state = get_shared_state()
    state["raw_message"] = payload
    state["is_new"] = True

@st.cache_resource
def get_mqtt_client():
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"st_trk_{int(time.time())}"  
    )
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_start()
    except Exception as e:
        print(f"[MQTT ERROR] {e}")
        
    return client

mqtt_client = get_mqtt_client()

def send_command(cmd: str):
    if mqtt_client:
        mqtt_client.publish(CMD_TOPIC, cmd, qos=0)

# ================= Process Incoming Messages (Main Thread) =================
if shared_state["is_new"]:
    payload_str = shared_state["raw_message"]
    shared_state["is_new"] = False
    
    try:
        if payload_str.startswith("{"):
            data = json.loads(payload_str)
            
            if "relay" in data:
                st.session_state.relay_state = data["relay"]
                    
            if "status" in data and data["status"] == "NO_FIX":
                st.session_state.gps_status = "NO_FIX"
                
            if "lat" in data and "lon" in data:
                st.session_state.last_gps = {
                    "lat": float(data["lat"]),
                    "lon": float(data["lon"]),
                    "maps_url": data.get("maps", f"https://www.google.com/maps/search/?api=1&query={data['lat']},{data['lon']}"),
                    "is_default": False
                }
                st.session_state.gps_status = "OK"
                
            st.session_state.last_update = time.strftime("%H:%M:%S")
            st.rerun()
            
    except Exception as e:
        print(f"[UI ERROR] Failed to parse UI data: {e}")

# ================= User Interface (GUI) =================
st.title("🚗 Triton Tracker & Control")
st.caption(f"Broker: `{MQTT_BROKER}` | System Status: `Active`")

col_s1, col_s2 = st.columns(2)
with col_s1:
    if st.session_state.relay_state == "ENABLED":
        st.success("🟢 Fuel Pump: ACTIVE (ON)")
    elif st.session_state.relay_state == "DISABLED":
        st.error("🔴 Fuel Pump: DISABLED (OFF)")
    else:
        st.warning("⚪ Status: UNKNOWN")
with col_s2:
    st.info(f"🕒 Last Update: {st.session_state.last_update}")

st.divider()
st.subheader("🕹️ Remote Control")
btn_col1, btn_col2 = st.columns(2)

with btn_col1:
    if st.button("⚡ Enable Pump (ON)", use_container_width=True, type="primary"):
        send_command("RELAY_ON")
        st.toast("⏳ Waiting for activation confirmation...", icon="⏳")
        time.sleep(2)
        st.rerun()
        
with btn_col2:
    if st.button("⛔ Disable Pump (OFF)", use_container_width=True):
        send_command("RELAY_OFF")
        st.toast("⏳ Waiting for deactivation confirmation...", icon="⏳")
        time.sleep(2)
        st.rerun()

st.divider()
st.subheader("📍 Vehicle Location")
if st.button("🛰️ Fetch Current Location (Get GPS)", use_container_width=True):
    send_command("GET_GPS")
    st.session_state.gps_status = "WAITING"
    st.toast("⏳ Querying GNSS satellites, please wait...", icon="⏳")
    time.sleep(3)
    st.rerun()

if st.session_state.gps_status == "NO_FIX":
    if isinstance(st.session_state.last_gps, dict) and st.session_state.last_gps.get("is_default"):
        st.warning("⚠️ GPS No Fix. The vehicle is likely in the underground parking. Showing default location.")
    else:
        st.warning("⚠️ GPS No Fix. Cannot lock onto satellites. Showing last known location.")

gps_data = st.session_state.last_gps
if gps_data:
    lat, lon, maps_url = gps_data["lat"], gps_data["lon"], gps_data["maps_url"]
    col_lat, col_lon = st.columns(2)
    col_lat.metric("Latitude", f"{lat:.5f}")
    col_lon.metric("Longitude", f"{lon:.5f}")
    st.link_button("🗺️ Open in Google Maps", url=maps_url, type="secondary", use_container_width=True)
    
    map_df = pd.DataFrame({"lat": [lat], "lon": [lon]})
    st.map(map_df, zoom=15, color='#0044ff')

st.divider()
if st.button("🔄 Refresh UI", use_container_width=True):
    st.rerun()
