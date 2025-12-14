# Tool Length Probe - Separater Probe für Werkzeuglängenmessung
# Unabhängig vom Werkstück-Probe (G38.2)
#
# Copyright (C) 2025 Freddy <infactionfreddy@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import logging
import pins

class ToolLengthProbe:
    """Dedizierter Tool-Length-Probe für automatische Werkzeuglängenmessung"""
    
    def __init__(self, config):
        self.printer = config.get_printer()
        self.name = config.get_name()
        
        # Probe-Pin Konfiguration (SEPARATER PIN vom G38.2 Probe!)
        self.mcu_probe = pins.setup_pin(self.printer, 'endstop', config.get('pin'))
        
        # Position des Tool-Length-Probe auf dem Tisch
        self.probe_x = config.getfloat('x')
        self.probe_y = config.getfloat('y')
        self.probe_z = config.getfloat('z')  # Z-Höhe der Probe-Oberfläche
        
        # Probe-Geschwindigkeit
        self.speed = config.getfloat('speed', 5.0)
        self.lift_speed = config.getfloat('lift_speed', 10.0)
        
        # Sampling-Parameter
        self.samples = config.getint('samples', 3)
        self.sample_retract_dist = config.getfloat('sample_retract_dist', 2.0)
        self.samples_result = config.getchoice('samples_result',
                                               {'median': 'median', 
                                                'average': 'average'},
                                               'average')
        self.samples_tolerance = config.getfloat('samples_tolerance', 0.01)
        self.samples_tolerance_retries = config.getint('samples_tolerance_retries', 3)
        
        # Maximum probe distance
        self.max_probe_distance = config.getfloat('max_probe_distance', 50.0)
        
        # Messergebnisse
        self.last_z_result = None
        self.last_measurements = []
        
        # Register commands
        self.gcode = self.printer.lookup_object('gcode')
        self._register_commands()
        
        # Register event handler
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        
        logging.info(f"Tool Length Probe initialized at X{self.probe_x} Y{self.probe_y} Z{self.probe_z}")
    
    def _register_commands(self):
        """Registriere G-Code Befehle"""
        self.gcode.register_command('PROBE_TOOL_LENGTH',
                                   self.cmd_PROBE_TOOL_LENGTH,
                                   desc=self.cmd_PROBE_TOOL_LENGTH_help)
        self.gcode.register_command('QUERY_TOOL_PROBE',
                                   self.cmd_QUERY_TOOL_PROBE,
                                   desc=self.cmd_QUERY_TOOL_PROBE_help)
    
    def _handle_ready(self):
        """Handle Klipper ready event"""
        self.gcode.respond_info(f"Tool Length Probe ready at X{self.probe_x} Y{self.probe_y}")
    
    def _probe_z(self, z_pos, speed):
        """Führe Z-Probe durch"""
        toolhead = self.printer.lookup_object('toolhead')
        
        # Probe-Sequenz
        phoming = self.printer.lookup_object('homing')
        pos = toolhead.get_position()
        
        # Setze Zielposition
        pos[2] = z_pos
        
        try:
            # Führe Probe durch
            epos = phoming.probing_move(self.mcu_probe, pos, speed)
            return epos[2]
        except self.printer.command_error as e:
            raise self.gcode.error(str(e))
    
    def _sample_z(self):
        """Führe mehrere Messungen durch und berechne Ergebnis"""
        toolhead = self.printer.lookup_object('toolhead')
        current_pos = toolhead.get_position()
        
        measurements = []
        
        for i in range(self.samples):
            if i > 0:
                # Fahre zwischen Messungen hoch
                current_pos[2] += self.sample_retract_dist
                toolhead.move(current_pos, self.lift_speed)
                toolhead.wait_moves()
            
            # Probe nach unten
            start_z = current_pos[2]
            target_z = self.probe_z - self.max_probe_distance
            
            measured_z = self._probe_z(target_z, self.speed)
            measurements.append(measured_z)
            
            # Update Position
            current_pos[2] = measured_z
        
        # Berechne Ergebnis
        if self.samples_result == 'median':
            result = sorted(measurements)[len(measurements) // 2]
        else:  # average
            result = sum(measurements) / len(measurements)
        
        # Prüfe Toleranz
        if self.samples > 1:
            max_diff = max(measurements) - min(measurements)
            if max_diff > self.samples_tolerance:
                raise self.gcode.error(
                    f"Probe samples exceed tolerance: {max_diff:.3f}mm > {self.samples_tolerance}mm"
                )
        
        self.last_measurements = measurements
        return result
    
    def probe_tool_length(self):
        """Messe Werkzeuglänge"""
        toolhead = self.printer.lookup_object('toolhead')
        
        # Sichere aktuelle Position
        self.gcode.run_script_from_command("SAVE_GCODE_STATE NAME=tool_probe_state")
        
        try:
            # Fahre zu Probe-Position (XY)
            self.gcode.run_script_from_command(
                f"G90\n"  # Absolute positioning
                f"G0 Z{self.probe_z + 10} F{self.lift_speed * 60}\n"  # Sicher hoch
                f"G0 X{self.probe_x} Y{self.probe_y}\n"  # Fahre zu Probe
            )
            
            toolhead.wait_moves()
            
            # Führe Messung durch
            measured_z = self._sample_z()
            
            self.last_z_result = measured_z
            
            # Fahre wieder hoch
            self.gcode.run_script_from_command(
                f"G91\n"  # Relative
                f"G0 Z{self.sample_retract_dist + 5} F{self.lift_speed * 60}\n"
                f"G90\n"  # Absolute
            )
            
            return measured_z
            
        finally:
            # Restore state
            self.gcode.run_script_from_command("RESTORE_GCODE_STATE NAME=tool_probe_state")
    
    # G-Code Commands
    
    cmd_PROBE_TOOL_LENGTH_help = "Measure tool length with tool probe"
    def cmd_PROBE_TOOL_LENGTH(self, gcmd):
        """PROBE_TOOL_LENGTH [SAMPLES=<n>]"""
        
        # Optional: Override samples
        samples = gcmd.get_int('SAMPLES', self.samples)
        old_samples = self.samples
        self.samples = samples
        
        try:
            gcmd.respond_info("Starting tool length measurement...")
            
            measured_z = self.probe_tool_length()
            
            gcmd.respond_info(f"Tool length measurement complete")
            gcmd.respond_info(f"Measured Z: {measured_z:.3f}mm")
            
            if len(self.last_measurements) > 1:
                gcmd.respond_info(f"Samples: {self.last_measurements}")
                avg = sum(self.last_measurements) / len(self.last_measurements)
                max_diff = max(self.last_measurements) - min(self.last_measurements)
                gcmd.respond_info(f"Average: {avg:.3f}mm, Range: {max_diff:.3f}mm")
            
        finally:
            self.samples = old_samples
    
    cmd_QUERY_TOOL_PROBE_help = "Query tool probe status"
    def cmd_QUERY_TOOL_PROBE(self, gcmd):
        """QUERY_TOOL_PROBE"""
        
        # Query probe pin status
        toolhead = self.printer.lookup_object('toolhead')
        print_time = toolhead.get_last_move_time()
        
        try:
            triggered = self.mcu_probe.query_endstop(print_time)
            status = "TRIGGERED" if triggered else "open"
        except:
            status = "unknown"
        
        gcmd.respond_info(f"Tool Probe: {status}")
        
        if self.last_z_result is not None:
            gcmd.respond_info(f"Last measurement: {self.last_z_result:.3f}mm")
        
        gcmd.respond_info(f"Probe location: X{self.probe_x} Y{self.probe_y} Z{self.probe_z}")
    
    def get_status(self, eventtime):
        """Status für Moonraker API"""
        return {
            'last_z_result': self.last_z_result,
            'last_measurements': self.last_measurements,
            'probe_x': self.probe_x,
            'probe_y': self.probe_y,
            'probe_z': self.probe_z,
            'samples': self.samples
        }


def load_config(config):
    return ToolLengthProbe(config)
