-- Shared request counters so rate limits hold across serverless instances.
-- Namespaced like 0002: safe to apply to the shared Supabase project.
-- Until this is applied the server keeps using its per-instance in-memory limiter.

CREATE TABLE IF NOT EXISTS public.lasermcp_rate_limits (
  bucket text NOT NULL,
  window_start timestamptz NOT NULL,
  hits integer NOT NULL DEFAULT 0,
  PRIMARY KEY (bucket, window_start)
);
ALTER TABLE public.lasermcp_rate_limits ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.lasermcp_rate_limits FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.lasermcp_rate_limits TO service_role;

-- Fixed window: one row per (bucket, window). Returns true while the caller is within the limit.
CREATE OR REPLACE FUNCTION public.lasermcp_rate_hit(p_bucket text, p_limit integer, p_window_sec integer)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  span integer := GREATEST(p_window_sec, 1);
  slot timestamptz := to_timestamp(floor(extract(epoch FROM now()) / span) * span);
  total integer;
BEGIN
  INSERT INTO lasermcp_rate_limits (bucket, window_start, hits) VALUES (p_bucket, slot, 1)
  ON CONFLICT (bucket, window_start) DO UPDATE SET hits = lasermcp_rate_limits.hits + 1
  RETURNING hits INTO total;
  -- Old windows are never read again; sweep them occasionally instead of scheduling a job.
  IF random() < 0.02 THEN
    DELETE FROM lasermcp_rate_limits WHERE window_start < now() - interval '2 days';
  END IF;
  RETURN total <= p_limit;
END;
$$;
REVOKE ALL ON FUNCTION public.lasermcp_rate_hit(text, integer, integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.lasermcp_rate_hit(text, integer, integer) TO service_role;
