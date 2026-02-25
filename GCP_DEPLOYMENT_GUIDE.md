# Anleitung: NDX Tracker in Google Cloud (GCP) betreiben

Diese Anleitung zeigt dir, wie du den `NDX_tracker.py` auf einer kleinen, kostenlosen (oder sehr günstigen) Instanz in der Google Cloud dauerhaft ausführst.

## 1. Google Cloud Instanz erstellen (Compute Engine)

1.  Gehe zur [Google Cloud Console](https://console.cloud.google.com/).
2.  Navigiere zu **Compute Engine** > **VM instances**.
3.  Klicke auf **Create Instance**.
4.  **Konfiguration:**
    *   **Region:** Wähle `us-east1` (South Carolina) oder `us-central1` (Iowa), da dort die Latenz zur New Yorker Börse am geringsten ist.
    *   **Machine type:** `e2-micro` (reicht völlig aus und ist oft im "Free Tier" enthalten).
    *   **Boot disk:** Debian oder Ubuntu (Standardeinstellung).
5.  Klicke unten auf **Create**.

## 2. Vorbereitung auf der VM

Sobald die Instanz läuft, klicke auf den **SSH** Button neben dem Namen der Instanz. Ein Terminal öffnet sich. Gib dort folgende Befehle ein:

```bash
# System updaten
sudo apt-get update

# Python und Pip installieren (falls nicht vorhanden)
sudo apt-get install -y python3 python3-pip

# Projekt-Ordner erstellen
mkdir ndx-tracker
cd ndx-tracker
```

## 3. Dateien hochladen

Du kannst die Datei direkt im Terminal erstellen:

```bash
nano NDX_tracker.py
```
*Kopiere den Inhalt deiner `NDX_tracker.py` hier hinein, drücke `Strg+O` (Speichern), `Enter` und `Strg+X` (Beenden).*

Erstelle die `requirements.txt`:
```bash
nano requirements.txt
```
Inhalt:
```text
yfinance
pandas
requests
pytz
```

Installiere die Abhängigkeiten:
```bash
pip3 install -r requirements.txt
```

## 4. Dauerhafter Betrieb (Screen oder Systemd)

Damit das Skript weiterläuft, wenn du das Fenster schließt, nutze am besten `screen`:

1.  Starte eine Screen-Session: `screen -S ndx`
2.  Starte das Skript: `python3 NDX_tracker.py`
3.  Verlasse die Session (ohne das Skript zu stoppen): Drücke `Strg+A` und danach nur `D` (für Detach).

Du kannst das Fenster nun schließen. Das Skript läuft 24/7 weiter.

**Wieder verbinden:** Falls du später schauen willst, was das Skript macht:
`screen -r ndx`

## 5. Kosten-Tipp
Die `e2-micro` Instanz ist in den USA oft dauerhaft kostenlos. Achte darauf, dass du keine unnötigen Premium-Features (wie statische IPs) buchst, falls du im Free-Tier bleiben möchtest.
