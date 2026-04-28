import * as z from "zod";

export const dnsStatusSchema = z.enum(["pending", "verified", "failed"]);
export const certStatusSchema = z.enum(["pending", "issuing", "active", "failed"]);
export const domainKindSchema = z.enum(["single"]); // wildcard reserved for v2

/** Server response shape (matches OrganizationDomainRead in core). */
export const customDomainSchema = z.object({
  id: z.string().uuid(),
  organization_id: z.string().uuid(),
  base_domain: z.string(),
  kind: domainKindSchema,
  dns_status: dnsStatusSchema,
  dns_status_message: z.string().nullable(),
  dns_last_checked_at: z.string().nullable(),
  cert_status: certStatusSchema,
  cert_status_message: z.string().nullable(),
  created_at: z.string(),
  assigned_project_id: z.string().uuid().nullable().optional(),
  assigned_project_name: z.string().nullable().optional(),
});

export type CustomDomain = z.infer<typeof customDomainSchema>;
export type DnsStatus = z.infer<typeof dnsStatusSchema>;
export type CertStatus = z.infer<typeof certStatusSchema>;
export type DomainKind = z.infer<typeof domainKindSchema>;

/**
 * Hostname per RFC 1035, lowercased, ≥3 labels (apex rejected for v1),
 * leftmost label cannot be 'www', max length 253.
 *
 * Mirrors the backend validator in
 * apps/core/src/core/schemas/organization_domain.py.
 */
export const HOSTNAME_REGEX =
  /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$/;

export const customDomainCreateSchema = z.object({
  base_domain: z
    .string()
    .min(3)
    .max(253)
    .transform((v) => v.trim().toLowerCase())
    .refine((v) => HOSTNAME_REGEX.test(v), "Invalid hostname format")
    .refine((v) => v.split(".").length >= 3, "Apex domains are not supported; use a subdomain")
    .refine((v) => !v.startsWith("www."), "Subdomain cannot be 'www'"),
});

export type CustomDomainCreate = z.infer<typeof customDomainCreateSchema>;

/** Empty-state-friendly status helper for the UI. */
export function describeOverallStatus(domain: CustomDomain): {
  state: "active" | "pending_dns" | "issuing" | "failed";
  label: string;
} {
  if (domain.dns_status === "failed") {
    return { state: "failed", label: "DNS check failed" };
  }
  if (domain.dns_status === "pending") {
    return { state: "pending_dns", label: "Waiting for DNS" };
  }
  if (domain.cert_status === "active") {
    return { state: "active", label: "Active" };
  }
  if (domain.cert_status === "failed") {
    return { state: "failed", label: "Certificate failed" };
  }
  return { state: "issuing", label: "Issuing certificate" };
}
