import streamlit as st
import pandas as pd
import json
import reverse_geocoder as rg
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 1. COMPREHENSIVE ISO MAPPING (Fixes the Dubai/11C issue)
ISO_MAP = {
    "AF": "AFG", "AL": "ALB", "DZ": "DZA", "AS": "ASM", "AD": "AND", "AO": "AGO", "AI": "AIA", "AQ": "ATA", "AG": "ATG", "AR": "ARG",
    "AM": "ARM", "AW": "ABW", "AU": "AUS", "AT": "AUT", "AZ": "AZE", "BS": "BHS", "BH": "BHR", "BD": "BGD", "BB": "BRB", "BY": "BLR",
    "BE": "BEL", "BZ": "BLZ", "BJ": "BEN", "BM": "BMU", "BT": "BTN", "BO": "BOL", "BA": "BIH", "BW": "BWA", "BR": "BRA", "BN": "BRN",
    "BG": "BGR", "BF": "BFA", "BI": "BDI", "KH": "KHM", "CM": "CMR", "CA": "CAN", "CV": "CPV", "KY": "CYM", "CF": "CAF", "TD": "TCD",
    "CL": "CHL", "CN": "CHN", "CO": "COL", "KM": "COM", "CG": "COG", "CD": "COD", "CK": "COK", "CR": "CRI", "CI": "CIV", "HR": "HRV",
    "CU": "CUB", "CY": "CYP", "CZ": "CZE", "DK": "DNK", "DJ": "DJI", "DM": "DMA", "DO": "DOM", "EC": "ECU", "EG": "EGY", "SV": "SLV",
    "GQ": "GNQ", "ER": "ERI", "EE": "EST", "ET": "ETH", "FK": "FLK", "FO": "FRO", "FJ": "FJI", "FI": "FIN", "FR": "FRA", "GF": "GUF",
    "PF": "PYF", "GA": "GAB", "GM": "GMB", "GE": "GEO", "DE": "DEU", "GH": "GHA", "GI": "GIB", "GR": "GRC", "GL": "GRL", "GD": "GRD",
    "GP": "GLP", "GU": "GUM", "GT": "GTM", "GN": "GIN", "GW": "GNB", "GY": "GUY", "HT": "HTI", "HN": "HND", "HK": "HKG", "HU": "HUN",
    "IS": "ISL", "IN": "IND", "ID": "IDN", "IR": "IRN", "IQ": "IRQ", "IE": "IRL", "IL": "ISR", "IT": "ITA", "JM": "JAM", "JP": "JPN",
    "JO": "JOR", "KZ": "KAZ", "KE": "KEN", "KI": "KIR", "KP": "PRK", "KR": "KOR", "KW": "KWT", "KG": "KGZ", "LA": "LAO", "LV": "LVA",
    "LB": "LBN", "LS": "LSO", "LR": "LBR", "LY": "LBY", "LI": "LIE", "LT": "LTU", "LU": "LUX", "MO": "MAC", "MK": "MKD", "MG": "MDG",
    "MW": "MWI", "MY": "MYS", "MV": "MDV", "ML": "MLI", "MT": "MLT", "MH": "MHL", "MQ": "MTQ", "MR": "MRT", "MU": "MUS", "YT": "MYT",
    "MX": "MEX", "FM": "FSM", "MD": "MDA", "MC": "MCO", "MN": "MNG", "MS": "MSR", "MA": "MAR", "MZ": "MOZ", "MM": "MMR", "NA": "NAM",
    "NR": "NRU", "NP": "NPL", "NL": "NLD", "NC": "NCL", "NZ": "NZL", "NI": "NIC", "NE": "NER", "NG": "NGA", "NU": "NIU", "NF": "NFK",
    "MP": "MNP", "NO": "NOR", "OM": "OMN", "PK": "PAK", "PW": "PLW", "PS": "PSE", "PA": "PAN", "PG": "PNG", "PY": "PRY", "PE": "PER",
    "PH": "PHL", "PN": "PCN", "PL": "POL", "PT": "PRT", "PR": "PRI", "QA": "QAT", "RE": "REU", "RO": "ROU", "RU": "RUS", "RW": "RWA",
    "SH": "SHN", "KN": "KNA", "LC": "LCA", "PM": "SPM", "VC": "VCT", "WS": "WSM", "SM": "SMR", "ST": "STP", "SA": "SAU", "SN": "SEN",
    "SC": "SYC", "SL": "SLE", "SG": "SGP", "SK": "SVK", "SI": "SVN", "SB": "SLB", "SO": "SOM", "ZA": "ZAF", "GS": "SGS", "ES": "ESP",
    "LK": "LKA", "SD": "SDN", "SR": "SUR", "SJ": "SJM", "SZ": "SWZ", "SE": "SWE", "CH": "CHE", "SY": "SYR", "TW": "TWN", "TJ": "TJK",
    "TZ": "TZA", "TH": "THA", "TL": "TLS", "TG": "TGO", "TK": "TKL", "TO": "TON", "TT": "TTO", "TN": "TUN", "TR": "TUR", "TM": "TKM",
    "TC": "TCA", "TV": "TUV", "UG": "UGA", "UA": "UKR", "AE": "ARE", "GB": "GBR", "US": "USA", "UM": "UMI", "UY": "URY", "UZ": "UZB",
    "VU": "VUT", "VE": "VEN", "VN": "VNM", "VG": "VGB", "VI": "VIR", "WF": "WLF", "EH": "ESH", "YE": "YEM", "ZM": "ZMB", "ZW": "ZWE"
}

