CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.healthcheck (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  note TEXT NOT NULL
);

INSERT INTO app.healthcheck (note)
SELECT 'goofish-insight bootstrap'
WHERE NOT EXISTS (
  SELECT 1
  FROM app.healthcheck
  WHERE note = 'goofish-insight bootstrap'
);
