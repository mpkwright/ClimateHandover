import streamlit as st
import pandas as pd
import numpy as np
import openmeteo_requests
import requests_cache
from retry_requests import retry
import altair as alt
from geopy.geocoders import Nominatim

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Climate Risk Dashboard", layout="wide")
st.markdown("""<style>.reportview-container { background: #f0f2f6 }</style>""", unsafe_allow_html=True)

st.title("🌍 Climate Risk & Resilience Dashboard")
st.markdown("""
**Decadal Risk Pathway Analysis**
* **Baseline:** 1991–2020 (ERA5 Reanalysis)
* **Future:** 2021–2050 (CMIP6 / MPI-ESM1-2-XR), broken down by decade.
""")

# --- 2. INPUTS ---
with st.sidebar:
    st.header("📍 Location Parameters")
    lat = st.number_input("Latitude", value=51.5074, format="%.4f", min_value=-90.0, max_value=90.0)
    lon = st.number_input("Longitude", value=-0.1278, format="%.4f", min_value=-180.0, max_value=180.0)
    
    st.markdown("---")
    st.caption("✅ **Live Data:** Decadal slices from 2021-2050")
    st.caption("⚠️ **Simulated:** Risk Labels (High/Med/Low)")
    run_btn = st.button("Generate Risk Analysis", type="primary")

# --- 3. DATA ENGINE ---

@st.cache_data
def get_location_name(lat, lon):
    try:
        geolocator = Nominatim(user_agent="climate_risk_app")
        location = geolocator.reverse((lat, lon), language='en')
        address = location.raw.get('address', {})
        return f"{address.get('state', '')}, {address.get('country', 'Unknown')}"
    except:
        return "Unknown Location"

@st.cache_data
def get_climate_data(lat, lon):
    # Setup Client with Caching
    cache_session = requests_cache.CachedSession('.cache', expire_after=3600*24)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    # 1. BASELINE (1991-2020)
    url_hist = "https://archive-api.open-meteo.com/v1/archive"
    params_hist = {
        "latitude": lat, "longitude": lon,
        "start_date": "1991-01-01", "end_date": "2020-12-31",
        "daily": ["temperature_2m_mean", "precipitation_sum"]
    }
    
    # 2. FUTURE (2021-2050)
    url_pro = "https://climate-api.open-meteo.com/v1/climate"
    params_pro = {
        "latitude": lat, "longitude": lon,
        "start_date": "2021-01-01", "end_date": "2050-12-31",
        "models": "MPI_ESM1_2_XR",
        "daily": ["temperature_2m_mean", "precipitation_sum"],
        "disable_bias_correction": "true" 
    }

    try:
        # -- Execute Historical --
        hist_resp = openmeteo.weather_api(url_hist, params=params_hist)[0]
        
        # -- Execute Future Scenarios --
        future_data = {}
        scenarios_to_fetch = {
            "ssp1_2_6": "SSP1-2.6 (Ambitious)",
            "ssp2_4_5": "SSP2-4.5 (Optimistic)",
            "ssp3_7_0": "SSP3-7.0 (BAU)"
        }
        
        for sc_key, sc_name in scenarios_to_fetch.items():
             p = params_pro.copy()
             p["scenarios"] = [sc_key]
             f_resp = openmeteo.weather_api(url_pro, params=p)[0]
             
             # Process Daily Data - FIXED DATE GENERATION
             f_daily = f_resp.Daily()
             
             # Create proper date range using start, end, and interval
             f_start = pd.to_datetime(f_daily.Time(), unit="s", origin="unix")
             f_end = pd.to_datetime(f_daily.TimeEnd(), unit="s", origin="unix")
             f_interval = pd.to_timedelta(f_daily.Interval(), unit="s")
             
             f_dates = pd.date_range(start=f_start, end=f_end, freq=f_interval, inclusive="left")
             
             f_temps = f_daily.Variables(0).ValuesAsNumpy()
             f_precip = f_daily.Variables(1).ValuesAsNumpy()
             
             # Ensure lengths match (trim if needed)
             min_len = min(len(f_dates), len(f_temps), len(f_precip))
             df_f = pd.DataFrame({
                 "temp": f_temps[:min_len], 
                 "precip": f_precip[:min_len]
             }, index=f_dates[:min_len])
             
             # Decadal Slicing
             decades = {
                 "2020s (2021-30)": df_f.loc['2021':'2030'],
                 "2030s (2031-40)": df_f.loc['2031':'2040'],
                 "2040s (2041-50)": df_f.loc['2041':'2050']
             }
             
             future_data[sc_name] = {}
             for d_name, d_df in decades.items():
                 if not d_df.empty:
                     future_data[sc_name][d_name] = {
                         "temp": d_df["temp"].mean(),
                         "precip": d_df["precip"].sum() / 10.0 # Annual avg
                     }

        # -- Process Historical Baseline --
        h_daily = hist_resp.Daily()
        
        # Fixed Date Generation for Historical
        h_start = pd.to_datetime(h_daily.Time(), unit="s", origin="unix")
        h_end = pd.to_datetime(h_daily.TimeEnd(), unit="s", origin="unix")
        h_interval = pd.to_timedelta(h_daily.Interval(), unit="s")
        h_dates = pd.date_range(start=h_start, end=h_end, freq=h_interval, inclusive="left")
        
        h_temps = h_daily.Variables(0).ValuesAsNumpy()
        h_precips = h_daily.Variables(1).ValuesAsNumpy()
        
        min_len_h = min(len(h_dates), len(h_temps), len(h_precips))
        
        baseline_temp = h_temps.mean()
        baseline_precip = h_precips.sum() / 30.0 
        
        # Monthly Data for Chart
        df_h = pd.DataFrame({
            "temp": h_temps[:min_len_h], 
            "precip": h_precips[:min_len_h]
        }, index=h_dates[:min_len_h])
        
        monthly = df_h.groupby(df_h.index.month).agg({"temp": "mean", "precip": "mean"})
        monthly["precip_total"] = monthly["precip"] * 30.44

        return {
            "baseline_temp": baseline_temp,
            "baseline_precip": baseline_precip,
            "future": future_data,
            "monthly": monthly
        }

    except Exception as e:
        # Improved error logging to see exactly where it fails
        import traceback
        st.error(f"Data Fetch Error: {e}")
        st.text(traceback.format_exc())
        return None

