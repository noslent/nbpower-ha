#!/usr/bin/env python3
# client_nbpower.py

#To run this demo do the following
# python3 -m venv venv
# source venv/bin/activate
# pip install BeautifulSoup
# 
# (now to run it paste the following block)
# python3 - <<'EOF'
# import asyncio
# from client_nbpower import demo
# asyncio.run(demo("YourUsername", "YourPassword"))
# EOF
import asyncio
import json
from urllib.parse import urljoin
from typing import Optional, Dict, Any

import aiohttp
from bs4 import BeautifulSoup  # pip install aiohttp beautifulsoup4

BASE = "https://nbpower.com"
WIDGET_API = "https://nbp-svc.smartcmobile.com/WidgetAPI"

VALID_MODES = {"Mi", "H", "D", "M", "S"}   # 15min, Hourly, Daily, Monthly, Seasonal
VALID_TYPES = {"K", "D"}                    # Kilowatt(kWh/kW), Dollar($)

def _coerce_mode(mode: str) -> str:
    m = (mode or "").strip()
    if m not in VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(VALID_MODES)}")
    return m

def _coerce_type(tp: str) -> str:
    t = (tp or "").strip().upper()
    if t not in VALID_TYPES:
        raise ValueError(f"type must be one of {sorted(VALID_TYPES)}")
    return t

