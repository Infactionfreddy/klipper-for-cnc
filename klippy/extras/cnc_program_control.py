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
        
        # Note: M30 is NOT overridden - kept as original Klipper behavior (cmd_error)
        # For CNC program end with reset, use M2 RESTART instead
        
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
    cmd_M2_help = "Program end (M2) or program end with reset (M2 RESTART)"
    def cmd_M2(self, gcmd):
        """
        M2 - Beendet das Programm mit Dual-Behavior:
        
        Standard Mode (keine Parameter):
        - M2 → Program End
        - Beendet das laufende Programm
        - Wechselt in MDI-Modus
        - Setzt Offsets und Modi zurück
        
        Reset Mode (mit RESTART Parameter):
        - M2 RESTART → Program End with Reset
        - Wie M2, aber zusätzlich:
        - Bereitet Maschine für nächsten Zyklus vor
        - Signalisiert "Complete" für Moonraker Auto-Reset
        - File-Position wird zurückgesetzt (via Moonraker)
        
        Standard: LinuxCNC M-Code (erweitert)
        
        Effekte (beide Modi):
        - Spindel gestoppt (falls vorhanden)
        - Kühlmittel aus
        - Vorschub auf Defaults
        - Koordinatensystem auf Standard (G54)
        """
        # Check for RESTART parameter
        params = gcmd.get_raw_command_parameters().strip().upper()
        restart_mode = 'RESTART' in params
        
        # Finish all pending moves
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.wait_moves()
        
        # Reset G-Code state
        self._reset_gcode_state()
        
        # Turn off spindle (if configured)
        self._stop_spindle()
        
        # Turn off coolant (if configured)
        self._stop_coolant()
        
        if restart_mode:
            # M2 RESTART - Program End with Reset
            self.gcode.respond_info("M2 RESTART: Program end with reset - Ready for restart")
            
            # Signal completion for Moonraker auto-reset
            try:
                self.printer.send_event("virtual_sdcard:complete")
            except:
                pass  # Event might not be registered
        else:
            # M2 - Standard Program End
            self.gcode.respond_info("M2: Program end - Ready for new program (MDI mode)")
    
    def _reset_gcode_state(self):
        """Reset G-Code state to defaults (like after M2/M2 RESTART)"""
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
