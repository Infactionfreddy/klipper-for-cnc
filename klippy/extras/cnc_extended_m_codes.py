# CNC M-Codes - Comprehensive LinuxCNC M-Code Implementation
# Standard-konforme M-Codes für CNC-Betrieb
# Basierend auf: https://linuxcnc.org/docs/devel/html/de/gcode/m-code.html
#
# Copyright (C) 2025 Universal CNC Controller Team
# This file may be distributed under the terms of the GNU GPLv3 license.

import logging

class CNCMCodes:
    """
    Comprehensive CNC M-Code Implementation
    
    Implements LinuxCNC-compatible M-Codes for professional CNC operation:
    
    Program Control:
    - M0, M1: Program pause (unconditional/optional)
    - M2, M30: Program end
    - M60: Pallet change pause
    
    Spindle Control:
    - M3, M4, M5: Spindle on CW/CCW, off
    - M19: Spindle orientation
    
    Coolant Control:
    - M7: Mist coolant on
    - M8: Flood coolant on
    - M9: All coolant off
    
    Override Control:
    - M48, M49: Enable/disable speed and feed overrides
    - M50: Feed override control
    - M51: Spindle speed override control
    - M52: Adaptive feed control
    - M53: Feed stop control
    
    Tool Control:
    - M61: Set current tool number
    
    Digital I/O:
    - M62-M65: Digital output control (synchronized and immediate)
    - M66: Wait on input
    
    Analog I/O:
    - M67: Analog output, synchronized
    - M68: Analog output, immediate
    
    Modal State:
    - M70: Save modal state
    - M71: Invalidate saved modal state
    - M72: Restore modal state
    - M73: Save and auto-restore modal state
    """
    
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        self.reactor = self.printer.get_reactor()
        
        # State tracking
        self.optional_stop_enabled = config.getboolean('optional_stop_enabled', True)
        self.spindle_state = {'running': False, 'direction': 0, 'speed': 0}
        self.coolant_mist = False
        self.coolant_flood = False
        self.feed_override_enabled = True
        self.spindle_override_enabled = True
        self.adaptive_feed_enabled = False
        self.feed_stop_enabled = False
        
        # Modal state stack (for M70-M73)
        self.modal_state_stack = []
        
        # Digital I/O state
        self.digital_outputs = {}
        self.digital_output_queue = []
        
        # Analog I/O state
        self.analog_outputs = {}
        self.analog_output_queue = []
        
        # References to other components
        self.pause_resume = None
        self.toolhead = None
        
        # Register M-Codes
        self._register_commands()
        
        # Register for ready event
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        
        logging.info("CNC M-Codes: Comprehensive M-Code support initialized")
    
    def _handle_ready(self):
        """Initialize references to other printer objects"""
        try:
            self.pause_resume = self.printer.lookup_object('pause_resume')
        except:
            logging.info("CNC M-Codes: pause_resume not available")
            self.pause_resume = None
        
        try:
            self.toolhead = self.printer.lookup_object('toolhead')
        except:
            logging.info("CNC M-Codes: toolhead not available")
            self.toolhead = None
    
    def _register_commands(self):
        """Register all M-Code commands"""
        
        # Program Control - NOTE: M0, M1, M2, M30 bereits in cnc_program_control.py
        # Nur M60 hier registrieren
        self.gcode.register_command('M60', self.cmd_M60, 
                                   desc=self.cmd_M60_help)
        
        # Spindle Control
        self.gcode.register_command('M3', self.cmd_M3, 
                                   desc=self.cmd_M3_help)
        self.gcode.register_command('M4', self.cmd_M4, 
                                   desc=self.cmd_M4_help)
        self.gcode.register_command('M5', self.cmd_M5, 
                                   desc=self.cmd_M5_help)
        self.gcode.register_command('M19', self.cmd_M19, 
                                   desc=self.cmd_M19_help)
        
        # Coolant Control
        self.gcode.register_command('M7', self.cmd_M7, 
                                   desc=self.cmd_M7_help)
        self.gcode.register_command('M8', self.cmd_M8, 
                                   desc=self.cmd_M8_help)
        self.gcode.register_command('M9', self.cmd_M9, 
                                   desc=self.cmd_M9_help)
        
        # Override Control
        self.gcode.register_command('M48', self.cmd_M48, 
                                   desc=self.cmd_M48_help)
        self.gcode.register_command('M49', self.cmd_M49, 
                                   desc=self.cmd_M49_help)
        self.gcode.register_command('M50', self.cmd_M50, 
                                   desc=self.cmd_M50_help)
        self.gcode.register_command('M51', self.cmd_M51, 
                                   desc=self.cmd_M51_help)
        self.gcode.register_command('M52', self.cmd_M52, 
                                   desc=self.cmd_M52_help)
        self.gcode.register_command('M53', self.cmd_M53, 
                                   desc=self.cmd_M53_help)
        
        # Tool Control
        self.gcode.register_command('M6', self.cmd_M6, 
                                   desc=self.cmd_M6_help)
        self.gcode.register_command('M61', self.cmd_M61, 
                                   desc=self.cmd_M61_help)
        
        # Digital I/O
        self.gcode.register_command('M62', self.cmd_M62, 
                                   desc=self.cmd_M62_help)
        self.gcode.register_command('M63', self.cmd_M63, 
                                   desc=self.cmd_M63_help)
        self.gcode.register_command('M64', self.cmd_M64, 
                                   desc=self.cmd_M64_help)
        self.gcode.register_command('M65', self.cmd_M65, 
                                   desc=self.cmd_M65_help)
        self.gcode.register_command('M66', self.cmd_M66, 
                                   desc=self.cmd_M66_help)
        
        # Analog I/O
        self.gcode.register_command('M67', self.cmd_M67, 
                                   desc=self.cmd_M67_help)
        self.gcode.register_command('M68', self.cmd_M68, 
                                   desc=self.cmd_M68_help)
        
        # Subroutines (Fanuc-Style)
        self.gcode.register_command('M98', self.cmd_M98, 
                                   desc=self.cmd_M98_help)
        self.gcode.register_command('M99', self.cmd_M99, 
                                   desc=self.cmd_M99_help)
        
        # Modal State Management
        self.gcode.register_command('M70', self.cmd_M70, 
                                   desc=self.cmd_M70_help)
        self.gcode.register_command('M71', self.cmd_M71, 
                                   desc=self.cmd_M71_help)
        self.gcode.register_command('M72', self.cmd_M72, 
                                   desc=self.cmd_M72_help)
        # M73 wird von display_status registriert - nicht hier registrieren
        # um Konflikte zu vermeiden
        # self.gcode.register_command('M73', self.cmd_M73, 
        #                            desc=self.cmd_M73_help)
        
        # Register user-defined M-Codes M100-M199
        # These can be overridden by custom shell commands
        # Exclude M-codes that are already registered by core modules:
        # M110, M112, M114, M115 (gcode.py), M104, M105, M109 (extruder.py)
        # M106, M107 (fan.py), M117, M118 (display_status/respond),
        # M119 (query_endstops), M140, M190 (heater_bed)
        excluded_codes = {110, 112, 114, 115, 104, 105, 109, 106, 107, 117, 118, 119, 140, 190}
        
        for m_code in range(100, 200):
            if m_code in excluded_codes:
                continue
            cmd_name = f"M{m_code}"
            # Only register if not already defined
            if not hasattr(self, f"cmd_M{m_code}"):
                self.gcode.register_command(
                    cmd_name,
                    lambda gcmd, mc=m_code: self._handle_user_mcode(gcmd, mc),
                    desc=f"User-defined M-Code M{m_code}"
                )
    
    # ========================================================================
    # PROGRAM CONTROL M-CODES
    # ========================================================================
    # NOTE: M0, M1, M2, M30 sind bereits in cnc_program_control.py implementiert
    
    cmd_M60_help = "Pallet change pause"
    def cmd_M60(self, gcmd):
        """M60 - Pallet change pause (stops program for pallet exchange)"""
        logging.info("CNC M-Codes: M60 - Pallet change pause")
        gcmd.respond_info("M60: Pallet change pause - Exchange pallet and resume")
        
        if self.pause_resume:
            self.pause_resume.cmd_PAUSE(gcmd)
        else:
            gcmd.respond_info("M60: Pause (pause_resume not configured)")
    
    # ========================================================================
    # SPINDLE CONTROL M-CODES
    # ========================================================================
    
    cmd_M3_help = "Spindle on, clockwise"
    def cmd_M3(self, gcmd):
        """M3 - Start spindle clockwise"""
        speed = gcmd.get_float('S', self.spindle_state['speed'], minval=0.)
        
        self.spindle_state = {
            'running': True,
            'direction': 1,  # Clockwise
            'speed': speed
        }
        
        logging.info(f"CNC M-Codes: M3 - Spindle CW at {speed} RPM")
        gcmd.respond_info(f"M3: Spindle clockwise at S{speed}")
        
        # TODO: Connect to actual spindle control via HAL pins
        # This would require HAL integration or output pin configuration
    
    cmd_M4_help = "Spindle on, counter-clockwise"
    def cmd_M4(self, gcmd):
        """M4 - Start spindle counter-clockwise"""
        speed = gcmd.get_float('S', self.spindle_state['speed'], minval=0.)
        
        self.spindle_state = {
            'running': True,
            'direction': -1,  # Counter-clockwise
            'speed': speed
        }
        
        logging.info(f"CNC M-Codes: M4 - Spindle CCW at {speed} RPM")
        gcmd.respond_info(f"M4: Spindle counter-clockwise at S{speed}")
    
    cmd_M5_help = "Spindle stop"
    def cmd_M5(self, gcmd):
        """M5 - Stop spindle"""
        self.spindle_state['running'] = False
        self.spindle_state['direction'] = 0
        
        logging.info("CNC M-Codes: M5 - Spindle stop")
        gcmd.respond_info("M5: Spindle stopped")
    
    cmd_M19_help = "Orient spindle"
    def cmd_M19(self, gcmd):
        """M19 - Orient spindle to specific angle"""
        angle = gcmd.get_float('R', 0., minval=0., maxval=360.)
        timeout = gcmd.get_float('Q', 5., minval=0.)
        direction = gcmd.get_int('P', 0, minval=0, maxval=2)
        
        logging.info(f"CNC M-Codes: M19 - Orient spindle to {angle}° (timeout {timeout}s)")
        gcmd.respond_info(f"M19: Spindle orientation to R{angle} degrees")
        
        # TODO: Implement spindle orientation with encoder feedback
        # Requires spindle encoder and orientation control
    
    # ========================================================================
    # COOLANT CONTROL M-CODES
    # ========================================================================
    
    cmd_M7_help = "Mist coolant on"
    def cmd_M7(self, gcmd):
        """M7 - Turn on mist coolant"""
        self.coolant_mist = True
        logging.info("CNC M-Codes: M7 - Mist coolant ON")
        gcmd.respond_info("M7: Mist coolant ON")
    
    cmd_M8_help = "Flood coolant on"
    def cmd_M8(self, gcmd):
        """M8 - Turn on flood coolant"""
        self.coolant_flood = True
        logging.info("CNC M-Codes: M8 - Flood coolant ON")
        gcmd.respond_info("M8: Flood coolant ON")
    
    cmd_M9_help = "All coolant off"
    def cmd_M9(self, gcmd):
        """M9 - Turn off all coolant"""
        self.coolant_mist = False
        self.coolant_flood = False
        logging.info("CNC M-Codes: M9 - All coolant OFF")
        gcmd.respond_info("M9: All coolant OFF")
    
    # ========================================================================
    # OVERRIDE CONTROL M-CODES
    # ========================================================================
    
    cmd_M48_help = "Enable speed and feed overrides"
    def cmd_M48(self, gcmd):
        """M48 - Enable speed and feed override controls"""
        self.feed_override_enabled = True
        self.spindle_override_enabled = True
        logging.info("CNC M-Codes: M48 - Overrides enabled")
        gcmd.respond_info("M48: Speed and feed overrides ENABLED")
    
    cmd_M49_help = "Disable speed and feed overrides"
    def cmd_M49(self, gcmd):
        """M49 - Disable speed and feed override controls"""
        self.feed_override_enabled = False
        self.spindle_override_enabled = False
        logging.info("CNC M-Codes: M49 - Overrides disabled")
        gcmd.respond_info("M49: Speed and feed overrides DISABLED")
    
    cmd_M50_help = "Feed override control"
    def cmd_M50(self, gcmd):
        """M50 - Control feed override"""
        enable = gcmd.get_int('P', 1, minval=0, maxval=1)
        self.feed_override_enabled = bool(enable)
        
        status = "ENABLED" if self.feed_override_enabled else "DISABLED"
        logging.info(f"CNC M-Codes: M50 P{enable} - Feed override {status}")
        gcmd.respond_info(f"M50: Feed override {status}")
    
    cmd_M51_help = "Spindle speed override control"
    def cmd_M51(self, gcmd):
        """M51 - Control spindle speed override"""
        enable = gcmd.get_int('P', 1, minval=0, maxval=1)
        self.spindle_override_enabled = bool(enable)
        
        status = "ENABLED" if self.spindle_override_enabled else "DISABLED"
        logging.info(f"CNC M-Codes: M51 P{enable} - Spindle override {status}")
        gcmd.respond_info(f"M51: Spindle override {status}")
    
    cmd_M52_help = "Adaptive feed control"
    def cmd_M52(self, gcmd):
        """M52 - Enable/disable adaptive feed"""
        enable = gcmd.get_int('P', 1, minval=0, maxval=1)
        self.adaptive_feed_enabled = bool(enable)
        
        status = "ENABLED" if self.adaptive_feed_enabled else "DISABLED"
        logging.info(f"CNC M-Codes: M52 P{enable} - Adaptive feed {status}")
        gcmd.respond_info(f"M52: Adaptive feed {status}")
    
    cmd_M53_help = "Feed stop control"
    def cmd_M53(self, gcmd):
        """M53 - Enable/disable feed stop switch"""
        enable = gcmd.get_int('P', 1, minval=0, maxval=1)
        self.feed_stop_enabled = bool(enable)
        
        status = "ENABLED" if self.feed_stop_enabled else "DISABLED"
        logging.info(f"CNC M-Codes: M53 P{enable} - Feed stop {status}")
        gcmd.respond_info(f"M53: Feed stop {status}")
    
    # ========================================================================
    # TOOL CONTROL M-CODES
    # ========================================================================
    
    cmd_M6_help = "Tool change"
    def cmd_M6(self, gcmd):
        """M6 - Tool change (manual or automatic)
        
        LinuxCNC Standard:
        - Stops spindle
        - Changes to tool selected by last T-word
        - Can involve axis movements (configured in printer.cfg)
        - Tool length offset NOT changed (use G43 after M6)
        """
        # Get tool number from last T command or from gcode variable
        # For now, implement manual tool change similar to hal_manualtoolchange
        
        # Stop spindle first
        self.spindle_state['running'] = False
        self.spindle_state['direction'] = 0
        
        tool_number = gcmd.get_int('T', None)
        if tool_number is None:
            # Try to get from saved variable
            tool_number = 0  # Default if no T-word specified
        
        logging.info(f"CNC M-Codes: M6 - Tool change to T{tool_number}")
        gcmd.respond_info(f"M6: Tool change - Insert tool T{tool_number} and resume")
        
        # Pause for manual tool change
        if self.pause_resume:
            self.pause_resume.cmd_PAUSE(gcmd)
        else:
            gcmd.respond_info("M6: Manual tool change (pause not configured)")
        
        # Update current tool
        gcmd.respond_raw(f"SET_GCODE_VARIABLE MACRO=_CNC_STATE VARIABLE=current_tool VALUE={tool_number}")
    
    cmd_M61_help = "Set current tool number"
    def cmd_M61(self, gcmd):
        """M61 - Set current tool number without tool change"""
        tool = gcmd.get_int('Q', minval=0)
        
        logging.info(f"CNC M-Codes: M61 Q{tool} - Set current tool")
        gcmd.respond_info(f"M61: Current tool set to T{tool}")
        
        # Update tool tracking variable
        gcmd.respond_raw(f"SET_GCODE_VARIABLE MACRO=_CNC_STATE VARIABLE=current_tool VALUE={tool}")
    
    # ========================================================================
    # DIGITAL I/O M-CODES
    # ========================================================================
    
    cmd_M62_help = "Digital output ON, synchronized"
    def cmd_M62(self, gcmd):
        """M62 - Turn on digital output synchronized with motion"""
        pin = gcmd.get_int('P', minval=0)
        
        # Queue the output change for next motion command
        self.digital_output_queue.append({'pin': pin, 'value': True})
        
        logging.info(f"CNC M-Codes: M62 P{pin} - Digital out ON (queued)")
        gcmd.respond_info(f"M62: Digital output {pin} ON (synchronized)")
    
    cmd_M63_help = "Digital output OFF, synchronized"
    def cmd_M63(self, gcmd):
        """M63 - Turn off digital output synchronized with motion"""
        pin = gcmd.get_int('P', minval=0)
        
        # Queue the output change for next motion command
        self.digital_output_queue.append({'pin': pin, 'value': False})
        
        logging.info(f"CNC M-Codes: M63 P{pin} - Digital out OFF (queued)")
        gcmd.respond_info(f"M63: Digital output {pin} OFF (synchronized)")
    
    cmd_M64_help = "Digital output ON, immediate"
    def cmd_M64(self, gcmd):
        """M64 - Turn on digital output immediately"""
        pin = gcmd.get_int('P', minval=0)
        
        self.digital_outputs[pin] = True
        
        logging.info(f"CNC M-Codes: M64 P{pin} - Digital out ON (immediate)")
        gcmd.respond_info(f"M64: Digital output {pin} ON (immediate)")
        
        # TODO: Set actual digital output pin via HAL or output_pin
    
    cmd_M65_help = "Digital output OFF, immediate"
    def cmd_M65(self, gcmd):
        """M65 - Turn off digital output immediately"""
        pin = gcmd.get_int('P', minval=0)
        
        self.digital_outputs[pin] = False
        
        logging.info(f"CNC M-Codes: M65 P{pin} - Digital out OFF (immediate)")
        gcmd.respond_info(f"M65: Digital output {pin} OFF (immediate)")
    
    cmd_M66_help = "Wait on input"
    def cmd_M66(self, gcmd):
        """M66 - Wait for input condition"""
        digital_pin = gcmd.get_int('P', None, minval=0)
        analog_pin = gcmd.get_int('E', None, minval=0)
        mode = gcmd.get_int('L', 0, minval=0, maxval=4)
        timeout = gcmd.get_float('Q', 0., minval=0.)
        
        if digital_pin is not None and analog_pin is not None:
            raise gcmd.error("M66: Cannot specify both P and E parameters")
        
        if digital_pin is None and analog_pin is None:
            raise gcmd.error("M66: Must specify either P (digital) or E (analog)")
        
        pin_type = "digital" if digital_pin is not None else "analog"
        pin_num = digital_pin if digital_pin is not None else analog_pin
        
        mode_names = ["IMMEDIATE", "RISE", "FALL", "HIGH", "LOW"]
        mode_name = mode_names[mode] if mode < len(mode_names) else "UNKNOWN"
        
        logging.info(f"CNC M-Codes: M66 - Wait on {pin_type} input {pin_num}, mode {mode_name}")
        gcmd.respond_info(f"M66: Waiting on {pin_type} input {pin_num} (mode {mode_name}, timeout {timeout}s)")
        
        # TODO: Implement actual input monitoring with timeout
        # Requires integration with digital/analog input pins
    
    # ========================================================================
    # ANALOG I/O M-CODES
    # ========================================================================
    
    cmd_M67_help = "Analog output, synchronized"
    def cmd_M67(self, gcmd):
        """M67 - Set analog output synchronized with motion"""
        pin = gcmd.get_int('E', minval=0)
        value = gcmd.get_float('Q')
        
        # Queue the output change for next motion command
        self.analog_output_queue.append({'pin': pin, 'value': value})
        
        logging.info(f"CNC M-Codes: M67 E{pin} Q{value} - Analog out (queued)")
        gcmd.respond_info(f"M67: Analog output {pin} = {value} (synchronized)")
    
    cmd_M68_help = "Analog output, immediate"
    def cmd_M68(self, gcmd):
        """M68 - Set analog output immediately"""
        pin = gcmd.get_int('E', minval=0)
        value = gcmd.get_float('Q')
        
        self.analog_outputs[pin] = value
        
        logging.info(f"CNC M-Codes: M68 E{pin} Q{value} - Analog out (immediate)")
        gcmd.respond_info(f"M68: Analog output {pin} = {value} (immediate)")
        
        # TODO: Set actual analog output via PWM or DAC
    
    # ========================================================================
    # SUBROUTINES (Fanuc-Style M98/M99)
    # ========================================================================
    
    cmd_M98_help = "Call subroutine (Fanuc-Style)"
    def cmd_M98(self, gcmd):
        """M98 - Call subroutine (Fanuc-Style)
        
        Format: M98 P<program_number> [L<repeat_count>]
        - P: Program number to call (O-word number)
        - L: Number of times to repeat (default 1)
        
        Note: Klipper O-code system already supports this functionality.
        M98 is provided for Fanuc-compatibility.
        """
        program = gcmd.get_int('P', minval=0)
        repeats = gcmd.get_int('L', 1, minval=1)
        
        logging.info(f"CNC M-Codes: M98 P{program} L{repeats} - Call subroutine")
        
        # Convert to Klipper O-code call
        for i in range(repeats):
            try:
                gcmd.respond_raw(f"O{program} call")
            except Exception as e:
                raise gcmd.error(f"M98: Subroutine O{program} not found: {e}")
        
        gcmd.respond_info(f"M98: Called subroutine O{program} ({repeats} times)")
    
    cmd_M99_help = "Return from subroutine (Fanuc-Style)"
    def cmd_M99(self, gcmd):
        """M99 - Return from subroutine (Fanuc-Style)
        
        Returns to calling program after M98.
        In Klipper, this is handled automatically by O-code 'endsub'.
        """
        logging.info("CNC M-Codes: M99 - Return from subroutine")
        
        # In Klipper, this is handled by 'endsub' keyword
        # M99 is provided for Fanuc-compatibility
        gcmd.respond_info("M99: Return from subroutine (use 'endsub' in Klipper O-code)")
    
    # ========================================================================
    # MODAL STATE MANAGEMENT M-CODES
    # ========================================================================
    
    def _capture_modal_state(self):
        """Capture current modal state"""
        # This would capture G20/G21, G17/G18/G19, G90/G91, G54-G59, etc.
        # For full implementation, would need access to GCodeMove state
        state = {
            'spindle': self.spindle_state.copy(),
            'coolant_mist': self.coolant_mist,
            'coolant_flood': self.coolant_flood,
            'feed_override': self.feed_override_enabled,
            'spindle_override': self.spindle_override_enabled,
            'adaptive_feed': self.adaptive_feed_enabled,
            'feed_stop': self.feed_stop_enabled,
        }
        return state
    
    def _restore_modal_state(self, state):
        """Restore modal state"""
        self.spindle_state = state['spindle'].copy()
        self.coolant_mist = state['coolant_mist']
        self.coolant_flood = state['coolant_flood']
        self.feed_override_enabled = state['feed_override']
        self.spindle_override_enabled = state['spindle_override']
        self.adaptive_feed_enabled = state['adaptive_feed']
        self.feed_stop_enabled = state['feed_stop']
    
    cmd_M70_help = "Save modal state"
    def cmd_M70(self, gcmd):
        """M70 - Save current modal state"""
        state = self._capture_modal_state()
        self.modal_state_stack.append(state)
        
        logging.info("CNC M-Codes: M70 - Modal state saved")
        gcmd.respond_info("M70: Modal state saved")
    
    cmd_M71_help = "Invalidate saved modal state"
    def cmd_M71(self, gcmd):
        """M71 - Invalidate saved modal state"""
        if self.modal_state_stack:
            self.modal_state_stack.pop()
            logging.info("CNC M-Codes: M71 - Modal state invalidated")
            gcmd.respond_info("M71: Modal state invalidated")
        else:
            logging.warning("CNC M-Codes: M71 - No saved state to invalidate")
            gcmd.respond_info("M71: No saved state to invalidate")
    
    cmd_M72_help = "Restore modal state"
    def cmd_M72(self, gcmd):
        """M72 - Restore saved modal state"""
        if not self.modal_state_stack:
            raise gcmd.error("M72: No saved modal state to restore")
        
        state = self.modal_state_stack.pop()
        self._restore_modal_state(state)
        
        logging.info("CNC M-Codes: M72 - Modal state restored")
        gcmd.respond_info("M72: Modal state restored")
    
    cmd_M73_help = "Save and auto-restore modal state"
    def cmd_M73(self, gcmd):
        """M73 - Save modal state with automatic restore on subroutine return"""
        state = self._capture_modal_state()
        state['auto_restore'] = True
        self.modal_state_stack.append(state)
        
        logging.info("CNC M-Codes: M73 - Modal state saved (auto-restore)")
        gcmd.respond_info("M73: Modal state saved (auto-restore on return)")
        
        # TODO: Integrate with subroutine/O-code system for automatic restore
    
    # ========================================================================
    # USER-DEFINED M-CODES (M100-M199)
    # ========================================================================
    
    def _handle_user_mcode(self, gcmd, mcode_number):
        """Handle user-defined M-Codes M100-M199
        
        LinuxCNC Standard:
        - Executes external program/script named M<number>
        - Script must be in configured path (PROGRAM_PREFIX)
        - Optional P and Q parameters passed as arguments
        - Execution blocks until script completes
        - Non-zero exit code stops G-Code program
        
        Klipper Implementation:
        - Uses shell_command integration if available
        - Falls back to macro/gcode_macro if defined
        - Parameters P and Q are passed as arguments
        """
        p_value = gcmd.get_float('P', None)
        q_value = gcmd.get_float('Q', None)
        
        mcode_name = f"M{mcode_number}"
        
        # Try to find shell_command integration
        try:
            shell_cmd = self.printer.lookup_object(f'shell_command {mcode_name.lower()}')
            # Execute shell command with parameters
            args = []
            if p_value is not None:
                args.append(str(p_value))
            if q_value is not None:
                args.append(str(q_value))
            
            logging.info(f"CNC M-Codes: {mcode_name} - Execute shell command with args {args}")
            # shell_cmd.run_command(args)  # Would need shell_command support
            gcmd.respond_info(f"{mcode_name}: Shell command (configure via [shell_command {mcode_name.lower()}])")
        except:
            # Try gcode_macro as fallback
            try:
                macro = self.printer.lookup_object(f'gcode_macro {mcode_name}')
                logging.info(f"CNC M-Codes: {mcode_name} - Execute macro")
                # Call the macro
                cmd_params = ""
                if p_value is not None:
                    cmd_params += f" P={p_value}"
                if q_value is not None:
                    cmd_params += f" Q={q_value}"
                gcmd.respond_raw(f"{mcode_name}{cmd_params}")
            except:
                # No shell command or macro defined
                logging.info(f"CNC M-Codes: {mcode_name} - Not configured")
                gcmd.respond_info(f"{mcode_name}: Not configured (define [shell_command {mcode_name.lower()}] or [gcode_macro {mcode_name}])")
    
    def get_status(self, eventtime):
        """Return status for queries"""
        return {
            'optional_stop_enabled': self.optional_stop_enabled,
            'spindle_running': self.spindle_state['running'],
            'spindle_direction': self.spindle_state['direction'],
            'spindle_speed': self.spindle_state['speed'],
            'coolant_mist': self.coolant_mist,
            'coolant_flood': self.coolant_flood,
            'feed_override_enabled': self.feed_override_enabled,
            'spindle_override_enabled': self.spindle_override_enabled,
            'adaptive_feed_enabled': self.adaptive_feed_enabled,
            'feed_stop_enabled': self.feed_stop_enabled,
        }

def load_config(config):
    return CNCMCodes(config)
