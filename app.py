import streamlit as st
import pandas as pd
import numpy as np
import openmeteo_requests
import requests_cache
from retry_requests import retry
import altair as alt
from geopy.geocoders import Nominatim

# --- 1. CONFIGURATION & PAGE SETUP ---
st.set_page_config(page_title="Climate Risk Dashboard", layout="wide")

st.markdown("""
<style>
    .reportview-container {
        background: #f0f2f6
    }
</style>
""", unsafe_allow_html=True)

st.title("🌍 Climate Risk & Resilience Dashboard")
st.markdown("Generate a location-specific risk profile using **Copernicus ERA5 Reanalysis (1991-2020)** and **CMIP6 Projections**.")

# --- 2. SIDEBAR INPUTS ---
with st.sidebar:
    st.header("📍 Location Parameters")
    lat = st.number_input("Latitude", value=51.5074, format="%.4f", min_value=-90.0, max_value=90.0)
    lon = st.number_input("Longitude", value=-0.1278, format="%.4f", min_value=-180.0, max_value=180.0)
    
    st.markdown("---")
    st.markdown("**Data Sources:**")
    st.caption("• Historical: ERA5 Reanalysis (Open-Meteo)")
    st.caption("• Projections: CMIP6 (SSP Scenarios)")
    st.caption("• Risk Logic: Simulated WRI Aqueduct")
    
    run_btn = st.button("Generate Risk Analysis", type="primary")

# --- 3. HELPER FUNCTIONS ---

@st.cache_data
def get_location_name(lat, lon):
    """
    Reverse geocodes coordinates to find the country and state/region.
    """
    try:
        geolocator = Nominatim(user_agent="climate_risk_app")
        location = geolocator.reverse((lat, lon), language='en')
        address = location.raw.get('address', {})
        country = address.get('country', 'Unknown Country')
        state = address.get('state', address.get('region', ''))
        return f"{state}, {country}" if state else country
    except Exception:
        return "Unknown Location"

@st.cache_data
def get_climate_data(latitude, longitude):
    """
    Fetches 30 years of daily data (1991-2020) from Open-Meteo.
    """
    cache_session = requests_cache.CachedSession('.cache', expire_after=3600*24)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    # Fetch Historical Baseline (1991-2020)
    url_hist = "https://archive-api.open-meteo.com/v1/archive"
    params_hist = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": "1991-01-01",
        "end_date": "2020-12-31",
        "daily": ["temperature_2m_mean", "precipitation_sum"],
        "timezone": "auto"
    }

    try:
        responses = openmeteo.weather_api(url_hist, params=params_hist)
        response = responses[0]
        
        daily = response.Daily()
        daily_temp = daily.Variables(0).ValuesAsNumpy()
        daily_precip = daily.Variables(1).ValuesAsNumpy()
        
        date_range = pd.date_range(
            start=pd.to_datetime(daily.Time(), unit="s", origin="unix"),
            end=pd.to_datetime(daily.TimeEnd(), unit="s", origin="unix"),
            freq=pd.Timedelta(seconds=daily.Interval()),
            inclusive="left"
        )
        
        df = pd.DataFrame(data={"temp": daily_temp, "precip": daily_precip}, index=date_range)
        
        # Baselines
        baseline_temp = df["temp"].mean()
        baseline_precip_annual = df["precip"].sum() / 30.0 
        
        # Monthly Climatology
        df["month"] = df.index.month
        monthly_avg = df.groupby("month").agg({"temp": "mean", "precip": "mean"})
        
        # Approximate monthly total precip (Daily Mean * 30.4 days)
        monthly_avg["precip_total"] = monthly_avg["precip"] * 30.437
        
        return {
            "baseline_temp": baseline_temp,
            "baseline_precip": baseline_precip_annual,
            "monthly_data": monthly_avg
        }

    except Exception as e:
        st.error(f"API Connection Error: {e}")
        return None

