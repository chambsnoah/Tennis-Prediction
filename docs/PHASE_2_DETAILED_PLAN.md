# Phase 2: Enhanced Intelligence & Analytics - Detailed Implementation Plan

## 🎯 Overview
**Duration:** 3-4 months | **Goal:** Transform from statistical models to ML-driven predictions with advanced analytics

**Key Objectives:**
- Implement machine learning models for match prediction
- Build PostgreSQL database layer with data migration
- Create advanced analytics dashboard
- Enhance simulation engine with momentum/fatigue modeling
- Improve prediction accuracy by 25-35%

---

## 📋 Phase 2 Roadmap

### **Month 1: Foundation & Data Layer**

#### **Week 1-2: Database Infrastructure**
**Priority:** High | **Effort:** 2 weeks | **Dependencies:** None

**Objectives:**
- Set up PostgreSQL database with proper schema design
- Create data migration scripts from JSON files
- Implement ORM layer with SQLAlchemy
- Set up database connection pooling and monitoring

**Deliverables:**
- `tennis_db/` module with database models
- Migration scripts for existing tournament data
- Database configuration and connection management
- Basic CRUD operations for players, matches, tournaments

**Technical Details:**
```text
# Database entities (see SQL section for authoritative schema)
- players: id, name, date_of_birth, country, current_ranking, career_high_ranking, created_at, updated_at
- tournaments: id, name, year, location, surface, category, start_date, end_date, created_at, updated_at
- matches: id, tournament_id, player1_id, player2_id, winner_id, score, surface, match_date, round, duration_minutes, created_at
- player_stats: id, player_id, surface, serve_win_percentage, return_win_percentage, break_points_saved_percentage, break_points_converted_percentage, aces_per_match, double_faults_per_match, first_serve_percentage, effective_date, created_at
- match_predictions: id, match_id, model_version, predicted_winner_id, confidence_score, actual_winner_id, features_used, prediction_date
```

**Success Criteria:**
- All existing JSON data successfully migrated
- Database queries perform <100ms for common operations
- Proper indexing on frequently queried columns

#### **Week 3-4: Historical Data Pipeline**
**Priority:** High | **Effort:** 2 weeks | **Dependencies:** Database infrastructure

**Objectives:**
- Collect and process 5+ years of historical match data (2015-2024)
- Implement data validation and cleaning pipeline
- Create feature engineering module for ML models
- Set up automated data refresh mechanisms

**Deliverables:**
- Historical data collection scripts
- Data validation and cleaning utilities
- Feature engineering pipeline
- Automated data update workflows

