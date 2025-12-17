import streamlit as st
import requests

# ---------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------
DATASET_ID = "c66d7f3a-d1a8-488f-af8b-302b0f2c3840"

# ---------------------------------------------------------
# 2. BACKEND FUNCTION
# ---------------------------------------------------------
def fetch_water_risk(lat, lon):
    """
    Queries the WRI API for water risk data using a 'clean' SQL string.
    """
    # FIX: Single line string + WKT geometry to avoid comma/newline parsing errors
    # We use 'FROM data' because the Dataset ID in the URL already selects the table.
    sql_query = f"SELECT bws_label, bws_score FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    
    url = f"https://api.resourcewatch.org/v1/query/{DATASET_ID}"
    params = {"sql": sql_query}

    try:
        response = requests.get(url, params=params)
        
        if response.status_code != 200:
            return {"error": f"API Error {response.status_code}: {response.text}"}

        data = response.json().get('data', [])
        
        if data:
            return data[0]
        else:
            return {"error": "No data at this location (Ocean or out of bounds)."}
            
    except Exception as e:
        return {"error": str(e)}

# ---------------------------------------------------------
# 3. FRONTEND UI
# ---------------------------------------------------------
st.title("💧 Water Risk Checker")
st.markdown("Enter coordinates to check **Baseline Water Stress**.")

col1, col2 = st.columns(2)
with col1:
    lat_input = st.number_input("Latitude", value=33.4484, format="%.4f")
with col2:
    lon_input = st.number_input("Longitude", value=-112.0740, format="%.4f")

if st.button("Check Risk Level"):
    with st.spinner("Querying WRI Database..."):
        result = fetch_water_risk(lat_input, lon_input)
    
    if "error" in result:
        st.warning(result["error"])
    else:
        label = result.get('bws_label', 'Unknown')
        score = result.get('bws_score', 'N/A')
        
        # Display Logic
        if score != 'N/A':
            score_val = float(score)
            if score_val >= 4:
                st.error(f"🔥 EXTREME RISK ({label})")
            elif score_val >= 3:
                st.warning(f"⚠️ HIGH RISK ({label})")
            else:
                st.success(f"✅ LOW/MEDIUM RISK ({label})")
        
        st.metric("Water Stress Score", f"{score} / 5")
