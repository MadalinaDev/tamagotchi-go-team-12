CREATE TABLE IF NOT EXISTS battles (
    battle_id UUID PRIMARY KEY,
    challenger_id UUID NOT NULL,
    opponent_id UUID NOT NULL,
    primary_pet_id UUID NOT NULL,
    secondary_pet_id UUID NOT NULL,
    boost TEXT NOT NULL CHECK (boost IN ('none', 'guard', 'power')),
    state TEXT NOT NULL CHECK (state IN ('pending', 'cancelled')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (challenger_id <> opponent_id),
    CHECK (primary_pet_id <> secondary_pet_id)
);

CREATE INDEX IF NOT EXISTS battles_challenger_idx ON battles (challenger_id, created_at DESC);
CREATE INDEX IF NOT EXISTS battles_opponent_idx ON battles (opponent_id, created_at DESC);
