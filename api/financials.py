# -*- coding: utf-8 -*-
"""
Vercel Python 서버리스 함수: GET /api/financials
쿼리: corp_code, corp_name, start(연도), end(연도)
DART Open API로 해당 회사의 start~end 연도 재무제표를 조회해 핵심 지표를 반환한다.
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import os
import requests

BASE_URL = "https://opendart.fss.or.kr/api"
REPORT_CODE_ANNUAL = "11011"
MAX_YEAR_SPAN = 7

TARGET_ACCOUNTS = {
    "매출액": ["매출액", "수익(매출액)", "영업수익"],
    "영업이익": ["영업이익", "영업이익(손실)"],
    "당기순이익": ["당기순이익", "당기순이익(손실)", "분기순이익", "분기순이익(손실)"],
    "자산총계": ["자산총계"],
    "부채총계": ["부채총계"],
    "자본총계": ["자본총계"],
}


def fetch_financial_statement(api_key, corp_code, year):
    """연결(CFS) 우선, 없으면 개별(OFS) 재시도."""
    for fs_div in ("CFS", "OFS"):
        params = {
            "crtfc_key": api_key,
            "corp_code": corp_code,
            "bsns_year": str(year),
            "reprt_code": REPORT_CODE_ANNUAL,
            "fs_div": fs_div,
        }
        resp = requests.get(f"{BASE_URL}/fnlttSinglAcntAll.json", params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "000":
            return data.get("list", []), fs_div
    return [], None


def extract_metrics(rows):
    result = {k: None for k in TARGET_ACCOUNTS}
    for row in rows:
        account_nm = (row.get("account_nm") or "").strip()
        amount_str = (row.get("thstrm_amount") or "").replace(",", "").strip()
        if not amount_str:
            continue
        try:
            amount = float(amount_str)
        except ValueError:
            continue
        for metric, aliases in TARGET_ACCOUNTS.items():
            if result[metric] is not None:
                continue
            if account_nm in aliases:
                result[metric] = amount
    return result


def build_record(corp_name, corp_code, year, metrics, fs_div):
    revenue = metrics.get("매출액")
    op_income = metrics.get("영업이익")
    net_income = metrics.get("당기순이익")
    assets = metrics.get("자산총계")
    liabilities = metrics.get("부채총계")
    equity = metrics.get("자본총계")

    record = {
        "회사명": corp_name,
        "corp_code": corp_code,
        "연도": year,
        "재무제표구분": "연결" if fs_div == "CFS" else "개별",
    }
    record.update(metrics)
    record["영업이익률(%)"] = round(op_income / revenue * 100, 2) if revenue and op_income is not None else None
    record["순이익률(%)"] = round(net_income / revenue * 100, 2) if revenue and net_income is not None else None
    record["부채비율(%)"] = round(liabilities / equity * 100, 2) if equity and liabilities is not None else None
    record["ROE(%)"] = round(net_income / equity * 100, 2) if equity and net_income is not None else None
    record["ROA(%)"] = round(net_income / assets * 100, 2) if assets and net_income is not None else None
    return record


def handle_request(query, api_key):
    """쿼리 파라미터(dict[str, list[str]])를 받아 (status, payload)를 반환. 로컬 dev 서버와 공유."""
    corp_code = (query.get("corp_code") or [""])[0].strip()
    corp_name = (query.get("corp_name") or [""])[0].strip() or corp_code

    try:
        start_year = int((query.get("start") or [""])[0])
        end_year = int((query.get("end") or [""])[0])
    except ValueError:
        return 400, {"error": "start/end 연도가 필요합니다."}

    if not corp_code:
        return 400, {"error": "corp_code가 필요합니다."}
    if not api_key:
        return 500, {"error": "서버에 DART_API_KEY 환경변수가 설정되어 있지 않습니다."}
    if end_year < start_year or end_year - start_year > MAX_YEAR_SPAN:
        return 400, {"error": f"조회 기간은 최대 {MAX_YEAR_SPAN + 1}개년까지 가능합니다."}

    records = []
    try:
        for year in range(start_year, end_year + 1):
            rows, fs_div = fetch_financial_statement(api_key, corp_code, year)
            if not rows:
                continue
            metrics = extract_metrics(rows)
            records.append(build_record(corp_name, corp_code, year, metrics, fs_div))
    except requests.RequestException as e:
        return 502, {"error": f"DART 조회 중 오류가 발생했습니다: {e}"}

    return 200, {"corp_code": corp_code, "corp_name": corp_name, "records": records}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        status, payload = handle_request(query, os.environ.get("DART_API_KEY"))
        self._send_json(payload, status)

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
