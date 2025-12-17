import streamlit as st
import requests

# ---------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------
BASELINE_ID = "c66d7f3a-d1a8-488f-af8b-302b0f2c3840"
FUTURE_ID = "2a571044-1a31-4092-9af8-48f406f13072"

# ---------------------------------------------------------
# 2. BACKEND LOGIC
# ---------------------------------------------------------
def fetch_baseline_risk(lat, lon):
    """
    Fetches current Baseline Water Stress.
    """
    # Clean SQL on one line
    sql_query = f"SELECT bws_label, bws_score FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    
    url = f"https://api.resourcewatch.org/v1/query/{BASELINE_ID}"
    
    try:
        response = requests.get(url, params={"sql": sql_query})
        if response.status_code == 200:
            data = response.json().get('data', [])
            return data[0] if data else {"error": "No baseline data found."}
        return {"error": f"API Error: {response.text}"}
    except Exception as e:
        return {"error": str(e)}

def fetch_future_risk(lat, lon):
    """
    Fetches Future Water Stress LABELS only.
    We fetch the 'tl' (Text Label) columns for 2030 & 2040 (Optimistic vs BAU).
    """
    # Note: We fetch only the labels (tl), ignoring the raw scores (tr)
    sql_query = f"SELECT ws3024tl, ws3028tl, ws4024tl, ws4028tl FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    
    url = f"https://api.resourcewatch.org/v1/query/{FUTURE_ID}"
    
    try:
        response = requests.get(url, params={"sql": sql_query})
        if response.status_code == 200:
            data = response.json().get('data', [])
            return data[0] if data else {"error": "No future data found."}
        return {"error": f"API Error: {response.text}"}
    except Exception as e:
        return {"error": str(e)}

def search_wri_datasets(term):
    url = "https://api.resourcewatch.org/v1/dataset"
    params = {"name": term, "published": "true", "limit": 10, "includes": "metadata"}
    try:
        return requests.get(url, params=params).json().get('data', [])
    except Exception:
        return []

def inspect_columns(dataset_id):
    url = f"https://api.resourcewatch.org/v1/query/{dataset_id}?sql=SELECT * FROM data LIMIT 1"
    try:
        return requests.get(url).json().get('data', [])
    except Exception:
        return None

# Helper to color-code risk labels
def display_risk_label(label):
    if not label:
        st.info("No Data")
        return
        
    l = label.lower()
    if "extremely high" in l:
        st.error(f"🔥 {label}")
    elif "high" in l:
        st.warning(f"⚠️ {label}")
    elif "medium" in l:
        st.info(f"💧 {label}")
    elif "low" in l:
        st.success(f"✅ {label}")
    else:
        st.write(f"ℹ️ {label}")

# ---------------------------------------------------------
# 3. FRONTEND UI
# ---------------------------------------------------------
st.set_page_config(page_title="Water Risk App", page_icon="💧", layout="wide")
st.title("💧 Water Risk Intelligence")

# Inputs
col1, col2 = st.columns(2)
with col1:
    lat_input = st.number_input("Latitude", value=33.4484, format="%.4f")
with col2:
    lon_input = st.number_input("Longitude", value=-112.0740, format="%.4f")

# --- 1. BASELINE ---
st.divider()
st.subheader("1. Current Baseline")
if st.button("Check Current Risk"):
    with st.spinner("Analyzing..."):
        res = fetch_baseline_risk(lat_input, lon_input)
    if "error" in res:
        st.warning(res["error"])
    else:
        score = res.get('bws_score', 'N/A')
        label = res.get('bws_label', 'Unknown')
        
        # Display Baseline with Score (since we know this scale is 0-5)
        st.metric("Baseline Score", f"{score} / 5")
        display_risk_label(label)

# --- 2. FUTURE PROJECTIONS ---
st.divider()
st.subheader("2. Future Projections (Labels Only)")
st.caption("Comparing Optimistic (RCP4.5) vs. Business as Usual (RCP8.5)")

if st.button("Generate Projections"):
    with st.spinner("Projecting Scenarios..."):
        f_res = fetch_future_risk(lat_input, lon_input)
    
    if "error" in f_res:
        st.warning(f_res["error"])
    else:
        # Row 1: 2030
        st.markdown("### 📅 2030 Projections")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**🌱 Optimistic**")
            display_risk_label(f_res.get('ws3024tl', 'N/A'))
        with c2:
            st.markdown("**🏭 Business as Usual**")
            display_risk_label(f_res.get('ws3028tl', 'N/A'))

        st.divider()

        # Row 2: 2040
        st.markdown("### 📅 2040 Projections")
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("**🌱 Optimistic**")
            display_risk_label(f_res.get('ws4024tl', 'N/A'))
        with c4:
            st.markdown("**🏭 Business as Usual**")
            display_risk_label(f_res.get('ws4028tl', 'N/A'))

# ---------------------------------------------------------
# 4. SIDEBAR TOOLS
# ---------------------------------------------------------
st.sidebar.header("🔧 Developer Tools")
search_query = st.sidebar.text_input("Search Datasets", "Water Stress")

if st.sidebar.button("Search API"):
    results = search_wri_datasets(search_query)
    if results:
        st.sidebar.success(f"Found {len(results)} datasets")
        for ds in results:
            with st.sidebar.expander(ds['attributes']['name']):
                st.code(ds['id'])
                st.json(ds)
    else:
        st.sidebar.warning("No datasets found.")

st.sidebar.divider()
st.sidebar.subheader("Inspect Columns")
inspect_id = st.sidebar.text_input("Dataset UUID", value=FUTURE_ID)
if st.sidebar.button("Get Columns"):
    cols = inspect_columns(inspect_id)
    if cols:
        st.sidebar.write(list(cols[0].keys()))
