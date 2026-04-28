"use client";

import { Dialog, DialogContent, DialogTitle } from "@mui/material";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";

import { createCustomDomain, useOrganizationDomain } from "@/lib/api/customDomains";
import type { CustomDomain, CustomDomainCreate } from "@/lib/validations/customDomain";

import { StepCertIssuing } from "./StepCertIssuing";
import { StepConfigureDns } from "./StepConfigureDns";
import { StepEnter } from "./StepEnter";

type Step = "enter" | "configure_dns" | "cert_issuing";

interface AddDomainDialogProps {
  open: boolean;
  onClose: () => void;
  organizationId: string;
  /** Called after the dialog creates a domain so the parent can mutate its list. */
  onCreated?: () => void;
}

export function AddDomainDialog({
  open,
  onClose,
  organizationId,
  onCreated,
}: AddDomainDialogProps) {
  const { t } = useTranslation("common");
  const [step, setStep] = useState<Step>("enter");
  const [createdDomain, setCreatedDomain] = useState<CustomDomain | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  // Poll the single-domain endpoint while the user is configuring DNS or
  // waiting on the cert. SWR ignores `null` keys, so we just gate on the
  // domain id (passing undefined when not needed).
  const shouldPoll = open && createdDomain !== null && step !== "enter";
  const { domain: polledDomain } = useOrganizationDomain(
    shouldPoll ? organizationId : undefined,
    shouldPoll ? createdDomain?.id : undefined,
    { polling: true }
  );

  // Drive transitions off of the polled domain.
  useEffect(() => {
    if (!polledDomain) return;
    setCreatedDomain(polledDomain);
    if (step === "configure_dns" && polledDomain.dns_status === "verified") {
      setStep("cert_issuing");
    }
  }, [polledDomain, step]);

  const reset = () => {
    setStep("enter");
    setCreatedDomain(null);
    setIsBusy(false);
  };

  const handleClose = () => {
    onClose();
    // Defer state reset to avoid flashing step 1 during dialog close animation.
    window.setTimeout(reset, 200);
  };

  const handleSubmit = async (data: CustomDomainCreate) => {
    setIsBusy(true);
    try {
      const created = await createCustomDomain(organizationId, data.base_domain);
      setCreatedDomain(created);
      onCreated?.();
      // If the backend already has a verified DNS (rare; normally pending),
      // skip straight to the cert-issuing screen.
      if (created.dns_status === "verified") {
        setStep("cert_issuing");
      } else {
        setStep("configure_dns");
      }
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : t("white_label_add_domain_create_failed", "Failed to add domain");
      toast.error(message);
    } finally {
      setIsBusy(false);
    }
  };

  const title = (() => {
    switch (step) {
      case "enter":
        return t("white_label_add_domain_title", "Add custom domain");
      case "configure_dns":
        return t("white_label_add_domain_configure_dns", "Configure DNS");
      case "cert_issuing":
        return t("white_label_add_domain_dns_verified", "DNS verified");
    }
  })();

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="sm">
      <DialogTitle>{title}</DialogTitle>
      <DialogContent sx={{ pt: 2 }}>
        {step === "enter" && (
          <StepEnter isBusy={isBusy} onCancel={handleClose} onSubmit={handleSubmit} />
        )}
        {step === "configure_dns" && createdDomain && (
          <StepConfigureDns
            organizationId={organizationId}
            domain={createdDomain}
            onDone={handleClose}
            onRefresh={() => {
              // The polled SWR hook will tick on its next interval; nothing
              // to do here, but we expose the hook so child components can
              // signal intent if needed in the future.
            }}
          />
        )}
        {step === "cert_issuing" && <StepCertIssuing onClose={handleClose} />}
      </DialogContent>
    </Dialog>
  );
}
