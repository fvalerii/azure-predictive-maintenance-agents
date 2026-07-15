# TireForge Production Line A — Operations & Maintenance Manual (Rev. 2)

## Machine Overview

| ID | Machine | Function | Critical Sensor |
|---|---|---|---|
| MX-001 | Mixer | Blends raw rubber compounds with carbon black and chemicals | Vibration, Temperature |
| EX-002 | Extruder | Shapes rubber into tire tread profiles | Pressure, Temperature |
| CP-003 | Curing Press | Vulcanizes tires under heat and pressure | Temperature, Pressure |
| CU-004 | Cooling Unit | Gradually cools cured tires to prevent thermal shock | Temperature |
| IS-005 | Inspection Station | Quality assurance via vibration and dimensional analysis | Vibration, RPM |

## Maintenance Procedures

- **Sensor Calibration (all machines):** If a vibration sensor reads more than 15% above its rated max, recalibrate the mount before assuming a mechanical fault — sensor drift is a common false positive.
- **Coolant Refill (CU-004):** Check coolant level and pump seal integrity every 500 operating hours.
- **Thermal Gasket Inspection (CP-003):** Inspect the press seal gasket every 90 days; replace at the first sign of visible cracking, since a failing gasket causes both pressure loss and heat leakage.
- **Bearing Lubrication (MX-001, EX-002):** Lubricate drive-motor bearings every 250 operating hours; unlubricated bearings are the leading cause of elevated vibration readings.
- **Critical Faults (any machine):** If temperature exceeds the machine's rated maximum by more than 10%, trigger an immediate E-Stop and do not resume operation until the root cause is cleared.

## Troubleshooting Guide

| Symptom | Likely Cause | Recommended Action | Part Number |
|---|---|---|---|
| Elevated vibration, normal temperature | Worn or unlubricated motor bearing | Inspect and replace bearing | TF-101 |
| High temperature + high pressure together | Degraded thermal seal or stuck pressure relief valve | Inspect gasket and relief valve; replace as needed | TF-202 / TF-404 |
| Pressure spikes with rated RPM = 0 | Relief valve failing to vent under load | Replace pressure relief valve; do not operate until replaced | TF-404 |
| Elevated vibration at rated RPM (inspection line) | Worn vibration damper mount | Replace damper mount | TF-505 |
| Cooling unit temperature drifting above range | Cooling pump underperforming or seal leak | Inspect pump; replace if flow rate is below spec | TF-303 |
| Repeated heat-related shutdowns on curing press | Heating element coil degradation | Test coil resistance; replace if out of spec | TF-606 |

## Spare Parts Reference

| Part # | Name | Used On |
|---|---|---|
| TF-101 | Motor Bearing | MX-001, EX-002 |
| TF-202 | Thermal Gasket | CP-003 |
| TF-303 | Cooling Pump | CU-004 |
| TF-404 | Pressure Relief Valve | CP-003 |
| TF-505 | Vibration Damper Mount | IS-005, MX-001 |
| TF-606 | Heating Element Coil | CP-003 |

Always confirm current stock via the inventory system before committing to a repair window — a documented fix with no part in stock still means downtime.
