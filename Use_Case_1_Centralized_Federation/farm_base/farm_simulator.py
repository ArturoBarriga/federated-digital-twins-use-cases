
# Abstract base class that every farm simulator inherits from
# Evolve one field's soil moisture and weather forward in time, one step per loop itreration
# Subclasses only implement push_telemetry() and check_actuator_commands().

import os
import random
import time
from datetime import datetime, timezone
from abc import ABC, abstractmethod

class FarmSimulator(ABC):
    def __init__(self, farm_id: str, area_ha: float, crop_type: str):
        self.farm_id = farm_id
        self.area_ha = area_ha
        self.crop_type = crop_type
        self._soil_humidity = random.uniform(20, 55)
        self._rainfall_mm = 0.0
        hour = datetime.now(timezone.utc).hour
        if 6 <= hour <= 18:
            self._temperature_c = random.uniform(22, 30)
        else:
            self._temperature_c = random.uniform(12, 20)
        self._humidity_pct = random.uniform(40, 60)
        self._wind_speed = random.uniform(5, 20)
        self._wind_direction = random.uniform(0, 360)
        self._running = True
        self._irrigating = False

    # Advance one timestep of farm state
    def step(self):
        hour = datetime.now(timezone.utc).hour

        # Evaporation, higher during the day
        if 6 <= hour <= 20:
            self._soil_humidity -= random.uniform(0.03, 0.08)
        else:
            self._soil_humidity -= random.uniform(0.005, 0.015)

        # Rainfall, each mm raises soil moisture by 1 % point
        if random.random() < 0.001:
            self._rainfall_mm = random.uniform(5, 25)
            self._soil_humidity += self._rainfall_mm
        else:
            self._rainfall_mm = 0.0

        # Irrigation, add 2-5 %/step while valve is open
        if self._irrigating:
            irrigation_change = random.uniform(1.0, 2.5)
            self._soil_humidity += irrigation_change
            if self._soil_humidity > 65:
                self._irrigating = False
        if self._soil_humidity < 5:
            self._soil_humidity = 5
        elif self._soil_humidity > 100:
            self._soil_humidity = 100

        # 4. Temperature, higher during the day
        if 6 <= hour <= 18:
            temperature_change = random.uniform(-0.5, 0.3)
            self._temperature_c += temperature_change

            if self._temperature_c < 15:
                self._temperature_c = 15
            elif self._temperature_c > 40:
                self._temperature_c = 40
        else:
            temperature_change = random.uniform(-0.3, 0.5)
            self._temperature_c += temperature_change

            if self._temperature_c < 5:
                self._temperature_c = 5
            elif self._temperature_c > 30:
                self._temperature_c = 30

        # 5. Humidity, inverse to temperatrure
        humidity_change = random.uniform(-2, 2)
        temperature_effect = (self._temperature_c - 20) * 0.1
        self._humidity_pct += humidity_change
        self._humidity_pct -= temperature_effect
        if self._humidity_pct < 10:
            self._humidity_pct = 10
        elif self._humidity_pct > 100:
            self._humidity_pct = 100

        # Wind speed, random walk
        wind_change = random.uniform(-2, 2)
        self._wind_speed += wind_change
        if self._wind_speed < 0:
            self._wind_speed = 0
        elif self._wind_speed > 60:
            self._wind_speed = 60

        # Wind direction, random walk
        wind_direction_change = random.uniform(-15, 15)
        self._wind_direction += wind_direction_change
        if self._wind_direction < 0:
            self._wind_direction += 360
        elif self._wind_direction >= 360:
            self._wind_direction -= 360

    def get_telemetry(self) -> dict:
        return {
            "farm_id": self.farm_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "soil_humidity_40cm_pct": round(self._soil_humidity, 1),
            "weather": {
                "temperature_c": round(self._temperature_c, 1),
                "humidity_pct": round(self._humidity_pct, 1),
                "rainfall_mm": round(self._rainfall_mm, 1),
                "wind_direction": round(self._wind_direction, 1),
                "wind_speed": round(self._wind_speed, 1),
            },
            "area_ha": self.area_ha,
            "crop_type": self.crop_type,
        }

    def start_irrigation(self, hours: float):
        self._irrigating = True

    def stop_irrigation(self):
        self._irrigating = False

    # Abstract methods, specific of each digital twin technology
    @abstractmethod
    def push_telemetry(self, telemetry: dict):
        pass  
        
    @abstractmethod
    def check_actuator_commands(self) -> list:
        pass  

    def run_loop(self, interval_seconds: float = 60.0):
        while self._running:
            self.step()
            self.push_telemetry(self.get_telemetry())
            for cmd in self.check_actuator_commands():
                if cmd["command"] == "irrigate":
                    print(f"[{self.farm_id}] Irrigation: {cmd['quota_m3']}m3 over {cmd['valve_open_hours']}h")
                    self.start_irrigation(cmd["valve_open_hours"])
                elif cmd["command"] == "stop":
                    self.stop_irrigation()
            time.sleep(interval_seconds)

    def stop(self):
        self._running = False
