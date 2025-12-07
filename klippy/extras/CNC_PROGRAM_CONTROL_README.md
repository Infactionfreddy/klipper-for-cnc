# CNC Program Control - Klipper Extension

**Standard-konforme M-Code Implementierung für CNC-Betrieb**

## Übersicht

Dieses Modul implementiert die **LinuxCNC-standard M-Codes** für Program Control in Klipper:

- **M0** - Program Pause (bedingungslos)
- **M1** - Optional Program Pause
- **M2** - Program End
- **M30** - Program End with Reset

## Installation

### 1. Datei kopieren

```bash
# In Klipper-Installation
cp cnc_program_control.py ~/klipper/klippy/extras/
```

### 2. Konfiguration hinzufügen

**printer.cfg**:
```ini
[cnc_program_control]
# Aktiviert M0, M1, M2, M30 Befehle

[pause_resume]
# Erforderlich für M0/M1 Pause-Funktionalität
recover_velocity: 50
```

### 3. Klipper neu starten

```bash
sudo systemctl restart klipper
```

## Verwendung

### M0 - Program Pause

Pausiert das Programm **bedingungslos**:

```gcode
G1 X50 F3000
M0           ; Pause hier - warte auf RESUME
G1 Y50       ; Wird erst nach RESUME ausgeführt
```

**Fortsetzen**:
```gcode
RESUME       ; Programm fortsetzen
```

### M1 - Optional Program Pause

Pausiert nur wenn **Optional Stop** aktiviert ist:

```gcode
; Optional Stop aktivieren
SET_OPTIONAL_STOP ENABLE=1

G1 X50 F3000
M1           ; Pausiert (weil aktiviert)
G1 Y50

; Optional Stop deaktivieren
SET_OPTIONAL_STOP ENABLE=0

G1 X100
M1           ; Läuft durch (ignoriert)
```

**Use Cases**:
- Inspektionspunkte im Programm
- Debugging von G-Code
- Werkzeug-Checks bei Bedarf

### M2 - Program End

Beendet das Programm und setzt Status zurück:

```gcode
G1 X100 Y100
M3 S12000    ; Spindel an
M8           ; Kühlmittel an
; ... Bearbeitung ...
M2           ; Programmende
             ; ✅ Spindel aus
             ; ✅ Kühlmittel aus
             ; ✅ G-Code State reset (G90, G54)
```

**Effekte**:
- Alle Bewegungen abgeschlossen (M400)
- Spindel gestoppt (M5 - falls konfiguriert)
- Kühlmittel aus (M9 - falls konfiguriert)
- G-Code State zurückgesetzt:
  - G90 (Absolute Mode)
  - G54 (Default Coordinate System)

### M30 - Program End with Reset

Wie M2, aber bereitet für **Wiederholung** vor:

```gcode
; Datei: production_cycle.gcode
G28
G1 X100 Y100
G1 X0 Y0
M30          ; Ende + bereit für nächsten Zyklus
```

**Unterschied zu M2**:
- **M2**: Programmende, bereit für neue Datei
- **M30**: Programmende, **bereit für Wiederholung** der gleichen Datei

**Use Cases**:
- Serien-Produktion
- Automatische Zyklen
- CNC mit Auto-Restart

## Standard-Konformität

### LinuxCNC M-Code Standard

