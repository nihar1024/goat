/**
 * Resolves a custom-domain hostname to a project ID via the backend's
 * anonymous lookup endpoint. Cached per-process for 60s to absorb the
 * burst of requests that follows a page load.
 *
 * Used exclusively by the Next.js middleware. Don't import this from
 * client components — it's edge-runtime / server only.
 */

const cache = new Map<string, { projectId: string | null; at: number }>();
const TTL_MS = 60_000;

export async function lookupCustomDomain(host: string): Promise<string | null> {
  const cached = cache.get(host);
  if (cached && Date.now() - cached.at < TTL_MS) {
    return cached.projectId;
  }

  const apiBase = process.env.NEXT_PUBLIC_API_URL;
  if (!apiBase) return null;

  try {
    const res = await fetch(
      `${apiBase}/api/v2/custom-domain-lookup?host=${encodeURIComponent(host)}`,
      { cache: "no-store" }
    );
    let projectId: string | null = null;
    if (res.ok) {
      const body = (await res.json()) as { project_id?: string };
      projectId = body.project_id ?? null;
    }
    cache.set(host, { projectId, at: Date.now() });
    return projectId;
  } catch {
    // Don't poison the cache on transient failures.
    return null;
  }
}
