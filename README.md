# Beckhoff ADS Auto für Home Assistant

Custom Integration für TwinCAT 3 über ADS/`pyads`. Sie entdeckt Blatt-Symbole unter einer oder mehreren Root-Strukturen und erzeugt daraus automatisch Home-Assistant-Entities.

## Funktionen

- UI-Konfiguration über Config Flow und Options Flow
- ADS-Verbindung zu einer TwinCAT-PLC
- Mehrere Roots, zum Beispiel `GVL_HA,MAIN.ha`
- Verschachtelte Strukturen: `pyads.get_all_symbols()` liefert die Blatt-Symbole; diese werden rekursiv wirkend flach als Pfad verarbeitet
- Optional Array-Elemente
- BOOL: `binary_sensor` oder schreibbarer `switch`
- Numerische Typen: `sensor` oder schreibbarer `number`
- STRING: `sensor` oder schreibbarer `text`
- Polling per `DataUpdateCoordinator`, I/O läuft im Executor
- Reconnect nach PLC-Neustart oder Kommunikationsfehler
- Rescan mit dynamischem Hinzufügen neuer Entities
- Services für Rescan, Lesen und Schreiben

## Vollständige Installation für Home Assistant Docker auf dem Raspberry Pi

Diese Anleitung gilt für Home Assistant Container beziehungsweise Docker Compose auf Raspberry Pi OS. Sie gilt **nicht** für Home Assistant OS. Alle Linux-Befehle werden auf dem Raspberry Pi per SSH ausgeführt.

### Voraussetzungen

Vorher müssen folgende Informationen bekannt sein:

- IP-Adresse des Raspberry Pi, zum Beispiel `192.168.178.50`
- IP-Adresse der Beckhoff-PLC, zum Beispiel `192.168.178.60`
- AMS Net ID der PLC, zum Beispiel `5.1.204.160.1.1`
- ADS-Port der TwinCAT-3-Runtime, normalerweise `851`
- SSH-Zugang zum Raspberry Pi
- Benutzer mit Zugriff auf den Docker- beziehungsweise Home-Assistant-Config-Ordner

Die PLC und der Raspberry Pi müssen sich im gleichen Netzwerk befinden oder über Routing erreichbar sein.

### Schritt 1: Per SSH auf dem Raspberry Pi anmelden

Von einem anderen Rechner ausführen:

```bash
ssh BENUTZERNAME@RASPBERRY_PI_IP
```

Beispiel:

```bash
ssh pi@192.168.178.50
```

### Schritt 2: Den Home-Assistant-Container ermitteln

Container anzeigen:

```bash
docker ps
```

Der Home-Assistant-Container heißt häufig `homeassistant`. Falls er anders heißt, muss dieser Name in den folgenden Befehlen ersetzt werden.

Den Host-Ordner anzeigen, der in den Container nach `/config` gemountet wird:

```bash
docker inspect homeassistant --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'
```

Beispielausgabe:

```text
/opt/homeassistant -> /config
```

In diesem Beispiel ist `/opt/homeassistant` der richtige Ordner auf dem Raspberry Pi. Dort muss auch die Datei `configuration.yaml` liegen:

```bash
ls -l /opt/homeassistant/configuration.yaml
```

Wenn dein Ergebnis beispielsweise `/home/pi/homeassistant -> /config` lautet, verwendest du stattdessen `/home/pi/homeassistant` als Config-Ordner.

In den folgenden Befehlen wird beispielhaft `/opt/homeassistant` verwendet.

### Schritt 3: Docker-Netzwerk für ADS konfigurieren

Für Docker auf Linux wird `network_mode: host` empfohlen. Dadurch verwendet Home Assistant direkt das Netzwerk des Raspberry Pi. Das erleichtert die ADS-Kommunikation und die ADS-Route.

Wenn du Docker Compose verwendest, sollte der Home-Assistant-Service ungefähr so aussehen:

```yaml
services:
  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable
    container_name: homeassistant
    network_mode: host
    volumes:
      - /opt/homeassistant:/config
      - /etc/localtime:/etc/localtime:ro
    restart: unless-stopped
```

Die vorhandenen weiteren Einstellungen wie `privileged`, `devices` oder Umgebungsvariablen bleiben erhalten. Bei `network_mode: host` wird normalerweise kein `ports:`-Abschnitt benötigt.

Nach einer Änderung der Compose-Datei aus dem Ordner mit der Datei `docker-compose.yml` ausführen:

```bash
docker compose up -d
```

Wenn du keine Compose-Datei ändern möchtest, funktioniert die Integration bei vielen Netzwerken auch mit dem bestehenden Bridge-Netzwerk. Für stabile ADS-Routen wird auf einem Raspberry Pi trotzdem `network_mode: host` empfohlen.

### Schritt 4: Integration direkt installieren

Diese Variante benötigt weder HACS noch ein Home-Assistant-Add-on.

Auf dem Raspberry Pi ausführen:

