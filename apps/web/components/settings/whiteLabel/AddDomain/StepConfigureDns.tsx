"use client";

import { LoadingButton } from "@mui/lab";
import { Alert, Button, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";

import { recheckCustomDomain } from "@/lib/api/customDomains";
import type { CustomDomain } from "@/lib/validations/customDomain";

import { DnsRecordCard } from "./DnsRecordCard";

interface StepConfigureDnsProps {
  organizationId: string;
  domain: CustomDomain;
  onDone: () => void;
  onRefresh: () => void;
}

export function StepConfigureDns({
  organizationId,
  domain,
  onDone,
  onRefresh,
}: StepConfigureDnsProps) {
  const { t } = useTranslation("common");
  const [isRechecking, setIsRechecking] = useState(false);

  const handleRecheck = async () => {
    setIsRechecking(true);
    try {
      await recheckCustomDomain(organizationId, domain.id);
      onRefresh();
    } catch {
      toast.error(t("white_label_add_domain_recheck_failed", "Failed to recheck DNS"));
    } finally {
      setIsRechecking(false);
    }
  };

  return (
    <Stack spacing={3}>
      <Typography variant="body2" color="text.secondary">
        {t(
          "white_label_add_domain_configure_description",
          "Add this CNAME record at your DNS provider. We'll automatically detect it once it propagates."
        )}
      </Typography>
      <DnsRecordCard domain={domain.base_domain} />
      <Alert severity="warning" variant="outlined">
        {t(
          "white_label_add_domain_checking_status",
          "Checking DNS every 30 seconds. This can take a few minutes after you update your records."
        )}
      </Alert>
      {domain.dns_status_message && (
        <Typography variant="caption" color="text.secondary">
          {domain.dns_status_message}
        </Typography>
      )}
      <Stack direction="row" spacing={1} justifyContent="flex-end">
        <LoadingButton
          variant="text"
          loading={isRechecking}
          onClick={handleRecheck}>
          <Typography variant="body2" fontWeight="bold">
            {t("white_label_add_domain_recheck_now", "Recheck now")}
          </Typography>
        </LoadingButton>
        <Button variant="contained" onClick={onDone}>
          <Typography variant="body2" fontWeight="bold" color="inherit">
            {t("done", "Done")}
          </Typography>
        </Button>
      </Stack>
    </Stack>
  );
}
