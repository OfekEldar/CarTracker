import json
import time
import pandas as pd
import paho.mqtt.client as mqtt
import streamlit as st

# ================= Page Config =================
st.set_page_config(
    page_title="Vehicle Tracker & Control",
    page_icon="🚗",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ================= Security & Login =================
def check_password():
    """Returns True if the user entered the correct password."""
    def password_entered():
        if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # מחיקת הסיסמה מהזיכרון
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🔒 Enter Password to access the tracker:", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("🔒 Enter Password to access the tracker:", type="password", on_change=password_entered, key="password")
        st.error("❌ Incorrect Password")
        return False
    return True

# עצירת טעינת האפליקציה אם הסיסמה שגויה או טרם הוזנה
if not check_password():
    st.stop()

# ================= System & MQTT Settings =================
MQTT_BROKER = "tcp://test.mosquitto.org:1883"
MQTT_PORT = 1883
CMD_TOPIC = "ofek/cmd10"
STATUS_TOPIC = "ofek/status"

# קריאת מספר הטלפון בצורה מאובטחת (לא חשוף ב-GitHub)
TARGET_PHONE = st.secrets["TARGET_PHONE"]

# ================= Initialize Session State =================
if "relay_state" not in st.session_state:
    st.session_state.relay_state = "UNKNOWN"
if "last_gps" not in st.session_state:
    st.session_state.last_gps = None
if "last_update" not in st.session_state:
    st.session_state.last_update = "No data yet"
if "sms_alert" not in st.session_state:
    st.session_state.sms_alert = False

# ================= MQTT Functions =================
def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        client.subscribe(STATUS_TOPIC)
        print(f"[MQTT] Subscribed to {STATUS_TOPIC}")

def on_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode("utf-8").strip()
        print(f"[MQTT IN] {payload_str}") # לוג לדיבאג

        # 1. זיהוי פקודות ריליי
        if "RELAY_IS_ON" in payload_str:
            st.session_state.relay_state = "ENABLED"
            st.session_state.sms_alert = True
            st.session_state.last_update = time.strftime("%H:%M:%S")
            
        elif "RELAY_IS_OFF" in payload_str:
            st.session_state.relay_state = "DISABLED"
            st.session_state.last_update = time.strftime("%H:%M:%S")
            
        # 2. זיהוי שגיאת GPS
        elif "GPS_NO_FIX" in payload_str:
            st.session_state.last_update = time.strftime("%H:%M:%S")
            st.session_state.gps_status = "NO_FIX"
            
        # 3. זיהוי מחרוזת GPS תקינה (מתחילה בדרך כלל בסטטוס הפיקס, למשל '3,' או '2,')
        # לדוגמה: 3,08,02,00,3205.1234,N,03448.5678,E...
        elif ",N," in payload_str or ",S," in payload_str:
            parts = payload_str.split(',')
            
            # וידוא שיש לנו מספיק נתונים במחרוזת
            if len(parts) >= 8 and parts[4] and parts[6]:
                lat_str = parts[4] # "3205.1234"
                lat_dir = parts[5] # "N"
                lon_str = parts[6] # "03448.5678"
                lon_dir = parts[7] # "E"

                # המרה מפורמט NMEA לפורמט עשרוני של Google Maps
                # Latitude: DDMM.MMMM -> DD.DDDD
                lat_deg = float(lat_str[:2])
                lat_min = float(lat_str[2:])
                lat_dec = lat_deg + (lat_min / 60.0)
                if lat_dir == 'S': lat_dec = -lat_dec

                # Longitude: DDDMM.MMMM -> DD.DDDD
                lon_deg = float(lon_str[:3])
                lon_min = float(lon_str[3:])
                lon_dec = lon_deg + (lon_min / 60.0)
                if lon_dir == 'W': lon_dec = -lon_dec

                st.session_state.last_gps = {
                    "lat": lat_dec,
                    "lon": lon_dec,
                    "maps_url": f"https://www.google.com/maps/search/?api=1&query={lat_dec},{lon_dec}"
                }
                st.session_state.gps_status = "OK"
                st.session_state.last_update = time.strftime("%H:%M:%S")

        # 4. תמיכה לאחור ב-JSON (אם בכל זאת הוספת את זה ב-ESP)
        elif payload_str.startswith("{"):
            data = json.loads(payload_str)
            if "relay" in data:
                st.session_state.relay_state = data["relay"]
            if "lat" in data and "lon" in data:
                lat, lon = float(data["lat"]), float(data["lon"])
                st.session_state.last_gps = {
                    "lat": lat,
                    "lon": lon,
                    "maps_url": f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
                }
            st.session_state.last_update = time.strftime("%H:%M:%S")

    except Exception as e:
        print(f"[MQTT ERROR] Failed to parse message: {e}")

@st.cache_resource
def get_mqtt_client():
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="streamlit_car_tracker_client")
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_start()
    except Exception as e:
        print(f"[MQTT] Connection Error: {e}")
    return client

mqtt_client = get_mqtt_client()

def send_command(cmd: str):
    if mqtt_client:
        mqtt_client.publish(CMD_TOPIC, cmd)

# ================= User Interface (GUI) =================
st.title("🚗 Vehicle Tracker & Control")
st.caption(f"Broker: `{MQTT_BROKER}` | SMS Target: `Hidden Securely`")

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

if st.session_state.sms_alert:
    st.toast("📲 SMS alert sent to your phone!", icon="📩")
    st.success("✅ System activation SMS successfully sent to secure phone number")
    st.session_state.sms_alert = False

st.divider()
st.subheader("🕹️ Remote Control")
btn_col1, btn_col2 = st.columns(2)
with btn_col1:
    if st.button("⚡ Enable Pump (ON)", use_container_width=True, type="primary"):
        send_command("RELAY_ON")
        st.toast("Enable command sent...")
with btn_col2:
    if st.button("⛔ Disable Pump (OFF)", use_container_width=True):
        send_command("RELAY_OFF")
        st.toast("Disable command sent...")

st.divider()
st.subheader("📍 Vehicle Location")
if st.button("🛰️ Fetch Current Location (Get GPS)", use_container_width=True):
    send_command("GET_GPS")
    st.toast("Location request sent to module...")

if st.session_state.last_gps:
    gps_data = st.session_state.last_gps
    lat, lon, maps_url = gps_data["lat"], gps_data["lon"], gps_data["maps_url"]
    col_lat, col_lon = st.columns(2)
    col_lat.metric("Latitude", f"{lat:.5f}")
    col_lon.metric("Longitude", f"{lon:.5f}")
    st.link_button("🗺️ Open in Google Maps", url=maps_url, type="secondary", use_container_width=True)
    map_df = pd.DataFrame({"lat": [lat], "lon": [lon]})
    st.map(map_df, zoom=15)
else:
    st.info("No location saved yet. Click 'Fetch Current Location' to get coordinates.")

st.divider()
if st.button("🔄 Refresh UI", use_container_width=True):
    st.rerun()
