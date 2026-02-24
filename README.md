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

## Display Output
- Chain size is taken from `config/config.yaml` (`display.width` / 64).
- Test panel wiring/colors on hardware:
```bash
python scripts/panel_test.py --width 192 --height 64
```
- Run live app output:
```bash
python scripts/live_preview.py --output both
```
- Output modes:
  - `--output emulator` writes `emulator_output/frame.png`
  - `--output hardware` writes only to the LED matrix
  - `--output both` writes to both targets