```bash
cd /tmp
rm -rf beckhoff_ads_auto-main beckhoff_ads_auto.zip
wget -O beckhoff_ads_auto.zip https://github.com/NKAutomations/beckhoff_ads_auto/archive/refs/heads/main.zip
unzip beckhoff_ads_auto.zip
mkdir -p /opt/homeassistant/custom_components
rm -rf /opt/homeassistant/custom_components/beckhoff_ads_auto
cp -r /tmp/beckhoff_ads_auto-main/custom_components/beckhoff_ads_auto /opt/homeassistant/custom_components/
```

Falls `wget` oder `unzip` nicht installiert ist:

```bash
sudo apt update
sudo apt install -y wget unzip
```

Installation prüfen:

```bash
ls -l /opt/homeassistant/custom_components/beckhoff_ads_auto
```

Die Dateien `manifest.json`, `__init__.py`, `config_flow.py` und `ads_client.py` müssen sichtbar sein.

### Schritt 5: Home Assistant neu starten

Bei Docker Compose:

```bash
docker compose restart homeassistant
```

Oder direkt:

```bash
docker restart homeassistant
```

`pyads` wird von Home Assistant anhand der `requirements` in [manifest.json](custom_components/beckhoff_ads_auto/manifest.json) automatisch als Integration-Abhängigkeit installiert. Es ist normalerweise **nicht** nötig, `pip install pyads` auf dem Raspberry Pi auszuführen.

Die Installation kann in den Container-Logs beobachtet werden:

```bash
docker logs -f homeassistant
```

Die Anzeige wird mit `Ctrl+C` beendet. Fehlermeldungen zu `beckhoff_ads_auto` oder `pyads` müssen vor der weiteren Einrichtung behoben werden.

### Schritt 6: ADS-Route in TwinCAT einrichten

Auf dem Windows-PC mit TwinCAT XAE:

1. TwinCAT-Projekt öffnen.
2. **SYSTEM → Routes** öffnen.
3. **Add Route** auswählen.
4. IP-Adresse des Raspberry Pi eintragen.
5. Die AMS Net ID des Raspberry Pi eintragen.
6. Die Route bestätigen beziehungsweise die Zugangsdaten eingeben.
7. Prüfen, dass die Route als aktiv angezeigt wird.

Beispiel:

| Gerät | IP-Adresse | AMS Net ID |
|---|---|---|
| Raspberry Pi | `192.168.178.50` | `192.168.178.50.1.1` |
| Beckhoff PLC | `192.168.178.60` | `5.1.204.160.1.1` |

Die Werte sind Beispiele. Die PLC-AMS-Net-ID muss exakt der in TwinCAT angezeigten AMS Net ID entsprechen. Die AMS Net ID des Raspberry Pi muss bei der verwendeten ADS-Konfiguration zur Route passen.

Die TwinCAT-3-Runtime verwendet normalerweise ADS-Port `851`. ADS-Kommunikation verwendet zusätzlich typischerweise TCP/UDP-Port `48898`. Firewall-Regeln und VLAN-Regeln dürfen diese Kommunikation nicht blockieren.

### Schritt 7: Integration in der Home-Assistant-Oberfläche hinzufügen

Nach dem Neustart im Browser:

1. **Einstellungen** öffnen.
2. **Geräte & Dienste** öffnen.
3. **Integration hinzufügen** anklicken.
4. Nach **Beckhoff ADS Auto** suchen.
5. Das Konfigurationsformular ausfüllen.

Beispielwerte:

| Formularfeld | Wert |
|---|---|
| PLC Host | `192.168.178.60` |
| AMS Net ID | `5.1.204.160.1.1` |
| ADS Port | `851` |
| Root-Symbole | `GVL_HA` |
| Polling-Intervall | `2` |
| Schreiben aktivieren | nach Bedarf |

Für mehrere Roots den Wert kommasepariert angeben:

```text
GVL_HA,MAIN.ha,GVL_Visualisierung
```

Der Root-Name muss exakt dem Symbolnamen in TwinCAT entsprechen. Es dürfen keine zusätzlichen Anführungszeichen verwendet werden.

### Schritt 8: Entities kontrollieren

Nach erfolgreicher Einrichtung:

1. **Einstellungen → Geräte & Dienste** öffnen.
2. **Beckhoff ADS Auto** auswählen.
3. Das automatisch angelegte Beckhoff-PLC-Gerät öffnen.
4. Die gefundenen Entities kontrollieren.

Bei Änderungen an der PLC-Struktur den Button **Rescan symbols** am PLC-Gerät ausführen.

### Alternative: Installation über HACS

Die direkte Installation aus Schritt 4 und die HACS-Installation sind Alternativen. Es soll nur eine der beiden Varianten verwendet werden.

1. HACS in Home Assistant öffnen.
2. **Integrationen** auswählen.
3. Das Drei-Punkte-Menü öffnen.
4. **Benutzerdefinierte Repositories** auswählen.
5. Diese Repository-URL eintragen:

```text
https://github.com/NKAutomations/beckhoff_ads_auto
```

