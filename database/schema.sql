CREATE TABLE IF NOT EXISTS modules (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    position    INT  NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS categories (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    module_id   BIGINT NOT NULL REFERENCES modules(id) ON DELETE RESTRICT,
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL,
    position    INT  NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (module_id, slug)
);

CREATE TABLE IF NOT EXISTS resources (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category_id  BIGINT NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    title        TEXT NOT NULL,
    description  TEXT,
    file_url     TEXT,
    storage_ref  TEXT,
    file_name    TEXT,
    created_by   BIGINT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (file_url IS NOT NULL OR storage_ref IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_categories_module  ON categories(module_id);
CREATE INDEX IF NOT EXISTS idx_resources_category ON resources(category_id);