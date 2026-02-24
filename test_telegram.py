"""
Telegram Test Script
--------------------
Führe dieses Skript aus, um zu prüfen ob dein Telegram Bot funktioniert.
Usage:
    python test_telegram.py <BOT_TOKEN> <CHAT_ID>
"""
import sys
import requests
import json

def test_telegram(token: str, chat_id: str):
    print(f"\n🔍 Teste Telegram Bot...")
    print(f"   Token: {token[:8]}...{token[-4:]}")
    print(f"   Chat ID: {chat_id}")

    # 1) Verify bot token is valid
    me_url = f"https://api.telegram.org/bot{token}/getMe"
    resp = requests.get(me_url, timeout=10)
    if resp.status_code != 200 or not resp.json().get("ok"):
        print(f"\n❌ Bot Token ungültig! Response: {resp.text}")
        return False
    bot_name = resp.json()["result"]["username"]
    print(f"\n✅ Bot Token OK  → @{bot_name}")

    # 2) Send test message
    send_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "✅ *Telegram Test erfolgreich!*\n\nDein Intraday Tracker kann Benachrichtigungen senden.",
        "parse_mode": "Markdown"
    }
    resp2 = requests.post(send_url, json=payload, timeout=10)
    data = resp2.json()

    if resp2.status_code == 200 and data.get("ok"):
        print(f"✅ Nachricht gesendet! Message ID: {data['result']['message_id']}")
        return True
    else:
        print(f"\n❌ Senden fehlgeschlagen!")
        err = data.get("description", "Unbekannter Fehler")
        print(f"   Fehlermeldung: {err}")
        if "chat not found" in err.lower():
            print("   → Chat ID falsch. Sende eine Nachricht an deinen Bot und versuche es erneut.")
        elif "unauthorized" in err.lower():
            print("   → Bot Token ungültig oder widerrufen.")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python test_telegram.py <BOT_TOKEN> <CHAT_ID>")
        print("\nWie bekomme ich diese Werte?")
        print("  Bot Token : Öffne Telegram → @BotFather → /newbot oder /mybots")
        print("  Chat ID   : Schreibe deinem Bot eine Nachricht, dann öffne:")
        print("              https://api.telegram.org/bot<TOKEN>/getUpdates")
        print("              und such nach 'id' unter 'chat'")
        sys.exit(1)

    token = sys.argv[1]
    chat_id = sys.argv[2]
    success = test_telegram(token, chat_id)
    sys.exit(0 if success else 1)
