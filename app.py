import streamlit as st
import requests

# --- CONFIGURATION ---
st.set_page_config(page_title="Water Stress Checker")
st.title("💧 Baseline Water Stress Lookup")
st.markdown("Checks **WRI Aqueduct 4.0** data via the Resource Watch API.")

# --- INPUTS ---
col1, col2 = st.columns(2)
lat = col1.number_input("Latitude", value=51.5074, format="%.4f")
lon = col2.number_input("Longitude", value=-0.1278, format="%.4f")

# --- THE LOGIC ---
def get_water_stress(lat, lon):
    # 1. CONSTANTS
    # This is the UUID for "Aqueduct Baseline Water Stress"
    DATASET_ID = "c66d7f3a-d1a8-488f-af8b-302b0f2c3840"
    
    try:
        # 2. STEP 1: GET THE TABLE NAME
        # We ask the API: "What is the current table name for this dataset?"
        metadata_url = f"https://api.resourcewatch.org/v1/dataset/{DATASET_ID}"
        r_meta = requests.get(metadata_url).json()
        table_name = r_meta['data']['attributes']['tableName']
        
        # 3. STEP 2: QUERY THE DATA
        # We write a SQL query to find the polygon ('the_geom') that contains our point.
        # ST_Intersects(the_geom, ST_SetSRID(ST_Point(lon, lat), 4326)) matches the point to the shape.
        sql = f"""
            SELECT bws_label, bws_score 
            FROM {table_name} 
            WHERE ST_Intersects(the_geom, ST_SetSRID(ST_Point({lon}, {lat}), 4326))
        """
        
        query_url = f"https://api.resourcewatch.org/v1/query?sql={sql}"
        r_data = requests.get(query_url).json()
        
        # 4. PARSE RESULT
        data = r_data.get('data', [])
        if len(data) > 0:
            return data[0] # Return the first match
        else:
            return None # Point is in the ocean or outside coverage
            
    except Exception as e:
        st.error(f"API Error: {e}")
        return None

# --- EXECUTION ---
if st.button("Check Water Stress", type="primary"):
    with st.spinner("Querying Resource Watch Database..."):
        result = get_water_stress(lat, lon)
        
        if result:
            label = result.get('bws_label', 'Unknown')
            score = result.get('bws_score', 'N/A')
            
            # Simple color coding
            color = "green"
            if "High" in label: color = "orange"
            if "Extremely High" in label: color = "red"
            
            st.success(f"**Found Basin Data!**")
            st.markdown(f"### Stress Level: :{color}[{label}]")
            st.metric("Risk Score (0-5)", score)
        else:
            st.warning("No data found for this location. (Likely ocean or remote area)")
