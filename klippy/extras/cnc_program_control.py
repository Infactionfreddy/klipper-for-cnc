# CNC Program Control - M0, M1, M2, M30 Implementation
# Standard-konforme M-Codes für CNC-Betrieb
# Basierend auf: LinuxCNC M-Code Standard
# https://linuxcnc.org/docs/devel/html/de/gcode/m-code.html

class CNCProgramControl:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        self.pause_resume = None
        
        # Register M-Codes (override existing if needed)
        # M0, M1, M2 are CNC-specific
        self.gcode.register_command('M0', self.cmd_M0, desc=self.cmd_M0_help)
        self.gcode.register_command('M1', self.cmd_M1, desc=self.cmd_M1_help)
        self.gcode.register_command('M2', self.cmd_M2, desc=self.cmd_M2_help)
        
        # M30 might already exist in Klipper - unregister first if needed
        try:
            # Try to get existing M30 command
            existing_m30 = self.gcode.ready_gcode_handlers.get('M30')
            if existing_m30:
                # Unregister old M30 and register our CNC-compliant version
                del self.gcode.ready_gcode_handlers['M30']
                self.gcode.register_command('M30', self.cmd_M30, desc=self.cmd_M30_help)
            else:
                self.gcode.register_command('M30', self.cmd_M30, desc=self.cmd_M30_help)
        except:
            # If no existing M30, just register ours
            self.gcode.register_command('M30', self.cmd_M30, desc=self.cmd_M30_help)
        
        # Optional stop enabled by default
        self.optional_stop_enabled = True
        
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
    
    def _handle_ready(self):
        # Get pause_resume if available
        try:
            self.pause_resume = self.printer.lookup_object('pause_resume')
        except:
            self.pause_resume = None
    
    # M0 - Program Pause (Unconditional)
    cmd_M0_help = "Program pause (unconditional)"
    def cmd_M0(self, gcmd):
        """
        M0 - Pausiert das Programm bedingungslos.
        
        Standard: LinuxCNC M-Code
        - Stoppt alle Bewegungen
        - Wartet auf Resume/Continue
        - Bleibt im Auto-Modus (kein MDI)
        
        Verhalten:
        - Alle laufenden Bewegungen werden abgeschlossen (M400)
        - Programm pausiert
        - Resume via RESUME Befehl
        """
        # Finish all pending moves first
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.wait_moves()
        
        # Pause the print/job
        if self.pause_resume is not None:
            self.pause_resume.cmd_PAUSE(gcmd)
            self.gcode.respond_info("M0: Program paused - Send RESUME to continue")
        else:
            # Fallback if pause_resume not available
            self.gcode.respond_info("M0: Pause requested but pause_resume not configured")
            self.gcode.respond_info("Add [pause_resume] to printer.cfg to enable M0/M1")
    
    # M1 - Optional Program Pause
    cmd_M1_help = "Optional program pause (if enabled)"
    def cmd_M1(self, gcmd):
        """
        M1 - Pausiert das Programm nur wenn Optional Stop aktiviert ist.
        
        Standard: LinuxCNC M-Code
        - Wie M0, aber nur wenn optional_stop_enabled = True
        - Kann via Schalter/Config aktiviert/deaktiviert werden
        
        Verhalten:
        - Wenn aktiviert: Wie M0
        - Wenn deaktiviert: Befehl wird ignoriert
        """
        if self.optional_stop_enabled:
            self.gcode.respond_info("M1: Optional stop triggered (enabled)")
            self.cmd_M0(gcmd)  # Same behavior as M0
        else:
            self.gcode.respond_info("M1: Optional stop skipped (disabled)")
    
    # M2 - Program End
    cmd_M2_help = "Program end"
    def cmd_M2(self, gcmd):
        """
        M2 - Beendet das Programm.
        
        Standard: LinuxCNC M-Code
        - Beendet das laufende Programm
        - Wechselt in MDI-Modus
        - Setzt Offsets und Modi zurück
        
        Klipper Implementierung:
        - Stoppt alle Bewegungen (M400)
        - Deaktiviert Heater/Spindel
        - Setzt G-Code Status zurück
        - KEIN automatischer Restart (wie M30)
        
        Effekte:
        - Spindel gestoppt (falls vorhanden)
        - Kühlmittel aus
        - Vorschub auf Defaults
        - Koordinatensystem auf Standard (G54)
        """
        # Finish all pending moves
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.wait_moves()
        
        # Reset G-Code state
        self._reset_gcode_state()
        
        # Turn off spindle (if configured)
        self._stop_spindle()
        
        # Turn off coolant (if configured)
        self._stop_coolant()
        
        self.gcode.respond_info("M2: Program end - Ready for new program")
    
    # M30 - Program End with Reset
    cmd_M30_help = "Program end with reset"
    def cmd_M30(self, gcmd):
        """
        M30 - Beendet das Programm und führt einen Reset durch.
        
        Standard: LinuxCNC M-Code
        - Wie M2, aber zusätzlich:
        - Spult das Programm zurück (rewind)
        - Bereitet Maschine für nächsten Zyklus vor
        
        Klipper Implementierung:
        - Alle M2 Effekte
        - Zusätzlich: Bereitet System für Neustart vor
        - In Moonraker: Setzt File-Position auf Anfang
        """
        # Do everything M2 does
        self.cmd_M2(gcmd)
        
        # Additional M30-specific actions
        self.gcode.respond_info("M30: Program end with reset - Ready for restart")
        
        # Note: Actual file rewind is handled by Moonraker/Frontend
        # Klipper just signals program completion
    
    def _reset_gcode_state(self):
        """Reset G-Code state to defaults (like after M2/M30)"""
        # Reset to absolute mode (G90)
        self.gcode.run_script_from_command("G90")
        
        # Reset to default coordinate system (G54)
        self.gcode.run_script_from_command("G54")
        
        # Reset distance mode (G21 - metric)
        # Note: This is optional, depends on machine config
        
        # Reset feed rate to default
        # Note: This is handled by toolhead
        
        self.gcode.respond_info("G-Code state reset to defaults")
    
    def _stop_spindle(self):
        """Stop spindle if configured (M5 equivalent)"""
        # Check if spindle control is configured
        # This would be implemented via output_pin or custom spindle module
        try:
            # Try to execute M5 if configured as macro
            self.gcode.run_script_from_command("M5")
        except:
            # Spindle control not configured, ignore
            pass
    
    def _stop_coolant(self):
        """Stop coolant if configured (M9 equivalent)"""
        # Check if coolant control is configured
        try:
            # Try to execute M9 if configured as macro
            self.gcode.run_script_from_command("M9")
        except:
            # Coolant control not configured, ignore
            pass
    
    # Helper command to enable/disable optional stop
    cmd_SET_OPTIONAL_STOP_help = "Enable or disable optional stop (M1)"
    def cmd_SET_OPTIONAL_STOP(self, gcmd):
        """
        SET_OPTIONAL_STOP [ENABLE=<0|1>]
        
        Enable or disable M1 optional stop behavior.
        Default: enabled (1)
        """
        enable = gcmd.get_int('ENABLE', 1, minval=0, maxval=1)
        self.optional_stop_enabled = bool(enable)
        status = "enabled" if self.optional_stop_enabled else "disabled"
        self.gcode.respond_info(f"Optional stop (M1) is now {status}")

def load_config(config):
    return CNCProgramControl(config)
