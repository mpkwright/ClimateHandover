import streamlit as st
import pandas as pd
import requests
import time

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Climate Risk Dashboard", layout="wide")
st.title("🌍 Climate Risk Dashboard")
st.markdown("""
**Robust Analysis Mode**
* **Climate Model:** MPI-ESM1-2-XR (Standard CMIP6)
* **Water Risk:** WRI Aqueduct 4.0 (Hardcoded Table Search)
""")

# --- 2. INPUTS ---
with st.sidebar:
    st.header("📍 Location")
    lat = st.number_input("Latitude", value=51.5074, format="%.4f")
    lon = st.number_input("Longitude", value=-0.1278, format="%.4f")
    run_btn = st.button("Generate Analysis", type="primary")

# --- 3. ROBUST DATA ENGINE ---

def get_climate_data_robust(lat, lon):
    # API Endpoint
    url = "https://climate-api.open-meteo.com/v1/climate"
    
    # We use MPI_ESM1_2_XR because we KNOW it works for these dates
    base_params = {
        "latitude": lat, "longitude": lon,
        "start_date": "2021-01-01", "end_date": "2050-12-31",
        "models": "MPI_ESM1_2_XR",
        "daily": ["temperature_2m_mean", "precipitation_sum"],
        "disable_bias_correction": "true"
    }
    
    results = {}
    
    # Scenarios to fetch
    scenarios = ["ssp1_2_6", "ssp2_4_5", "ssp3_7_0"]
    
    for sc in scenarios:
        # Create unique parameters for this SPECIFIC scenario
        # We add 'cache_buster' to ensure the API doesn't return the previous loop's result
        params = base_params.copy()
        params["scenarios"] = sc
        params["_cb"] = int(time.time() * 1000) + scenarios.index(sc)
        
        try:
            r = requests.get(url, params=params)
            r.raise_for_status() # Raise error if 400/500
            data = r.json()
            
            # Extract
            temps = data.get('daily', {}).get('temperature_2m_mean', [])
            precips = data.get('daily', {}).get('precipitation_sum', [])
            
            # Math Helper: Filter None values
            valid_temps = [x for x in temps if x is not None]
            valid_precips = [x for x in precips if x is not None]
            
            if not valid_temps:
                results[sc] = {"temp": "No Data", "precip": "No Data"}
            else:
                avg_temp = sum(valid_temps) / len(valid_temps)
                # Annual Precip = (Total Sum / Days) * 365
                avg_precip = (sum(valid_precips) / len(valid_precips)) * 365.25
                
                results[sc] = {
                    "temp": avg_temp, 
                    "precip": avg_precip
                }
                
        except Exception as e:
            results[sc] = {"temp": f"Err: {str(e)[:20]}", "precip": "Err"}

    return results

def get_water_stress_robust(lat, lon):
    # We confirmed this table name in your previous logs. 
    # Hardcoding it removes the "Metadata Fetch" point of failure.
    TABLE_NAME = "wat_050_aqueduct_baseline_water_stress"
    
    # We try 3 search radii: 1km (exact), 50km (near), 500km (regional)
    radii = [0.01, 0.5, 5.0] 
    
    for r in radii:
        sql = f"""
            SELECT bws_label, bws_score 
            FROM {TABLE_NAME} 
            WHERE ST_DWithin(the_geom, ST_SetSRID(ST_Point({lon}, {lat}), 4326), {r}) 
            LIMIT 1
        """
        url = f"https://api.resourcewatch.org/v1/query?sql={sql}"
        
        try:
            resp = requests.get(url)
            data = resp.json().get('data', [])
            if data:
                val = data[0].get('bws_label', 'Unknown')
                # If we had to search far (0.5 or 5.0), add a note
                if r > 0.01:
                    return f"{val} (Regional Match)"
                return val
        except:
            continue # Try next radius
            
    return "No Data (Ocean/Remote)"

# --- 4. MAIN APP ---

if run_btn:
    with st.spinner("Fetching data..."):
        # 1. Get Climate
        c_results = get_climate_data_robust(lat, lon)
        
        # 2. Get Water
        w_stress = get_water_stress_robust(lat, lon)
        
        # 3. Build Table
        rows = []
        for sc, metrics in c_results.items():
            t_val = metrics['temp']
            p_val = metrics['precip']
            
            # Formatting checks
            if isinstance(t_val, (int, float)):
                t_str = f"{t_val:.2f} °C"
            else:
                t_str = str(t_val)
                
            if isinstance(p_val, (int, float)):
                p_str = f"{p_val:.0f} mm"
            else:
                p_str = str(p_val)
                
            rows.append({
                "Scenario": sc.upper().replace("_", "-"),
                "Avg Temp (2021-2050)": t_str,
                "Annual Precip": p_str,
                "Water Stress (Baseline)": w_stress
            })
            
        st.subheader("Analysis Results")
        st.table(pd.DataFrame(rows))
        
        # DEBUG EXPANDER (Hidden by default, open if needed)
        with st.expander("Show Raw Data Check"):
            st.json(c_results)