# 2. DATABASE LOADER
@st.cache_data
def load_wb_db():
    with open("climate_WB_data.json", "r") as f:
        return json.load(f)

WB_DB = load_wb_db()

# 3. CUSTOM STYLING (Smaller hazard fonts to prevent cutoff)
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.1rem !important; font-weight: 700; }
    [data-testid="stMetricLabel"] { font-size: 0.85rem !important; }
    </style>
    """, unsafe_allow_html=True)

# 4. CORE ENGINE
def get_wb_val(loc_id, var, scenario, period):
    try:
        m_key = '2020-07' if period == '2020-2039' else '2040-07'
        return WB_DB['data'][var][period][scenario][loc_id][m_key]
    except: return None

def analyze_point(lat, lon, manual_id=None):
    loc_info = rg.search((lat, lon))[0]
    iso3 = ISO_MAP.get(loc_info['cc'], "USA")
    target_id = manual_id if manual_id else iso3
    
    # Identify available sub-regions for this country
    sub_regions = [k for k in WB_DB['data']['tas']['2020-2039']['ssp245'].keys() if k.startswith(iso3)]
    
    res = {"Location": f"{loc_info['name']}, {loc_info['cc']}", "ID": target_id, "SubRegions": sub_regions}
    
    # Hazard Data (WRI)
    RISK_CONFIG = {
        "Baseline Water Stress": "c66d7f3a-d1a8-488f-af8b-302b0f2c3840",
        "Drought Risk": "5c9507d1-47f7-4c6a-9e64-fc210ccc48e2",
        "Riverine Flood": "df9ef304-672f-4c17-97f4-f9f8fa2849ff",
        "Coastal Flood": "d39919a9-0940-4038-87ac-662f944bc846"
    }
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(total=3)))
    
    for name, uuid in RISK_CONFIG.items():
        sql = f"SELECT * FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
        try:
            r = session.get(f"https://api.resourcewatch.org/v1/query/{uuid}", params={"sql": sql}, timeout=5)
            val = "N/A"
            if r.json().get('data'):
                row_data = r.json()['data'][0]
                val = next((v for k, v in row_data.items() if 'label' in k.lower()), "N/A")
            res[name] = val
        except: res[name] = "N/A"

    # Climate Data (JSON)
    for var in ['tas', 'pr']:
        for sc in ['ssp126', 'ssp245', 'ssp370']:
            for prd in ['2020-2039', '2040-2059']:
                res[f"{var}_{sc}_{prd}"] = get_wb_val(target_id, var, sc, prd)
    return res

# 5. UI TABS
st.set_page_config(page_title="Climate Intelligence Dashboard", layout="wide")
st.title("🌍 Integrated Climate & Hazard Risk Portal")

t1, t2 = st.tabs(["📍 Single Location", "🚀 Batch Processing"])

with t1:
    with st.sidebar:
        st.header("📍 Location Parameters")
        lat_in = st.number_input("Latitude", value=25.2048, format="%.4f")
        lon_in = st.number_input("Longitude", value=55.2708, format="%.4f")
        sid_in = st.text_input("GADM ID (Optional)", placeholder="e.g. ARE.2553173")
        if st.button("Generate Risk Report"):
            st.session_state.data = analyze_point(lat_in, lon_in, sid_in)

    if 'data' in st.session_state:
        d = st.session_state.data
        st.map(pd.DataFrame({'lat': [lat_in], 'lon': [lon_in]}), zoom=7)
        
        st.info(f"📍 Detected Location: **{d['Location']}**. Sub-Regions in JSON: `{', '.join(d['SubRegions'][:10])}...`")
        st.subheader(f"Current & Projected Risks for ID: {d['ID']}")
        
        # HAZARDS - SPLIT OVER 2 ROWS FOR FONT VISIBILITY
        h_row1 = st.columns(2)
        h_row2 = st.columns(2)
        h_row1[0].metric("🌊 Water Stress", d.get("Baseline Water Stress", "N/A"))
        h_row1[1].metric("🏜️ Drought Risk", d.get("Drought Risk", "N/A"))
        h_row2[0].metric("🏠 Riverine Flood", d.get("Riverine Flood", "N/A"))
        h_row2[1].metric("🏖️ Coastal Flood", d.get("Coastal Flood", "N/A"))

        st.divider()
        st.subheader("🔮 Climate Projections (All JSON Scenarios)")
        
        # PROJECTION TABLE (Fixed 'r' bug and added SSP126)
        def fm(v, u): return f"{v:.2f}{u}" if v is not None else "N/A"
        res_table = [
            {"Scenario": "Optimistic (SSP1-2.6)", "Temp +10Y": fm(d['tas_ssp126_2020-2039'], "C"), "Temp +25Y": fm(d['tas_ssp126_2040-2059'], "C"), "Prec +10Y": fm(d['pr_ssp126_2020-2039'], "mm"), "Prec +25Y": fm(d['pr_ssp126_2040-2059'], "mm")},
            {"Scenario": "Moderate (SSP2-4.5)", "Temp +10Y": fm(d['tas_ssp245_2020-2039'], "C"), "Temp +25Y": fm(d['tas_ssp245_2040-2059'], "C"), "Prec +10Y": fm(d['pr_ssp245_2020-2039'], "mm"), "Prec +25Y": fm(d['pr_ssp245_2040-2059'], "mm")},
            {"Scenario": "High Risk (SSP3-7.0)", "Temp +10Y": fm(d['tas_ssp370_2020-2039'], "C"), "Temp +25Y": fm(d['tas_ssp370_2040-2059'], "C"), "Prec +10Y": fm(d['pr_ssp370_2020-2039'], "mm"), "Prec +25Y": fm(d['pr_ssp370_2040-2059'], "mm")}
        ]
        st.table(pd.DataFrame(res_table))

        # TRIPLE-SCENARIO CHARTS
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Temperature Pathways (C)**")
            t_df = pd.DataFrame({
                "SSP1-2.6": [d['tas_ssp126_2020-2039'], d['tas_ssp126_2040-2059']],
                "SSP2-4.5": [d['tas_ssp245_2020-2039'], d['tas_ssp245_2040-2059']],
                "SSP3-7.0": [d['tas_ssp370_2020-2039'], d['tas_ssp370_2040-2059']]
            }, index=[2030, 2050])
            st.line_chart(t_df)
        with c2:
            st.write("**Precipitation Pathways (mm)**")
            p_df = pd.DataFrame({
                "SSP1-2.6": [d['pr_ssp126_2020-2039'], d['pr_ssp126_2040-2059']],
                "SSP2-4.5": [d['pr_ssp245_2020-2039'], d['pr_ssp245_2040-2059']],
                "SSP3-7.0": [d['pr_ssp370_2020-2039'], d['pr_ssp370_2040-2059']]
            }, index=[2030, 2050])
            st.line_chart(p_df)

with t2:
    st.markdown("### 📥 Bulk Analysis Tool")
    st.info("Upload a CSV with 'latitude' and 'longitude' columns to process multiple sites against the local JSON database.")
    up_csv = st.file_uploader("Upload CSV", type=["csv"])
    if up_csv:
        df_in = pd.read_csv(up_csv)
        if st.button("Run Batch Processing"):
            results = []
            progress = st.progress(0)
            for i, row in df_in.iterrows():
                results.append(analyze_point(row['latitude'], row['longitude']))
                progress.progress((i + 1) / len(df_in))
            
            df_final = pd.DataFrame(results)
            st.success("Batch Processing Complete!")
            st.dataframe(df_final, use_container_width=True)
            st.download_button("💾 Download Batch Results", df_final.to_csv(index=False).encode('utf-8'), "climate_risk_batch.csv", "text/csv")
