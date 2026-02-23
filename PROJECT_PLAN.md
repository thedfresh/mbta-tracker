# MBTA Route 109 Tracker – Project Plan (Revised)
# projects/mbta-tracker

This document outlines the phased deliverables for the MBTA Route 109 Tracker project.

The project is both:
1. A **practical commuter decision aid** addressing unreliable real-time transit predictions on a single route.
2. A **resume-driven data engineering and applied ML project**, emphasizing evidence capture, explainable modeling, and disciplined iteration over sophistication.

The guiding principle is **trust over cleverness**: every output must be defensible with observable evidence.

---

## Phase 0: Evidence Capture (In Progress)

### Purpose
Establish a reliable, unbiased record of how MBTA predictions, vehicle assignments, and ETA updates behave in real conditions.

This phase prioritizes *ground truth observation* over interpretation.

### Deliverables
- Continuous raw data logs (append-only):
  - `predictions.jsonl`
  - `vehicles.jsonl`
  - `errors.jsonl`
- Stable polling infrastructure (Raspberry Pi, headless)
- Git-based workflow (Mac ↔ GitHub ↔ Pi)
- Documented polling cadence:
  - Fixed interval (e.g., 30s or 60s)
  - Rationale tied to ETA drift detection and API limits
- Basic error capture (network, API failures)

### Operational Notes
- Logs are retained verbatim during Phase 0
- No transformation, filtering, or scoring
- Disk growth is monitored but not yet optimized

### Exit Criteria
- ≥2 weeks of continuous polling
- At least one personally experienced “problem period” captured
- Confidence that collected data reflects real MBTA behavior (not artifacts)

---

## Phase 0.5: Schema Design & Backfill Validation

### Purpose
Prepare for structured analysis without prematurely optimizing storage or queries.

### Deliverables
- Conceptual data model identifying core entities:
  - poll event
  - prediction snapshot
  - trip
  - vehicle
- Decision on storage format for analysis (e.g., SQLite, Parquet, or similar)
- Backfill of existing raw logs into structured form
- Validation that no information is lost during backfill

### Non-Goals
- No heavy indexing or partitioning
- No performance tuning beyond correctness
- No normalization beyond analytical clarity

### Exit Criteria
- Structured queries can reproduce known trip timelines
- Raw logs remain the authoritative source of truth

---

## Phase 1: Offline Analysis and Signal Discovery

### Purpose
Identify which observable signals correlate with unreliable or misleading trip predictions.

This phase is exploratory but disciplined.

### Deliverables
- Single, consistent analysis environment (Python preferred)
- Reconstructable trip timelines showing:
  - vehicle assignment timing
  - ETA drift over time
  - prediction disappearance or stagnation
- Identification of candidate signals, e.g.:
  - vehicle unassigned within X minutes of scheduled departure
  - late inbound trip completion relative to outbound start
  - vehicle assigned but stationary too long
  - ETA instability vs. stability
- Explicit identification of **non-signals** to avoid noise

### Exit Criteria
- Able to answer:  
  *“At time T, what did the system know that consumer apps obscured?”*
- Plain-English explanations for both failed and successful trips
- Evidence-backed intuition about what matters

---

## Phase 2: Scoring and Confidence Modeling

### Purpose
Collapse complex, time-series signals into a small, explainable confidence state per trip.

This phase begins heuristic modeling and sets the foundation for future ML.

### Deliverables
- Initial confidence states:
  - GOOD
  - RISKY
  - BAD
- Empirically derived heuristics (subject to revision), e.g.:
  - No vehicle by T-12 → BAD
  - Late assignment + high ETA drift → RISKY
- Explicit handling of missing or stale data:
  - predictions disappear
  - vehicle updates stop
- Minimal structured output per trip:
  - trip_id
  - scheduled departure (or minutes until)
  - confidence state
  - short, human-readable reason

### Validation Requirement
- Manual spot-checks of ≥10 real trips
- Confidence states must align with human intuition
- System must err toward pessimism over false optimism

### Exit Criteria
- Scores are reproducible from raw logs
- Each score is defensible with evidence
- Failure modes are documented, not hidden

---

## Phase 3: Local Display MVP

### Purpose
Answer the commuter question at a glance:
**“Which of the next N trips should I trust?”**

### Deliverables
- Local display (LED or equivalent) showing:
  - next N trips
  - time to departure
  - confidence indicator (GOOD / RISKY / BAD)
- Display rules:
  - never suppress trips unless confidence is BAD
  - ambiguity is shown, not hidden
  - tie-breaking favors higher confidence over minor ETA differences

### Key Constraint
A glance while putting on shoes must not mislead.

### Exit Criteria
- Display influences real decisions
- Trust in display exceeds trust in standard MBTA apps for Route 109

---

## Phase 4: ML Enrichment and Expansion (Optional, Post-MVP)

### Purpose
Introduce machine learning **only where it adds value** beyond heuristics.

### Possible Directions
- Supervised models predicting failure likelihood
- Feature importance analysis to validate heuristic assumptions
- Temporal models capturing confidence decay over time
- Hybrid system: rules for safety, ML for refinement

### Constraints
- ML must be explainable
- No black-box predictions without fallback logic
- Only pursued if Phase 3 is already useful and trusted

---

## Explicit Non-Goals

- No generalized transit platform
- No early ML-first approach
- No premature optimization
- No expansion beyond Route 109 until trust is established

---

## Big Picture

- Phases 0–1: prove the problem exists and is diagnosable
- Phase 2: decide what the system is willing to say, and why
- Phase 3: build a tool that changes real decisions
- Phase 4: apply ML to refine, not replace, human trust

This project values **evidence, humility, and clarity** over novelty.