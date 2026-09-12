-- LaserMCP Sprint 0.5 — application metadata only. No CAD bytes.
-- Apply in Supabase SQL editor or via your migration runner.
-- Server uses SUPABASE_SERVICE_ROLE_KEY (bypasses RLS). Browser never receives it.

CREATE TABLE IF NOT EXISTS public.organizations (
  id uuid PRIMARY KEY,
  kind text NOT NULL CHECK (kind IN ('personal', 'workspace')),
  name text NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.organization_members (
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  user_id text NOT NULL,
  role text NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, user_id)
);

CREATE TABLE IF NOT EXISTS public.artifacts (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  project_id uuid,
  version_id uuid,
  kind text NOT NULL,
  storage_path text NOT NULL,
  file_size bigint NOT NULL,
  mime_type text NOT NULL,
  hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz,
  source_file_id text
);

CREATE INDEX IF NOT EXISTS artifacts_organization_id_idx ON public.artifacts (organization_id);
CREATE INDEX IF NOT EXISTS artifacts_source_file_id_idx ON public.artifacts (source_file_id);

CREATE TABLE IF NOT EXISTS public.api_keys (
  id text PRIMARY KEY,
  name text NOT NULL,
  hash text NOT NULL UNIQUE,
  prefix text,
  owner_user_id text,
  organization_id uuid REFERENCES public.organizations (id),
  role text,
  plan text,
  kind text,
  email text,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_used_at timestamptz,
  expires_at timestamptz,
  revoked_at timestamptz
);

CREATE INDEX IF NOT EXISTS api_keys_owner_user_id_idx ON public.api_keys (owner_user_id);

ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.organization_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.api_keys ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.organizations FROM anon, public;
REVOKE ALL ON public.organization_members FROM anon, public;
REVOKE ALL ON public.artifacts FROM anon, public;
REVOKE ALL ON public.api_keys FROM anon, public;

-- Defense in depth for a future user-JWT dashboard. MCP/API keys use the service role.
DROP POLICY IF EXISTS organizations_member_select ON public.organizations;
CREATE POLICY organizations_member_select ON public.organizations
  FOR SELECT TO authenticated
  USING (
    id IN (
      SELECT organization_id FROM public.organization_members
      WHERE user_id = auth.uid()::text
    )
  );

-- Avoid a self-referential RLS subquery (Postgres can recurse).
DROP POLICY IF EXISTS organization_members_self_select ON public.organization_members;
CREATE POLICY organization_members_self_select ON public.organization_members
  FOR SELECT TO authenticated
  USING (user_id = auth.uid()::text);

DROP POLICY IF EXISTS artifacts_member_select ON public.artifacts;
CREATE POLICY artifacts_member_select ON public.artifacts
  FOR SELECT TO authenticated
  USING (
    organization_id IN (
      SELECT organization_id FROM public.organization_members
      WHERE user_id = auth.uid()::text
    )
  );

DROP POLICY IF EXISTS api_keys_owner_select ON public.api_keys;
CREATE POLICY api_keys_owner_select ON public.api_keys
  FOR SELECT TO authenticated
  USING (owner_user_id = auth.uid()::text);
