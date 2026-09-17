-- Standalone migration. Namespaced tables leave unrelated application data intact.
BEGIN;
CREATE TABLE IF NOT EXISTS public.lasermcp_organizations (
  id uuid PRIMARY KEY,
  kind text NOT NULL CHECK (kind IN ('personal', 'workspace')),
  name text NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.lasermcp_organization_members (
  organization_id uuid NOT NULL REFERENCES public.lasermcp_organizations(id) ON DELETE CASCADE,
  user_id text NOT NULL,
  role text NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, user_id)
);
CREATE TABLE IF NOT EXISTS public.lasermcp_artifacts (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES public.lasermcp_organizations(id) ON DELETE CASCADE,
  project_id text,
  version_id text,
  kind text NOT NULL,
  storage_path text NOT NULL,
  file_size bigint NOT NULL,
  mime_type text NOT NULL,
  hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz,
  source_file_id text
);
CREATE INDEX IF NOT EXISTS lasermcp_artifacts_source_idx ON public.lasermcp_artifacts(source_file_id, created_at DESC);
CREATE INDEX IF NOT EXISTS lasermcp_artifacts_org_idx ON public.lasermcp_artifacts(organization_id);
ALTER TABLE public.lasermcp_organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lasermcp_organization_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lasermcp_artifacts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.lasermcp_organizations, public.lasermcp_organization_members, public.lasermcp_artifacts FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.lasermcp_organizations, public.lasermcp_organization_members, public.lasermcp_artifacts TO service_role;

INSERT INTO public.lasermcp_organizations (id, kind, name, created_by)
VALUES ('00000000-0000-0000-0000-000000000001', 'workspace', 'Public workshop', 'system')
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.lasermcp_projects (
  id text PRIMARY KEY,
  payload jsonb NOT NULL
);
ALTER TABLE public.lasermcp_projects ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.lasermcp_projects FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.lasermcp_projects TO service_role;

-- Lock the project row before numbering and appending a version.
CREATE OR REPLACE FUNCTION public.append_lasermcp_version(p_id text, p_name text, p_version jsonb)
RETURNS jsonb LANGUAGE plpgsql SET search_path = public AS $$
DECLARE
  project jsonb;
  version_number integer;
  stamp text := to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"');
BEGIN
  INSERT INTO lasermcp_projects(id, payload)
  VALUES (p_id, jsonb_build_object('id', p_id, 'name', coalesce(nullif(p_name, ''), p_id), 'created', stamp, 'versions', '[]'::jsonb))
  ON CONFLICT(id) DO NOTHING;
  SELECT payload INTO project FROM lasermcp_projects WHERE id = p_id FOR UPDATE;
  version_number := jsonb_array_length(project->'versions') + 1;
  p_name := coalesce(nullif(p_name, ''), project->>'name', p_id);
  project := project || jsonb_build_object('name', p_name, 'updated', stamp,
    'versions', (project->'versions') || jsonb_build_array(p_version || jsonb_build_object('n', version_number)));
  UPDATE lasermcp_projects SET payload = project WHERE id = p_id;
  RETURN jsonb_build_object('project_id', p_id, 'name', p_name, 'version', version_number);
END;
$$;
REVOKE ALL ON FUNCTION public.append_lasermcp_version(text, text, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.append_lasermcp_version(text, text, jsonb) TO service_role;

CREATE OR REPLACE FUNCTION public.approve_lasermcp_version(p_id text)
RETURNS jsonb LANGUAGE plpgsql SET search_path = public AS $$
DECLARE project jsonb; idx integer;
BEGIN
  SELECT payload INTO project FROM lasermcp_projects WHERE id = p_id FOR UPDATE;
  IF project IS NULL THEN RAISE EXCEPTION 'unknown project'; END IF;
  idx := jsonb_array_length(project->'versions') - 1;
  IF idx < 0 THEN RAISE EXCEPTION 'no versions to approve'; END IF;
  project := jsonb_set(project, ARRAY['versions', idx::text],
    (project->'versions'->idx) || jsonb_build_object('approved', true, 'approved_at', now()));
  UPDATE lasermcp_projects SET payload = project WHERE id = p_id;
  RETURN jsonb_build_object('project_id', p_id, 'version', project->'versions'->idx->'n');
END;
$$;
REVOKE ALL ON FUNCTION public.approve_lasermcp_version(text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.approve_lasermcp_version(text) TO service_role;
NOTIFY pgrst, 'reload schema';
COMMIT;
