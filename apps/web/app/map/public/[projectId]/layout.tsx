import { API_BASE_URL, APP_URL } from "@/lib/constants";
import { getLocalizedMetadata } from "@/lib/metadata";
import type { ProjectPublic } from "@/lib/validations/project";

export async function generateMetadata({ params: { projectId } }) {
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
    const url = `${APP_URL}/map/public/${projectId}`;
    const faviconUrl = publicProject.config.project.builder_config?.settings?.favicon_url;

    const metadata = getLocalizedMetadata(
      "en",
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
