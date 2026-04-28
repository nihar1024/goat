import { Chip } from "@mui/material";
import { useTranslation } from "react-i18next";

import { describeOverallStatus } from "@/lib/validations/customDomain";
import type { CustomDomain } from "@/lib/validations/customDomain";

interface Props {
  domain: CustomDomain;
}

// "active" uses the project primary green for visual consistency with the
// rest of the white-label UI; the other states use semantic MUI palettes.
const STATE_TO_COLOR = {
  active: "primary",
  pending_dns: "warning",
  issuing: "info",
  failed: "error",
} as const;

const STATE_TO_KEY: Record<ReturnType<typeof describeOverallStatus>["state"], string> = {
  active: "white_label_status_active",
  pending_dns: "white_label_status_waiting_for_dns",
  issuing: "white_label_status_issuing",
  failed: "white_label_status_failed",
};

export function DomainStatusChip({ domain }: Props) {
  const { t } = useTranslation("common");
  const { state, label } = describeOverallStatus(domain);
  // The label string from describeOverallStatus differentiates DNS vs cert
  // failure; we keep it as the i18n fallback so that nuance survives even
  // when both states share the same color.
  const fallback = label;
  const key = STATE_TO_KEY[state];
  return <Chip size="small" color={STATE_TO_COLOR[state]} label={t(key, fallback)} />;
}
