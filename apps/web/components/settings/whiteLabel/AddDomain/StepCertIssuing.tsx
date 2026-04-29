"use client";

import { Alert, Button, Stack, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";

interface StepCertIssuingProps {
  onClose: () => void;
}

export function StepCertIssuing({ onClose }: StepCertIssuingProps) {
  const { t } = useTranslation("common");
  return (
    <Stack spacing={3}>
      <Alert severity="success" variant="outlined">
        <Typography variant="body2">
          {t(
            "white_label_add_domain_cert_issuing",
            "DNS verified. Issuing SSL certificate from Let's Encrypt — usually under 2 minutes."
          )}
        </Typography>
      </Alert>
      <Stack direction="row" justifyContent="flex-end">
        <Button variant="contained" onClick={onClose}>
          <Typography variant="body2" fontWeight="bold" color="inherit">
            {t("close", "Close")}
          </Typography>
        </Button>
      </Stack>
    </Stack>
  );
}