class NBPowerClient:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    # --- helpers ---
    def _get_session_id(self) -> Optional[str]:
        cookies = self.session.cookie_jar.filter_cookies(BASE)
        morsel = cookies.get("sessionId")
        return morsel.value if morsel and getattr(morsel, "value", None) else None

    # --- flow ---
    async def prime_session(self) -> bool:
        """
        1) GET /Default.aspx
        2) POST English button with:
           __VIEWSTATE, __VIEWSTATEGENERATOR, __EVENTVALIDATION, btnEnglish=English
        """
        default_url = f"{BASE}/Default.aspx"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": BASE + "/",
            "Origin": BASE,
        }

        async with self.session.get(default_url, headers=headers) as r:
            html = await r.text()

        soup = BeautifulSoup(html, "html.parser")
        form = soup.find("form")
        if not form:
            print("prime_session: no <form> on Default.aspx")
            return False

        formfields = {
            i.get("name"): i.get("value", "")
            for i in form.find_all("input")
            if i.get("name")
        }

        data = {
            "__VIEWSTATE": formfields.get("__VIEWSTATE", ""),
            "__VIEWSTATEGENERATOR": formfields.get("__VIEWSTATEGENERATOR", ""),
            "__EVENTVALIDATION": formfields.get("__EVENTVALIDATION", ""),
            "btnEnglish": "English",
        }

        post_headers = {
            **headers,
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": default_url,
        }

        action = form.get("action") or default_url
        post_url = urljoin(default_url, action)
        async with self.session.post(
            post_url, data=data, headers=post_headers, allow_redirects=True
        ) as r2:
            _ = await r2.text()
            print("prime_session:", r2.status, r2.url)
            print("SessionId (primed):", self._get_session_id())
            return r2.status in (200, 302)

    async def login(self, username: str, password: str) -> bool:
        """
        WebForms login: scrape inputs, POST back with creds (keeps session cookies).
        """
        login_url = f"{BASE}/auth/weblogin.aspx"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": login_url,
            "Origin": BASE,
        }

        async with self.session.get(login_url, headers=headers) as r:
            html = await r.text()
            print("SessionId (before login):", self._get_session_id())

        soup = BeautifulSoup(html, "html.parser")
        form = soup.find("form")
        if not form:
            print("login: no <form> found")
            return False

        data = {
            i.get("name"): i.get("value", "")
            for i in form.find_all("input")
            if i.get("name")
        }

        # Known field names with fallbacks by type
        if "ctl00$contentPlaceHolder$txtUsername" in data:
            data["ctl00$contentPlaceHolder$txtUsername"] = username
        else:
            u = form.select_one('input[type="text"], input[type="email"]')
            if u and u.get("name"):
                data[u["name"]] = username

        if "ctl00$contentPlaceHolder$txtPassword" in data:
            data["ctl00$contentPlaceHolder$txtPassword"] = password
        else:
            p = form.select_one('input[type="password"]')
            if p and p.get("name"):
                data[p["name"]] = password

        if "ctl00$contentPlaceHolder$btnLogin" in data:
            # ensure a value
            data["ctl00$contentPlaceHolder$btnLogin"] = data.get(
                "ctl00$contentPlaceHolder$btnLogin", "Login"
            )
        else:
            btn = form.select_one('input[type="submit"], button[type="submit"]')
            if btn and btn.get("name"):
                data[btn["name"]] = btn.get("value", "Login")

        # Optional captcha hidden value
        if "ctl00$contentPlaceHolder$hdnCaptchaText" in data:
            data["ctl00$contentPlaceHolder$hdnCaptchaText"] = data.get(
                "ctl00$contentPlaceHolder$hdnCaptchaText",
                "BotDetect CAPTCHA ASP.NET Form Validation",
            )

        # Optional search inputs
        for k in ("ctl00$txtSearchMobile", "ctl00$txtSearch"):
            if k in data:
                data[k] = ""

        post_headers = {
            **headers,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        action = form.get("action") or login_url
        post_url = urljoin(login_url, action)
        async with self.session.post(
            post_url, data=data, headers=post_headers, allow_redirects=True
        ) as r2:
            html2 = await r2.text()
            print("SessionId (after login):", self._get_session_id())
            print("login:", r2.status, r2.url)
            if "weblogin.aspx" in str(r2.url).lower() or "Cookies required" in html2:
                return False
            return True

    async def get_account_token(self) -> Optional[str]:
        """
        Parse token from AccountSummaryView.aspx (preferred).
        """
        url = f"{BASE}/Customer/AccountSummaryView.aspx"
        async with self.session.get(url) as r:
            html = await r.text()

        soup = BeautifulSoup(html, "html.parser")
        form = soup.find("form")
        if not form:
            return None

        formfields = {
            i.get("name"): i.get("value", "")
            for i in form.find_all("input")
            if i.get("name")
        }
        # Specific hidden input observed
        return formfields.get("ctl00$contentPlaceHolder$ucConsumptionGraph$accountSEWToken")

    async def get_token(self) -> Optional[str]:
        """
        Fallback WidgetAPI token fetch.
        """
        url = f"{WIDGET_API}/Token/GetToken"
        headers = {
            "Origin": BASE,
            "Referer": f"{BASE}/Customer/AccountSummaryView.aspx",
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
        }
        async with self.session.post(url, json={"Utility": "NBPower"}, headers=headers) as r:
            txt = await r.text()
            print("token resp:", txt)
            if r.status != 200:
                return None
            try:
                j = json.loads(txt)
            except Exception:
                return None
            return j.get("result", {}).get("Token") or j.get("Token")

    async def verify_token(self, token: str) -> Optional[dict]:
        """
        Return the JSON body from VerifyToken (or a {'raw':..., 'status':...} fallback).
        """
        url = f"{WIDGET_API}/Token/VerifyToken"
        headers = {
            "Origin": BASE,
            "Referer": f"{BASE}/Customer/AccountSummaryView.aspx",
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
        }
        payload = {"Token": token}
        async with self.session.post(url, json=payload, headers=headers) as r:
            txt = await r.text()
            try:
                return json.loads(txt)
            except json.JSONDecodeError:
                return {"raw": txt, "status": r.status}

    async def meter_info(
        self,
        token: str,
        account_number: str,
        utility_account_number: str,
    ) -> Optional[dict]:
        """
        Return JSON from GetMultiMeter (or {'raw', 'status'} on non-JSON).
        """
        url = f"{WIDGET_API}/Usage/GetMultiMeter"
        headers = {
            "Origin": BASE,
            "Referer": f"{BASE}/",
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
            "Token": token,
        }
        payload = {
            "Token": token,
            "AccountNumber": account_number,
            "UtilityAccountNumber": utility_account_number,
            "MeterType": "E",
        }
        async with self.session.post(url, json=payload, headers=headers) as r:
            txt = await r.text()
            try:
                return json.loads(txt)
            except json.JSONDecodeError:
                return {"raw": txt, "status": r.status}

    async def get_usage(
        self,
        token: str,
        account_number: str,
        utility_account_number: str,
        meter_number: str = "",
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        usage_type: str = "e",
    ) -> Dict[str, Any]:
        url = f"{WIDGET_API}/Usage/GetUsageGeneration"
        payload = {
            "Type": "K",
            "Mode": "M",
            "strdate": None,
            "enddate": None,
            "date": None,
            "hourlyType": "H",
            "seasonId": "",
            "weatherOverlay": 1,
            "usageyear": "",
            "MeterNumber": meter_number,
            "DateFromDaily": date_from or "",
            "DateToDaily": date_to or "",
            "IsNetUsage": "false",
            "IsNewUsageApi": "true",
            "usageType": usage_type,
            "LanguageCode": "EN",
            "Token": token,
            "AccountNumber": account_number,
            "UtilityAccountNumber": utility_account_number,
            "UserType": "Residential",
            "Uom": "kW",
            "RatePlanCategoryName": "RES_RURAL",
        }
        headers = {
            "Content-Type": "application/json",
            "Origin": BASE,
            "Referer": BASE + "/",
            "User-Agent": "Mozilla/5.0",
            "Token": token,
        }
        async with self.session.post(url, json=payload, headers=headers) as resp:
            print("usage status:", resp.status)
            txt = await resp.text()
            if resp.status != 200:
                print("usage error:", txt)
                return {}
            j = json.loads(txt)
            result = j.get("result") or j
            data = result.get("Data")
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    pass
            return {"result": result, "data": data, "raw": j}

    # drop-in alongside your get_usage(): same endpoint, but parametric
    async def get_usage_data(
        self,
        token: str,
        account_number: str,
        utility_account_number: str,
        meter_number: str = "",
        *,
        mode: str = "M",         # Mi|H|D|M|S
        rtype: str = "K",        # K (kWh/kW) or D ($)
        date_from: Optional[str] = None,  # "YYYY-MM-DD" or API’s expected format
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        mode = _coerce_mode(mode)
        rtype = _coerce_type(rtype)

        url = f"{WIDGET_API}/Usage/GetUsageGeneration"
        payload = {
            # keep your defaults, but set Mode + usageType + dates dynamically
            "Type": rtype,              # K or D
            "Mode": mode,               # Mi/H/D/M/S
            "strdate": None,
            "enddate": None,
            "date": None,
            "hourlyType": "H",
            "seasonId": "",
            "weatherOverlay": 1,
            "usageyear": "",
            "MeterNumber": meter_number,
            "DateFromDaily": date_from or "",
            "DateToDaily": date_to or "",
            "IsNetUsage": "false",
            "IsNewUsageApi": "true",
            "usageType": "e",           # electricity
            "LanguageCode": "EN",
            "Token": token,
            "AccountNumber": account_number,
            "UtilityAccountNumber": utility_account_number,
            "UserType": "Residential",
            "Uom": "kW",
            "RatePlanCategoryName": "RES_RURAL",
        }
        headers = {
            "Content-Type": "application/json",
            "Origin": BASE,
            "Referer": BASE + "/",
            "User-Agent": "Mozilla/5.0",
            "Token": token,
        }
        async with self.session.post(url, json=payload, headers=headers) as resp:
            txt = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"usage {resp.status}: {txt}")
            j = json.loads(txt)
            result = j.get("result") or j
            data = result.get("Data")
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    pass
            return {"result": result, "data": data, "raw": j}


async def demo(username: str, password: str):
    async with aiohttp.ClientSession() as sess:
        c = NBPowerClient(sess)

        primed = await c.prime_session()
        print("primed:", primed)

        ok = await c.login(username, password)
        print("login ok:", ok)
        if not ok:
            return

        # Prefer token parsed from AccountSummaryView.aspx; fallback if needed
        token = await c.get_account_token()
        print("token:", "<obtained>" if token else None)
        if not token:
            token = await c.get_token()
            print("fallback token:", "<obtained>" if token else None)
        if not token:
            return

        verify_result = await c.verify_token(token)
        print("verify result:", verify_result)
        if not verify_result or not isinstance(verify_result, dict):
            return

        # pull account numbers from verify payload
        result = verify_result.get("result", {})
        data = result.get("Data", {}) if isinstance(result, dict) else {}
        account_number = data.get("AccountNumber", "")
        utility_account_number = data.get("UtilityAccountNumber", "")

        # meter details
        meter_result = await c.meter_info(token, account_number, utility_account_number)
        if not meter_result or not isinstance(meter_result, dict):
            return
        m_result = meter_result.get("result", {}) if isinstance(meter_result, dict) else {}
        m_details = m_result.get("MeterDetails") or []
        meter_number = ""
        if isinstance(m_details, list) and m_details:
            meter_number = m_details[0].get("MeterNumber", "")

        # Monthly kWh between two dates
        res = await c.get_usage_data(
            token, account_number, utility_account_number, meter_number,
            mode="M", rtype="K", date_from="2025-08-20", date_to="2025-10-15"
        )
        rows = normalize_usage_payload(res)
        print("Monthly rows:", rows[:3])

        # Daily dollars for the last cycle
        res_dollars = await c.get_usage_data(
            token, account_number, utility_account_number, meter_number,
            mode="D", rtype="D", date_from="2025-09-13", date_to="2025-10-15"
        )
        rows_dollars = normalize_usage_payload(res_dollars)
        print("Daily $ rows:", rows_dollars[:3])

        # 15-minute intervals (Mi) — beware of volume
        res_15m = await c.get_usage_data(
            token, account_number, utility_account_number, meter_number,
            mode="Mi", rtype="K", date_from="2025-10-01", date_to="2025-10-02"
        )
        rows_15m = normalize_usage_payload(res_15m)
        print("15-min rows:", len(rows_15m))

        res = await c.get_usage_data(token, account_number, utility_account_number, meter_number,
                                    mode="M", rtype="K", date_from="2025-10-01", date_to="2025-10-31")
        mtd = extract_tentative(res)
        print("MTD:", mtd)

        # usage = await c.get_usage(token, account_number, utility_account_number, meter_number)
        # if usage:
        #     print("usage keys:", list(usage["data"].keys()) if isinstance(usage["data"], dict) else type(usage["data"]))

def normalize_usage_payload(payload: Dict[str, Any]) -> list[dict]:
    """
    Returns a list of rows:
      - For K: {'start': iso, 'end': iso|None, 'kwh': float|None, 'kw': float|None, 'amount': None}
      - For D: {'start': iso, 'end': iso|None, 'kwh': None, 'kw': None, 'amount': float|None}
    Tries common keys seen in objUsageGenerationResultSetTwo (intervals) and ...One/Three (meta/ranges).
    """
    data = (payload or {}).get("data") or {}
    rows = []

    # Interval/period list frequently lives here:
    series = data.get("objUsageGenerationResultSetTwo") or data.get("objUsageGenerationResultSetOne") or []
    if isinstance(series, list):
        for it in series:
            # Dates: prefer ISO-ish if present; fall back to 'UsageDate' or 'FromDate'
            start = it.get("UsageDate") or it.get("FromDate") or it.get("WeatherUsageDate")
            end = it.get("ToDate")  # monthly/daily often have a range
            # Energy / demand / dollars
            kwh = it.get("Consumption") or it.get("UsageValue")
            kw = it.get("DemandValue") or it.get("MaxDemand")
            amount = it.get("Amount")  # for Type D, but sometimes present even with K

            # coerce numeric if strings
            def _num(v):
                if v is None:
                    return None
                try:
                    return float(str(v).replace(",", ""))
                except:
                    return None

            rows.append({
                "start": start,
                "end": end,
                "kwh": _num(kwh),
                "kw": _num(kw),
                "amount": _num(amount),
                "month": it.get("Month"),
                "year": it.get("Year"),
                "billing_days": it.get("BillingDays"),
            })

    return rows

def extract_tentative(payload: dict) -> dict:
    """
    Returns month-to-date + projection from getTentativeData.
    Keys present (when available):
      so_far_kwh, so_far_dollars, projected_kwh, projected_dollars,
      peak_load_kw, average_kw, highest_kw
    """
    data = (payload or {}).get("data") or {}
    arr = data.get("getTentativeData") or []
    if not arr or not isinstance(arr, list) or not isinstance(arr[0], dict):
        return {}
    d = arr[0]
    def _num(v):
        try:
            return float(str(v).replace(",", "")) if v is not None else None
        except Exception:
            return None
    return {
        "so_far_kwh": _num(d.get("SoFar")),
        "so_far_dollars": _num(d.get("SoFarDollar")),
        "projected_kwh": _num(d.get("ExpectedUsage")),
        "projected_dollars": _num(d.get("ProjectedBillDollar")),
        "peak_load_kw": _num(d.get("PeakLoad")),
        "average_kw": _num(d.get("Average")),
        "highest_kw": _num(d.get("Highest")),
    }


if __name__ == "__main__":
    # fill these in before running
    asyncio.run(demo("YOUR_USERNAME", "YOUR_PASSWORD"))
