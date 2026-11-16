-- Interval-count research: per-cell integer lower/upper bounds with verified
-- row/column totals. Deliberately separate tables from the exact-count study so
-- existing CellCount/CorrespondenceRun data and runs are untouched.
--
-- interval_studies        one row per bounded-count study (natural key: name)
-- interval_categories     row/column categories with verified_total (natural key: study,axis,code)
-- interval_cell_bounds    per (row,column) integer bounds, 0 <= lower <= upper
-- interval_runs           queued/succeeded bound-solving runs with JSON result
--
-- Totals consistency and joint capacity feasibility are enforced in the solver,
-- not by a DB constraint: equal totals alone are not sufficient for feasibility.
CREATE TABLE IF NOT EXISTS interval_studies (
 id SERIAL PRIMARY KEY,
 name VARCHAR(100) UNIQUE NOT NULL,
 filename VARCHAR(160) NOT NULL,
 description VARCHAR(500) NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS interval_categories (
 id SERIAL PRIMARY KEY,
 study_id INTEGER NOT NULL REFERENCES interval_studies(id),
 axis VARCHAR(10) NOT NULL,
 code VARCHAR(30) NOT NULL,
 label VARCHAR(80) NOT NULL,
 position INTEGER NOT NULL,
 verified_total INTEGER NOT NULL DEFAULT 0,
 CONSTRAINT interval_total_nonnegative CHECK (verified_total >= 0),
 UNIQUE (study_id, axis, code)
);
CREATE TABLE IF NOT EXISTS interval_cell_bounds (
 id SERIAL PRIMARY KEY,
 study_id INTEGER NOT NULL REFERENCES interval_studies(id),
 row_id INTEGER NOT NULL REFERENCES interval_categories(id),
 column_id INTEGER NOT NULL REFERENCES interval_categories(id),
 lower INTEGER NOT NULL DEFAULT 0,
 upper INTEGER NOT NULL DEFAULT 0,
 CONSTRAINT interval_bounds_ordered CHECK (lower >= 0 AND upper >= lower),
 UNIQUE (row_id, column_id)
);
CREATE TABLE IF NOT EXISTS interval_runs (
 id SERIAL PRIMARY KEY,
 study_id INTEGER NOT NULL REFERENCES interval_studies(id),
 name VARCHAR(100) NOT NULL,
 time_limit INTEGER NOT NULL DEFAULT 20,
 status VARCHAR(20) NOT NULL DEFAULT 'queued',
 result JSON NOT NULL DEFAULT '{}',
 error VARCHAR(1000),
 creator_id INTEGER NOT NULL REFERENCES users(id),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
