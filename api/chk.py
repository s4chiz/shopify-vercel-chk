import asyncio
import time
import sys
import os
from urllib.parse import urlparse, parse_qs
from flask import Flask, request, Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sh_checker import process_card, parse_cc_string, extract_clean_response

app = Flask(__name__)


@app.route("/chk", methods=["GET"])
@app.route("/", methods=["GET"])
def chk():
    cc_raw  = request.args.get("cc", "").strip()
    site    = request.args.get("site", "").strip()
    proxy   = request.args.get("proxy", "").strip()

    if not cc_raw:
        return Response("Error: missing 'cc' parameter (format: num|mm|yy|cvv)", status=400, mimetype="text/plain")
    if not site:
        return Response("Error: missing 'site' parameter (Shopify store URL)", status=400, mimetype="text/plain")

    try:
        parts = parse_cc_string(cc_raw)
        cc  = parts["cc"]
        mes = parts["mes"]
        ano = parts["ano"]
        cvv = parts["cvv"]
    except Exception as e:
        return Response(f"Error: invalid cc format — {e}\nExpected: num|mm|yy|cvv", status=400, mimetype="text/plain")

    t0 = time.time()
    success = False
    message = "ERROR"
    total_price = "0"
    currency = "USD"

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success, message, gateway, total_price, currency = loop.run_until_complete(
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
    amount_str = (
        f"{total_price} {currency.upper()}"
        if total_price and str(total_price) not in ("0", "0.0", "0.00")
        else total_price or "0"
    )

    gateway_str = gateway if gateway and gateway not in ("", "UNKNOWN") else "Shopify Payments"

    body = (
        f"Cc: {cc_raw}\n"
        f"Response: {clean_msg}\n"
        f"Gateway: {gateway_str}\n"
        f"Amount: {amount_str}\n"
        f"Site: {site}\n"
        f"Proxy: {proxy or 'None'}\n"
        f"Time: {elapsed}s"
    )
    return Response(body, status=200, mimetype="text/plain")