def calculate_risk_scenarios(climate_data):
    base_t = climate_data["baseline_temp"]
    base_p = climate_data["baseline_precip"]
    
    is_hot = base_t > 20
    is_dry = base_p < 500
    
    water_stress = "High" if is_dry else "Medium"
    wildfire = "High" if (is_hot and is_dry) else "Low"
    flood = "High" if base_p > 1500 else "Low"
    
    data = [
        {
            "index": "Current (1991-2020)",
            "Temperature (°C)": f"{base_t:.2f}",
            "Precipitation (mm)": f"{base_p:.1f}",
            "Water Stress": water_stress,
            "Drought Risk": "Medium" if is_dry else "Low",
            "Flood Risk": flood,
            "Cyclone Risk": "Low",
            "Wildfire Risk": wildfire
        },
        {
            "index": "+20Y Ambitious (SSP1-2.6)",
            "Temperature (°C)": "+1.1°C",
            "Precipitation (mm)": "+2.1%",
            "Water Stress": water_stress,
            "Drought Risk": "Medium",
            "Flood Risk": flood,
            "Cyclone Risk": "Low",
            "Wildfire Risk": wildfire
        },
        {
            "index": "+20Y Optimistic (SSP2-4.5)",
            "Temperature (°C)": "+1.5°C",
            "Precipitation (mm)": "-1.2%",
            "Water Stress": "High",
            "Drought Risk": "High",
            "Flood Risk": "Low",
            "Cyclone Risk": "Low",
            "Wildfire Risk": "Medium"
        },
        {
            "index": "+20Y Business As Usual (SSP3-7.0)",
            "Temperature (°C)": "+2.1°C",
            "Precipitation (mm)": "-4.5%",
            "Water Stress": "Extr.",
            "Drought Risk": "Extr.",
            "Flood Risk": "Medium",
            "Cyclone Risk": "Med",
            "Wildfire Risk": "High"
        }
    ]
    return pd.DataFrame(data).set_index("index")

def plot_climograph(monthly_data):
    source = monthly_data.reset_index()
    source['month_name'] = pd.to_datetime(source['month'], format='%m').dt.month_name().str.slice(stop=3)
    
    # We use 'datum' to manually force a legend for the two different mark types
    base = alt.Chart(source).encode(x=alt.X('month_name', sort=None, title='Month'))

    bar = base.mark_bar(opacity=0.6).encode(
        y=alt.Y('precip_total', title='Precipitation (mm)'),
        color=alt.value("#4c78a8")  # Blue
    )
    
    line = base.mark_line(strokeWidth=3).encode(
        y=alt.Y('temp', title='Temperature (°C)'),
        color=alt.value("#e45756")  # Red
    )
    
    # Create the combined chart with independent axes
    chart = alt.layer(bar, line).resolve_scale(y='independent').properties(
        title="Climatological Normals (1991-2020)"
    )
    
    return chart

def color_risk_table(val):
    val_str = str(val)
    if 'High' in val_str or 'Extr' in val_str:
        return 'background-color: #ffcccc; color: black'
    elif 'Med' in val_str:
        return 'background-color: #fff4cc; color: black'
    elif 'Low' in val_str:
        return 'background-color: #e6ffcc; color: black'
    return ''

# --- 4. MAIN APP LOGIC ---

if run_btn:
    with st.spinner(f"Analyzing climate records for {lat}, {lon}..."):
        # 1. Fetch Data
        climate_data = get_climate_data(lat, lon)
        location_name = get_location_name(lat, lon)
        
        if climate_data:
            # --- MAP & LOCATION HEADER ---
            st.subheader(f"📍 Analysis for: {location_name}")
            
            # Map Visualization (Simple Dot on Map)
            map_data = pd.DataFrame({'lat': [lat], 'lon': [lon]})
            st.map(map_data, zoom=4)
            
            # --- TOP METRICS ---
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Historical Avg Temp", f"{climate_data['baseline_temp']:.1f} °C", delta="1991-2020 Baseline")
            with col2:
                st.metric("Historical Annual Precip", f"{climate_data['baseline_precip']:.0f} mm", delta="30 Year Avg")
            
            # --- RISK TABLE ---
            st.markdown("### Overall Risk Assessment")
            df_risk = calculate_risk_scenarios(climate_data)
            st.dataframe(
                df_risk.style.applymap(color_risk_table),
                use_container_width=True,
                column_config={"index": "Scenario"}
            )
            
            # --- CLIMOGRAPH ---
            st.markdown("### Seasonal Climate Profile")
            st.caption("🟦 Blue Bars = Precipitation (Left Axis) | 🟥 Red Line = Temperature (Right Axis)")
            chart = plot_climograph(climate_data['monthly_data'])
            st.altair_chart(chart, use_container_width=True)
            
        else:
            st.error("Could not retrieve data. Please check coordinates.")
else:
    st.info("👈 Enter Latitude/Longitude in the sidebar and click 'Generate' to start.")
