CREATE TABLE IF NOT EXISTS conda_env_sessions (
    event_hash text PRIMARY KEY,
    event_time timestamptz NOT NULL,
    env_name text NOT NULL,
    user_id text NOT NULL,
    pid bigint,
    sys_executable text,
    sys_prefix text,
    source_file text,
    source_line integer,
    inserted_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conda_env_sessions_time ON conda_env_sessions (event_time);
CREATE INDEX IF NOT EXISTS idx_conda_env_sessions_env_time ON conda_env_sessions (env_name, event_time);
CREATE INDEX IF NOT EXISTS idx_conda_env_sessions_user_time ON conda_env_sessions (user_id, event_time);

CREATE TABLE IF NOT EXISTS conda_env_packages (
    event_hash text NOT NULL REFERENCES conda_env_sessions(event_hash) ON DELETE CASCADE,
    package_name text NOT NULL,
    inserted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (event_hash, package_name)
);

CREATE INDEX IF NOT EXISTS idx_conda_env_packages_name ON conda_env_packages (package_name);

CREATE TABLE IF NOT EXISTS conda_env_ingest_runs (
    id bigserial PRIMARY KEY,
    run_at timestamptz NOT NULL DEFAULT now(),
    input_file text NOT NULL,
    rows_in_file integer NOT NULL,
    rows_parsed integer NOT NULL,
    bad_rows integer NOT NULL
);

CREATE OR REPLACE VIEW conda_env_daily_usage AS
SELECT
    date_trunc('day', s.event_time) AS day,
    s.env_name,
    count(
        DISTINCT md5(
            concat_ws(
                '|',
                s.env_name,
                s.user_id,
                coalesce(s.pid::text, ''),
                coalesce(s.sys_executable, ''),
                coalesce(s.sys_prefix, ''),
                date_trunc('day', s.event_time)::text
            )
        )
    ) AS sessions,
    count(DISTINCT s.user_id) AS active_users
FROM conda_env_sessions s
GROUP BY 1, 2;

CREATE OR REPLACE VIEW conda_env_package_daily_usage AS
SELECT
    date_trunc('day', s.event_time) AS day,
    s.env_name,
    p.package_name,
    count(*) AS package_uses,
    count(DISTINCT s.user_id) AS users_using_package
FROM conda_env_sessions s
JOIN conda_env_packages p ON p.event_hash = s.event_hash
GROUP BY 1, 2, 3;

CREATE OR REPLACE VIEW conda_env_usage_daily AS
SELECT
    date_trunc('day', s.event_time)::date AS period_start,
    s.env_name,
    count(
        DISTINCT md5(
            concat_ws(
                '|',
                s.env_name,
                s.user_id,
                coalesce(s.pid::text, ''),
                coalesce(s.sys_executable, ''),
                coalesce(s.sys_prefix, ''),
                date_trunc('day', s.event_time)::text
            )
        )
    ) AS sessions,
    count(DISTINCT s.user_id) AS unique_users
FROM conda_env_sessions s
GROUP BY 1, 2;

CREATE OR REPLACE VIEW conda_env_usage_weekly AS
SELECT
    date_trunc('week', s.event_time)::date AS period_start,
    s.env_name,
    count(
        DISTINCT md5(
            concat_ws(
                '|',
                s.env_name,
                s.user_id,
                coalesce(s.pid::text, ''),
                coalesce(s.sys_executable, ''),
                coalesce(s.sys_prefix, ''),
                date_trunc('day', s.event_time)::text
            )
        )
    ) AS sessions,
    count(DISTINCT s.user_id) AS unique_users
FROM conda_env_sessions s
GROUP BY 1, 2;

CREATE OR REPLACE VIEW conda_env_usage_monthly AS
SELECT
    date_trunc('month', s.event_time)::date AS period_start,
    s.env_name,
    count(
        DISTINCT md5(
            concat_ws(
                '|',
                s.env_name,
                s.user_id,
                coalesce(s.pid::text, ''),
                coalesce(s.sys_executable, ''),
                coalesce(s.sys_prefix, ''),
                date_trunc('day', s.event_time)::text
            )
        )
    ) AS sessions,
    count(DISTINCT s.user_id) AS unique_users
FROM conda_env_sessions s
GROUP BY 1, 2;

CREATE OR REPLACE VIEW conda_env_usage_daily_total AS
SELECT
    date_trunc('day', s.event_time)::date AS period_start,
    count(
        DISTINCT md5(
            concat_ws(
                '|',
                s.env_name,
                s.user_id,
                coalesce(s.pid::text, ''),
                coalesce(s.sys_executable, ''),
                coalesce(s.sys_prefix, ''),
                date_trunc('day', s.event_time)::text
            )
        )
    ) AS sessions,
    count(DISTINCT s.user_id) AS unique_users
FROM conda_env_sessions s
GROUP BY 1;

CREATE OR REPLACE VIEW conda_env_usage_weekly_total AS
SELECT
    date_trunc('week', s.event_time)::date AS period_start,
    count(
        DISTINCT md5(
            concat_ws(
                '|',
                s.env_name,
                s.user_id,
                coalesce(s.pid::text, ''),
                coalesce(s.sys_executable, ''),
                coalesce(s.sys_prefix, ''),
                date_trunc('day', s.event_time)::text
            )
        )
    ) AS sessions,
    count(DISTINCT s.user_id) AS unique_users
FROM conda_env_sessions s
GROUP BY 1;

CREATE OR REPLACE VIEW conda_env_usage_monthly_total AS
SELECT
    date_trunc('month', s.event_time)::date AS period_start,
    count(
        DISTINCT md5(
            concat_ws(
                '|',
                s.env_name,
                s.user_id,
                coalesce(s.pid::text, ''),
                coalesce(s.sys_executable, ''),
                coalesce(s.sys_prefix, ''),
                date_trunc('day', s.event_time)::text
            )
        )
    ) AS sessions,
    count(DISTINCT s.user_id) AS unique_users
FROM conda_env_sessions s
GROUP BY 1;

CREATE OR REPLACE VIEW conda_env_package_usage_by_env AS
SELECT
    s.env_name,
    p.package_name,
    count(*) AS package_uses
FROM conda_env_sessions s
JOIN conda_env_packages p ON p.event_hash = s.event_hash
GROUP BY 1, 2;

CREATE OR REPLACE VIEW conda_env_package_ranking_by_env AS
SELECT
    env_name,
    package_name,
    package_uses,
    dense_rank() OVER (PARTITION BY env_name ORDER BY package_uses DESC, package_name) AS package_rank
FROM conda_env_package_usage_by_env;
