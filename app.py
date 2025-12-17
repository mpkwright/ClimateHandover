import streamlit as st
import pandas as pd
import requests
import altair as alt

# --- 1. SETUP ---
st.set_page_config(page_title="Climate Risk Analysis (Clean)", layout="wide")

st.title("🌍 Climate Risk Analysis: Clean Slate")
st.markdown("""
This dashboard fetches raw climate data with **strict isolation** to ensure scenario divergence is real.
* **Climate:** EC-Earth3P-HR (High Res) | 2024–2100
* **Water:** WRI Aqueduct 4.0 | Spatial Buffer Search
""")

# --- 2. INPUTS ---
with st.sidebar:
    st.header("📍 Location")
    lat = st.number_input("Latitude", value=51.5074, format="%.4f")
    lon = st.number_input("Longitude", value=-0.1278, format="%.4f")
    
    st.markdown("---")
    st.caption("Pressing this forces fresh API calls.")
    run_btn = st.button("Run New Analysis", type="primary")

# --- 3. CLIMATE ENGINE (STRICT ISOLATION) ---

def fetch_scenario(lat, lon, scenario_code, scenario_label):
    """
    Fetches a SINGLE scenario to ensure no parameter bleeding/caching issues.
    """
    url = "https://climate-api.open-meteo.com/v1/climate"
    
    # We request data up to 2100 to SEE the divergence
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": "2024-01-01",
        "end_date": "2099-12-31",
        "models": "EC_Earth3P_HR",
        "scenarios": scenario_code,
        "daily": ["temperature_2m_mean", "precipitation_sum"],
        "disable_bias_correction": "true" 
    }
    
    try:
        r = requests.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        
        # Parse Dates
        daily = data.get('daily', {})
        dates = pd.to_datetime(daily.get('time', []))
        temps = daily.get('temperature_2m_mean', [])
        precips = daily.get('precipitation_sum', [])
        
        # Create Series
        df = pd.DataFrame({
            "Date": dates,
            "Temp": temps,
            "Precip": precips,
            "Scenario": scenario_label
        })
        
        # Calculate Aggregates
        avg_temp = df['Temp'].mean()
        total_precip = df['Precip'].mean() * 365.25 # Annualized
        
        return df, avg_temp, total_precip
        
    except Exception as e:
        st.error(f"Failed to fetch {scenario_label}: {e}")
        return pd.DataFrame(), 0, 0

# --- 4. WATER ENGINE (BUFFER SEARCH) ---

def fetch_water_risk(lat, lon):
    """
    Uses a spatial buffer (circle) to find intersecting water basins.
    """
    # WRI Aqueduct Baseline Water Stress Table
    table = "wat_050_aqueduct_baseline_water_stress"
    
    # Query: Create a buffer of 0.1 degrees (~11km) around the point and find intersection
    sql = f"""
        SELECT bws_label, bws_score
        FROM {table}
        WHERE ST_Intersects(the_geom, ST_Buffer(ST_SetSRID(ST_Point({lon}, {lat}), 4326), 0.1))
        LIMIT 1
    """
    
    url = f"https://api.resourcewatch.org/v1/query?sql={sql}"
    
    try:
        r = requests.get(url)
        data = r.json().get('data', [])
        if data:
            return data[0].get('bws_label', 'Unknown')
        else:
            return "No Basin Found (Ocean/Remote)"
    except Exception as e:
        return f"API Error: {str(e)}"

# --- 5. MAIN EXECUTION ---

if run_btn:
    with st.spinner("Fetching strict climate scenarios..."):
        
        # 1. Fetch Water Risk
        water_risk = fetch_water_risk(lat, lon)
        
        # 2. Fetch Climate Scenarios (Distinct Calls)
        # We fetch distinct dataframes to prove they are different
        df_ssp1, t_ssp1, p_ssp1 = fetch_scenario(lat, lon, "ssp1_2_6", "SSP1-2.6 (Low)")
        df_ssp2, t_ssp2, p_ssp2 = fetch_scenario(lat, lon, "ssp2_4_5", "SSP2-4.5 (Med)")
        df_ssp3, t_ssp3, p_ssp3 = fetch_scenario(lat, lon, "ssp3_7_0", "SSP3-7.0 (High)")
        
        # 3. Combine for Charting
        all_data = pd.concat([df_ssp1, df_ssp2, df_ssp3])
        
        # Resample to Annual Average for cleaner charts
        all_data['Year'] = all_data['Date'].dt.year
        chart_data = all_data.groupby(['Year', 'Scenario'])[['Temp', 'Precip']].mean().reset_index()

        # --- RESULTS DISPLAY ---
        
        st.subheader(f"Results for {lat}, {lon}")
        
        # A. Water Risk
        st.info(f"💧 **Current Water Stress (WRI Aqueduct):** {water_risk}")
        
        # B. Summary Table
        summary_rows = [
            {"Scenario": "SSP1-2.6 (Low Carbon)", "Avg Temp (2024-2100)": f"{t_ssp1:.2f} °C", "Annual Precip": f"{p_ssp1:.0f} mm"},
            {"Scenario": "SSP2-4.5 (Middle Road)", "Avg Temp (2024-2100)": f"{t_ssp2:.2f} °C", "Annual Precip": f"{p_ssp2:.0f} mm"},
            {"Scenario": "SSP3-7.0 (High Carbon)", "Avg Temp (2024-2100)": f"{t_ssp3:.2f} °C", "Annual Precip": f"{p_ssp3:.0f} mm"},
        ]
        st.table(pd.DataFrame(summary_rows))
        
        # C. Divergence Chart (The Proof)
        st.subheader("📉 Scenario Divergence (2024–2100)")
        st.markdown("If the lines separate over time, the API is working correctly.")
        
        line_chart = alt.Chart(chart_data).mark_line().encode(
            x=alt.X('Year', axis=alt.Axis(format='d')),
            y=alt.Y('Temp', title='Mean Temperature (°C)', scale=alt.Scale(zero=False)),
            color='Scenario',
            tooltip=['Year', 'Scenario', 'Temp']
        ).properties(height=400)
        
        st.altair_chart(line_chart, use_container_width=True)
