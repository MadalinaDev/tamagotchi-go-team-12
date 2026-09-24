CREATE TABLE IF NOT EXISTS tamagotchis (
    pet_id UUID PRIMARY KEY,
    owner_id UUID NOT NULL,
    package_id UUID NOT NULL,
    name VARCHAR(40) NOT NULL,
    combat_type TEXT NOT NULL CHECK (combat_type IN ('flame','nature','earth','electric','water','shadow')),
    xp BIGINT NOT NULL DEFAULT 0 CHECK (xp >= 0),
    level INTEGER NOT NULL DEFAULT 1 CHECK (level > 0),
    sprite_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
    definition_version INTEGER NOT NULL DEFAULT 1,
    care_stats JSONB NOT NULL DEFAULT '{}'::jsonb,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (owner_id, package_id)
);

CREATE INDEX IF NOT EXISTS tamagotchis_owner_idx ON tamagotchis (owner_id, created_at, pet_id);

-- Issuance survives pet deletion: deleting a starter cannot farm new starters.
CREATE TABLE IF NOT EXISTS starter_issuances (
    owner_id UUID NOT NULL,
    package_id UUID NOT NULL,
    PRIMARY KEY(owner_id, package_id)
);
INSERT INTO starter_issuances(owner_id, package_id)
SELECT owner_id, package_id FROM tamagotchis ON CONFLICT DO NOTHING;
