-- =============================================================================
-- PRISM - PostgreSQL initial setup
-- Run as postgres superuser: psql -U postgres -f setup_db.sql
-- =============================================================================

-- Create user (change password!)
CREATE USER prism WITH PASSWORD 'changeme_strong_password';

-- Create database
CREATE DATABASE prism OWNER prism ENCODING 'UTF8' LC_COLLATE 'en_US.UTF-8' LC_CTYPE 'en_US.UTF-8';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE prism TO prism;

-- Connect to the new database and grant schema privileges
\c prism
GRANT ALL ON SCHEMA public TO prism;

-- Performance settings (run these as superuser after connecting to prism db)
-- These are optimized for a write-heavy audit log workload
ALTER SYSTEM SET shared_buffers = '256MB';           -- 25% of RAM is a good starting point
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = '0.9';
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = '100';
ALTER SYSTEM SET work_mem = '4MB';

SELECT pg_reload_conf();
