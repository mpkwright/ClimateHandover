import streamlit as st
import pandas as pd
import requests
import altair as alt

# --- 1. SETUP ---
st.set_page_config(page_title="Climate Risk Analysis", layout="wide")

st.title("🌍 Climate Risk Analysis: Robust Mode")
st.markdown("""
**Configuration:**
* **Climate Model:** MPI-ESM1-2-XR (Standard CMIP6) | 2020–2050
* **Water Risk:** WRI Aqueduct 4.0 | Spatial Buffer Search (~10km)
""")

# --- 2. INPUTS ---
with st.sidebar:
    st.header("📍 Location")
    lat = st.number_input("Latitude", value=51.5074, format="%.4f")
    lon = st.number_input("Longitude", value=-0.1278, format="%.4f")
    
    st.markdown("---")
    st.caption("Pressing this forces fresh API calls.")
    run_btn = st.button("Run Analysis", type="primary")

# --- 3. CLIMATE ENGINE ---

def fetch_scenario_robust(lat, lon, scenario_code, scenario_label):
    """
    Fetches data using the stable MPI model for a safe date range (2020-2050).
    """
    url = "https://climate-api.open-meteo.com/v1/climate"
    
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": "2020-01-01", 
        "end_date": "2050-12-31",      # Capped at 2050 to ensure API stability
        "models": "MPI_ESM1_2_XR",     # The most reliable model on the free tier
        "scenarios": scenario_code,
        "daily": ["temperature_2m_mean", "precipitation_sum"],
        "disable_bias_correction": "true" 
    }
    
    try:
        r = requests.get(url, params=params)
        r.raise_for_status() # This tracks if the API fails (400/500 errors)
        data = r.json()
        
        # Parse Daily Data
        daily = data.get('daily', {})
        if not daily:
            return pd.DataFrame(), 0, 0
            
        dates = pd.to_datetime(daily.get('time', []))
        temps = daily.get('temperature_2m_mean', [])
        precips = daily.get('precipitation_sum', [])
        
        # Create DataFrame
        df = pd.DataFrame({
            "Date": dates,
            "Temp": temps,
            "Precip": precips,
            "Scenario": scenario_label
        })
        
        # Calculate Averages (ignoring Nones)
        avg_temp = df['Temp'].mean()
        # Annual Precip = Daily Mean * 365.25
        total_precip = df['Precip'].mean() * 365.25 
        
        return df, avg_temp, total_precip
        
    except Exception as e:
        # Log the error but don't crash the app
        print(f"Failed to fetch {scenario_label}: {e}")
        return pd.DataFrame(), 0, 0

# --- 4. WATER ENGINE ---

def fetch_water_risk(lat, lon):
    """
    Finds intersecting water basins using a 10km buffer.
    """
    table = "wat_050_aqueduct_baseline_water_stress"
    
    # 0.1 degrees is roughly 11km. This finds the nearest basin if you are slightly off.
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
        return f"Water API Error: {str(e)[:20]}..."

# --- 5. MAIN EXECUTION ---

if run_btn:
    with st.spinner("Fetching climate scenarios..."):
        
        # 1. Fetch Water Risk
        water_risk = fetch_water_risk(lat, lon)
        
        # 2. Fetch Climate Scenarios
        # We make distinct calls for each
        df_ssp1, t_ssp1, p_ssp1 = fetch_scenario_robust(lat, lon, "ssp1_2_6", "SSP1-2.6 (Low)")
        df_ssp2, t_ssp2, p_ssp2 = fetch_scenario_robust(lat, lon, "ssp2_4_5", "SSP2-4.5 (Med)")
        df_ssp3, t_ssp3, p_ssp3 = fetch_scenario_robust(lat, lon, "ssp3_7_0", "SSP3-7.0 (High)")
        
        # 3. Combine Data
        # We use a list comprehension to only concat non-empty dataframes
        valid_dfs = [d for d in [df_ssp1, df_ssp2, df_ssp3] if not d.empty]
        
        if valid_dfs:
            all_data = pd.concat(valid_dfs)
            all_data['Year'] = all_data['Date'].dt.year
            
            # Group by Year for the Chart (cleaner lines)
            chart_data = all_data.groupby(['Year', 'Scenario'])[['Temp', 'Precip']].mean().reset_index()

            # --- DISPLAY RESULTS ---
            st.subheader(f"Results for {lat}, {lon}")
            st.info(f"💧 **Current Water Stress:** {water_risk}")
            
            # Summary Table
            summary_rows = [
                {"Scenario": "SSP1-2.6", "Avg Temp (2020-50)": f"{t_ssp1:.2f} °C", "Annual Precip": f"{p_ssp1:.0f} mm"},
                {"Scenario": "SSP2-4.5", "Avg Temp (2020-50)": f"{t_ssp2:.2f} °C", "Annual Precip": f"{p_ssp2:.0f} mm"},
                {"Scenario": "SSP3-7.0", "Avg Temp (2020-50)": f"{t_ssp3:.2f} °C", "Annual Precip": f"{p_ssp3:.0f} mm"},
            ]
            st.table(pd.DataFrame(summary_rows))
            
            # Divergence Chart
            st.subheader("📉 Scenario Trajectories (2020–2050)")
            line_chart = alt.Chart(chart_data).mark_line().encode(
                x=alt.X('Year', axis=alt.Axis(format='d')),
                y=alt.Y('Temp', title='Mean Temperature (°C)', scale=alt.Scale(zero=False)),
                color='Scenario',
                tooltip=['Year', 'Scenario', 'Temp']
            ).properties(height=400)
            
            st.altair_chart(line_chart, use_container_width=True)
            
        else:
            st.error("❌ Climate Data API Error. Please check coordinates or try again later.")
