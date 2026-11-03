import time
import pandas as pd
import requests
from requests.exceptions import ConnectionError, JSONDecodeError, Timeout


class VajraAnalyticsClone:

  def __init__(self, symbol="NIFTY"):
    self.symbol = symbol.upper()
    # Symbol ke anusar sahi endpoint select karna
    if self.symbol in ["NIFTY", "BANKNIFTY", "FINNIFTY"]:
      self.base_url = (
          f"https://www.nseindia.com/api/option-chain-indices?symbol={self.symbol}"
      )
    else:
      self.base_url = (
          f"https://www.nseindia.com/api/option-chain-equities?symbol={self.symbol}"
      )

    self.headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    self.session = requests.Session()

  def connect_nse(self):
    """NSE session cookies establish karne ke liye initial request with error handling"""
    try:
      response = self.session.get(
          "https://www.nseindia.com", headers=self.headers, timeout=10
      )
      response.raise_for_status()
      return True
    except (ConnectionError, Timeout) as e:
      print(f"[Error] Network connection failed during session init: {e}")
      return False
    except Exception as e:
      print(f"[Error] Unexpected error during connection: {e}")
      return False

  def fetch_option_chain_data(self, retries=3, delay=2):
    """Retry mechanism aur robust error handling ke sath option chain fetch karna"""
    for attempt in range(1, retries + 1):
      if not self.connect_nse():
        print(
            f"[Retry {attempt}/{retries}] Reconnecting to NSE homepage in"
            f" {delay}s..."
        )
        time.sleep(delay)
        continue

      try:
        response = self.session.get(
            self.base_url, headers=self.headers, timeout=10
        )

        if response.status_code == 200:
          return response.json()
        elif response.status_code in [401, 403]:
          print(
              f"[Warning] Access blocked or unauthorized (Status:"
              f" {response.status_code}). Retrying..."
          )
        else:
          print(
              f"[Warning] Server responded with status code:"
              f" {response.status_code}"
          )

      except Timeout:
        print(f"[Error] Request timeout on attempt {attempt}.")
      except ConnectionError:
        print(f"[Error] Connection error occurred on attempt {attempt}.")
      except JSONDecodeError:
        print("[Error] Failed to parse JSON response from NSE.")
      except Exception as e:
        print(f"[Error] An unexpected error occurred: {e}")

      time.sleep(delay)

    print("[Critical] Failed to fetch option chain data after multiple retries.")
    return None

  def analyze_base_levels(self, json_data):
    """Safe data parsing with KeyError and empty data checks"""
    if not json_data or not isinstance(json_data, dict):
      print("[Error] Invalid or empty JSON data received.")
      return None

    try:
      records = json_data.get("records")
      if not records or "data" not in records:
        print("[Error] 'records' or 'data' key missing in API response.")
        return None

      data = records["data"]
      strike_list = []

      for item in data:
        if not isinstance(item, dict):
          continue
        if "CE" in item and "PE" in item:
          ce = item["CE"]
          pe = item["PE"]
          strike_list.append({
              "StrikePrice": item.get("strikePrice"),
              "CE_OI": ce.get("openInterest", 0),
              "CE_ChgOI": ce.get("changeinOpenInterest", 0),
              "CE_Volume": ce.get("totalTradedVolume", 0),
              "PE_OI": pe.get("openInterest", 0),
              "PE_ChgOI": pe.get("changeinOpenInterest", 0),
              "PE_Volume": pe.get("totalTradedVolume", 0),
          })

      if not strike_list:
        print("[Warning] No valid strike data found in the records.")
        return None

      df = pd.DataFrame(strike_list)

      if (
          df.empty
          or "CE_Volume" not in df.columns
          or "PE_Volume" not in df.columns
      ):
        print("[Error] DataFrame is empty or required columns are missing.")
        return None

      max_ce_volume_row = df.loc[df["CE_Volume"].idxmax()]
      max_pe_volume_row = df.loc[df["PE_Volume"].idxmax()]

      cip = max_ce_volume_row["StrikePrice"]
      pip = max_pe_volume_row["StrikePrice"]

      return {
          "CIP": cip,
          "PIP": pip,
          "CE_Data": max_ce_volume_row,
          "PE_Data": max_pe_volume_row,
      }

    except KeyError as e:
      print(f"[Error] Missing expected key in data structure: {e}")
      return None
    except Exception as e:
      print(f"[Error] Error during data analysis: {e}")
      return None

  def calculate_zones(self, cip, pip):
    if cip is None or pip is None:
      print("[Error] Cannot calculate zones due to missing base levels.")
      return None
    try:
      return {
          "Supply Zone 2": cip + 50,
          "Supply Zone 1": cip,
          "Demand Zone 1": pip,
          "Demand Zone 2": pip - 50,
      }
    except Exception as e:
      print(f"[Error] Zone calculation failed: {e}")
      return None

  def risk_management_rule(self, entry_price, stop_loss_pts=30):
    if entry_price is None:
      return None
    try:
      sl = entry_price - stop_loss_pts
      target_1 = entry_price + (stop_loss_pts * 1.5)
      target_2 = entry_price + (stop_loss_pts * 2)

      return {
          "Entry Price": entry_price,
          "Stop Loss": sl,
          "Target 1 (1:1.5)": target_1,
          "Target 2 (1:2)": target_2,
      }
    except Exception as e:
      print(f"[Error] Risk management calculation failed: {e}")
      return None


# --- Execution Example ---
if __name__ == "__main__":
  strategy = VajraAnalyticsClone(symbol="NIFTY")

  print("Fetching live Option Chain & calculating Vajra levels securely...")
  raw_data = strategy.fetch_option_chain_data()

  if raw_data:
    levels = strategy.analyze_base_levels(raw_data)
    if levels:
      print(f"\n--- Identified Base Levels ---")
      print(f"CIP (Call Base / Resistance): {levels['CIP']}")
      print(f"PIP (Put Base / Support): {levels['PIP']}")

      zones = strategy.calculate_zones(levels["CIP"], levels["PIP"])
      if zones:
        print(f"\n--- Calculated Chart Zones ---")
        for zone_name, price in zones.items():
          print(f"{zone_name}: {price}")

      trade_plan = strategy.risk_management_rule(
          entry_price=levels["PIP"], stop_loss_pts=30
      )
      if trade_plan:
        print(f"\n--- Risk Management Setup ---")
        for k, v in trade_plan.items():
          print(f"{k}: {v}")
  else:
    print(
        "[Info] Execution stopped due to failure in fetching option chain data."
          )
        
