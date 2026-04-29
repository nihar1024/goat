import useSWR from "swr";

import { apiRequestAuth, fetcher } from "@/lib/api/fetcher";
import type { CustomDomain } from "@/lib/validations/customDomain";

export const ORGANIZATIONS_API_BASE_URL = new URL(
  "api/v2/organizations",
  process.env.NEXT_PUBLIC_API_URL
).href;

const orgDomainsUrl = (orgId: string) => `${ORGANIZATIONS_API_BASE_URL}/${orgId}/domains/`;

const oneDomainUrl = (orgId: string, domainId: string) =>
  `${ORGANIZATIONS_API_BASE_URL}/${orgId}/domains/${domainId}`;

const projectCustomDomainUrl = (projectId: string) =>
  new URL(`api/v2/project/${projectId}/public/custom-domain`, process.env.NEXT_PUBLIC_API_URL).href;

/**
 * List all custom domains for an organization.
 *
 * Background revalidation every 30s catches state transitions for users
 * who navigate away from the detail panel; the panel itself polls faster.
 */
export function useOrganizationDomains(organizationId: string | undefined) {
  const { data, isLoading, error, mutate, isValidating } = useSWR<CustomDomain[]>(
    organizationId ? [orgDomainsUrl(organizationId)] : null,
    fetcher,
    { refreshInterval: 30_000 }
  );
  return { domains: data, isLoading, isError: error, mutate, isValidating };
}

/**
 * Single domain. Set `polling: true` while watching transitional states
 * (the DetailDrawer in Phase 9B uses this to feel live).
 */
export function useOrganizationDomain(
  organizationId: string | undefined,
  domainId: string | undefined,
  options: { polling?: boolean } = {}
) {
  const { data, isLoading, error, mutate } = useSWR<CustomDomain>(
    organizationId && domainId ? [oneDomainUrl(organizationId, domainId)] : null,
    fetcher,
    { refreshInterval: options.polling ? 5_000 : 30_000 }
  );
  return { domain: data, isLoading, isError: error, mutate };
}

export async function createCustomDomain(
  organizationId: string,
  baseDomain: string
): Promise<CustomDomain> {
  const response = await apiRequestAuth(orgDomainsUrl(organizationId), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ base_domain: baseDomain }),
  });
  if (!response.ok) {
    throw new Error("Failed to create custom domain");
  }
  return await response.json();
}

export async function deleteCustomDomain(organizationId: string, domainId: string): Promise<void> {
  const response = await apiRequestAuth(oneDomainUrl(organizationId, domainId), {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Failed to delete custom domain ${domainId}`);
  }
}

export async function recheckCustomDomain(
  organizationId: string,
  domainId: string
): Promise<CustomDomain> {
  const response = await apiRequestAuth(`${oneDomainUrl(organizationId, domainId)}/recheck`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(`Failed to recheck custom domain ${domainId}`);
  }
  return await response.json();
}

export async function assignDomainToProject(projectId: string, domainId: string): Promise<void> {
  const response = await apiRequestAuth(projectCustomDomainUrl(projectId), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ domain_id: domainId }),
  });
  if (!response.ok) {
    throw new Error("Failed to assign domain to project");
  }
}

export async function unassignDomainFromProject(projectId: string): Promise<void> {
  const response = await apiRequestAuth(projectCustomDomainUrl(projectId), {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error("Failed to unassign domain from project");
  }
}
