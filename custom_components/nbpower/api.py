import json
from datetime import date, timedelta
from typing import Optional, Dict, Any
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from .const import BASE, WIDGET_API

VALID_MODES = {"Mi", "H", "D", "M", "S"}  # 15min, Hourly, Daily, Monthly, Seasonal
VALID_TYPES = {"K", "D"}                  # K (kWh/kW), D (dollars)


def _num(v):
    if v is None:
        return None
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return None


def first_of_month_iso(today: date) -> str:
    return today.replace(day=1).isoformat()


class NBPowerClient:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self._token: Optional[str] = None
        self._account_number: Optional[str] = None
        self._utility_account_number: Optional[str] = None
        self._meter_number: Optional[str] = None

    @property
    def account_number(self) -> Optional[str]:
        """Return the cached account number, if available."""

        return self._account_number

    @property
    def utility_account_number(self) -> Optional[str]:
        """Return the cached utility account number, if available."""

        return self._utility_account_number

    @property
    def meter_number(self) -> Optional[str]:
        """Return the cached meter number, if available."""

        return self._meter_number

    # ---- Session priming & login ----
    async def prime_session(self) -> bool:
        default_url = f"{BASE}/Default.aspx"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": BASE + "/", "Origin": BASE}
        async with self.session.get(default_url, headers=headers) as r:
            html = await r.text()
        soup = BeautifulSoup(html, "html.parser")
        form = soup.find("form")
        if not form:
            return False
        formfields = {i.get("name"): i.get("value", "") for i in form.find_all("input") if i.get("name")}
        data = {
            "__VIEWSTATE": formfields.get("__VIEWSTATE", ""),
            "__VIEWSTATEGENERATOR": formfields.get("__VIEWSTATEGENERATOR", ""),
            "__EVENTVALIDATION": formfields.get("__EVENTVALIDATION", ""),
            "btnEnglish": "English",
        }
        post_headers = {**headers, "Content-Type": "application/x-www-form-urlencoded", "Referer": default_url}
        action = form.get("action") or default_url
        post_url = urljoin(default_url, action)
        async with self.session.post(post_url, data=data, headers=post_headers, allow_redirects=True) as r2:
            return r2.status in (200, 302)

    async def login(self, username: str, password: str) -> bool:
        login_url = f"{BASE}/auth/weblogin.aspx"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": login_url, "Origin": BASE}
        async with self.session.get(login_url, headers=headers) as r:
            html = await r.text()
        soup = BeautifulSoup(html, "html.parser")
        form = soup.find("form")
        if not form:
            return False

        data = {i.get("name"): i.get("value", "") for i in form.find_all("input") if i.get("name")}
        # Known names with fallbacks
        user_in = "ctl00$contentPlaceHolder$txtUsername"
        pass_in = "ctl00$contentPlaceHolder$txtPassword"
        if user_in in data:
            data[user_in] = username
        else:
            u = form.select_one('input[type="text"], input[type="email"]')
            if u and u.get("name"):
                data[u["name"]] = username
        if pass_in in data:
            data[pass_in] = password
        else:
            p = form.select_one('input[type="password"]')
            if p and p.get("name"):
                data[p["name"]] = password
        if "ctl00$contentPlaceHolder$btnLogin" in data:
            data["ctl00$contentPlaceHolder$btnLogin"] = data.get("ctl00$contentPlaceHolder$btnLogin", "Login")
        else:
            btn = form.select_one('input[type="submit"], button[type="submit"]')
            if btn and btn.get("name"):
                data[btn["name"]] = btn.get("value", "Login")
        if "ctl00$contentPlaceHolder$hdnCaptchaText" in data:
            data["ctl00$contentPlaceHolder$hdnCaptchaText"] = data.get(
                "ctl00$contentPlaceHolder$hdnCaptchaText",
                "BotDetect CAPTCHA ASP.NET Form Validation",
            )
        for k in ("ctl00$txtSearchMobile", "ctl00$txtSearch"):
            if k in data:
                data[k] = ""

        post_headers = {**headers, "Content-Type": "application/x-www-form-urlencoded"}
        action = form.get("action") or login_url
        post_url = urljoin(login_url, action)
        async with self.session.post(post_url, data=data, headers=post_headers, allow_redirects=True) as r2:
            html2 = await r2.text()
            if "weblogin.aspx" in str(r2.url).lower() or "Cookies required" in html2:
                return False
            return True

    # ---- Token & account/meter discovery ----
    async def get_account_token(self) -> Optional[str]:
        url = f"{BASE}/Customer/AccountSummaryView.aspx"
        async with self.session.get(url) as r:
            html = await r.text()
        soup = BeautifulSoup(html, "html.parser")
        form = soup.find("form")
        if not form:
            return None
        fields = {i.get("name"): i.get("value", "") for i in form.find_all("input") if i.get("name")}
        return fields.get("ctl00$contentPlaceHolder$ucConsumptionGraph$accountSEWToken")

    async def verify_token(self, token: str) -> Optional[dict]:
        url = f"{WIDGET_API}/Token/VerifyToken"
        headers = {"Origin": BASE, "Referer": f"{BASE}/Customer/AccountSummaryView.aspx", "User-Agent": "Mozilla/5.0",
                   "Content-Type": "application/json"}
        async with self.session.post(url, json={"Token": token}, headers=headers) as r:
            txt = await r.text()
            try:
                return json.loads(txt)
            except json.JSONDecodeError:
                return {"raw": txt, "status": r.status}

    async def meter_info(self, token: str, account_number: str, utility_account_number: str) -> Optional[dict]:
        url = f"{WIDGET_API}/Usage/GetMultiMeter"
        headers = {"Origin": BASE, "Referer": f"{BASE}/", "User-Agent": "Mozilla/5.0",
                   "Content-Type": "application/json", "Token": token}
        payload = {"Token": token, "AccountNumber": account_number,
                   "UtilityAccountNumber": utility_account_number, "MeterType": "E"}
        async with self.session.post(url, json=payload, headers=headers) as r:
            txt = await r.text()
            try:
                return json.loads(txt)
            except json.JSONDecodeError:
                return {"raw": txt, "status": r.status}

    # ---- Usage (parametric) ----
    async def get_usage_data(
        self,
        token: str,
        account_number: str,
        utility_account_number: str,
        meter_number: str,
        *,
        mode: str = "M",   # Mi/H/D/M/S
        rtype: str = "K",  # K or D
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        if mode not in VALID_MODES:
            raise ValueError(f"mode must be one of {sorted(VALID_MODES)}")
        rtype = (rtype or "K").upper()
        if rtype not in VALID_TYPES:
            raise ValueError(f"type must be one of {sorted(VALID_TYPES)}")

        url = f"{WIDGET_API}/Usage/GetUsageGeneration"
        payload = {
            "Type": rtype,
            "Mode": mode,
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
            "usageType": "e",
            "LanguageCode": "EN",
            "Token": token,
            "AccountNumber": account_number,
            "UtilityAccountNumber": utility_account_number,
            "UserType": "Residential",
            "Uom": "kW",
            "RatePlanCategoryName": "RES_RURAL",
        }
        headers = {"Content-Type": "application/json", "Origin": BASE, "Referer": BASE + "/",
                   "User-Agent": "Mozilla/5.0", "Token": token}
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

    # ---- Normalizers ----
    @staticmethod
    def extract_tentative(payload: dict) -> dict:
        """Pull MTD + projection from getTentativeData."""
        data = (payload or {}).get("data") or {}
        arr = data.get("getTentativeData") or []
        if not arr or not isinstance(arr, list) or not isinstance(arr[0], dict):
            return {}
        d = arr[0]
        return {
            "so_far_kwh": _num(d.get("SoFar")),
            "so_far_dollars": _num(d.get("SoFarDollar")),
            "projected_kwh": _num(d.get("ProjectedBill")),
            "projected_dollars": _num(d.get("ProjectedBillDollar")),
            "peak_load_kw": _num(d.get("PeakLoad")),
            "average_kw": _num(d.get("Average")),
            "highest_kw": _num(d.get("Highest")),
        }

    @staticmethod
    def extract_mi_day(payload: dict, target_date: Optional[date] = None) -> dict:
        """Return a summary for a 15-minute (Mi) usage payload."""

        data = (payload or {}).get("data") or {}
        intervals = data.get("objUsageGenerationResultSetTwo")
        if not isinstance(intervals, list) or not intervals:
            return {}

        interval_list: list[dict[str, Any]] = []
        total_kwh = 0.0
        total_cost = 0.0
        peak_demand = None
        usage_present = False
        cost_present = False

        for row in intervals:
            usage = _num(row.get("UsageValue"))
            if usage is None:
                usage = _num(row.get("Consumption"))
            demand = _num(row.get("DemandValue"))
            amount = _num(row.get("Amount"))

            if usage is not None:
                total_kwh += usage
                usage_present = True
            if amount is not None:
                total_cost += amount
                cost_present = True
            if demand is not None:
                peak_demand = demand if peak_demand is None else max(peak_demand, demand)

            interval_list.append(
                {
                    "time": row.get("Hourly"),
                    "usage_kwh": usage,
                    "demand_kw": demand,
                    "cost": amount,
                    "status": row.get("ValidationStatus"),
                }
            )

        result: dict[str, Any] = {
            "mi_last_date": target_date.isoformat() if isinstance(target_date, date) else None,
            "mi_interval_count": len(interval_list),
            "mi_interval_data": interval_list,
        }

        if usage_present:
            result["mi_last_total_kwh"] = round(total_kwh, 3)
        if cost_present:
            result["mi_last_total_cost"] = round(total_cost, 2)
        if peak_demand is not None:
            result["mi_peak_demand_kw"] = peak_demand

        return result

    # ---- One-shot bootstrap used by the coordinator ----
    async def ensure_bootstrap(
        self,
        username: str,
        password: str,
        *,
        account_number: Optional[str] = None,
        utility_account_number: Optional[str] = None,
        meter_number: Optional[str] = None,
    ) -> None:
        if not await self.prime_session():
            raise RuntimeError("Failed to prime session")
        if not await self.login(username, password):
            raise RuntimeError("Login failed")
        token = await self.get_account_token()
        if not token:
            raise RuntimeError("Token not found in account page")
        self._token = token
        if account_number and utility_account_number:
            self._account_number = account_number
            self._utility_account_number = utility_account_number
            if meter_number is not None:
                self._meter_number = meter_number
            return
        v = await self.verify_token(token)
        result = (v or {}).get("result", {})
        data = result.get("Data", {}) if isinstance(result, dict) else {}
        self._account_number = data.get("AccountNumber")
        self._utility_account_number = data.get("UtilityAccountNumber")
        if not (self._account_number and self._utility_account_number):
            raise RuntimeError("Missing account identifiers from VerifyToken")
        m = await self.meter_info(token, self._account_number, self._utility_account_number)
        md = (m or {}).get("result", {}).get("MeterDetails") or []
        if isinstance(md, list) and md:
            self._meter_number = md[0].get("MeterNumber") or ""
        else:
            self._meter_number = ""

    async def fetch_mtd(self, today: Optional[date] = None) -> dict:
        """Return tentative (MTD) block using monthly mode."""
        if not all([self._token, self._account_number, self._utility_account_number]):
            raise RuntimeError("Client not bootstrapped")
        if not self._meter_number:
            # still try — some APIs don’t require meter number for monthly
            self._meter_number = ""
        today = today or date.today()
        res = await self.get_usage_data(
            self._token,
            self._account_number,
            self._utility_account_number,
            self._meter_number,
            mode="M",
            rtype="K",
            date_from=first_of_month_iso(today),
            date_to=today.isoformat(),
        )
        return self.extract_tentative(res)

    async def fetch_latest_mi_day(
        self,
        reference: Optional[date] = None,
        *,
        lookback_days: int = 3,
    ) -> dict:
        """Fetch the most recent day that has Mi (15-minute) data available."""

        if not all([self._token, self._account_number, self._utility_account_number]):
            raise RuntimeError("Client not bootstrapped")

        reference = reference or date.today()
        meter_number = self._meter_number or ""

        for offset in range(1, max(lookback_days, 1) + 1):
            target_date = reference - timedelta(days=offset)
            payload = await self.get_usage_data(
                self._token,
                self._account_number,
                self._utility_account_number,
                meter_number,
                mode="Mi",
                rtype="K",
                date_from=target_date.isoformat(),
                date_to=target_date.isoformat(),
            )
            detail = self.extract_mi_day(payload, target_date)
            if detail:
                detail["mi_lookback_days"] = offset
                return detail

        return {}
