import streamlit as st
import requests

# ---------------------------------------------------------
# 1. CONFIGURATION & DATASET MAP
# ---------------------------------------------------------
# NOTE: If you see "N/A" for any of these, copy the UUID into the
# Sidebar Inspector to find the real column names, then update 'cols'.

RISK_CONFIG = {
    "Baseline Water Stress": {
        "uuid": "c66d7f3a-d1a8-488f-af8b-302b0f2c3840",
        "cols": ["bws_score", "bws_label"], 
        "color": "blue"
    },
    "Drought Risk": {
        "uuid": "5c9507d1-47f7-4c6a-9e64-fc210ccc48e2",
        "cols": ["drr_score", "drr_label"], # Verify this with Inspector!
        "color": "orange"
    },
    "Riverine Flood Risk": {
        "uuid": "df9ef304-672f-4c17-97f4-f9f8fa2849ff",
        "cols": ["rfr_score", "rfr_label"], # Verify this with Inspector!
        "color": "cyan"
    },
    "Coastal Flood Risk": {
        "uuid": "d39919a9-0940-4038-87ac-662f944bc846",
        "cols": ["cfr_score", "cfr_label"], # Verify this with Inspector!
        "color": "teal"
    }
}

# Future Projections (Aqueduct 2.1)
FUTURE_ID = "2a571044-1a31-4092-9af8-48f406f13072"

# ---------------------------------------------------------
# 2. BACKEND LOGIC
# ---------------------------------------------------------
def fetch_risk_data(lat, lon, dataset_key):
    """
    Generic fetcher for any risk dataset defined in RISK_CONFIG.
    """
    config = RISK_CONFIG[dataset_key]
    dataset_id = config['uuid']
    score_col, label_col = config['cols']
    
    # robust single-line SQL
    sql_query = f"SELECT {score_col}, {label_col} FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    
    url = f"https://api.resourcewatch.org/v1/query/{dataset_id}"
    
    try:
        response = requests.get(url, params={"sql": sql_query})
        if response.status_code == 200:
            data = response.json().get('data', [])
            return data[0] if data else {}
        return {"error": f"API Error: {response.text}"}
    except Exception as e:
        return {"error": str(e)}

def fetch_future_projections(lat, lon):
    """
    Fetches 2030 & 2040 Future Labels (Optimistic vs BAU).
    Schema: ws (Water Stress) + Year (30/40) + Scenario (24/28) + tl (Label)
    """
    sql_query = f"SELECT ws3024tl, ws3028tl, ws4024tl, ws4028tl FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    url = f"https://api.resourcewatch.org/v1/query/{FUTURE_ID}"
    
    try:
        response = requests.get(url, params={"sql": sql_query})
        if response.status_code == 200:
            data = response.json().get('data', [])
            return data[0] if data else {}
        return {"error": f"API Error: {response.text}"}
    except Exception as e:
        return {"error": str(e)}

# --- Sidebar Helper Functions ---
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

# --- UI Helper ---
def display_risk_badge(label):
    if not label:
        st.caption("No Data / Safe")
        return
        
    l = str(label).lower()
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
st.set_page_config(page_title="Climate Hazard Dashboard", page_icon="🌍", layout="wide")

st.title("🌍 Climate Hazard Dashboard")
st.markdown("Analyze **Water Stress, Drought, and Flood Risks** for any location.")

# --- INPUTS ---
col1, col2 = st.columns(2)
with col1:
    lat_input = st.number_input("Latitude", value=33.4484, format="%.4f")
with col2:
    lon_input = st.number_input("Longitude", value=-112.0740, format="%.4f")

# --- SECTION 1: CURRENT HAZARDS ---
st.divider()
st.subheader("1. Current Climate Hazards")

if st.button("Analyze Current Risks"):
    with st.spinner("Querying hazard databases..."):
        
        # Dynamic Columns for each hazard
        cols = st.columns(len(RISK_CONFIG))
        
        for idx, (name, config) in enumerate(RISK_CONFIG.items()):
            with cols[idx]:
                st.markdown(f"**{name}**")
                res = fetch_risk_data(lat_input, lon_input, name)
                
                if "error" in res:
                    st.error("API Error")
                    with st.expander("Details"):
                        st.write(res['error'])
                else:
                    # Parse config columns
                    s_col, l_col = config['cols']
                    
                    score = res.get(s_col, 'N/A')
                    label = res.get(l_col, None)
                    
                    if score != 'N/A':
                        st.metric("Score", f"{score} / 5")
                    else:
                        st.metric("Score", "N/A")
                        
                    display_risk_badge(label)

# --- SECTION 2: FUTURE PROJECTIONS ---
st.divider()
st.subheader("2. Future Water Stress (2030-2040)")

if st.button("Predict Future Stress"):
    with st.spinner("Projecting scenarios..."):
        f_res = fetch_future_projections(lat_input, lon_input)
        
    if "error" in f_res:
        st.warning(f_res["error"])
    else:
        # 2030 Row
        st.markdown("### 📅 2030")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**🌱 Optimistic (RCP4.5)**")
            display_risk_badge(f_res.get('ws3024tl'))
        with c2:
            st.markdown("**🏭 Business as Usual (RCP8.5)**")
            display_risk_badge(f_res.get('ws3028tl'))

        st.markdown("---")

        # 2040 Row
        st.markdown("### 📅 2040")
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("**🌱 Optimistic (RCP4.5)**")
            display_risk_badge(f_res.get('ws4024tl'))
        with c4:
            st.markdown("**🏭 Business as Usual (RCP8.5)**")
            display_risk_badge(f_res.get('ws4028tl'))

# ---------------------------------------------------------
# 4. SIDEBAR (DEVELOPER TOOLS)
# ---------------------------------------------------------
st.sidebar.header("🔧 Developer Tools")
st.sidebar.markdown("Use these tools to find new datasets or fix column names.")
st.sidebar.divider()

# --- TOOL A: DATASET FINDER ---
st.sidebar.subheader("🔎 Dataset Finder")
search_term = st.sidebar.text_input("Search term", "Flood")

if st.sidebar.button("Search API"):
    with st.sidebar.status("Searching..."):
        results = search_wri_datasets(search_term)
    
    if results:
        st.sidebar.success(f"Found {len(results)} datasets")
        for ds in results:
            with st.sidebar.expander(ds['attributes']['name']):
                st.code(ds['id'])
                st.caption(f"Provider: {ds['attributes']['provider']}")
                st.json(ds)
    else:
        st.sidebar.warning("No datasets found.")

st.sidebar.divider()

# --- TOOL B: COLUMN INSPECTOR ---
st.sidebar.subheader("🕵️ Column Inspector")
st.sidebar.info("Paste a UUID here to see its table structure.")

# Default to Drought Risk so you can check it easily
inspect_id = st.sidebar.text_input("Dataset UUID", value="5c9507d1-47f7-4c6a-9e64-fc210ccc48e2")

if st.sidebar.button("Inspect Columns"):
    with st.sidebar.status("Fetching one row..."):
        cols = inspect_columns(inspect_id)
    
    if cols:
        st.sidebar.success("Columns found!")
        st.sidebar.write(list(cols[0].keys()))
    else:
        st.sidebar.error("Could not fetch data. Dataset might be empty.")
