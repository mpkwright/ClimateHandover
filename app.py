import streamlit as st
import pandas as pd
import json
import reverse_geocoder as rg
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 1. AUTHENTICATION
def check_password():
    if st.session_state.get("password_correct", False): return True
    def password_entered():
        if st.session_state["password"] == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
    st.title("🔒 Access Protected")
    st.text_input("Password", type="password", on_change=password_entered, key="password")
    return False

if not check_password(): st.stop()

# 2. ISO MAPPING & CONFIG
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

@st.cache_data
def load_wb_db():
    with open("climate_WB_data.json", "r") as f:
        return json.load(f)

WB_DB = load_wb_db()
session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(total=3)))

# 3. DATA FETCHERS
@st.cache_data(ttl=86400)
def fetch_historical_climatology(iso3):
    """Fetches official 1991-2020 averages from World Bank Indicators API."""
    res = {"temp": None, "prec": None}
    try:
        t_url = f"https://api.worldbank.org/v2/country/{iso3}/indicator/EN.CLC.TEMP?format=json&date=1991:2020"
        r_t = session.get(t_url, timeout=5).json()
        if len(r_t) > 1 and r_t[1]:
            vals = [i['value'] for i in r_t[1] if i['value'] is not None]
            if vals: res["temp"] = sum(vals) / len(vals)
        
        p_url = f"https://api.worldbank.org/v2/country/{iso3}/indicator/EN.CLC.PRCP?format=json&date=1991:2020"
        r_p = session.get(p_url, timeout=5).json()
        if len(r_p) > 1 and r_p[1]:
            vals = [i['value'] for i in r_p[1] if i['value'] is not None]
            if vals: res["prec"] = sum(vals) / len(vals)
    except: pass
    return res

def get_wb_val(loc_id, var, scenario, period):
    try:
        m_key = '2020-07' if period == '2020-2039' else '2040-07'
        return WB_DB['data'][var][period][scenario][loc_id][m_key]
    except: return None

def analyze_location(lat, lon, manual_id=None):
    loc_info = rg.search((lat, lon))[0]
    iso3 = ISO_MAP.get(loc_info['cc'], "USA")
    target_id = manual_id if manual_id else iso3
    
    # Identify sub-regions for help-text
    sub_regions = [k for k in WB_DB['data']['tas']['2020-2039']['ssp245'].keys() if k.startswith(iso3)]
    hist = fetch_historical_climatology(iso3)
    
    res = {"Location": f"{loc_info['name']}, {loc_info['cc']}", "ID": target_id, "SubRegions": sub_regions, "Lat": lat, "Lon": lon}
    res.update({"T_Hist": hist['temp'], "P_Hist": hist['prec']})
    
    # Hazard Data (WRI)
    RISK_MAP = {
        "Baseline Water Stress": "c66d7f3a-d1a8-488f-af8b-302b0f2c3840",
        "Drought Risk": "5c9507d1-47f7-4c6a-9e64-fc210ccc48e2",
        "Riverine Flood": "df9ef304-672f-4c17-97f4-f9f8fa2849ff",
        "Coastal Flood": "d39919a9-0940-4038-87ac-662f944bc846"
    }
    for name, uuid in RISK_MAP.items():
        sql = f"SELECT * FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
        try:
            r = session.get(f"https://api.resourcewatch.org/v1/query/{uuid}", params={"sql": sql}, timeout=5)
            val = "N/A"
            if r.json().get('data'):
                val = next((v for k, v in r.json()['data'][0].items() if 'label' in k.lower()), "N/A")
            res[name] = val
        except: res[name] = "N/A"

    # Climate Projections
    for var in ['tas', 'pr']:
        for sc in ['ssp126', 'ssp245', 'ssp370']:
            for prd in ['2020-2039', '2040-2059']:
                res[f"{var}_{sc}_{prd}"] = get_wb_val(target_id, var, sc, prd)
    return res

# 4. STREAMLIT UI
st.set_page_config(page_title="Risk Intel", layout="wide")
st.markdown("<style>[data-testid='stMetricValue']{font-size:1.1rem !important; font-weight:700;}</style>", unsafe_allow_html=True)
st.title("🌍 Integrated Climate & Hazard Risk Portal")

