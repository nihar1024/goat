"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { LoadingButton } from "@mui/lab";
import { Button, Stack, TextField, Typography } from "@mui/material";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { customDomainCreateSchema } from "@/lib/validations/customDomain";
import type { CustomDomainCreate } from "@/lib/validations/customDomain";

interface StepEnterProps {
  isBusy: boolean;
  onCancel: () => void;
  onSubmit: (data: CustomDomainCreate) => void;
}

export function StepEnter({ isBusy, onCancel, onSubmit }: StepEnterProps) {
  const { t } = useTranslation("common");
  const {
    register,
    handleSubmit,
    formState: { errors, isValid },
  } = useForm<CustomDomainCreate>({
    mode: "onChange",
    resolver: zodResolver(customDomainCreateSchema),
    defaultValues: { base_domain: "" },
  });

  return (
    <Stack component="form" spacing={3} onSubmit={handleSubmit(onSubmit)}>
      <Typography variant="body2" color="text.secondary">
        {t(
          "white_label_add_domain_enter_description",
          "Enter the subdomain you want to point at your dashboard."
        )}
      </Typography>
      <TextField
        autoFocus
        fullWidth
        label={t("white_label_add_domain_domain_name", "Domain name")}
        placeholder="dashboards.example.com"
        {...register("base_domain")}
        error={!!errors.base_domain}
        helperText={errors.base_domain?.message}
      />
      <Stack direction="row" spacing={1} justifyContent="flex-end">
        <Button onClick={onCancel} variant="text">
          <Typography variant="body2" fontWeight="bold">
            {t("cancel")}
          </Typography>
        </Button>
        <LoadingButton
          variant="contained"
          loading={isBusy}
          disabled={!isValid}
          type="submit">
          <Typography variant="body2" fontWeight="bold" color="inherit">
            {t("white_label_add_domain_continue", "Continue")}
          </Typography>
        </LoadingButton>
      </Stack>
    </Stack>
  );
}
