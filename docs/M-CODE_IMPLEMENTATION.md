# M-Code Implementierung - Klipper-CNC

## Übersicht: Program Control M-Codes

Dieses Dokument beschreibt die Implementierung der CNC Program Control M-Codes (M0, M1, M2, M30) in Klipper-CNC und erklärt die Unterschiede zu den ISO/LinuxCNC Standards.

---

## M0 - Program Pause (Unconditional)

### ISO/LinuxCNC Standard
- **Funktion**: Bedingungslose Programmpause
- **Verhalten**: Stoppt alle Bewegungen, wartet auf Resume/Continue
- **Verwendung**: `M0` oder `M0 (Kommentar)`

### Klipper-CNC Implementierung
```gcode
M0
```

**Verhalten**:
1. Alle laufenden Bewegungen werden abgeschlossen (M400)
2. Programm pausiert via `pause_resume` Modul
3. Fortsetzung via `RESUME` Befehl

**Anforderungen**: `[pause_resume]` muss in `printer.cfg` konfiguriert sein

**Status**: ✅ Standard-konform

---

## M1 - Optional Program Pause

### ISO/LinuxCNC Standard
- **Funktion**: Optionale Programmpause (nur wenn aktiviert)
- **Verhalten**: Wie M0, aber nur wenn "Optional Stop" aktiviert ist
- **Verwendung**: `M1` oder `M1 (Kommentar)`

### Klipper-CNC Implementierung
```gcode
M1
```

**Verhalten**:
- Wenn `optional_stop_enabled = True`: Wie M0
- Wenn `optional_stop_enabled = False`: Befehl wird ignoriert

**Konfiguration**:
```gcode
SET_OPTIONAL_STOP ENABLE=1  # Aktivieren (Standard)
SET_OPTIONAL_STOP ENABLE=0  # Deaktivieren
```

**Status**: ✅ Standard-konform

---

## M2 - Program End

### ISO/LinuxCNC Standard
- **Funktion**: Programmende
- **Verhalten**: 
  - Beendet das laufende Programm
  - Wechselt in MDI-Modus
  - Setzt G-Code Modi zurück (G90, G54, etc.)
  - Schaltet Spindel/Kühlmittel aus
- **Verwendung**: `M2`

### Klipper-CNC Implementierung

#### ✅ Standard Mode: `M2`
```gcode
M2
```

**Verhalten**:
1. Alle Bewegungen abschließen (M400)
2. G-Code State zurücksetzen (G90, G54)
3. Spindel stoppen (M5 - falls konfiguriert)
4. Kühlmittel aus (M9 - falls konfiguriert)
5. Message: "Program end - Ready for new program (MDI mode)"

**Status**: ✅ Standard-konform

---

#### 🔧 Projekt-Erweiterung: `M2 RESTART`

```gcode
M2 RESTART
```

**Funktion**: Program End **mit Reset** für Wiederholung

**Verhalten**:
1. Alle M2 Standard-Funktionen
2. **Zusätzlich**: Event `virtual_sdcard:complete` senden
3. **Zusätzlich**: Moonraker setzt File-Position auf Anfang zurück
4. Message: "Program end with reset - Ready for restart"

**Verwendung**: 
- Für CNC-Operationen, die wiederholt werden sollen
- Ersetzt ISO/LinuxCNC M30 Funktionalität (siehe unten)

**Status**: ⚙️ Projekt-Erweiterung (nicht ISO-Standard)

**Äquivalent zu**: ISO/LinuxCNC **M30**

---

## M30 - Program End with Reset / Delete File

### ISO/LinuxCNC Standard (CNC)
- **Funktion**: Program End with Reset
- **Verhalten**: 
  - Wie M2, aber zusätzlich:
  - Spult Programm zurück (rewind)
  - Optional: Rückkehr zur Home-Position
  - Bereitet Maschine für nächsten Zyklus vor
- **Verwendung**: `M30`

### Marlin/RepRap Standard (3D-Print)
- **Funktion**: Delete File
- **Verhalten**: Löscht eine Datei von der SD-Karte
- **Verwendung**: `M30 /path/to/file.gcode`

---

### Klipper-CNC Implementierung

**Projekt-Entscheidung**: 
- M30 ist **DEAKTIVIERT** (wie Original-Klipper: `cmd_error`)
- CNC M30-Funktionalität ist in **M2 RESTART** implementiert
- 3D-Print M30 (Delete File) wird **NICHT** unterstützt

---

#### ❌ M30 (jegliche Verwendung) → ERROR

