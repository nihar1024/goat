"use client";

import {
  Box,
  Button,
  Link as MuiLink,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import dayjs from "dayjs";
import { useTranslation } from "react-i18next";

import { describeOverallStatus } from "@/lib/validations/customDomain";
import type { CustomDomain } from "@/lib/validations/customDomain";

import { DomainStatusChip } from "./DomainStatusChip";

interface DomainListProps {
  domains: CustomDomain[];
  /** Map of domain.id -> assigned project name. Domains absent from the map are treated as unassigned. */
  assignedProjectNames?: Record<string, string>;
  onOpenDetail: (domain: CustomDomain) => void;
  onRecheck: (domain: CustomDomain) => void;
  onDelete: (domain: CustomDomain) => void;
  onUnassign: (domain: CustomDomain) => void;
}

function formatAddedAt(iso: string): string {
  // dayjs default format gives a localized ISO-ish date (YYYY-MM-DD HH:mm).
  // We avoid the relativeTime plugin to keep the bundle lean — Phase 9C can
  // revisit if PMs ask for "X hours ago".
  return dayjs(iso).format("YYYY-MM-DD");
}

export function DomainList({
  domains,
  assignedProjectNames,
  onOpenDetail,
  onRecheck,
  onDelete,
  onUnassign,
}: DomainListProps) {
  const { t } = useTranslation("common");

  return (
    <TableContainer sx={{ border: 1, borderColor: "divider", borderRadius: 1 }}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell sx={{ fontWeight: 600 }}>{t("white_label_list_domain", "Domain")}</TableCell>
            <TableCell sx={{ fontWeight: 600 }}>{t("white_label_list_status", "Status")}</TableCell>
            <TableCell sx={{ fontWeight: 600 }}>
              {t("white_label_list_assigned_to", "Assigned to")}
            </TableCell>
            <TableCell sx={{ fontWeight: 600 }}>{t("white_label_list_added", "Added")}</TableCell>
            <TableCell align="right" sx={{ fontWeight: 600 }}>
              {t("white_label_list_actions", "Actions")}
            </TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {domains.map((domain) => {
            const { state } = describeOverallStatus(domain);
            const assignedName = assignedProjectNames?.[domain.id];
            const isAssigned = Boolean(assignedName);
            return (
              <TableRow key={domain.id} hover>
                <TableCell>
                  {state === "active" ? (
                    <Tooltip title={t("white_label_list_open_in_new_tab", "Open in new tab")}>
                      <MuiLink
                        href={`https://${domain.base_domain}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        underline="hover"
                        sx={{ fontFamily: "monospace", fontSize: "0.875rem" }}>
                        {domain.base_domain}
                      </MuiLink>
                    </Tooltip>
                  ) : (
                    <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
                      {domain.base_domain}
                    </Typography>
                  )}
                </TableCell>
                <TableCell>
                  <DomainStatusChip domain={domain} />
                </TableCell>
                <TableCell>
                  {isAssigned ? (
                    <Typography variant="body2">{assignedName}</Typography>
                  ) : (
                    <Typography variant="body2" fontStyle="italic" color="text.disabled">
                      {t("white_label_list_not_assigned", "Not assigned")}
                    </Typography>
                  )}
                </TableCell>
                <TableCell>
                  <Typography variant="body2" color="text.secondary">
                    {formatAddedAt(domain.created_at)}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Stack direction="row" spacing={1} justifyContent="flex-end">
                    {state === "issuing" && (
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => onOpenDetail(domain)}>
                        {t("white_label_list_action_details", "Details")}
                      </Button>
                    )}
                    {state === "pending_dns" && (
                      <>
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={() => onOpenDetail(domain)}>
                          {t("white_label_list_action_show_dns", "Show DNS")}
                        </Button>
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={() => onRecheck(domain)}>
                          {t("white_label_list_action_recheck", "Recheck")}
                        </Button>
                      </>
                    )}
                    {state === "failed" && (
                      <>
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={() => onOpenDetail(domain)}>
                          {t("white_label_list_action_details", "Details")}
                        </Button>
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={() => onRecheck(domain)}>
                          {t("white_label_list_action_retry", "Retry")}
                        </Button>
                      </>
                    )}
                    {state === "active" && isAssigned && (
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => onUnassign(domain)}>
                        {t("white_label_list_action_unassign", "Unassign")}
                      </Button>
                    )}
                    <Button
                      size="small"
                      variant="outlined"
                      color="error"
                      onClick={() => onDelete(domain)}>
                      {t("white_label_list_action_delete", "Delete")}
                    </Button>
                  </Stack>
                </TableCell>
              </TableRow>
            );
          })}
          {domains.length === 0 && (
            <TableRow>
              <TableCell colSpan={5}>
                <Box sx={{ py: 4, textAlign: "center" }}>
                  <Typography variant="body2" color="text.secondary">
                    {t("white_label_list_empty", "No custom domains yet.")}
                  </Typography>
                </Box>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
