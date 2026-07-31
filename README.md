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

## Installation

### Manuell

1. Den Ordner `custom_components/beckhoff_ads_auto` nach `/config/custom_components/` kopieren.
2. Home Assistant neu starten.
3. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach **Beckhoff ADS Auto** suchen.
4. PLC-Host, AMS Net ID, ADS-Port und Root-Symbole eingeben.

`pyads` wird über `manifest.json` automatisch installiert. Bei einer Docker-Installation muss der Container ausgehend die PLC erreichen können; bei Router/NAT ist zusätzlich die ADS Route einzurichten.

### HACS

Das Repository als benutzerdefiniertes Repository vom Typ **Integration** hinzufügen. Danach **Beckhoff ADS Auto** installieren und Home Assistant neu starten.

## Home Assistant als Docker-Container

Bei Docker müssen Dateien in das auf dem Host gemountete Home-Assistant-Konfigurationsverzeichnis kopiert werden. Der Zielpfad im Container ist normalerweise `/config`.

Zuerst den Container und die Mounts prüfen:

```bash
docker ps
docker inspect homeassistant --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'
```

Wenn der Host-Ordner beispielsweise `/opt/homeassistant` ist, kann die Integration direkt dort installiert werden:

```bash
mkdir -p /opt/homeassistant/custom_components
unzip beckhoff_ads_auto.zip -d /tmp/beckhoff_ads_auto
cp -r /tmp/beckhoff_ads_auto/custom_components/beckhoff_ads_auto /opt/homeassistant/custom_components/
docker restart homeassistant
```

Bei Docker Compose wird normalerweise der Ordner neben `configuration.yaml` verwendet:

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

`network_mode: host` ist auf einem Linux-Raspberry-Pi für ADS am einfachsten. Dadurch kann der Container die Netzwerkadresse des Raspberry Pi verwenden. Nach Änderungen an `docker-compose.yml`:

```bash
docker compose up -d
```

Danach wird HACS wie oben beschrieben installiert. Alternativ kann die Integration ohne HACS direkt nach `/opt/homeassistant/custom_components/beckhoff_ads_auto` kopiert werden. `pyads` wird beim Laden der Integration anhand der `manifest.json` in die Home-Assistant-Abhängigkeiten installiert.

Die ADS-Route in TwinCAT muss auf die IP-Adresse und AMS Net ID des Raspberry Pi zeigen. Bei Docker Bridge-Netzwerken kann die Container-IP wechseln; deshalb wird für diese Integration auf dem Raspberry Pi `network_mode: host` empfohlen.

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