```gcode
M30
M30 /path/to/file.gcode
```

**Ergebnis**: 
```
!! SD write not supported
```

**Begründung**: 
- Original-Klipper Verhalten beibehalten
- Keine Konflikte zwischen CNC und 3D-Print Standards
- **Alternative**: Verwende `M2 RESTART` für CNC Program Reset

---

## Vergleichstabelle: Standard vs. Implementierung

| Befehl | ISO/LinuxCNC Standard | Klipper-CNC Implementierung | Status |
|--------|----------------------|----------------------------|--------|
| **M0** | Program Pause | Program Pause | ✅ Identisch |
| **M1** | Optional Pause | Optional Pause | ✅ Identisch |
| **M2** | Program End (MDI) | Program End (MDI) | ✅ Identisch |
| **M2 RESTART** | *(existiert nicht)* | Program End + Reset | ⚙️ Erweiterung |
| **M30** | Program End + Reset | ERROR (cmd_error) | ⚠️ Deaktiviert |

---

## Entscheidungsgründe

### Warum M2 RESTART statt M30 für CNC Reset?

1. **Original-Klipper Kompatibilität**: M30 bleibt wie in Original-Klipper deaktiviert (`cmd_error`)
2. **Keine Änderung am Core**: virtual_sdcard.py bleibt unverändert
3. **Klarheit**: Explizite Unterscheidung zwischen:
   - `M2` = Job beendet, MDI-Modus
   - `M2 RESTART` = Job beendet, bereit für Wiederholung
4. **Flexibilität**: CNC-Funktionalität ohne Konflikt mit Original-Klipper
5. **Integration**: Funktioniert nahtlos mit Moonraker Auto-Reset

### Warum M30 deaktiviert lassen?

1. **Original-Klipper Standard**: Bleibt konsistent mit Upstream-Klipper
2. **Keine Breaking Changes**: Kein custom Code in virtual_sdcard.py nötig
3. **Vermeidung von Bugs**: Klare Trennung ohne Dual-Behavior
4. **Einfacher zu warten**: Weniger Abweichungen von Original-Klipper

---

## Moonraker Integration

### Auto-Reset Funktionalität

Wenn `M2 RESTART` ausgeführt wird:

1. **Klipper** sendet Event: `virtual_sdcard:complete`
2. **Moonraker** (`m30_handler.py`) empfängt Event
3. **Moonraker** führt aus: `SDCARD_RESET_FILE`
4. **File-Position** wird auf Anfang zurückgesetzt
5. **Bereit für** Cycle Start / Resume

**Konfiguration** (`moonraker.conf`):
```ini
[m2_restart_handler]
# Automatisch geladen, keine Konfiguration nötig
# Überwacht virtual_sdcard:complete Event von M2 RESTART
```

---

## Verwendungsbeispiele

### CNC-Workflow mit Wiederholung

```gcode
; Program Start
G21 G90 G54          ; Metric, Absolute, WCS1
G0 Z5                ; Safe height
M3 S12000            ; Spindle on

; ... CNC Operations ...

M5                   ; Spindle off
M9                   ; Coolant off
G0 Z50               ; Safe position

M2 RESTART           ; Program end - Ready for restart
```

**Ergebnis**: File-Position wird zurückgesetzt, Cycle Start startet Programm von vorne

---

### CNC-Workflow ohne Wiederholung

```gcode
; Single-run program
G21 G90 G54
G0 Z5
M3 S12000

; ... CNC Operations ...

M5
M9
G0 Z50

M2                   ; Program end - MDI mode
```

**Ergebnis**: Programm beendet, Maschine im MDI-Modus, kein Auto-Reset

---

### 3D-Print File Management

```gcode
; Delete old test files
M30 /test/old_print.gcode
M30 /calibration/temp.gcode

; Start new print
M23 /prints/final.gcode
M24
```

**Ergebnis**: Dateien werden gelöscht, kompatibel mit Marlin/RepRap

---

## Migration von Standard-Klipper

### Änderungen für bestehende G-Code Programme

| Alt (ISO/LinuxCNC) | Neu (Klipper-CNC) | Anmerkung |
|--------------------|-------------------|-----------|
| `M30` | `M2 RESTART` | Für CNC Program Reset |
| `M2` | `M2` | Keine Änderung nötig |
| `M30 <file>` | `M30 <file>` | 3D-Print: Keine Änderung |

### Post-Processor Anpassung (Fusion360, etc.)

**Fusion360 CAM Post-Processor**:

