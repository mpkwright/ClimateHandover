import streamlit as st
import pandas as pd
import requests
import time

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Climate Risk Dashboard", layout="wide")
st.title("🌍 Climate Risk Dashboard")
st.markdown("""
**Decadal Risk Pathway Analysis**
* **Climate Model:** UKESM1-0-LL (CMIP6) - *Chosen for high scenario sensitivity*
* **Water Risk:** WRI Aqueduct 4.0 - *Using Nearest Neighbor Geosearch*
""")

# --- 2. INPUTS ---
with st.sidebar:
    st.header("📍 Location")
    # Default: London
    lat = st.number_input("Latitude", value=51.5074, format="%.4f", min_value=-90.0, max_value=90.0)
    lon = st.number_input("Longitude", value=-0.1278, format="%.4f", min_value=-180.0, max_value=180.0)
    
    st.markdown("---")
    run_btn = st.button("Generate Analysis", type="primary")

# --- 3. DATA ENGINE (ROBUST) ---

def get_climate_data(lat, lon):
    """
    Fetches climate data using UKESM1_0_LL.
    """
    url = "https://climate-api.open-meteo.com/v1/climate"
    scenarios = {
        "ssp1_2_6": "SSP1-2.6 (Low Carbon)",
        "ssp2_4_5": "SSP2-4.5 (Middle Road)",
        "ssp3_7_0": "SSP3-7.0 (High Carbon)"
    }
    
    results = {}
    
    # 1. Fetch Future Scenarios
    for sc_key, sc_label in scenarios.items():
        params = {
            "latitude": lat, "longitude": lon,
            "start_date": "2021-01-01", "end_date": "2050-12-31",
            "models": "UKESM1_0_LL", # Switched to UKESM for better variance
            "scenarios": sc_key, 
            "daily": ["temperature_2m_mean", "precipitation_sum"],
            "disable_bias_correction": "true"
        }
        
        try:
            r = requests.get(url, params=params)
            data = r.json()
            
            # Extract arrays
            temps = data.get('daily', {}).get('temperature_2m_mean', [])
            precips = data.get('daily', {}).get('precipitation_sum', [])
            
            # Calculate simple decadal averages (2020s, 30s, 40s) to show progression
            # 30 years total = ~10950 days. 
            # Slice 1: 0-3650 (2020s), Slice 2: 3650-7300 (2030s), Slice 3: 7300-End (2040s)
            
            # Safe mean helper
            def mean(l): return sum(x for x in l if x is not None) / len([x for x in l if x is not None]) if l else 0
            
            results[sc_label] = {
                "2030s_temp": mean(temps[3650:7300]),
                "2050s_temp": mean(temps[7300:]),
                "precip_annual": (sum(x for x in precips if x is not None) / 30.0) # Annual Avg
            }
            
        except Exception as e:
            print(f"Error fetching {sc_key}: {e}")
            results[sc_label] = {"2030s_temp": 0, "2050s_temp": 0, "precip_annual": 0}

    # 2. Fetch Baseline (Reference)
    # We use the Historical run of the SAME model to ensure apples-to-apples comparison
    try:
        params_hist = params.copy()
        params_hist['start_date'] = "1990-01-01"
        params_hist['end_date'] = "2014-12-31" # CMIP6 historical usually ends 2014
        params_hist.pop('scenarios') # Historical doesn't have scenarios
        
        r_hist = requests.get(url, params=params_hist)
        d_hist = r_hist.json()
        h_temps = d_hist.get('daily', {}).get('temperature_2m_mean', [])
        h_precips = d_hist.get('daily', {}).get('precipitation_sum', [])
        
        baseline = {
            "temp": sum(x for x in h_temps if x is not None) / len(h_temps) if h_temps else 0,
            "precip": (sum(x for x in h_precips if x is not None) / 25.0) # 25 years
        }
    except:
        baseline = {"temp": 0, "precip": 0}

    return {"baseline": baseline, "future": results}

def get_water_stress_nearest(lat, lon):
    """
    Finds the NEAREST water basin with data, ignoring distance limits.
    """
    # 1. Get Table Name
    meta_url = "https://api.resourcewatch.org/v1/dataset/c66d7f3a-d1a8-488f-af8b-302b0f2c3840"
    try:
        r_meta = requests.get(meta_url).json()
        table_name = r_meta['data']['attributes']['tableName']
    except:
        return "N/A (API Error)"

    # 2. Nearest Neighbor Query
    # The <-> operator in PostGIS calculates distance. 
    # ORDER BY distance LIMIT 1 gives us the single closest point.
    sql = f"""
        SELECT bws_label, bws_score, 
               ST_Distance(the_geom::geography, ST_SetSRID(ST_Point({lon}, {lat}), 4326)::geography) as dist_meters
        FROM {table_name} 
        ORDER BY the_geom <-> ST_SetSRID(ST_Point({lon}, {lat}), 4326) 
        LIMIT 1
    """
    
    url = f"https://api.resourcewatch.org/v1/query?sql={sql}"
    
    try:
        r = requests.get(url).json()
        if 'data' in r and len(r['data']) > 0:
            rec = r['data'][0]
            label = rec.get('bws_label', 'Unknown')
            dist_km = rec.get('dist_meters', 0) / 1000.0
            
            # If it's ridiculously far (>500km), warn the user
            if dist_km > 500:
                return f"{label} (Nearest basin is {dist_km:.0f}km away)"
            return label
        else:
            return "No Data Found"
    except Exception as e:
        return f"Error: {e}"

# --- 4. MAIN APP ---

if run_btn:
    with st.spinner("Running Analysis..."):
        # Fetch Data
        c_data = get_climate_data(lat, lon)
        w_stress = get_water_stress_nearest(lat, lon)
        
        # Display Top Metrics
        st.subheader("Results")
        
        # Build DataFrame
        rows = []
        
        # Baseline Row
        b_temp = c_data['baseline']['temp']
        b_precip = c_data['baseline']['precip']
        
        rows.append({
            "Scenario": "Historical Baseline (1990-2014)",
            "Temp (Avg)": f"{b_temp:.2f} °C",
            "Precip (Annual)": f"{b_precip:.0f} mm",
            "Water Stress": w_stress
        })
        
        # Future Rows
        for sc, metrics in c_data['future'].items():
            # Delta calculation
            delta_t = metrics['2050s_temp'] - b_temp
            delta_p = ((metrics['precip_annual'] - b_precip) / b_precip) * 100 if b_precip else 0
            
            rows.append({
                "Scenario": sc,
                "Temp (Avg)": f"{metrics['2050s_temp']:.2f} °C (+{delta_t:.1f})",
                "Precip (Annual)": f"{metrics['precip_annual']:.0f} mm ({delta_p:+.1f}%)",
                "Water Stress": "See Baseline (Projected)"
            })
            
        df = pd.DataFrame(rows)
        st.table(df)
        
        st.info(f"ℹ️ Water Stress Data sourced from the nearest WRI Aqueduct basin to your location.")
