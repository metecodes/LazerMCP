-- Generated files expire after 24 hours; remove bytes using the Storage API.
BEGIN;
CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;
CREATE EXTENSION IF NOT EXISTS http WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS supabase_vault WITH SCHEMA vault;

CREATE OR REPLACE FUNCTION public.lasermcp_set_artifact_expiry()
RETURNS trigger LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN NEW.created_at := OLD.created_at; END IF;
  NEW.expires_at := NEW.created_at + interval '24 hours';
  RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION public.lasermcp_set_artifact_expiry() FROM PUBLIC, anon, authenticated;
DROP TRIGGER IF EXISTS lasermcp_artifact_expiry ON public.lasermcp_artifacts;
CREATE TRIGGER lasermcp_artifact_expiry BEFORE INSERT OR UPDATE ON public.lasermcp_artifacts
FOR EACH ROW EXECUTE FUNCTION public.lasermcp_set_artifact_expiry();
UPDATE public.lasermcp_artifacts SET expires_at = created_at + interval '24 hours';
CREATE INDEX IF NOT EXISTS lasermcp_artifacts_expiry_idx ON public.lasermcp_artifacts(expires_at);

-- Credentials are installed separately using parameterized Vault calls.
-- Only the postgres-owned cron job can execute this function.
CREATE OR REPLACE FUNCTION public.lasermcp_cleanup_artifacts()
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, extensions AS $$
DECLARE
  ids uuid[];
  paths text[];
  project_url text;
  service_key text;
  bucket text;
  response extensions.http_response;
  deleted integer := 0;
BEGIN
  IF NOT pg_try_advisory_xact_lock(784630125) THEN RETURN 0; END IF;
  SELECT array_agg(id), array_agg(storage_path) INTO ids, paths
  FROM (SELECT id, storage_path FROM public.lasermcp_artifacts
        WHERE expires_at <= now() ORDER BY expires_at LIMIT 100 FOR UPDATE SKIP LOCKED) expired;
  IF ids IS NULL THEN RETURN 0; END IF;
  SELECT decrypted_secret INTO project_url FROM vault.decrypted_secrets WHERE name = 'lasermcp_storage_url';
  SELECT decrypted_secret INTO service_key FROM vault.decrypted_secrets WHERE name = 'lasermcp_storage_key';
  SELECT decrypted_secret INTO bucket FROM vault.decrypted_secrets WHERE name = 'lasermcp_storage_bucket';
  IF project_url IS NULL OR service_key IS NULL OR bucket IS NULL THEN
    RAISE EXCEPTION 'LaserMCP cleanup Vault configuration missing';
  END IF;
  SELECT * INTO response FROM extensions.http((
    'DELETE', project_url || '/storage/v1/object/' || bucket,
    ARRAY[extensions.http_header('Authorization', 'Bearer ' || service_key),
          extensions.http_header('apikey', service_key)],
    'application/json', jsonb_build_object('prefixes', paths)::text
  )::extensions.http_request);
  IF response.status BETWEEN 200 AND 299 THEN
    DELETE FROM public.lasermcp_artifacts WHERE id = ANY(ids);
    GET DIAGNOSTICS deleted = ROW_COUNT;
  ELSE
    -- Avoid logging response bodies or credentials; keep records for retry.
    RAISE WARNING 'LaserMCP Storage cleanup HTTP %; records retained', response.status;
  END IF;
  RETURN deleted;
END;
$$;
REVOKE ALL ON FUNCTION public.lasermcp_cleanup_artifacts() FROM PUBLIC, anon, authenticated, service_role;
SELECT cron.schedule('lasermcp-artifact-cleanup', '*/15 * * * *', 'SELECT public.lasermcp_cleanup_artifacts();');
NOTIFY pgrst, 'reload schema';
COMMIT;