**Data Sources:**
- ATP/WTA official results
  - Terms & licensing: Review ATP and WTA Terms & Conditions before use (see ATP Terms: https://www.atptour.com/en/corporate/terms and WTA Terms: https://www.wtatennis.com/), and consult legal counsel for commercial usage.
  - Forbidden / restricted actions: do not scrape protected pages, redistribute official feeds, or republish bulk data without explicit permission; caching and republishing may be restricted.
  - Vendor-specific contractual items: comply with published rate limits, attribution requirements, and any paid subscription/overage fees.
  - Contact / permission process: for bulk or commercial use, request a data license from the ATP/WTA data team via their official contacts; document correspondence and agreements.

- Tennis Abstract (and similar independent data projects)
  - Terms & licensing: Tennis Abstract is a privately run site; its data and pages are subject to its owner’s terms. Do not assume open reuse.
  - Forbidden / restricted actions: explicit scraping, bulk download, caching, or redistribution without consent is prohibited unless permission is granted.
  - Contact / permission process: reach out to the site owner (contact via site contact form or email) to request reuse rights or a data extract; include proposed use, distribution, and attribution plan.
  - Special note: for Match Charting Project and community datasets, check contributor licenses and attribute sources as required.

- API providers (example vendors: Sportradar, Opta, Tennis-Data, other commercial APIs)
  - Terms & licensing: always follow the provider's Developer Terms and Service Agreement (each vendor publishes their own T&Cs and developer docs). Example vendor pages:
    - Sportradar: https://developer.sportradar.com/
    - Tennis-Data (example): check vendor site for terms
  - Forbidden / restricted actions: respect rate limits, do not share API keys, do not redistribute raw feed data unless the contract explicitly permits it, and respect caching windows defined in the contract.
  - Vendor-specific contractual items: rate limits, overage charges, required attribution, permitted use cases (internal only vs. public redistribution), SLAs, and termination clauses. Track these per-vendor in the contract record.
  - Contact / permission process: sign official API contract or commercial license. For paid vendors, coordinate with procurement/legal.

Data permissions and contract storage
- Store signed permissions, contracts, and vendor correspondence under `legal/ops/data-permissions/` in the repository (or in the company's secure contract storage if repo is public). Each file should include: vendor name, contact, contract reference, allowed use cases, rate limits, attribution requirements, and expiration/renewal dates.

Pre-ingestion checklist (MANDATORY before any automated ingestion)
- [ ] Verify T&Cs for the data source and record the location of the applicable Terms document
- [ ] Confirm whether scraping is permitted; if not, obtain API access or written permission
- [ ] Obtain and store written permission or signed contract (if required) in `legal/ops/data-permissions/`
- [ ] Note rate limits, attribution rules, caching restrictions, and overage fees in vendor record
- [ ] Get legal sign-off for commercial or public redistribution of the data

---

### **Month 2: Machine Learning Pipeline**

#### **Week 5-6: ML Model Development**
**Priority:** High | **Effort:** 2 weeks | **Dependencies:** Historical data pipeline

**Objectives:**
- Implement XGBoost/LightGBM models for match prediction
- Create comprehensive feature set (50+ features)
- Develop model training and validation pipelines
- Implement A/B testing framework for model comparison

**Feature Engineering:**
```python
# Core Features (25 features)
- Player rankings and ranking differences
- Recent form (last 10 matches win percentage)
- Head-to-head statistics
- Surface-specific performance
- Age and experience factors

# Advanced Features (25+ features)
- Momentum indicators (win streaks, recent performance)
- Fatigue factors (matches played in last 30 days)
- Tournament importance weighting
- Weather impact factors (for outdoor tournaments)
- Psychological factors (comeback ability, pressure handling)
```

### Temporal validity & feature freshness (REQUIRED)
To avoid leaking post-match information and ensure models reflect only information available before a match, the following rules must be enforced in feature engineering and model evaluation:

- Time-based cross-validation and pre-match cutoff:
  - All training/validation splits MUST be time-based (not random). Use an explicit pre-match cutoff timestamp when constructing features for a given match: only include data with event timestamps strictly earlier than the match start time.
  - When evaluating models, ensure the validation fold only contains matches that start after the training fold window (rolling or expanding windows recommended).

- Feature freshness windows:
  - Define and enforce freshness windows per feature (examples below). Only use matches that completed before the target match start.
    - "last_10_matches": use the 10 most-recently completed matches with end_time < match.start_time
    - "last_30_days": count matches where match.end_time >= (match.start_time - interval '30 days') AND match.end_time < match.start_time
    - "effective_date" fields (e.g., player_stats) must be <= match.start_date

- Weather / external data gating:
  - Only attach weather features to a match when a pre-match forecast or observation exists with timestamp <= match.start_time.
  - If pre-match weather is unavailable and match is outdoor, fall back to climatology or conservative default values (document fallback logic per tournament) and mark feature as imputed.
  - For indoor matches, do not attach outdoor weather features.

- Momentum, fatigue and psychological features:
  - Compute only from data with timestamps strictly prior to the match start. Do not use any in-match, post-match, or same-start-time data.
  - Examples:
    - Momentum: compute win streak using only prior match end times (e.g., 3 consecutive wins with end_time < target.start_time)
    - Fatigue: total minutes played in the last 14 days where match.end_time < target.start_time
    - Psychological: comeback_rate based on matches completed before target.start_time

Examples
- Safe: last_10_win_pct = wins / 10 computed from the 10 prior matches that ended before match.start_time
- Unsafe (leak): including a match that finished after match.start_time or using updated rankings published after the match start

Enforcement checklist (Feature Engineering & Model Evaluation)
- [ ] Use time-based CV and record pre-match cutoff timestamps used for each split
- [ ] For each feature, document freshness window and ensure queries filter by event end_time < match.start_time
- [ ] Verify weather features are only attached when pre-match weather data is available; otherwise use documented fallback
- [ ] Ensure momentum/fatigue/psych features are computed exclusively from pre-match data and timestamped accordingly
- [ ] Add unit/integration tests that assert no feature contains data timestamp >= match.start_time for a sample of matches

**Model Architecture:**
- **Primary Model:** XGBoost Classifier with feature importance analysis
- **Secondary Model:** LightGBM for ensemble predictions
- **Fallback Model:** Enhanced statistical model for edge cases

**Primary metrics & evaluation protocol (REQUIRED)**
- Primary metric: Log loss (cross-entropy) measured on time-respecting validation folds and the reserved holdout.
- Secondary metric: Brier score for probabilistic calibration and ranking stability.
- Target improvement: require a documented relative improvement versus the Phase 1 baseline for the primary metric (e.g., target 25-35% relative improvement in log loss versus Phase 1 baseline). Record the Phase 1 baseline values used for comparison.

Calibration & reliability checks:
- Compute Expected Calibration Error (ECE) and Maximum Calibration Error (MCE) on validation and holdout sets. Define acceptance thresholds (example: ECE < 0.05, MCE < 0.10) and justify any deviations.
- Produce reliability plots / calibration curves for each model version and include these in model evaluation reports.
- Run post-hoc calibration (Platt scaling / isotonic) only when justified, and report pre- and post-calibration metrics.

Time-aware validation and holdout:
- All validation must be time-aware (rolling-origin / expanding-window CV). Do not use random shuffles that mix future data into training.
- Reserve a chronological holdout set consisting of all matches from calendar year 2024 (or the most recent season) to simulate production performance. The holdout must not be used for model selection or hyperparameter tuning.
- Document the exact pre-match cutoff timestamps used to construct train/validation/holdout splits.

Latency & production constraints:
- Measure inference latency percentiles (p50, p95) for the prediction pipeline (including feature extraction for a single match request).
- Set targets and report results alongside accuracy metrics. Example targets: p50 < 50ms, p95 < 200ms (customize per deployment).

A/B testing and statistical significance:
- For model rollouts, run A/B experiments comparing the new model to the production baseline using the primary metric and relevant business KPIs.
- Report uplift with 95% confidence intervals and p-values. Use a significance threshold of p < 0.05 for release decisions, and require a minimum practical uplift (effect size) to justify rollout.
- Track secondary metrics (calibration, latency, error modes) and ensure no regression beyond pre-approved tolerances.

Reporting & artifacts:
- For every candidate model version, produce a Model Evaluation Report that includes: primary/secondary metric values, calibration metrics (ECE/MCE), reliability plots, time-split CV results, 2024 holdout performance, latency percentiles, feature importance, and any post-hoc calibration applied.
- Store evaluation reports and related artifacts under `tennis_ml/reports/models/<model_version>/`.

Updated Success Criteria (additions)
- [ ] Primary metric (log loss) improved relative to Phase 1 baseline by the documented target
- [ ] Brier score reported and not regressed vs baseline
- [ ] ECE and MCE within accepted thresholds (or remediation plan documented)
- [ ] Time-aware CV performed and 2024 holdout reserved and evaluated
- [ ] Inference latency percentiles (p50/p95) measured and within target bounds
- [ ] A/B test results reported with 95% CI and p < 0.05 (or documented rationale if alternative thresholds used)

---

### **Month 2: Machine Learning Pipeline**

#### **Week 7-8: Model Integration & Testing**
**Priority:** High | **Effort:** 2 weeks | **Dependencies:** ML model development

**Objectives:**
- Integrate ML models into existing prediction system
- Create model versioning and deployment pipeline
- Implement model monitoring and performance tracking
- Develop confidence scoring system

**Integration Points:**
- `tennis_preds/ml_predictor.py` - New ML prediction module
- Enhanced `PlayerEnhanced` class with ML features
- Model confidence scoring and uncertainty estimation
- Fallback mechanisms for model failures

---

### **Month 3: Enhanced Analytics & Simulation**

#### **Week 9-10: Advanced Analytics Dashboard**
**Priority:** Medium | **Effort:** 2 weeks | **Dependencies:** Database infrastructure

**Objectives:**
- Build comprehensive analytics dashboard
- Implement performance trend analysis
- Create surface-specific win probability matrices
- Develop tournament progression analytics

**Dashboard Features:**
- Player performance trends over time
- Surface-specific statistics and comparisons
- Break point conversion analysis by player/surface
- Tournament bracket probability calculations
- Historical matchup analysis

**Technical Implementation:**
- FastAPI backend for analytics endpoints
- Chart.js/D3.js for data visualization
- Real-time data updates via WebSockets (or SSE as an alternative for server-initiated streams)
- Export functionality (PDF, CSV, JSON)

### Security & robustness requirements (REQUIRED)
- Authentication & Authorization:
  - Use OAuth2 / JWT for API and real-time endpoints with per-user scopes/roles. Validate tokens on every request and on WebSocket connect.
  - Enforce fine-grained scopes (e.g., analytics:read, analytics:write, admin) and check scope membership on each endpoint.
  - For WebSockets, accept tokens via the Authorization header during the initial HTTP upgrade or via a secure WebSocket subprotocol; validate and expire tokens server-side.

- Rate limiting & throttling:
  - Implement rate limiting middleware for HTTP endpoints and per-tenant / per-user throttling policies. Enforce request size limits.
  - For WebSockets, enforce message-rate limits and per-connection quotas; implement backpressure strategies and a disconnect policy when clients exceed limits.

- XSS / CSRF / input validation:
  - Apply strict output encoding for any data rendered into charts or HTML; never inject unescaped user input into templates.
  - Validate and sanitize all user-provided filters, query params, and uploaded data on the server side with an allowlist approach.
  - Require CSRF protection for any state-changing HTTP endpoints (POST/PUT/DELETE) when used from browsers. Prefer using same-site cookies or double-submit cookies for CSRF tokens.
  - Use a Content Security Policy (CSP) and HTTP security headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Strict-Transport-Security) to mitigate XSS and related attacks.

- WebSocket / real-time channel specifics:
  - Authenticate at connect time; reject unauthorized upgrade attempts.
  - Limit concurrent connections per user/tenant and enforce message size and message-rate limits.
  - Implement server-side backpressure: queue length limits, pause/resume semantics, and graceful disconnect with error codes when overloaded.
  - Provide SSE (Server-Sent Events) fallback for clients that cannot maintain WebSocket connections; design same auth flows and rate limits for SSE.

- Caching & performance:
  - Use a cache layer (Redis recommended) for hot queries and precomputed analytics. Define TTLs per data class (e.g., leaderboard: 5m, player_stats: 1h, match_aggregates: 24h).
  - Cache invalidation strategy: invalidate on upstream data refresh or via versioned cache keys.

- Observability & graceful degradation:
  - Instrument all endpoints and real-time channels with metrics (requests, latencies p50/p95, error rates, active connections) and logs.
  - Implement health checks and circuit-breakers for downstream services (ML inference, external APIs).
  - Provide graceful degradation: return cached results or reduced-resolution analytics when upstream services are slow; document SSE fallback behavior.

- Token & secret handling:
  - Do not expose API keys or tokens to client-side code. Use short-lived JWTs and refresh tokens with secure storage.
  - For WS/SSE auth, prefer passing a validated Authorization header during upgrade; if sending tokens in query strings is unavoidable, strictly limit lifetime and scope and log usage.

- Implementation notes & checklist:
  - [ ] OAuth2/JWT implemented with per-user scopes and token validation on all API and WS endpoints
  - [ ] Rate limiting middleware and per-tenant throttling configured
  - [ ] Request size, message-rate limits, and backpressure/disconnect policy defined for WS
  - [ ] CSRF protection and CSP/encoding in place for browser-facing endpoints
  - [ ] Input validation and output encoding for all user-provided filters
  - [ ] Redis (or equivalent) cache layer for hot queries with documented TTLs
  - [ ] Monitoring, logging, and alerting configured for latency/error budgets and connection metrics
  - [ ] SSE fallback implemented and documented for clients that cannot use WebSockets

#### **Week 11-12: Enhanced Simulation Engine**
**Priority:** Medium | **Effort:** 2 weeks | **Dependencies:** ML model integration

**Objectives:**
- Add momentum modeling to simulation engine
- Implement fatigue and injury impact calculations
- Create weather condition adjustments
- Enhance crowd influence factors

**Simulation Enhancements:**
```python
# New Simulation Features
- Momentum tracking (win/loss streaks affect performance)
- Fatigue modeling (performance degradation over tournament)
- Weather impact (wind, temperature, humidity for outdoor)
- Psychological factors (comeback ability, pressure situations)
- Injury simulation (reduced performance based on injury history)
```

**Integration:**
- Enhanced `TennisMatch` class with new factors
- ML-driven probability adjustments
- Real-time simulation statistics
- Performance benchmarking against actual results

---

### **Month 4: Production & Optimization**

#### **Week 13-14: Performance Optimization**
**Priority:** Medium | **Effort:** 2 weeks | **Dependencies:** All previous components

**Objectives:**
- Optimize database queries and caching
- Improve ML model inference speed
- Enhance API response times
- Implement horizontal scaling considerations

**Performance SLOs (percentile-based, tied to scope & hardware)**
- Database:
  - OLTP / operational queries (user-facing lookups): p95 < 50ms, p99 < 150ms
  - Analytic / complex queries: p95 < 150ms, p99 < 300ms
  - Note: SLOs should be labeled by environment (dev/staging/prod) and instance class (db.m5.large / db.r5.xlarge etc.)

- ML inference (in-memory models):
  - Target: p95 < 100ms for in-memory models running on c5.xlarge (example baseline)
  - Define adjusted targets per instance class (e.g., c5.large p95 < 250ms). Document instance class used for measurements in each report.

- API endpoints (end-to-end including feature extraction):
  - p95 < 200ms, p99 < 400ms
  - Error-rate SLO: total 5xx/error responses < 0.5% over rolling 5m and 1h windows

- Simulation throughput:
  - Throughput normalized per vCPU: ≥1,000 matches/minute per vCPU under representative load
  - Define steady-state vs burst targets and corresponding latency envelopes

- Observability & alerts:
  - Monitor p50/p95/p99 latency percentiles for each component and end-to-end flows
  - Alert on SLO burn (e.g., sustained violation over 5-15 minutes) and on error-rate thresholds

**Optimization Techniques (aligned to SLOs & environment labels)**
- Database query optimization and indexing targeted to meet DB p95/p99 SLOs (use explain/analyze and track percentile latencies per query)
- ML model quantization and optimization with SLO-aware inference paths (fast-path for low-latency requests, batch/async for heavy workloads)
- Redis caching for frequently accessed/hot queries with explicit TTLs and cache hit metrics (use caching to bring analytic p95 down where appropriate)
- Async processing and background workers for heavy computations; ensure synchronous paths meet API p95 SLOs while batching where possible for throughput
- Use environment and hardware labels in monitoring (e.g., prod:c5.xlarge, prod:c5.large) so SLOs and alerts are scoped to the instance class used for evaluation
- Include latency percentiles and throughput-per-vCPU in benchmark reports and use these as gating criteria for production deployments

#### **Week 15-16: Testing & Deployment**
**Priority:** High | **Effort:** 2 weeks | **Dependencies:** Performance optimization

**Objectives:**
- Comprehensive testing of all Phase 2 features
- Performance benchmarking against Phase 1
- Documentation updates and user guides
- Production deployment preparation

**Testing Scope:**
- Unit tests for all new modules (target: 80% coverage)
- Integration tests for ML pipeline
- Performance tests with load simulation
- User acceptance testing for analytics dashboard

Data & reproducibility testing (REQUIRED):
- Schema / contract validation on ingestion (e.g., Great Expectations / Deequ):
  - Implement critical table/field assertions (examples: players.id NOT NULL and unique; player_stats.player_id exists in players; match.match_date is a valid date and winner_id NULLable only if match in-progress).
  - Store expectations as code and run them as part of ingestion pipelines and CI; fail pipeline on expectation violations.
- Deterministic training & artifact hashing:
  - Hash input datasets, preprocessing steps, and random seeds; record dataset_digest and seed in model metadata.
  - Provide deterministic training checks that assert identical model artifacts and metrics when rerunning with the same seed and dataset_digest.
- Property-based tests for feature engineering:
  - Use fuzzing / hypothesis-style tests to assert invariants (e.g., derived percentages are in [0,1], counts are non-negative, last_n_matches selects earlier matches by end_time).
  - Include edge-case scenarios (missing values, overlapping timestamps, duplicate records) to ensure transformations are robust.
- CI validations & schema-drift detection:
  - CI pipelines must run ingestion expectations, deterministic training checks (sample-mode), and property-based tests on PRs.
  - Add automated schema-drift alerts: track field-level types, null-rates, and cardinality changes and fail CI or open issues when drift exceeds thresholds.

---

## 🏗️ Technical Architecture

### **New Module Structure**
```
tennis_ml/                    # New ML module
├── __init__.py
├── models/                   # ML model implementations
│   ├── __init__.py
│   ├── xgboost_predictor.py
│   ├── lightgbm_predictor.py
│   └── ensemble_predictor.py
├── features/                 # Feature engineering
│   ├── __init__.py
│   ├── feature_engineer.py
│   ├── player_features.py
│   └── match_features.py
├── training/                 # Model training pipeline
│   ├── __init__.py
│   ├── data_preparation.py
│   ├── model_training.py
│   └── model_evaluation.py
└── utils/                    # ML utilities
    ├── __init__.py
    └── mlflow_integration.md  # Use MLflow Tracking & Model Registry instead of bespoke utilities


### Model registry & monitoring (PREFERRED)
- Adopt MLflow (or an equivalent standardized stack) for experiment tracking, model registry, and metrics collection rather than a bespoke `model_versioning.py` / `performance_monitoring.py` implementation.
- Integration notes:
  - Use MLflow Tracking for experiments (parameters, metrics, artifacts) and store run metadata in a central tracking server.
  - Use MLflow Model Registry to register models, create stages (Staging/Production), manage model versions, and support A/B rollouts and promotion workflows.
  - Record model signatures and input/output schema to enforce contract compatibility at inference time.
  - Log artifacts (trained model, preprocessing objects, dataset digests) and use MLflow’s REST API or client for automated deployments and rollback.

Benefits:
- Experiment lineage and reproducibility out-of-the-box
- Standardized packaging and model signatures for safe serving
- Easier A/B testing, staged rollouts, and rollback via Registry
- Ecosystem integrations for monitoring, deployment, and CI/CD

tennis_db/                    # New database module
├── __init__.py
├── models/                   # SQLAlchemy models
│   ├── __init__.py
│   ├── player.py
│   ├── match.py
│   ├── tournament.py
│   └── prediction.py
├── migrations/               # Database migrations
│   ├── __init__.py
│   └── migration_scripts.py
└── connection.py             # Database connection management

analytics/                    # Analytics module
├── __init__.py
├── dashboard/                # Dashboard components
│   ├── __init__.py
│   ├── player_analytics.py
│   ├── tournament_analytics.py
│   └── performance_trends.py
└── api/                      # Analytics API endpoints
    ├── __init__.py
    └── endpoints.py
```

### **Database Schema Evolution**
```sql
-- Enhanced schema for Phase 2
CREATE TABLE players (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    country VARCHAR(3),
    date_of_birth DATE,
    current_ranking INTEGER,
    career_high_ranking INTEGER,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Trigger function to automatically update `updated_at` timestamp on row updates
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Attach trigger to players table so updated_at refreshes on UPDATE
CREATE TRIGGER trg_players_update_updated_at
BEFORE UPDATE ON players
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE player_stats (
    id SERIAL PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES players(id),
    surface VARCHAR(20) NOT NULL CHECK (surface IN ('hard','clay','grass')),
    serve_win_percentage DECIMAL(5,2),
    return_win_percentage DECIMAL(5,2),
    break_points_saved_percentage DECIMAL(5,2),
    break_points_converted_percentage DECIMAL(5,2),
    aces_per_match DECIMAL(5,2),
    double_faults_per_match DECIMAL(5,2),
    first_serve_percentage DECIMAL(5,2),
    effective_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Ensure tournaments table exists before creating matches that reference it
CREATE TABLE tournaments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    location VARCHAR(100),
    surface VARCHAR(20), -- 'hard', 'clay', 'grass'
    category VARCHAR(50), -- 'grand_slam', 'masters_1000', 'atp_500', 'wta_500', etc.
    start_date DATE,
    end_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE matches (
    id SERIAL PRIMARY KEY,
    tournament_id INTEGER REFERENCES tournaments(id),
    player1_id INTEGER REFERENCES players(id),
    player2_id INTEGER REFERENCES players(id),
    winner_id INTEGER REFERENCES players(id),
    score VARCHAR(50),
    surface VARCHAR(20),
    match_date DATE,
    round VARCHAR(20), -- 'R1', 'R2', 'QF', 'SF', 'F'
    duration_minutes INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE match_predictions (
    id SERIAL PRIMARY KEY,
    match_id INTEGER REFERENCES matches(id),
    model_version VARCHAR(50),
    predicted_winner_id INTEGER REFERENCES players(id),
    confidence_score DECIMAL(5,4),
    actual_winner_id INTEGER REFERENCES players(id),
    features_used JSONB,
    prediction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes to improve FK lookups and common queries
CREATE INDEX idx_matches_tournament_id ON matches(tournament_id);
CREATE INDEX idx_matches_players ON matches(player1_id, player2_id);
CREATE INDEX idx_player_stats_player_surface ON player_stats(player_id, surface);
```

---

## 📊 Success Metrics & KPIs

### **Technical Metrics**
- **Prediction Accuracy:** Target 65-70% on unseen data
- **Model Inference Time:** <100ms per prediction
- **Database Query Time:** <50ms for complex analytics
- **API Response Time:** <200ms for all endpoints
- **Test Coverage:** >80% for new code

### **Business Metrics**
- **User Engagement:** 40% increase in simulation runs
- **Prediction Confidence:** Average confidence score >0.75
- **Data Freshness:** <24 hours for player statistics
- **System Uptime:** >99.5% availability

### **Performance Benchmarks**
- **Simulation Speed:** 1000+ matches per minute
- **Concurrent Users:** Support 100+ simultaneous users
- **Data Processing:** Handle 10,000+ historical matches
- **Analytics Generation:** <5 seconds for complex reports

---

## 🔄 Migration Strategy

### **Data Migration Plan (Hardened for idempotency & safe cutover)**
1. **Phase 1:** Export existing JSON data to canonical CSV/NDJSON format and generate stable natural keys where possible.
   - Produce documentation mapping JSON fields -> canonical schema fields and stable key selection (e.g., external_id, source + stable slug).
   - Compute and record a checksum (SHA256) per-exported record and produce a manifest with file-level and record-level checksums.

2. **Phase 2:** Implement deterministic IDs and idempotent import scripts.
   - Use deterministic IDs or stable natural keys for primary key generation so repeated imports produce the same keys (avoid non-deterministic SERIAL where stable keys are required).
   - Import scripts MUST be idempotent: use upserts (INSERT ... ON CONFLICT DO UPDATE) or equivalent ORM upsert facilities and record a batch_id and per-record checksum in an import log table.
   - Store a per-record checksum (e.g., sha256) in a dedicated column (e.g., data_checksum) to detect corruption or unintended changes.
   - Support dry-run mode that validates transforms and shows row counts / checksum diffs without committing.
   - Validate referential integrity pre- and post-import by running integrity checks against players/matches/tournaments relationships in a staging schema.

3. **Phase 3:** Dual-write, shadow reads, and reconciliation (parallel systems)
   - Run a controlled dual-write window where writers persist to JSON (legacy) AND the DB. Writes should be idempotent and include batch_id metadata.
   - Implement shadow reads: for a percentage of reads, fetch results from both JSON and DB and compare responses (structured comparison using checksums). Log any mismatches for investigation.
   - Automate pre/post migration checks: row counts per-table, aggregated checksums, and sampled diffs (store samples and diffs under `legal/ops/migration-audit/` or `tennis_db/migrations/audit/`).
   - Define thresholds for acceptable discrepancy rates (e.g., <0.1% mismatches). If exceeded, pause cutover and investigate.

4. **Phase 4:** Feature-flagged flip to DB-only + final reconciliation
   - Perform a final reconciliation run (full counts + checksum validation). If all checks pass or discrepancies are remediated, perform a feature-flagged flip where reads route to DB by default for a canary subset and then progressively to 100%.
   - Before the flip, optionally place JSON store in read-only freeze mode to avoid new writes during the final verification window.
   - Flip procedure must be feature-flagged and documented with precise rollback steps (see below). Keep dual-write active for a short tail period after the flip to catch late discrepancies.

5. **Phase 5:** Archive JSON and cleanup / rollback plan
   - After successful cutover and a stabilization window, archive JSON files and the final manifests to `legal/ops/data-archives/` with retention metadata.
   - Rollback plan (explicit):
     - If discrepancies exceed thresholds or critical errors occur after flip, immediately toggle feature flag to route reads back to JSON-only.
     - Re-enable dual-write if it was disabled, run reconciliation, and remediate data (replay idempotent imports or restore from pre-migration DB backups).
     - Document recovery steps including restoring DB from snapshot, re-running idempotent import with verified manifest, and validating referential integrity.

Additional migration hardening details
- Import logging & audit: record batch_id, source file, start/end timestamps, per-table row counts, and checksums for each import run.
- Automated validation: provide scripts that run pre/post referential integrity checks, checksum reconciliation, and sampled JSON vs DB diffs; fail fast on integrity errors.
- Storage of artifacts: store manifests, import logs, reconciliation reports, and sampled diffs under `tennis_db/migrations/audit/` and a copy under `legal/ops/migration-audit/` for legal/audit trail.
- Testing: include unit tests for transformation logic, and integration tests for idempotency and upsert semantics. Use staging environment to rehearse cutover.

---

## 📈 Phase 2 Deliverables Checklist

### **Core Deliverables**
- [ ] PostgreSQL database with complete schema
- [ ] ML prediction models (XGBoost + LightGBM)
- [ ] Feature engineering pipeline (50+ features)
- [ ] Analytics dashboard with visualizations
- [ ] Enhanced simulation engine with momentum
- [ ] Performance monitoring and alerting
- [ ] Comprehensive test suite (>80% coverage)
- [ ] Updated documentation and user guides

### **Integration Deliverables**
- [ ] Seamless integration with existing codebase
- [ ] Backward compatibility maintained
- [ ] A/B testing framework operational
- [ ] Production deployment scripts
- [ ] Monitoring and logging infrastructure

### **Quality Assurance**
- [ ] Security audit and penetration testing
- [ ] Performance benchmarking completed
- [ ] User acceptance testing passed
- [ ] Documentation updated and reviewed

---

## 🎯 Next Steps

### **Immediate Actions (Week 1)**
1. Set up development environment for Phase 2
2. Create detailed task breakdown and timeline
3. Begin database schema design and implementation
4. Start historical data collection process

### **Resource Requirements**
- **Development Team:** 2-3 full-time developers
- **Data Engineer:** 1 specialist for data pipeline
- **ML Engineer:** 1 specialist for model development
- **DevOps Engineer:** 0.5 FTE for infrastructure
- **QA Engineer:** 1 for testing and validation

### **Budget Considerations**
- **Database:** PostgreSQL hosting ($50-200/month)
- **ML Training:** Cloud GPU instances ($200-500/month)
- **API Costs:** Additional API quota ($100-300/month)
- **Monitoring:** Application monitoring tools ($50-150/month)

---

## 📞 Support & Communication

### **Weekly Checkpoints**
- **Monday:** Sprint planning and task assignment
- **Wednesday:** Mid-week progress review
- **Friday:** End-of-week status and blockers

### **Communication Channels**
- **Technical Discussions:** GitHub Issues and Pull Requests
- **Daily Updates:** Slack/Teams channel
- **Weekly Reports:** Email summary to stakeholders
- **Blocker Escalation:** Immediate notification for critical issues

### **Documentation Updates**
- **Technical Docs:** Updated with new architecture
- **User Guides:** New features and capabilities
- **API Documentation:** OpenAPI specifications
- **Deployment Guides:** Production setup instructions

---

*This Phase 2 plan provides a comprehensive roadmap for transforming the Tennis Prediction application into an ML-driven, analytics-powered platform. The modular approach allows for iterative development while maintaining system stability and user experience.*