6. Kategorie **Integration** auswählen.
7. Repository hinzufügen.
8. **Beckhoff ADS Auto** installieren.
9. Home Assistant neu starten.
10. Mit Schritt 7 dieser Anleitung fortfahren.

Wenn HACS die Integration nicht findet, zuerst prüfen, ob der Repository-Typ **Integration** ausgewählt wurde und ob der Home-Assistant-Container Internetzugriff besitzt.

### Docker-Installation überprüfen

Der endgültige Pfad muss innerhalb des Containers so aussehen:

```bash
docker exec homeassistant ls -l /config/custom_components/beckhoff_ads_auto
```

Die Antwort muss Dateien wie `manifest.json` und `__init__.py` enthalten. Der Ordner darf nicht versehentlich so verschachtelt sein:

```text
/config/custom_components/beckhoff_ads_auto-main/custom_components/beckhoff_ads_auto
```

Der korrekte Pfad ist:

```text
/config/custom_components/beckhoff_ads_auto/manifest.json
```

### Fehler: `permission denied` bei `docker ps`

Wenn bei `docker ps` eine Meldung wie `permission denied while trying to connect to the Docker daemon socket` erscheint, hat der aktuell angemeldete Linux-Benutzer keinen Zugriff auf den Docker-Socket.

Zuerst testen:

```bash
sudo docker ps
```

Wenn dieser Befehl funktioniert, den eigenen Benutzer dauerhaft zur Docker-Gruppe hinzufügen. `BENUTZERNAME` durch den Linux-Benutzer ersetzen, mit dem du per SSH angemeldet bist:

```bash
sudo usermod -aG docker BENUTZERNAME
```

Den aktuell angemeldeten Benutzernamen kannst du anzeigen:

```bash
whoami
```

Danach die SSH-Sitzung vollständig beenden:

```bash
exit
```

Neu per SSH anmelden und testen:

```bash
docker ps
```

Alternativ kann die Gruppenzugehörigkeit in der aktuellen Sitzung einmalig neu geladen werden:

```bash
newgrp docker
docker ps
```

Für die nächsten Docker-Befehle kann bis zum erneuten Login auch `sudo` verwendet werden, zum Beispiel:

```bash
sudo docker inspect homeassistant --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'
sudo docker restart homeassistant
```

Wenn auch `sudo docker ps` nicht funktioniert, den Docker-Dienst prüfen:

```bash
sudo systemctl status docker
sudo systemctl start docker
sudo systemctl enable docker
```

Den Docker-Socket nicht mit `chmod 777 /var/run/docker.sock` freigeben. Das wäre eine unnötige Sicherheitslücke.

## Beispiel einer TwinCAT-Struktur

```iecst
TYPE ST_HA_STATUS : STRUCT
    Running : BOOL;
    Temperature : REAL;
    Counter : DINT;
    Message : STRING(80);
END_STRUCT
END_TYPE

VAR_GLOBAL
    GVL_HA : ST_HA_STATUS;
END_VAR
```

Als Root wird `GVL_HA` eingetragen. Erwartete Entity-Pfade sind beispielsweise `GVL_HA.Running`, `GVL_HA.Temperature`, `GVL_HA.Counter` und `GVL_HA.Message`.

## Optionen und Filter

- **Include**, **Exclude** und **Read-only** akzeptieren einen Prefix oder regulären Ausdruck.
- Bei ungültigem Regex wird der Filter als Prefix behandelt.
- **Write enable** muss global aktiviert sein, zusätzlich muss das PLC-Symbol schreibbar sein.
- Mit **Include array elements** werden Pfade wie `GVL_HA.Values[0]` berücksichtigt.
- Polling ist auf 0,5 bis 10 Sekunden begrenzt.

## Services

```yaml
service: beckhoff_ads_auto.rescan
data:
  entry_id: "optional_config_entry_id"
```

```yaml
service: beckhoff_ads_auto.read_symbol
data:
  symbol: GVL_HA.Counter
  entry_id: "optional_config_entry_id"
```

```yaml
service: beckhoff_ads_auto.write_symbol
data:
  symbol: GVL_HA.Counter
  value: 42
  entry_id: "optional_config_entry_id"
```

`read_symbol` liefert bei unterstützten Home-Assistant-Versionen eine Service-Response mit `symbol` und `value` zurück.

## Troubleshooting

- AMS Net ID ist nicht automatisch die IP-Adresse. Die ADS Route zwischen HA-Host und PLC muss eingerichtet sein.
- Standardport für die TwinCAT Runtime ist `851`.
- Bei Verbindungsproblemen Debug-Logging aktivieren:

```yaml
logger:
  default: warning
  logs:
    custom_components.beckhoff_ads_auto: debug
```

- Prüfen, ob die Root-Schreibweise exakt dem PLC-Symbolnamen entspricht.
- `STRING` wird mit der von pyads gemeldeten PLC-Symboldefinition gelesen und geschrieben.
- Nach Änderungen der PLC-Struktur den Rescan-Button am PLC-Gerät drücken oder den Rescan-Service ausführen.
