#!/usr/bin/env python3
"""Unofficial Apple Singapore pickup monitor. Uses Apple's undocumented pickup endpoint."""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL = "https://www.apple.com/sg/shop/retail/pickup-message"
BUY_URL = "https://www.apple.com/sg/shop/buy-iphone/iphone-duo"
STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))

# Singapore part numbers for the six requested configurations.
PARTS = {
    "MK2D4X/A": ("256GB", "Star White"),
    "MK2E4X/A": ("256GB", "Night Sky"),
    "MK2F4X/A": ("512GB", "Star White"),
    "MK2G4X/A": ("512GB", "Night Sky"),
    "MK2H4X/A": ("1TB", "Star White"),
    "MK2J4X/A": ("1TB", "Night Sky"),
}

# Official Apple Store postal codes. Query each area so the pickup response can
# discover the corresponding store number; no store IDs are guessed.
STORES = {
    "Apple Orchard Road": "238857",
    "Apple Marina Bay Sands": "018972",
    "Apple Jewel Changi Airport": "819666",
}

USER_AGENT = "Mozilla/5.0 (compatible; SingaporePickupMonitor/1.0)"


def request_json(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Referer": BUY_URL,
        },
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        if response.status != 200:
            raise RuntimeError(f"Apple endpoint returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def apple_pickup_url(postal_code):
    params = [("pl", "true")]
    for i, part in enumerate(PARTS):
        params.append((f"parts.{i}", part))
    params.append(("location", postal_code))
    return BASE_URL + "?" + urllib.parse.urlencode(params)


def is_available(part_data):
    """Only return True for an explicit positive pickupDisplay value."""
    if not isinstance(part_data, dict):
        raise RuntimeError("Unexpected Apple part-availability response shape")
    display = str(part_data.get("pickupDisplay", "")).strip().lower()
    if not display:
        # Do not silently treat an unknown API response as out of stock.
        raise RuntimeError("Apple response omitted pickupDisplay")
    negative_words = ("unavailable", "not available", "check back", "not currently")
    if any(word in display for word in negative_words):
        return False
    return display == "available" or display.startswith("available ")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID GitHub secret")

    def telegram(message):
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not result.get("ok"):
            raise RuntimeError("Telegram rejected the message")

    if mode == "test":
        telegram(
            "✅ Singapore iPhone Duo monitor test succeeded.\n"
            "Watching 256GB, 512GB and 1TB in Star White and Night Sky "
            "at Orchard Road, Marina Bay Sands and Jewel Changi Airport."
        )
        print("Telegram test message sent.")
        return
    if mode != "check":
        raise RuntimeError("Mode must be 'check' or 'test'")

    # Load state but do not overwrite it until all Apple requests succeed and
    # any newly-available-stock alert has been delivered successfully.
    if STATE_FILE.exists():
        old_state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(old_state, dict):
            raise RuntimeError("state.json must contain a JSON object")
    else:
        old_state = {}

    found = {}
    seen_store_names = set()

    # One request per store area, with all six part numbers in each request.
    # Apple may return nearby stores; only exact requested store names count.
    for expected_name, postal_code in STORES.items():
        data = request_json(apple_pickup_url(postal_code))
        body = data.get("body", {})
        stores = body.get("stores")
        if not isinstance(stores, list):
            raise RuntimeError("Apple response missing body.stores; endpoint may have changed")

        target = None
        for store in stores:
            actual_name = str(store.get("storeName", "")).strip()
            normalised_actual = actual_name.removeprefix("Apple ").casefold()
            normalised_expected = expected_name.removeprefix("Apple ").casefold()

            if normalised_actual == normalised_expected:
                target = store
                break

        if target is None:
            # Fail safely: don't announce "out of stock" if the requested store
            # wasn't present in Apple's response.
            names = ", ".join(str(s.get("storeName", "?")) for s in stores)
            raise RuntimeError(
                f"Apple did not return {expected_name} for postal code {postal_code}. "
                f"Returned stores: {names or '(none)'}. No state was changed."
            )

        availability = target.get("partsAvailability")
        if not isinstance(availability, dict):
            raise RuntimeError(f"Apple response missing partsAvailability for {expected_name}")

        seen_store_names.add(expected_name)
        for part, (capacity, colour) in PARTS.items():
            if part not in availability:
                raise RuntimeError(
                    f"Apple response omitted part {part} at {expected_name}; "
                    "no state was changed."
                )
            key = f"{expected_name}|{part}"
            found[key] = {
                "available": is_available(availability[part]),
                "store": expected_name,
                "part": part,
                "capacity": capacity,
                "colour": colour,
            }
        # Keep requests polite; this is only three requests per run.
        time.sleep(1.5)

    if seen_store_names != set(STORES):
        raise RuntimeError("Not all three requested stores were checked; no state was changed.")

    newly_available = []
    next_state = {}
    for key, item in found.items():
        now = item["available"]
        was = old_state.get(key) is True
        next_state[key] = now
        if now and not was:
            newly_available.append(item)

    if newly_available:
        lines = [
            "📱 iPhone Duo pickup availability detected in Singapore",
            "",
        ]
        for item in newly_available:
            lines.append(
                f"• {item['store']}: {item['capacity']} {item['colour']}"
            )
        lines.extend(["", f"Check and order: {BUY_URL}"])
        telegram("\n".join(lines))
        print(f"Sent Telegram alert for {len(newly_available)} newly available item(s).")
    else:
        print("Check complete. No newly available configurations.")

    STATE_FILE.write_text(
        json.dumps(next_state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Successfully checked {len(found)} store/configuration combinations.")


if __name__ == "__main__":
    try:
        main()
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"Network error; availability was not updated: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Monitor failed safely; availability was not updated: {exc}", file=sys.stderr)
        sys.exit(1)