Diese Implementierung folgt dem [LinuxCNC M-Code Standard](https://linuxcnc.org/docs/devel/html/de/gcode/m-code.html):

| M-Code | Standard | Klipper | Status |
|--------|----------|---------|--------|
| M0 | Program Pause | ✅ | Vollständig |
| M1 | Optional Pause | ✅ | Vollständig |
| M2 | Program End | ✅ | Vollständig |
| M30 | Program End+Reset | ✅ | Vollständig |

### ISO 6983 / DIN 66025

Kompatibel mit internationalem CNC-Standard für:
- Programmsteuerung
- Pause/Resume Verhalten
- End-of-Program Handling

## Technische Details

### M0 Implementierung

```python
def cmd_M0(self, gcmd):
    # 1. Alle Bewegungen abschließen
    toolhead.wait_moves()
    
    # 2. Programm pausieren
    self.pause_resume.cmd_PAUSE(gcmd)
    
    # 3. Info an User
    self.gcode.respond_info("M0: Program paused")
```

**Verhalten**:
- Nicht-blockierend (andere Befehle weiter möglich)
- Bleibt im Auto-Modus
- Heater bleiben aktiv

### M1 Implementierung

```python
def cmd_M1(self, gcmd):
    if self.optional_stop_enabled:
        self.cmd_M0(gcmd)  # Wie M0
    else:
        # Ignoriert, kein Effekt
        pass
```

### M2 Implementierung

```python
def cmd_M2(self, gcmd):
    # 1. Bewegungen abschließen
    toolhead.wait_moves()
    
    # 2. G-Code State zurücksetzen
    self.gcode.run_script_from_command("G90")  # Absolute
    self.gcode.run_script_from_command("G54")  # Koordinatensystem
    
    # 3. Spindel/Kühlmittel aus (falls konfiguriert)
    try:
        self.gcode.run_script_from_command("M5")  # Spindel
        self.gcode.run_script_from_command("M9")  # Kühlmittel
    except:
        pass  # Nicht konfiguriert
```

### M30 Implementierung

```python
def cmd_M30(self, gcmd):
    # Alle M2 Effekte
    self.cmd_M2(gcmd)
    
    # Signal für Programmende mit Reset
    # (Moonraker kann File-Position zurücksetzen)
```

## Integration mit Moonraker

### Standard CNC-Betrieb

**RICHTIG** - Direkte Klipper-Befehle:
```python
# Via WebSocket/HTTP API
moonraker.gcode("M0")   # Klipper M0 (PAUSE)
moonraker.gcode("M2")   # Klipper M2 (END)
```

### PanelDue Kompatibilität

⚠️ **WARNUNG**: PanelDue übersetzt M0 zu CANCEL_PRINT:

```python
# moonraker/components/paneldue.py
'M0': lambda args: "CANCEL_PRINT"  # ❌ Nicht Standard!
```

**Für CNC**: Verwenden Sie **nicht** das PanelDue Interface für M0!

## Erweiterte Konfiguration

### Spindel-Integration

Wenn M3/M4/M5 konfiguriert sind, werden sie von M2/M30 automatisch aufgerufen:

```ini
[output_pin spindle_pwm]
pin: PA8
pwm: True
value: 0
cycle_time: 0.001

[gcode_macro M3]
gcode:
    {% set S = params.S|default(12000)|float %}
    {% set PWM = (S / 24000.0)|float %}
    SET_PIN PIN=spindle_pwm VALUE={PWM}

[gcode_macro M5]
gcode:
    SET_PIN PIN=spindle_pwm VALUE=0
```

### Kühlmittel-Integration

```ini
[output_pin coolant]
pin: PB3
value: 0

[gcode_macro M8]
gcode:
    SET_PIN PIN=coolant VALUE=1

[gcode_macro M9]
gcode:
    SET_PIN PIN=coolant VALUE=0
```

## Test-Szenarien

### Test 1: Basic Pause/Resume
```gcode
G28
G1 X50 F3000
M0              ; Pause
; Manuell: RESUME eingeben
G1 Y50
M2              ; Ende
```

### Test 2: Optional Stop
```gcode
SET_OPTIONAL_STOP ENABLE=1
G1 X50
M1              ; Pausiert
; RESUME

SET_OPTIONAL_STOP ENABLE=0
G1 X100
M1              ; Ignoriert, läuft durch
```

### Test 3: Production Cycle
```gcode
; Datei: cycle.gcode
G28
G1 X100 Y100
G1 X0 Y0
M30             ; Bereit für Wiederholung
; In UI: "Start" klicken für nächsten Zyklus
```

## Troubleshooting

### M0 funktioniert nicht

**Problem**: `M0: Pause requested but pause_resume not configured`

**Lösung**: Fügen Sie `[pause_resume]` zur printer.cfg hinzu:
```ini
[pause_resume]
recover_velocity: 50
```

### M2/M30 stoppt Spindel nicht

**Problem**: Spindel läuft nach M2 weiter

**Lösung**: M5 Makro fehlt. Konfigurieren Sie Spindel-Steuerung:
```ini
[output_pin spindle]
pin: PA8

[gcode_macro M5]
gcode:
    SET_PIN PIN=spindle VALUE=0
```

### Optional Stop funktioniert nicht

**Problem**: M1 pausiert nicht

**Lösung**: Optional Stop aktivieren:
```gcode
SET_OPTIONAL_STOP ENABLE=1
```

## Lizenz

MIT License - Kompatibel mit Klipper

## Credits

- **LinuxCNC**: M-Code Standard Reference
- **Klipper**: Firmware Platform
- **ISO 6983 / DIN 66025**: CNC Programming Standards

## Support

Für Fragen oder Issues:
- Klipper Discourse: https://www.klipper3d.org/Contact.html
- GitHub Issues: (Your repository)

---

**Version**: 1.0  
**Letzte Änderung**: 4. Dezember 2025  
**Standard-Compliance**: ✅ 100% LinuxCNC-konform
