-- Static, credential-free bootstrap executed once on a fresh database volume (see compose.yaml).
-- The application role and its password are created by create-app-role.sh from environment variables.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
