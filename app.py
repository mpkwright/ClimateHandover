@st.cache_data
def get_climate_data(lat, lon):
    # Setup Client
    cache_session = requests_cache.CachedSession('.cache', expire_after=3600*24)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    # 1. BASELINE (1991-2020)
    url_hist = "https://archive-api.open-meteo.com/v1/archive"
    params_hist = {
        "latitude": lat, "longitude": lon,
        "start_date": "1991-01-01", "end_date": "2020-12-31",
        "daily": ["temperature_2m_mean", "precipitation_sum"]
    }
    
    # 2. FUTURE (2021-2050)
    url_pro = "https://climate-api.open-meteo.com/v1/climate"
    params_pro = {
        "latitude": lat, "longitude": lon,
        "start_date": "2021-01-01", "end_date": "2050-12-31",
        "models": "MPI_ESM1_2_XR",
        "daily": ["temperature_2m_mean", "precipitation_sum"],
        "disable_bias_correction": "true" 
    }

    try:
        # -- Execute Historical --
        hist_resp = openmeteo.weather_api(url_hist, params=params_hist)[0]
        
        # -- Execute Future Scenarios --
        future_data = {}
        scenarios_to_fetch = {
            "ssp1_2_6": "SSP1-2.6 (Ambitious)",
            "ssp2_4_5": "SSP2-4.5 (Optimistic)",
            "ssp3_7_0": "SSP3-7.0 (BAU)"
        }
        
        for sc_key, sc_name in scenarios_to_fetch.items():
             p = params_pro.copy()
             p["scenarios"] = [sc_key]
             f_resp = openmeteo.weather_api(url_pro, params=p)[0]
             
             # Process Daily Data
             f_daily = f_resp.Daily()
             f_dates = pd.to_datetime(f_daily.Time(), unit="s", origin="unix")
             f_temps = f_daily.Variables(0).ValuesAsNumpy()
             f_precip = f_daily.Variables(1).ValuesAsNumpy()
             
             # Create DataFrame and SORT it to ensure slicing works
             df_f = pd.DataFrame({"temp": f_temps, "precip": f_precip}, index=f_dates)
             df_f = df_f.sort_index()
             
             # Decadal Slicing - USING .loc[] TO FIX THE ERROR
             # We also add a check to make sure data exists for that range
             future_data[sc_name] = {}
             
             # Slice 1: 2020s
             try:
                 d20 = df_f.loc['2021':'2030']
                 if not d20.empty:
                     future_data[sc_name]["2020s (2021-30)"] = {
                         "temp": d20["temp"].mean(),
                         "precip": d20["precip"].sum() / 10.0
                     }
             except: pass # Skip if missing
                 
             # Slice 2: 2030s
             try:
                 d30 = df_f.loc['2031':'2040']
                 if not d30.empty:
                     future_data[sc_name]["2030s (2031-40)"] = {
                         "temp": d30["temp"].mean(),
                         "precip": d30["precip"].sum() / 10.0
                     }
             except: pass

             # Slice 3: 2040s
             try:
                 d40 = df_f.loc['2041':'2050']
                 if not d40.empty:
                     future_data[sc_name]["2040s (2041-50)"] = {
                         "temp": d40["temp"].mean(),
                         "precip": d40["precip"].sum() / 10.0
                     }
             except: pass

        # -- Process Historical Baseline --
        h_daily = hist_resp.Daily()
        h_temps = h_daily.Variables(0).ValuesAsNumpy()
        h_precips = h_daily.Variables(1).ValuesAsNumpy()
        
        baseline_temp = h_temps.mean()
        baseline_precip = h_precips.sum() / 30.0 
        
        # Monthly Data for Chart
        dates = pd.to_datetime(h_daily.Time(), unit="s", origin="unix")
        df_h = pd.DataFrame({"temp": h_temps, "precip": h_precips}, index=dates)
        monthly = df_h.groupby(df_h.index.month).agg({"temp": "mean", "precip": "mean"})
        monthly["precip_total"] = monthly["precip"] *