t1, t2 = st.tabs(["📍 Analysis", "🚀 Batch Processing"])

with t1:
    with st.sidebar:
        lat_in = st.number_input("Latitude", value=25.2048, format="%.4f")
        lon_in = st.number_input("Longitude", value=55.2708, format="%.4f")
        sid_in = st.text_input("GADM ID (Optional)", placeholder="e.g. ARE.2553173")
        if st.button("Run Report"): st.session_state.rpt = analyze_location(lat_in, lon_in, sid_in)

    if 'rpt' in st.session_state:
        d = st.session_state.rpt
        st.map(pd.DataFrame({'lat': [lat_in], 'lon': [lon_in]}), zoom=7)
        st.info(f"📍 Location: **{d['Location']}**. Available IDs: `{', '.join(d['SubRegions'][:5])}...`")
        
        # Hazard Grid
        h1, h2 = st.columns(2); h3, h4 = st.columns(2)
        h1.metric("🌊 Water Stress", d["Baseline Water Stress"])
        h2.metric("🏜️ Drought Risk", d["Drought Risk"])
        h3.metric("🏠 Riverine Flood", d["Riverine Flood"])
        h4.metric("🏖️ Coastal Flood", d["Coastal Flood"])

        st.divider()
        st.subheader("🔮 Comparison: Historical vs. Future")
        def fm(v, u): return f"{v:.2f}{u}" if v else "N/A"
        
        res_table = [
            {"Scenario": "Optimistic (SSP1-2.6)", "Hist (91-20)": fm(d['T_Hist'], "C"), "T +10Y": fm(d['tas_ssp126_2020-2039'], "C"), "T +25Y": fm(d['tas_ssp126_2040-2059'], "C"), "P +10Y": fm(d['pr_ssp126_2020-2039'], "mm"), "P +25Y": fm(d['pr_ssp126_2040-2059'], "mm")},
            {"Scenario": "Moderate (SSP2-4.5)", "Hist (91-20)": fm(d['T_Hist'], "C"), "T +10Y": fm(d['tas_ssp245_2020-2039'], "C"), "T +25Y": fm(d['tas_ssp245_2040-2059'], "C"), "P +10Y": fm(d['pr_ssp245_2020-2039'], "mm"), "P +25Y": fm(d['pr_ssp245_2040-2059'], "mm")},
            {"Scenario": "High Risk (SSP3-7.0)", "Hist (91-20)": fm(d['T_Hist'], "C"), "T +10Y": fm(d['tas_ssp370_2020-2039'], "C"), "T +25Y": fm(d['tas_ssp370_2040-2059'], "C"), "P +10Y": fm(d['pr_ssp370_2020-2039'], "mm"), "P +25Y": fm(d['pr_ssp370_2040-2059'], "mm")}
        ]
        st.table(pd.DataFrame(res_table))

        # Trends
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Temperature Pathways (C)**")
            idx = ["91-20", "2030s", "2050s"]
            st.line_chart(pd.DataFrame({
                "SSP126": [d['T_Hist'], d['tas_ssp126_2020-2039'], d['tas_ssp126_2040-2059']],
                "SSP370": [d['T_Hist'], d['tas_ssp370_2020-2039'], d['tas_ssp370_2040-2059']]
            }, index=idx))
        with c2:
            st.write("**Precipitation Pathways (mm)**")
            st.line_chart(pd.DataFrame({
                "SSP126": [d['P_Hist'], d['pr_ssp126_2020-2039'], d['pr_ssp126_2040-2059']],
                "SSP370": [d['P_Hist'], d['pr_ssp370_2020-2039'], d['pr_ssp370_2040-2059']]
            }, index=idx))

with t2:
    st.markdown("### 🚀 Bulk Site Analysis")
    up = st.file_uploader("Upload CSV", type=["csv"])
    if up and st.button("Run Batch"):
        df_in = pd.read_csv(up)
        results = []
        prog = st.progress(0)
        for i, r in df_in.iterrows():
            results.append(analyze_location(r['latitude'], r['longitude']))
            prog.progress((i+1)/len(df_in))
        st.dataframe(pd.DataFrame(results))
