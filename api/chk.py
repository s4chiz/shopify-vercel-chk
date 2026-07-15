from http.server import BaseHTTPRequestHandler
import asyncio
import time
import sys
import os
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sh_checker import process_card, parse_cc_string, extract_clean_response


class handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def _respond(self, status: int, body: str):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query, keep_blank_values=True)

        cc_raw  = (query.get("cc")    or [""])[0].strip()
        site    = (query.get("site")  or [""])[0].strip()
        proxy   = (query.get("proxy") or [""])[0].strip()

        if not cc_raw:
            self._respond(400, "Error: missing 'cc' parameter (format: num|mm|yy|cvv)")
            return
        if not site:
            self._respond(400, "Error: missing 'site' parameter (Shopify store URL)")
            return

        try:
            parts = parse_cc_string(cc_raw)
            cc  = parts["cc"]
            mes = parts["mes"]
            ano = parts["ano"]
            cvv = parts["cvv"]
        except Exception as e:
            self._respond(400, f"Error: invalid cc format — {e}\nExpected: num|mm|yy|cvv")
            return

        t0 = time.time()
        success = False
        message = "ERROR"
        total_price = "0"
        currency = "USD"

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                success, message, _gateway, total_price, currency = loop.run_until_complete(
                    asyncio.wait_for(
                        process_card(cc, mes, ano, cvv, site, proxy_str=proxy or None),
                        timeout=55,
                    )
                )
            finally:
                loop.close()
        except asyncio.TimeoutError:
            message = "TIMEOUT"
        except Exception as e:
            message = str(e) or type(e).__name__

        elapsed = round(time.time() - t0, 2)

        clean_msg = extract_clean_response(message)

        amount_str = f"{total_price} {currency.upper()}" if total_price and str(total_price) not in ("0", "0.0", "0.00") else total_price or "0"

        body = (
            f"Cc: {cc_raw}\n"
            f"Response: {clean_msg}\n"
            f"Amount: {amount_str}\n"
            f"Site: {site}\n"
            f"Proxy: {proxy or 'None'}\n"
            f"Time: {elapsed}s"
        )

        self._respond(200, body)

    def do_POST(self):
        self.do_GET()
