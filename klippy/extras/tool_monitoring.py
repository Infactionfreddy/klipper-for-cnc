# Tool Monitoring - Kollisions-, Verschleiß- und Brucherkennung
# 
# Copyright (C) 2025 Freddy <infactionfreddy@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import logging
import math
from datetime import datetime

class ToolMonitoring:
    """Überwacht Werkzeugzustand und erkennt Kollisionen, Verschleiß und Bruch"""
    
    def __init__(self, config):
        self.printer = config.get_printer()
        self.name = config.get_name()
        
        # Konfiguration
        self.enable_collision_detection = config.getboolean('enable_collision_detection', True)
        self.enable_wear_monitoring = config.getboolean('enable_wear_monitoring', True)
        self.enable_break_detection = config.getboolean('enable_break_detection', True)
        
        # Kollisionserkennung Parameter
        self.collision_force_threshold = config.getfloat('collision_force_threshold', 50.0)
        self.collision_acceleration_threshold = config.getfloat('collision_acceleration_threshold', 5000.0)
        
        # Verschleißerkennung Parameter
        self.wear_check_interval = config.getfloat('wear_check_interval', 60.0)  # Sekunden
        self.wear_vibration_threshold = config.getfloat('wear_vibration_threshold', 2.0)
        
        # Probe-basierte Verschleißerkennung
        self.enable_probe_wear_detection = config.getboolean('enable_probe_wear_detection', False)
        self.probe_wear_threshold = config.getfloat('probe_wear_threshold', 0.5)  # mm Abweichung
        self.probe_wear_check_frequency = config.getint('probe_wear_check_frequency', 5)  # Alle X Jobs
        
        # Werkzeugbruch Parameter
        self.break_detection_sensitivity = config.getfloat('break_detection_sensitivity', 0.8)
        self.break_spindle_current_threshold = config.getfloat('break_spindle_current_threshold', 0.5)
        
        # Aktionsmodus
        self.action_on_collision = config.get('action_on_collision', 'pause')  # pause, stop, continue
        self.action_on_break = config.get('action_on_break', 'stop')  # pause, stop
        
        # Status
        self.monitoring_active = False
        self.collision_detected = False
        self.break_detected = False
        self.wear_alert = False
        
        # Messwerte
        self.last_position = [0, 0, 0, 0]
        self.last_velocity = [0, 0, 0]
        self.baseline_current = 0
        self.current_spindle_current = 0
        self.vibration_level = 0
        
        # Tool Database Referenz
        self.tool_database = None
        
        # Spindle Control Referenz
        self.spindle = None
        
        # Statistiken
        self.collision_count = 0
        self.false_positives = 0
        self.total_monitoring_time = 0
        
        # Probe-basierte Verschleißmessung
        self.probe = None
        self.probe_measurements = {}  # {tool_id: [measurements]}
        self.job_count = 0
        
        # Register commands
        self.gcode = self.printer.lookup_object('gcode')
        self._register_commands()
        
        # Register event handlers
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        self.printer.register_event_handler("klippy:shutdown", self._handle_shutdown)
        
        # Timer für periodische Überwachung
        self.reactor = self.printer.get_reactor()
        self.check_timer = None
        
        logging.info("Tool Monitoring initialized")
    
    def _register_commands(self):
        """Registriere G-Code Befehle"""
        self.gcode.register_command('START_TOOL_MONITORING',
                                   self.cmd_START_MONITORING,
                                   desc=self.cmd_START_MONITORING_help)
        self.gcode.register_command('STOP_TOOL_MONITORING',
                                   self.cmd_STOP_MONITORING,
                                   desc=self.cmd_STOP_MONITORING_help)
        self.gcode.register_command('TOOL_MONITORING_STATUS',
                                   self.cmd_MONITORING_STATUS,
                                   desc=self.cmd_MONITORING_STATUS_help)
        self.gcode.register_command('RESET_COLLISION_DETECTION',
                                   self.cmd_RESET_COLLISION,
                                   desc=self.cmd_RESET_COLLISION_help)
        self.gcode.register_command('CALIBRATE_TOOL_BASELINE',
                                   self.cmd_CALIBRATE_BASELINE,
                                   desc=self.cmd_CALIBRATE_BASELINE_help)
        self.gcode.register_command('SET_MONITORING_PARAMS',
                                   self.cmd_SET_PARAMS,
                                   desc=self.cmd_SET_PARAMS_help)
        self.gcode.register_command('MEASURE_TOOL_LENGTH',
                                   self.cmd_MEASURE_TOOL_LENGTH,
                                   desc=self.cmd_MEASURE_TOOL_LENGTH_help)
        self.gcode.register_command('CHECK_TOOL_WEAR_PROBE',
                                   self.cmd_CHECK_TOOL_WEAR_PROBE,
                                   desc=self.cmd_CHECK_TOOL_WEAR_PROBE_help)
    
    def _handle_ready(self):
        """Handle Klipper ready event"""
        # Lookup andere Module
        try:
            self.tool_database = self.printer.lookup_object('tool_database')
        except:
            logging.warning("Tool Database not found")
        
        try:
            self.spindle = self.printer.lookup_object('spindle_control')
        except:
            logging.warning("Spindle Control not found")
        
        try:
            self.probe = self.printer.lookup_object('tool_length_probe')
            logging.info("Tool Length Probe found - wear detection via length measurement enabled")
        except:
            self.probe = None
            logging.warning("Tool Length Probe not found - probe-based wear detection disabled")
        
        self.gcode.respond_info("Tool Monitoring ready")
    
    def _handle_shutdown(self):
        """Handle shutdown"""
        self.stop_monitoring()
    
    def start_monitoring(self):
        """Starte Werkzeugüberwachung"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self.collision_detected = False
        self.break_detected = False
        
        # Starte Timer für periodische Checks
        if self.check_timer is None:
            self.check_timer = self.reactor.register_timer(
                self._periodic_check, 
                self.reactor.NOW
            )
        
        logging.info("Tool monitoring started")
    
    def stop_monitoring(self):
        """Stoppe Werkzeugüberwachung"""
        if not self.monitoring_active:
            return
        
        self.monitoring_active = False
        
        # Stoppe Timer
        if self.check_timer is not None:
            self.reactor.unregister_timer(self.check_timer)
            self.check_timer = None
        
        logging.info("Tool monitoring stopped")
    
    def _periodic_check(self, eventtime):
        """Periodische Überwachungschecks"""
        if not self.monitoring_active:
            return self.reactor.NEVER
        
        try:
            # Hole Toolhead
            toolhead = self.printer.lookup_object('toolhead')
            current_pos = toolhead.get_position()
            
            # Kollisionserkennung
            if self.enable_collision_detection:
                self._check_collision(current_pos)
            
            # Werkzeugbrucherkennung
            if self.enable_break_detection:
                self._check_tool_break()
            
            # Verschleißüberwachung
            if self.enable_wear_monitoring:
                self._check_tool_wear()
            
            # Update letzte Position
            self.last_position = current_pos[:]
            
        except Exception as e:
            logging.error(f"Tool monitoring error: {e}")
        
        return eventtime + self.wear_check_interval
    
    def _check_collision(self, current_pos):
        """Prüfe auf Kollision basierend auf unerwarteten Bewegungsänderungen"""
        if self.collision_detected:
            return
        
        # Berechne Geschwindigkeitsänderung
        velocity = [
            current_pos[i] - self.last_position[i]
            for i in range(3)
        ]
        
        # Berechne Beschleunigung (Änderung der Geschwindigkeit)
        acceleration = [
            abs(velocity[i] - self.last_velocity[i])
            for i in range(3)
        ]
        
        max_accel = max(acceleration)
        
        # Prüfe ob Beschleunigung Schwellwert überschreitet
        if max_accel > self.collision_acceleration_threshold:
            self._handle_collision_detected(max_accel)
        
        self.last_velocity = velocity[:]
    
    def _check_tool_break(self):
        """Prüfe auf Werkzeugbruch"""
        if self.break_detected:
            return
        
        if not self.spindle:
            return
        
        # Hole aktuelle Spindel-Stromaufnahme
        spindle_status = self.spindle.get_status(self.reactor.monotonic())
        
        # Wenn Spindel läuft, prüfe Stromaufnahme
        if spindle_status.get('speed', 0) > 0:
            # Simulierte Stromaufnahme (in realer Anwendung von Sensor)
            self.current_spindle_current = spindle_status.get('current', self.baseline_current)
            
            # Prüfe auf plötzlichen Stromabfall (Indikator für Werkzeugbruch)
            if self.baseline_current > 0:
                current_ratio = self.current_spindle_current / self.baseline_current
                
                if current_ratio < self.break_spindle_current_threshold:
                    self._handle_break_detected(current_ratio)
    
    def _check_tool_wear(self):
        """Prüfe Werkzeugverschleiß"""
        if not self.tool_database:
            return
        
        current_tool = self.tool_database.get_current_tool()
        
        if not current_tool:
            return
        
        # Prüfe Verschleißlevel aus Nutzungsstatistiken
        if current_tool.needs_warning() and not self.wear_alert:
            self.wear_alert = True
            self.gcode.respond_info(
                f"WARNING: Tool {current_tool.tool_id} '{current_tool.name}' "
                f"wear level at {current_tool.wear_level:.1f}%"
            )
        
        if current_tool.needs_replacement():
            self.gcode.respond_info(
                f"CRITICAL: Tool {current_tool.tool_id} '{current_tool.name}' "
                f"needs replacement!"
            )
        
        # Probe-basierte Verschleißprüfung (wenn aktiviert)
        if self.enable_probe_wear_detection and self.probe:
            self._check_probe_wear(current_tool)
    
    def _handle_collision_detected(self, acceleration):
        """Handle erkannte Kollision"""
        self.collision_detected = True
        self.collision_count += 1
        
        logging.warning(f"Collision detected! Acceleration: {acceleration:.1f}")
        
        self.gcode.respond_info(
            f"!!! COLLISION DETECTED !!!\n"
            f"Acceleration spike: {acceleration:.1f} mm/s²"
        )
        
        # Führe Aktion aus
        if self.action_on_collision == 'pause':
            self.gcode.run_script_from_command("PAUSE")
        elif self.action_on_collision == 'stop':
            self.gcode.run_script_from_command("M112")  # Emergency stop
    
    def _handle_break_detected(self, current_ratio):
        """Handle erkannten Werkzeugbruch"""
        self.break_detected = True
        
        logging.error(f"Tool break detected! Current ratio: {current_ratio:.2f}")
        
        self.gcode.respond_info(
            f"!!! TOOL BREAK DETECTED !!!\n"
            f"Spindle current dropped to {current_ratio*100:.1f}% of baseline"
        )
        
        # Markiere Tool als inaktiv
        if self.tool_database:
            current_tool = self.tool_database.get_current_tool()
            if current_tool:
                self.tool_database.update_tool(current_tool.tool_id, is_active=False)
        
        # Führe Aktion aus
        if self.action_on_break == 'pause':
            self.gcode.run_script_from_command("PAUSE")
        elif self.action_on_break == 'stop':
            self.gcode.run_script_from_command("M112")  # Emergency stop
    
    def calibrate_baseline(self):
        """Kalibriere Baseline-Werte für Vergleich"""
        if not self.spindle:
            return
        
        spindle_status = self.spindle.get_status(self.reactor.monotonic())
        self.baseline_current = spindle_status.get('current', 1.0)
        
        logging.info(f"Baseline calibrated: current={self.baseline_current}")
    
    def reset_collision_detection(self):
        """Reset Kollisionserkennung"""
        self.collision_detected = False
        self.break_detected = False
        self.wear_alert = False
    
    def _check_probe_wear(self, tool):
        """Prüfe Verschleiß durch Probe-Längenmessung"""
        # Prüfe nur alle X Jobs
        if self.job_count % self.probe_wear_check_frequency != 0:
            return
        
        tool_id = tool.tool_id
        
        # Hole Messhistorie
        if tool_id not in self.probe_measurements:
            self.probe_measurements[tool_id] = []
        
        measurements = self.probe_measurements[tool_id]
        
        # Wenn wir Messungen haben, vergleiche mit Original
        if len(measurements) > 0:
            original_length = measurements[0]  # Erste Messung = Original
            
            if len(measurements) > 1:
                latest_length = measurements[-1]
                wear_amount = original_length - latest_length
                
                # Warnung bei signifikantem Verschleiß
                if wear_amount > self.probe_wear_threshold:
                    self.gcode.respond_info(
                        f"PROBE WEAR DETECTED: Tool {tool_id} has worn {wear_amount:.3f}mm!\n"
                        f"Original: {original_length:.3f}mm, Current: {latest_length:.3f}mm"
                    )
                    
                    # Update Verschleißlevel basierend auf physischer Messung
                    # Annahme: 2mm Verschleiß = 100% (konfigurierbar)
                    max_wear = 2.0  # mm
                    wear_percent = min(100, (wear_amount / max_wear) * 100)
                    
                    # Setze höheren Wert (Statistik oder Messung)
                    tool.wear_level = max(tool.wear_level, wear_percent)
                    self.tool_database._save_database()
    
    def measure_tool_length(self, tool=None, store=True):
        """Messe aktuelle Werkzeuglänge mit Tool Length Probe"""
        if not self.probe:
            raise self.gcode.error("No tool length probe configured")
        
        if tool is None:
            if not self.tool_database:
                raise self.gcode.error("No tool database")
            tool = self.tool_database.get_current_tool()
            if not tool:
                raise self.gcode.error("No tool selected")
        
        # Führe Probe-Messung durch mit dediziertem Tool Length Probe
        try:
            # Verwende probe_tool_length() Methode des tool_length_probe Moduls
            measured_z = self.probe.probe_tool_length()
        except Exception as e:
            # Fallback: versuche über get_status wenn Standard-Probe verwendet wird
            probe_state = self.probe.get_status(self.reactor.monotonic())
            measured_z = probe_state.get('last_z_result', 0)
            if measured_z == 0:
                raise self.gcode.error(f"Tool length measurement failed: {e}")
        
        if store:
            # Speichere Messung
            if tool.tool_id not in self.probe_measurements:
                self.probe_measurements[tool.tool_id] = []
            
            self.probe_measurements[tool.tool_id].append(measured_z)
            
            logging.info(f"Tool {tool.tool_id} length measured: {measured_z:.3f}mm")
        
        return measured_z
    
    def update_tool_usage(self, runtime=0, distance=0):
        """Update Tool-Nutzungsstatistiken"""
        if not self.tool_database:
            return
        
        current_tool = self.tool_database.get_current_tool()
        if current_tool:
            current_tool.update_usage(runtime=runtime, distance=distance)
            
            # Inkrementiere Spindel-Zyklus wenn Spindel aktiv
            if self.spindle:
                spindle_status = self.spindle.get_status(self.reactor.monotonic())
                if spindle_status.get('speed', 0) > 0:
                    current_tool.spindle_on_count += 1
            
            # Speichere Änderungen
            self.tool_database._save_database()
    
    # G-Code Commands
    
    cmd_START_MONITORING_help = "Start tool monitoring"
    def cmd_START_MONITORING(self, gcmd):
        """START_TOOL_MONITORING"""
        self.start_monitoring()
        gcmd.respond_info("Tool monitoring started")
        
        if self.enable_collision_detection:
            gcmd.respond_info("- Collision detection: ENABLED")
        if self.enable_break_detection:
            gcmd.respond_info("- Break detection: ENABLED")
        if self.enable_wear_monitoring:
            gcmd.respond_info("- Wear monitoring: ENABLED")
    
    cmd_STOP_MONITORING_help = "Stop tool monitoring"
    def cmd_STOP_MONITORING(self, gcmd):
        """STOP_TOOL_MONITORING"""
        self.stop_monitoring()
        gcmd.respond_info("Tool monitoring stopped")
    
    cmd_MONITORING_STATUS_help = "Show tool monitoring status"
    def cmd_MONITORING_STATUS(self, gcmd):
        """TOOL_MONITORING_STATUS"""
        gcmd.respond_info("=== Tool Monitoring Status ===")
        gcmd.respond_info(f"Active: {'YES' if self.monitoring_active else 'NO'}")
        gcmd.respond_info(f"Collision Detection: {'ENABLED' if self.enable_collision_detection else 'DISABLED'}")
        gcmd.respond_info(f"Break Detection: {'ENABLED' if self.enable_break_detection else 'DISABLED'}")
        gcmd.respond_info(f"Wear Monitoring: {'ENABLED' if self.enable_wear_monitoring else 'DISABLED'}")
        gcmd.respond_info(f"---")
        gcmd.respond_info(f"Collision Detected: {'YES' if self.collision_detected else 'NO'}")
        gcmd.respond_info(f"Break Detected: {'YES' if self.break_detected else 'NO'}")
        gcmd.respond_info(f"Wear Alert: {'YES' if self.wear_alert else 'NO'}")
        gcmd.respond_info(f"Total Collisions: {self.collision_count}")
        gcmd.respond_info(f"Baseline Current: {self.baseline_current:.2f}A")
        gcmd.respond_info(f"Current Current: {self.current_spindle_current:.2f}A")
    
    cmd_RESET_COLLISION_help = "Reset collision detection flags"
    def cmd_RESET_COLLISION(self, gcmd):
        """RESET_COLLISION_DETECTION"""
        self.reset_collision_detection()
        gcmd.respond_info("Collision detection reset")
    
    cmd_CALIBRATE_BASELINE_help = "Calibrate baseline values"
    def cmd_CALIBRATE_BASELINE(self, gcmd):
        """CALIBRATE_TOOL_BASELINE"""
        self.calibrate_baseline()
        gcmd.respond_info(f"Baseline calibrated: {self.baseline_current:.2f}A")
    
    cmd_SET_PARAMS_help = "Set monitoring parameters"
    def cmd_SET_PARAMS(self, gcmd):
        """SET_MONITORING_PARAMS [COLLISION_THRESHOLD=<val>] [BREAK_THRESHOLD=<val>]"""
        
        if gcmd.get_float('COLLISION_THRESHOLD', None) is not None:
            self.collision_acceleration_threshold = gcmd.get_float('COLLISION_THRESHOLD')
            gcmd.respond_info(f"Collision threshold set to {self.collision_acceleration_threshold}")
        
        if gcmd.get_float('BREAK_THRESHOLD', None) is not None:
            self.break_spindle_current_threshold = gcmd.get_float('BREAK_THRESHOLD')
            gcmd.respond_info(f"Break threshold set to {self.break_spindle_current_threshold}")
        
        if gcmd.get_float('WEAR_CHECK_INTERVAL', None) is not None:
            self.wear_check_interval = gcmd.get_float('WEAR_CHECK_INTERVAL')
            gcmd.respond_info(f"Wear check interval set to {self.wear_check_interval}s")
    
    cmd_MEASURE_TOOL_LENGTH_help = "Measure current tool length with tool length probe"
    def cmd_MEASURE_TOOL_LENGTH(self, gcmd):
        """MEASURE_TOOL_LENGTH [TOOL_ID=<id>]"""
        tool_id = gcmd.get_int('TOOL_ID', None)
        
        if tool_id is not None:
            tool = self.tool_database.get_tool(tool_id)
            if not tool:
                raise gcmd.error(f"Tool {tool_id} not found")
        else:
            tool = None
        
        gcmd.respond_info("Starting tool length measurement...")
        
        # Messe und speichere (probe_tool_length() kümmert sich um Bewegung)
        length = self.measure_tool_length(tool, store=True)
        
        if tool:
            tool_id = tool.tool_id
            measurements = self.probe_measurements.get(tool_id, [])
            count = len(measurements)
            
            gcmd.respond_info(
                f"Tool {tool_id} length: {length:.3f}mm\n"
                f"Measurement #{count}"
            )
            
            if count > 1:
                original = measurements[0]
                wear = original - length
                gcmd.respond_info(
                    f"Original length: {original:.3f}mm\n"
                    f"Wear detected: {wear:.3f}mm ({(wear/original)*100:.1f}%)"
                )
        else:
            gcmd.respond_info(f"Length measured: {length:.3f}mm")
        
        # Fahre zurück nach oben
        self.gcode.run_script_from_command("G91\nG0 Z5\nG90")
    
    cmd_CHECK_TOOL_WEAR_PROBE_help = "Check tool wear via probe measurement"
    def cmd_CHECK_TOOL_WEAR_PROBE(self, gcmd):
        """CHECK_TOOL_WEAR_PROBE [TOOL_ID=<id>]"""
        tool_id = gcmd.get_int('TOOL_ID', None)
        
        if tool_id:
            if tool_id not in self.probe_measurements:
                gcmd.respond_info(f"No measurements for tool {tool_id}")
                return
            
            measurements = self.probe_measurements[tool_id]
        else:
            # Zeige alle Tools
            gcmd.respond_info("=== Tool Wear (Probe Measurements) ===")
            for tid, measurements in self.probe_measurements.items():
                if len(measurements) < 2:
                    continue
                
                original = measurements[0]
                latest = measurements[-1]
                wear = original - latest
                wear_percent = (wear / original) * 100 if original > 0 else 0
                
                gcmd.respond_info(
                    f"T{tid}: {wear:.3f}mm wear ({wear_percent:.1f}%) - "
                    f"{original:.3f}mm → {latest:.3f}mm ({len(measurements)} measurements)"
                )
            return
        
        # Einzelnes Tool
        if len(measurements) < 2:
            gcmd.respond_info(f"Tool {tool_id}: Only {len(measurements)} measurement(s), need at least 2")
            return
        
        original = measurements[0]
        latest = measurements[-1]
        wear = original - latest
        wear_percent = (wear / original) * 100 if original > 0 else 0
        
        gcmd.respond_info(f"=== Tool {tool_id} Wear Analysis ===")
        gcmd.respond_info(f"Original length: {original:.3f}mm")
        gcmd.respond_info(f"Current length: {latest:.3f}mm")
        gcmd.respond_info(f"Wear amount: {wear:.3f}mm ({wear_percent:.1f}%)")
        gcmd.respond_info(f"Total measurements: {len(measurements)}")
        
        # Zeige Trend
        if len(measurements) > 2:
            gcmd.respond_info("\nMeasurement history:")
            for i, m in enumerate(measurements):
                wear_from_orig = original - m
                gcmd.respond_info(f"  #{i+1}: {m:.3f}mm (-{wear_from_orig:.3f}mm)")
        
        # Warnung
        if wear > self.probe_wear_threshold:
            gcmd.respond_info(f"\n⚠️  WARNING: Wear exceeds threshold ({self.probe_wear_threshold}mm)!")
    
    def get_status(self, eventtime):
        """Status für Moonraker API"""
        return {
            'monitoring_active': self.monitoring_active,
            'collision_detected': self.collision_detected,
            'break_detected': self.break_detected,
            'wear_alert': self.wear_alert,
            'collision_count': self.collision_count,
            'baseline_current': self.baseline_current,
            'current_current': self.current_spindle_current,
            'vibration_level': self.vibration_level,
            'collision_detection_enabled': self.enable_collision_detection,
            'break_detection_enabled': self.enable_break_detection,
            'wear_monitoring_enabled': self.enable_wear_monitoring
        }


def load_config(config):
    return ToolMonitoring(config)
