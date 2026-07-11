# -*- coding: utf-8 -*-
"""
로컬 개발용 서버. index.html/corp_list.json을 정적으로 서빙하면서
/api/financials 요청은 api/financials.py의 로직을 그대로 재사용해 처리한다.
Vercel CLI 없이 로컬에서 웹앱 전체를 검증하기 위한 용도.

사용법: python dev_server.py  (기본 포트 8000)
"""
import os
import sys
from http.server import SimpleHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "api"))

from dotenv import load_dotenv
load_dotenv()

from financials import handle_request  # noqa: E402


class DevHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/financials":
            query = parse_qs(parsed.query)
            status, payload = handle_request(query, os.environ.get("DART_API_KEY"))
            self._send_json(payload, status)
            return
        super().do_GET()

    def _send_json(self, payload, status=200):
        import json
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Dev server running: http://localhost:{port}")
    HTTPServer(("localhost", port), DevHandler).serve_forever()
