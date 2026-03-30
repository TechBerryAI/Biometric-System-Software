-- Run in pgAdmin: connect as user `postgres`, open Query Tool on the `postgres` database, then execute.
-- Or: psql -U postgres -f setup_local_database.sql

-- 1) Create database (skip if you already created `biometric_db` in pgAdmin)
CREATE DATABASE biometric_db
    WITH
    OWNER = postgres
    ENCODING = 'UTF8';

-- 2) Optional: dedicated app user (alternative to using `postgres` in DATABASE_URL)
-- CREATE ROLE biometric LOGIN PASSWORD 'choose_a_strong_password';
-- GRANT ALL PRIVILEGES ON DATABASE biometric_db TO biometric;
-- After migrations, grant schema usage:
-- \c biometric_db
-- GRANT ALL ON SCHEMA public TO biometric;

-- 3) Set backend/.env
-- DATABASE_URL=postgresql+psycopg://postgres:YOUR_ACTUAL_PASSWORD@localhost:5432/biometric_db
--
-- 4) From repo: cd backend && .venv\Scripts\activate && alembic upgrade head
