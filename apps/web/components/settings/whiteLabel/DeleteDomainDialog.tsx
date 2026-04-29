"use client";

import { LoadingButton } from "@mui/lab";
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Typography,
} from "@mui/material";
import { useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { toast } from "react-toastify";

import type { CustomDomain } from "@/lib/validations/customDomain";

interface DeleteDomainDialogProps {
  open: boolean;
  onClose: () => void;
  domain: CustomDomain | null;
  /** Pass a project name when the domain is currently assigned. Triggers the heavier copy. */
  assignedProjectName?: string;
  onConfirm: () => Promise<void>;
}

export function DeleteDomainDialog({
  open,
  onClose,
  domain,
  assignedProjectName,
  onConfirm,
}: DeleteDomainDialogProps) {
  const { t } = useTranslation("common");
  const [isBusy, setIsBusy] = useState(false);

  const isAssigned = Boolean(assignedProjectName);

  const handleConfirm = async () => {
    setIsBusy(true);
    try {
      await onConfirm();
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : t("white_label_delete_failed", "Failed to delete domain");
      toast.error(message);
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{t("white_label_delete_title", "Delete custom domain")}</DialogTitle>
      <DialogContent>
        {domain && (
          <Box sx={{ pt: 1 }}>
            <Typography variant="body2" sx={{ mb: 2 }}>
              <Trans
                i18nKey="white_label_delete_identify"
                defaults="You are about to delete <b>{{domain}}</b>."
                values={{ domain: domain.base_domain }}
                components={{ b: <b /> }}
              />
            </Typography>

            {isAssigned ? (
              <>
                <Alert severity="warning" sx={{ mb: 2 }}>
                  <Trans
                    i18nKey="white_label_delete_assigned_warning"
                    defaults="This domain is currently assigned to <b>{{project}}</b>. Deleting it will immediately stop serving the dashboard at this URL."
                    values={{ project: assignedProjectName ?? "" }}
                    components={{ b: <b /> }}
                  />
                </Alert>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  {t(
                    "white_label_delete_consequences_intro",
                    "This action will:"
                  )}
                </Typography>
                <Box component="ul" sx={{ pl: 3, m: 0 }}>
                  <li>
                    <Typography variant="body2" color="text.secondary">
                      {t(
                        "white_label_delete_consequence_unassign",
                        "Unassign the domain from the project"
                      )}
                    </Typography>
                  </li>
                  <li>
                    <Typography variant="body2" color="text.secondary">
                      {t(
                        "white_label_delete_consequence_cert",
                        "Remove the SSL certificate"
                      )}
                    </Typography>
                  </li>
                  <li>
                    <Typography variant="body2" color="text.secondary">
                      {t(
                        "white_label_delete_consequence_serve",
                        "Stop serving the dashboard at this URL"
                      )}
                    </Typography>
                  </li>
                </Box>
              </>
            ) : (
              <Typography variant="body2" color="text.secondary">
                {t(
                  "white_label_delete_unassigned_description",
                  "This domain is not assigned to any project. Removing it will free the certificate slot."
                )}
              </Typography>
            )}
          </Box>
        )}
      </DialogContent>
      <DialogActions disableSpacing sx={{ pb: 2 }}>
        <Button onClick={onClose} variant="text" disabled={isBusy}>
          <Typography variant="body2" fontWeight="bold">
            {t("cancel")}
          </Typography>
        </Button>
        <LoadingButton
          variant="contained"
          color="error"
          loading={isBusy}
          onClick={handleConfirm}>
          <Typography variant="body2" fontWeight="bold" color="inherit">
            {isAssigned
              ? t("white_label_delete_confirm_assigned", "Delete domain")
              : t("white_label_delete_confirm_unassigned", "Delete")}
          </Typography>
        </LoadingButton>
      </DialogActions>
    </Dialog>
  );
}
