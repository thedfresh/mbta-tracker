# MBTA Transit Display

Always-on LED matrix display for MBTA Route 109 arrival times.

## Structure
- `src/data/` — MBTA and traffic API clients
- `src/logic/` — reliability scoring and travel-time estimation
- `src/rendering/` — scene composition and scroll engine
- `src/display/` — display driver interface (emulator + hardware)
- `config/` — configuration
- `scripts/` — legacy data collection scripts

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
