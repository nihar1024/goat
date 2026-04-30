import { headers } from "next/headers";

import { API_BASE_URL, APP_URL } from "@/lib/constants";
import { getLocalizedMetadata } from "@/lib/metadata";
import type { ProjectPublic } from "@/lib/validations/project";

export async function generateMetadata({ params: { projectId } }) {
  const lng = "en";
  const PROJECTS_API_BASE_URL = new URL("api/v2/project", API_BASE_URL).href;
  let publicProject: ProjectPublic | null = null;
  try {
    const res = await fetch(`${PROJECTS_API_BASE_URL}/${projectId}/public`, {
      cache: "no-store",
    });

    if (res.ok) {
      publicProject = await res.json();
    }
  } catch (err) {
    console.error("Failed to fetch public project:", err);
  }

  if (publicProject?.config?.project?.name) {
    const title = publicProject.config.project.name;
    const faviconUrl = publicProject.config.project.builder_config?.settings?.favicon_url;

    // Use the request's Host header so OG previews on a custom domain
    // show that domain, not the canonical app URL.
    const headersList = headers();
    const reqHost = headersList.get("host");
    const protocol = headersList.get("x-forwarded-proto") ?? "https";
    const fallbackUrl = APP_URL ?? "";
    let baseUrl: string;
    try {
      baseUrl = reqHost ? `${protocol}://${reqHost}` : fallbackUrl;
    } catch {
      baseUrl = fallbackUrl;
    }

    // On a custom domain the public path is hidden by middleware rewrite —
    // the user-visible URL is just `/`. On the canonical host we still
    // show the full path. Distinguish by comparing host.
    const canonicalHost = (() => {
      if (!APP_URL) return null;
      try {
        return new URL(APP_URL).host;
      } catch {
        return null;
      }
    })();
    const url =
      reqHost && reqHost !== canonicalHost
        ? `${baseUrl}/`
        : `${baseUrl}/map/public/${projectId}`;

    const metadata = getLocalizedMetadata(
      lng,
      {
        en: { title },
        de: { title },
      },
      {
        openGraphUrl: url,
        robotsIndex: true,
      }
    );

    if (faviconUrl) {
      return { ...metadata, icons: { icon: faviconUrl } };
    }
    return metadata;
  }

  return {};
}

export default function PageLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