def calculate_risk_table(data):
    b_t = data["baseline_temp"]
    b_p = data["baseline_precip"]
    
    # Risk Logic (Simulated for Demo)
    def get_labels(t, p):
        drought = "High" if p < 500 else ("Medium" if p < 800 else "Low")
        flood = "High" if p > 1200 else ("Medium" if p > 800 else "Low")
        wildfire = "High" if (t > 15 and p < 600) else "Low"
        return drought, flood, wildfire

    rows = []
    
    # 1. Current Row
    d, f, w = get_labels(b_t, b_p)
    rows.append({
        "Scenario": "Current Baseline",
        "Decade": "1991-2020",
        "Temp": f"{b_t:.2f} °C",
        "Precip": f"{b_p:.0f} mm",
        "Water Stress": "Medium" if b_p < 1000 else "Low",
        "Drought": d, "Flood": f, "Cyclone": "Low", "Wildfire": w
    })
    
    # 2. Future Rows (Loop Scenarios -> Loop Decades)
    for sc_name, decades in data["future"].items():
        for dec_name, metrics in decades.items():
            
            delta_t = metrics["temp"] - b_t
            delta_p_pct = ((metrics["precip"] - b_p) / b_p) * 100 if b_p != 0 else 0
            
            fd, ff, fw = get_labels(metrics["temp"], metrics["precip"])
            
            rows.append({
                "Scenario": sc_name,
                "Decade": dec_name,
                "Temp": f"{'+' if delta_t>0 else ''}{delta_t:.2f} °C",
                "Precip": f"{'+' if delta_p_pct>0 else ''}{delta_p_pct:.1f} %",
                "Water Stress": "High" if metrics["precip"] < 1000 else "Low",
                "Drought": fd, "Flood": ff, "Cyclone": "Low", "Wildfire": fw
            })

    return pd.DataFrame(rows)

# --- 4. VISUALIZATION ---
def plot_chart(monthly):
    src = monthly.reset_index()
    src['month_name'] = pd.to_datetime(src['index'], format='%m').dt.month_name().str.slice(stop=3)
    base = alt.Chart(src).encode(x=alt.X('month_name', sort=None, title='Month'))
    bar = base.mark_bar(opacity=0.5, color='#4c78a8').encode(y='precip_total', tooltip='precip_total')
    line = base.mark_line(color='#e45756', strokeWidth=3).encode(y='temp', tooltip='temp')
    return alt.layer(bar, line).resolve_scale(y='independent').properties(title="Seasonal Baseline (1991-2020)")

def style_rows(val):
    s = str(val)
    if 'High' in s: return 'background-color: #ffcccc; color: black'
    if 'Med' in s: return 'background-color: #fff4cc; color: black'
    if 'Low' in s: return 'background-color: #ccffcc; color: black'
    return ''

# --- 5. MAIN ---
if run_btn:
    with st.spinner("Fetching Decadal Projections..."):
        data = get_climate_data(lat, lon)
        if data:
            st.subheader(f"📍 Analysis for: {get_location_name(lat, lon)}")
            st.map(pd.DataFrame({'lat':[lat], 'lon':[lon]}), zoom=4)
            
            c1, c2 = st.columns(2)
            c1.metric("Baseline Temp", f"{data['baseline_temp']:.1f}°C")
            c2.metric("Baseline Precip", f"{data['baseline_precip']:.0f}mm")
            
            st.markdown("### 🔮 Decadal Risk Pathways")
            df = calculate_risk_table(data)
            
            st.dataframe(
                df.style.applymap(style_rows), 
                use_container_width=True,
                column_order=["Scenario", "Decade", "Temp", "Precip", "Water Stress", "Drought", "Flood", "Wildfire"]
            )
            
            st.altair_chart(plot_chart(data['monthly']), use_container_width=True)
        else:
            pass # Error handled in function
else:
    st.info("👈 Enter Latitude/Longitude in the sidebar and click 'Generate' to start.")