Standard-Output verwendet oft M30 für Program End. Dies muss angepasst werden:

**Vorher (ISO/LinuxCNC Standard)**:
```javascript
// Fusion360 Post-Processor (alt)
writeBlock("M30");  // Program end with reset
```

**Nachher (Klipper-CNC)**:
```javascript
// Fusion360 Post-Processor (neu)
writeBlock("M2 RESTART");  // Program end with reset
// ODER
writeBlock("M2");  // Program end (kein Reset)
```

**Empfehlung**: Erstelle einen custom Post-Processor für Klipper-CNC

---

## Technische Details

### Event Flow: M2 RESTART

```
┌─────────────────┐
│ G-Code: M2 RESTART │
└────────┬────────┘
         │
         v
┌─────────────────────────┐
│ cnc_program_control.py  │
│ - Wait moves            │
│ - Reset G-Code state    │
│ - Stop spindle/coolant  │
│ - Send event: complete  │
└────────┬────────────────┘
         │
         v
┌─────────────────────────┐
│ Moonraker               │
│ m2_restart_handler.py   │
│ - Detect state=complete │
│ - Run SDCARD_RESET_FILE │
└────────┬────────────────┘
         │
         v
┌─────────────────────────┐
│ virtual_sdcard.py       │
│ - Reset file position   │
│ - Ready for restart     │
└─────────────────────────┘
```

### Konfigurationsdateien

**printer.cfg**:
```ini
[cnc_program_control]
# Aktiviert M0, M1, M2, M30

[pause_resume]
# Erforderlich für M0/M1
recover_velocity: 50

[virtual_sdcard]
path: ~/printer_data/gcodes
```

**moonraker.conf**:
```ini
[m30_handler]
# Automatisch geladen, keine Config nötig
# Überwacht print_stats für state='complete'
# Führt SDCARD_RESET_FILE bei M2 RESTART aus
```

---

## FAQ

### Q: Warum funktioniert mein M30 nicht mehr?

**A**: M30 ist wie in Original-Klipper deaktiviert (`SD write not supported`). Verwende stattdessen:
```gcode
M2 RESTART    # Für CNC Program Reset
```

### Q: Kann ich M30 für File-Delete nutzen?

**A**: Nein, M30 ist komplett deaktiviert (Original-Klipper Verhalten). Für File-Management verwende Moonraker's API oder Frontend-Funktionen.

### Q: Was ist der Unterschied zwischen M2 und M2 RESTART?

**A**: 
- **M2**: Programm beendet, Maschine im MDI-Modus, **kein** File-Reset
- **M2 RESTART**: Programm beendet, File-Position zurückgesetzt, **bereit für Cycle Start**

### Q: Funktioniert M30 noch für 3D-Druck?

**A**: Nein, M30 ist komplett deaktiviert. Das ist konsistent mit Original-Klipper, wo M30 ebenfalls `SD write not supported` zurückgibt.

### Q: Ist M2 RESTART Standard-konform?

**A**: Nein, es ist eine Projekt-Erweiterung. Es implementiert die Funktionalität von ISO/LinuxCNC M30, aber mit einem anderen Namen zur Vermeidung von Konflikten.

---

## Referenzen

### Standards

- **ISO 6983**: Programming format and definitions of address words (G-Code)
- **LinuxCNC**: https://linuxcnc.org/docs/html/gcode/m-code.html
- **Marlin Firmware**: https://marlinfw.org/docs/gcode/M030.html
- **RepRap Wiki**: https://reprap.org/wiki/G-code#M30:_Program_Stop

### Projekt-Dateien

- **Implementierung**: `klipper-cnc/klippy/extras/cnc_program_control.py`
- **Virtual SD**: `klipper-cnc/klippy/extras/virtual_sdcard.py` (Original-Klipper)
- **Moonraker Handler**: `moonraker-cnc/moonraker/components/m2_restart_handler.py`
- **Konfiguration**: `klipper-cnc/config/example-cnc-program-control.cfg`

---

## Changelog

### Version 1.0 (2025-12-10)
- ✅ M0, M1, M2 Standard-konform implementiert
- ✅ M2 RESTART als Projekt-Erweiterung hinzugefügt
- ✅ M30 auf Delete-File reduziert (3D-Print Kompatibilität)
- ✅ Moonraker Integration für Auto-Reset
- ✅ Dokumentation erstellt

---

**Projekt**: Klipper-CNC  
**Autor**: Universal CNC Controller Team  
**Lizenz**: GNU GPLv3  
**Datum**: 10. Dezember 2025
