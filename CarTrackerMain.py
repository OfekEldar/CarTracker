import json
import time
import pandas as pd
import paho.mqtt.client as mqtt
import streamlit as st

# ================= System & MQTT Settings =================
MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
CMD_TOPIC = "ofek/cmd10"
STATUS_TOPIC = "ofek/status"
TARGET_PHONE = "+972523808029"

# ================= Page Config (Mobile Friendly) =================
st.set_page_config(
    page_title="Vehicle Tracker & Control",
    page_icon="🚗",
    layout="centered",
    initial_sidebar_state="collapsed",
)

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
        payload_str = msg.payload.decode("utf-8")

        # Parse JSON
        if payload_str.startswith("{"):
            data = json.loads(payload_str)

            # Update Relay / Pump state
            if "relay" in data:
                old_state = st.session_state.relay_state
                st.session_state.relay_state = data["relay"]
                if data["relay"] == "ENABLED" and old_state != "ENABLED":
                    st.session_state.sms_alert = True

            # Update GPS location
            if "lat" in data and "lon" in data:
                lat = float(data["lat"])
                lon = float(data["lon"])
                st.session_state.last_gps = {
                    "lat": lat,
                    "lon": lon,
                    "speed": data.get("speed_knots", "0"),
                    # Create direct link to open Google Maps app on mobile
                    "maps_url": f"https://www.google.com/maps/search/?api=1&query={lat},{lon}",
                }

            st.session_state.last_update = time.strftime("%H:%M:%S")

        # Backwards compatibility (plain text)
        elif "RELAY_IS_ON" in payload_str:
            st.session_state.relay_state = "ENABLED"
            st.session_state.sms_alert = True
            st.session_state.last_update = time.strftime("%H:%M:%S")
        elif "RELAY_IS_OFF" in payload_str:
            st.session_state.relay_state = "DISABLED"
            st.session_state.last_update = time.strftime("%H:%M:%S")

    except Exception as e:
        print(f"[MQTT ERROR] {e}")


@st.cache_resource
def get_mqtt_client():
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="streamlit_car_tracker_client",
    )
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
st.caption(f"Broker: `{MQTT_BROKER}` | SMS Target: `{TARGET_PHONE}`")

# Top Status Display
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

# SMS Alert Notification
if st.session_state.sms_alert:
    st.toast("📲 SMS alert sent to your phone!", icon="📩")
    st.success(f"✅ System activation SMS successfully sent to {TARGET_PHONE}")
    st.session_state.sms_alert = False

st.divider()

# Control Buttons
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

# Location Section
st.subheader("📍 Vehicle Location")

if st.button("🛰️ Fetch Current Location (Get GPS)", use_container_width=True):
    send_command("GET_GPS")
    st.toast("Location request sent to module...")

if st.session_state.last_gps:
    gps_data = st.session_state.last_gps
    lat = gps_data["lat"]
    lon = gps_data["lon"]
    maps_url = gps_data["maps_url"]

    # Show coordinates
    col_lat, col_lon = st.columns(2)
    col_lat.metric("Latitude", f"{lat:.5f}")
    col_lon.metric("Longitude", f"{lon:.5f}")

    # Direct link to Google Maps
    st.link_button(
        "🗺️ Open in Google Maps",
        url=maps_url,
        type="secondary",
        use_container_width=True,
    )

    # Embedded map in Streamlit
    map_df = pd.DataFrame({"lat": [lat], "lon": [lon]})
    st.map(map_df, zoom=15)

else:
    st.info("No location saved yet. Click 'Fetch Current Location' to get coordinates.")

st.divider()

# Refresh Button
if st.button("🔄 Refresh UI", use_container_width=True):
    st.rerun()
