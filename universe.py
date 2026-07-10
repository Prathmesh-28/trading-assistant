"""Market universe: index list + NIFTY 50 constituents (NSE trading symbols).

Static by design — constituents churn a few names a year; edit here when they
do. The dashboard's Markets tab reads these through /api/market."""

# (trading_symbol, display name)
NIFTY50 = [
    ("RELIANCE", "Reliance Industries"), ("HDFCBANK", "HDFC Bank"),
    ("ICICIBANK", "ICICI Bank"), ("INFY", "Infosys"), ("TCS", "TCS"),
    ("ITC", "ITC"), ("LT", "Larsen & Toubro"), ("KOTAKBANK", "Kotak Mahindra Bank"),
    ("AXISBANK", "Axis Bank"), ("SBIN", "State Bank of India"),
    ("BHARTIARTL", "Bharti Airtel"), ("ASIANPAINT", "Asian Paints"),
    ("MARUTI", "Maruti Suzuki"), ("HCLTECH", "HCL Technologies"),
    ("SUNPHARMA", "Sun Pharma"), ("TITAN", "Titan"), ("ULTRACEMCO", "UltraTech Cement"),
    ("WIPRO", "Wipro"), ("NESTLEIND", "Nestle India"), ("POWERGRID", "Power Grid"),
    ("NTPC", "NTPC"), ("TATAMOTORS", "Tata Motors"), ("M&M", "Mahindra & Mahindra"),
    ("BAJFINANCE", "Bajaj Finance"), ("BAJAJFINSV", "Bajaj Finserv"),
    ("TECHM", "Tech Mahindra"), ("ADANIENT", "Adani Enterprises"),
    ("ADANIPORTS", "Adani Ports"), ("COALINDIA", "Coal India"),
    ("HINDALCO", "Hindalco"), ("JSWSTEEL", "JSW Steel"), ("TATASTEEL", "Tata Steel"),
    ("DRREDDY", "Dr Reddy's Labs"), ("CIPLA", "Cipla"), ("DIVISLAB", "Divi's Labs"),
    ("APOLLOHOSP", "Apollo Hospitals"), ("EICHERMOT", "Eicher Motors"),
    ("HEROMOTOCO", "Hero MotoCorp"), ("BAJAJ-AUTO", "Bajaj Auto"),
    ("BRITANNIA", "Britannia"), ("GRASIM", "Grasim"), ("HDFCLIFE", "HDFC Life"),
    ("SBILIFE", "SBI Life"), ("INDUSINDBK", "IndusInd Bank"), ("ONGC", "ONGC"),
    ("BPCL", "BPCL"), ("UPL", "UPL"), ("TATACONSUM", "Tata Consumer"),
    ("LTIM", "LTIMindtree"), ("SHRIRAMFIN", "Shriram Finance"),
]

NAMES = dict(NIFTY50)

# Indices shown on the dashboard strip. Groww serves NSE indices through the
# same quote API with these trading symbols; SENSEX is BSE.
INDICES = [
    ("NIFTY", "NIFTY 50", "NSE"),
    ("SENSEX", "SENSEX", "BSE"),
    ("BANKNIFTY", "BANK NIFTY", "NSE"),
]


def group_symbols(group: str, watchlist: list) -> list:
    if group == "nifty50":
        return [s for s, _ in NIFTY50]
    return list(watchlist)
