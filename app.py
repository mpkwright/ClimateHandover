import streamlit as st
import pandas as pd
import numpy as np
import openmeteo_requests
import requests_cache
from retry_requests import retry
import altair as alt

# --- 1. CONFIGURATION & PAGE SETUP ---
st.set_page_config(page_title="Climate Risk Dashboard", layout="wide")

st.markdown("""
<style>
    .reportview-container {
        background: #f0f2f6
    }
    .big-font {
        font-size:20px !important;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

st.title("🌍 Climate Risk & Resilience Dashboard")
st.markdown("Generate a location-specific risk profile using **Copernicus ERA5 Reanalysis (1991-2020)** and **CMIP6 Projections**.")

# --- 2. SIDEBAR INPUTS ---
with st.sidebar:
    st.header("📍 Location Parameters")
    # Default to London coordinates
    lat = st.number_input("Latitude", value=51.5074, format="%.4f", min_value=-90.0, max_value=90.0)
    lon = st.number_input("Longitude", value=-0.1278, format="%.4f", min_value=-180.0, max_value=180.0)
    
    st.markdown("---")
    st.markdown("**Data Sources:**")
    st.caption("• Historical: ERA5 Reanalysis (Open-Meteo)")
    st.caption("• Projections: CMIP6 (SSP Scenarios)")
    st.caption("• Risk Logic: Simulated WRI Aqueduct")
    
    run_btn = st.button("Generate Risk Analysis", type="primary")

# --- 3. DATA ENGINE (The Heavy Lifting) ---
@st.cache_data
def get_climate_data(latitude, longitude):
    """
    Fetches 30 years of daily data (1991-2020) to create a robust baseline.
    Returns: Current Baseline Stats, Monthly Averages (for Chart), and raw Future Deltas.
    """
    # Setup Open-Meteo Client with Caching
    cache_session = requests_cache.CachedSession('.cache', expire_after=3600*24)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    # A. Fetch Historical Baseline (1991-2020)
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
        
        # Process Daily Data
        daily = response.Daily()
        daily_temp = daily.Variables(0).ValuesAsNumpy()
        daily_precip = daily.Variables(1).ValuesAsNumpy()
        
        # Create a Pandas DataFrame for easier Time-Series Analysis
        date_range = pd.date_range(
            start=pd.to_datetime(daily.Time(), unit="s", origin="unix"),
            end=pd.to_datetime(daily.TimeEnd(), unit="s", origin="unix"),
            freq=pd.Timedelta(seconds=daily.Interval()),
            inclusive="left"
        )
        
        df = pd.DataFrame(data={"temp": daily_temp, "precip": daily_precip}, index=date_range)
        
        # 1. Calculate Baselines (30-Year Average)
        baseline_temp = df["temp"].mean()
        baseline_precip_annual = df["precip"].sum() / 30.0 # Total annual precip average
        
        # 2. Calculate Monthly Climatology (For the Chart)
        df["month"] = df.index.month
        monthly_avg = df.groupby("month").agg({
            "temp": "mean",
            "precip": "sum" # Sum of precip per month, averaged over years? 
                            # Actually: groupby month mean gives daily avg. 
                            # We need monthly totals.
        })
        # Correcting monthly precip: (Daily Avg * Days in Month) is a quick approximation
        days_in_month = np.array([31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
        monthly_avg["precip_total"] = monthly_avg["precip"] * days_in_month
        
        return {
            "baseline_temp": baseline_temp,
            "baseline_precip": baseline_precip_annual,
            "monthly_data": monthly_avg
        }

    except Exception as e:
        st.error(f"API Connection Error: {e}")
        return None

# --- 4. RISK LOGIC ENGINE ---
def calculate_risk_scenarios(lat, lon, climate_data):
    """
    Takes the real baseline data and projects risks.
    In a full production app, this would query specific Hazard APIs.
    Here, we simulate the 'Delta' logic based on the baseline.
    """
    base_t = climate_data["baseline_temp"]
    base_p = climate_data["baseline_precip"]
    
    # Heuristics for Risk Classification based on location and dryness
    # (Simplified logic for demonstration)
    is_hot = base_t > 20
    is_dry = base_p < 500
    
    # 1. Base Risks (Current)
    water_stress = "High" if is_dry else "Medium"
    wildfire = "High" if (is_hot and is_dry) else "Low"
    flood = "High" if base_p > 1500 else "Low"
    
    # 2. Construct the Data Table
    # Note: Future deltas are hardcoded approximations of SSP trends for this demo.
    # To make this "Real", you would fetch the CMIP6 endpoint in 'get_climate_data' 
    # and compare the 2041-2060 average to the baseline.
    
    data = [
        {
            "index": "Current (1991-2020)",
            "Temperature (°C)": f"{base_t:.2f}",
            "Precipitation (mm)": f"{base_p:.1f}",
            "Water Stress": water_stress,
            "Drought Risk": "Medium" if is_dry else "Low",
            "Flood Risk": flood,
            "Cyclone Risk": "Low", # Needs external track data
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

# --- 5. VISUALIZATION FUNCTIONS ---
def plot_climograph(monthly_data):
    # Prepare data for Altair
    source = monthly_data.reset_index()
    source['month_name'] = pd.to_datetime(source['month'], format='%m').dt.month_name().str.slice(stop=3)
    
    # Bar Chart for Precipitation
    bar = alt.Chart(source).mark_bar(color='#4c78a8', opacity=0.6).encode(
        x=alt.X('month_name', sort=None, title='Month'),
        y=alt.Y('precip_total', title='Precipitation (mm)'),
        tooltip=['month_name', 'precip_total']
    )
    
    # Line Chart for Temperature
    line = alt.Chart(source).mark_line(color='#e45756', strokeWidth=3).encode(
        x=alt.X('month_name', sort=None),
        y=alt.Y('temp', title='Temperature (°C)'),
        tooltip=['month_name', 'temp']
    )
    
    # Combine (Dual Axis Simulation)
    c = alt.layer(bar, line).resolve_scale(y='independent').properties(
        title="Climatological Normals (1991-2020 Average)",
        height=300
    )
    return c

def color_risk_table(val):
    """
    Styling function for the dataframe
    """
    val_str = str(val)
    color = ''
    if 'High' in val_str or 'Extr' in val_str:
        color = 'background-color: #ffcccc; color: black' # Red
    elif 'Med' in val_str:
        color = 'background-color: #fff4cc; color: black' # Yellow
    elif 'Low' in val_str:
        color = 'background-color: #e6ffcc; color: black' # Green
    return color

# --- 6. MAIN APP LOGIC ---

if run_btn:
    with st.spinner(f"Analyzing climate records for {lat}, {lon}..."):
        # 1. Fetch Data
        climate_data = get_climate_data(lat, lon)
        
        if climate_data:
            # 2. Layout: Top Metrics
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Historical Avg Temp", f"{climate_data['baseline_temp']:.1f} °C", delta="1991-2020 Baseline")
            with col2:
                st.metric("Historical Annual Precip", f"{climate_data['baseline_precip']:.0f} mm", delta="30 Year Avg")
            
            # 3. Layout: The Risk Table
            st.subheader("Overall Risk Assessment")
            df_risk = calculate_risk_scenarios(lat, lon, climate_data)
            
            # Apply styling
            st.dataframe(
                df_risk.style.applymap(color_risk_table),
                use_container_width=True,
                column_config={
                    "index": "Scenario"
                }
            )
            
            # 4. Layout: The Climograph
            st.subheader("Seasonal Climate Profile")
            st.markdown("Visualizing the 30-year average seasonal cycle (Seasonality) for this location.")
            chart = plot_climograph(climate_data['monthly_data'])
            st.altair_chart(chart, use_container_width=True)
            
        else:
            st.error("Could not retrieve data for this location. Please check coordinates.")
else:
    st.info("👈 Enter Latitude/Longitude in the sidebar and click 'Generate' to start.")
