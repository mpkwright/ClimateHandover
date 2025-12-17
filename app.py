import streamlit as st
import requests

# ---------------------------------------------------------
# 1. CONFIGURATION & BACKEND LOGIC
# ---------------------------------------------------------
BASELINE_DATASET_ID = "c66d7f3a-d1a8-488f-af8b-302b0f2c3840"

def fetch_water_risk(lat, lon):
    """
    Queries the WRI API for baseline water risk data.
    """
    # Clean SQL on one line to avoid API parsing errors
    sql_query = f"SELECT bws_label, bws_score FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    
    url = f"https://api.resourcewatch.org/v1/query/{BASELINE_DATASET_ID}"
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

def search_future_datasets():
    """
    Searches for 'Aqueduct' datasets and filters for 'projected'.
    """
    url = "https://api.resourcewatch.org/v1/dataset"
    # 1. Broad search for the Aqueduct family
    params = {
        "name": "Aqueduct", 
        "published": "true",
        "limit": 100, # Get a larger list to filter through
        "includes": "metadata"
    }

    try:
        response = requests.get(url, params=params)
        all_data = response.json().get('data', [])
        
        # 2. Filter locally for "projected"
        filtered_results = []
        for ds in all_data:
            name = ds['attributes']['name'].lower()
            if "projected" in name:
                filtered_results.append(ds)
                
        return filtered_results
        
    except Exception as e:
        return []

# ---------------------------------------------------------
# 2. FRONTEND UI (Main Area)
# ---------------------------------------------------------
st.set_page_config(page_title="Water Risk Checker", page_icon="💧")

st.title("💧 Water Risk Checker")
st.markdown("Enter coordinates to check **Baseline Water Stress**.")

# Input Section
col1, col2 = st.columns(2)
with col1:
    lat_input = st.number_input("Latitude", value=33.4484, format="%.4f")
with col2:
    lon_input = st.number_input("Longitude", value=-112.0740, format="%.4f")

# Check Button
if st.button("Check Risk Level"):
    with st.spinner("Querying WRI Database..."):
        result = fetch_water_risk(lat_input, lon_input)
    
    if "error" in result:
        st.warning(result["error"])
    else:
        label = result.get('bws_label', 'Unknown')
        score = result.get('bws_score', 'N/A')
        
        # Color Logic
        if score != 'N/A':
            score_val = float(score)
            if score_val >= 4:
                st.error(f"🔥 EXTREME RISK ({label})")
            elif score_val >= 3:
                st.warning(f"⚠️ HIGH RISK ({label})")
            else:
                st.success(f"✅ LOW/MEDIUM RISK ({label})")
        
        st.metric("Water Stress Score", f"{score} / 5")

# ---------------------------------------------------------
# 3. SIDEBAR (Developer Tools)
# ---------------------------------------------------------
st.sidebar.header("🔧 Developer Tools")
st.sidebar.info("Use this to find UUIDs for future projection datasets.")

if st.sidebar.button("Debug: Search 'Projected' Datasets"):
    with st.sidebar.status("Searching API for 'Aqueduct' + 'Projected'..."):
        datasets = search_future_datasets()
        
    if datasets:
        st.sidebar.success(f"Found {len(datasets)} datasets!")
        
        for ds in datasets:
            name = ds['attributes']['name']
            ds_id = ds['id']
            provider = ds['attributes']['provider']
            
            with st.sidebar.expander(f"📂 {name}"):
                st.write(f"**Provider:** {provider}")
                st.text_input("UUID", ds_id, key=ds_id)
                st.json(ds) 
    else:
        st.sidebar.warning("No datasets found matching 'Aqueduct' and 'Projected'.")
