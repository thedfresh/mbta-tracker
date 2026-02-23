# MBTA Transit Display

Always-on LED matrix display for MBTA Route 109 arrival times.

## Structure
- `src/data/` — MBTA and traffic API clients
- `src/logic/` — reliability scoring and travel-time estimation
- `src/rendering/` — scene composition and scroll engine
- `src/display/` — display driver interface (emulator + hardware)
- `config/` — configuration
- `scripts/` — legacy data collection scripts

## Route Topology
- Direction 1 = inbound toward Harvard (commuter direction)
- Direction 0 = outbound toward Linden Square
- Boarding stop: 5483 (Broadway @ Shute St, direction 1, stop_sequence 10)
- Terminal stop: 7412 (Linden Sq, direction 1, stop_sequence 1)
- Inbound run: 44 stops, ~66 min avg duration
- Outbound run: 41 stops, ~54 min avg duration
- Key feasibility signal: vehicle presence at stop 7412 before scheduled departure

## Data Collection
- `scripts/collect.py` polls every 30s
- Logs to `logs/route109_inbound.jsonl` and `logs/schedule_snapshots.jsonl`
- Deployed as systemd service on Raspberry Pi (`deploy/route109-collector.service`)
- Venv location on Pi: `~/mbta-tracker/venv` (not `.venv`)

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
