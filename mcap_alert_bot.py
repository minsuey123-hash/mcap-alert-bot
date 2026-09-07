#!/usr/bin/env python3
import json
import os
import time
import urllib.request
import urllib.error

# 콤마로 여러 체인 지정 가능: 예) "solana,robinhood,bsc,base"
NETWORKS = [n.strip() for n in os.environ.get("NETWORK", "solana").split(",") if n.strip()]
MCAP_THRESHOLD_USD = float(os.environ.get("MCAP_THRESHOLD_USD", "200000"))
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "45"))
STATE_FILE = os.environ.get("STATE_FILE", "seen_pools.json")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "여기에_봇토큰_붙여넣기")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "여기에_챗아이디_붙여넣기")

RUN_ONCE = os.environ.get("RUN_ONCE", "false").lower() == "true"


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"alerted": {}}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def fetch_new_pools(network):
    url = f"https://api.geckoterminal.com/api/v2/networks/{network}/new_pools"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def send_telegram(text: str):
    if "여기에" in TELEGRAM_BOT_TOKEN or "여기에" in TELEGRAM_CHAT_ID:
        print("[경고] 텔레그램 토큰/챗ID 설정 안 됨 -> 콘솔에만 출력합니다.")
        print(text)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = json.dumps(
        {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML",
         "disable_web_page_preview": False}
    ).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
    except urllib.error.URLError as e:
        print(f"[텔레그램 전송 실패] {e}")


def market_cap_of(pool_attrs: dict):
    mc = pool_attrs.get("market_cap_usd")
    if mc:
        return float(mc)
    fdv = pool_attrs.get("fdv_usd")
    if fdv:
        return float(fdv)
    return None


def format_alert(network: str, pool: dict) -> str:
    attrs = pool["attributes"]
    name = attrs.get("name", "unknown")
    mc = market_cap_of(attrs)
    price = attrs.get("base_token_price_usd", "?")
    pool_addr = attrs.get("address", "")
    dexscreener_link = f"https://dexscreener.com/{network}/{pool_addr}"
    gt_link = f"https://www.geckoterminal.com/{network}/pools/{pool_addr}"
    return (
        f"🚨 <b>{name}</b> 시총 ${MCAP_THRESHOLD_USD:,} 돌파\n"
        f"현재 시총: ${mc:,.0f}\n"
        f"가격: ${price}\n"
        f"체인: {network}\n"
        f"DexScreener: {dexscreener_link}\n"
        f"GeckoTerminal: {gt_link}"
    )


def check_network(network, state):
    try:
        data = fetch_new_pools(network)
    except urllib.error.HTTPError as e:
        print(f"[{network}] API 에러 {e.code}")
        return
    except Exception as e:
        print(f"[{network}] 에러: {e}")
        return

    pools = data.get("data", [])
    for pool in pools:
        # 체인별로 pool id가 겹치지 않게 네트워크 이름을 붙여서 key로 사용
        pool_id = f"{network}:{pool['id']}"
        mc = market_cap_of(pool["attributes"])
        if mc is None:
            continue

        already_alerted = state["alerted"].get(pool_id, False)

        if mc >= MCAP_THRESHOLD_USD and not already_alerted:
            msg = format_alert(network, pool)
            print(msg)
            send_telegram(msg)
            state["alerted"][pool_id] = True


def check_once(state):
    for network in NETWORKS:
        check_network(network, state)

    if len(state["alerted"]) > 20000:
        keys = list(state["alerted"].keys())[-20000:]
        state["alerted"] = {k: True for k in keys}


def main():
    mode = "1회 실행 (RUN_ONCE=true)" if RUN_ONCE else f"무한루프 ({POLL_SECONDS}초마다)"
    print(f"[시작] {NETWORKS} 체인, ${MCAP_THRESHOLD_USD:,.0f} 이상 새 풀 감시 - {mode}")
    state = load_state()

    if RUN_ONCE:
        check_once(state)
        save_state(state)
        return

    while True:
        check_once(state)
        save_state(state)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
