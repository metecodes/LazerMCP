CREATE TABLE IF NOT EXISTS public.lasermcp_assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id text NOT NULL,
  name text NOT NULL,
  asset_type text NOT NULL CHECK (asset_type IN ('logo','icon','illustration')),
  storage_path text NOT NULL,
  default_operation text NOT NULL DEFAULT 'ENGRAVE' CHECK (default_operation IN ('CUT','ENGRAVE','SCORE','GUIDE','UNKNOWN')),
  bounds jsonb NOT NULL,
  token_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id,name)
);
ALTER TABLE public.lasermcp_assets ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.lasermcp_assets FROM anon, authenticated;
CREATE INDEX IF NOT EXISTS lasermcp_assets_org ON public.lasermcp_assets(organization_id);
