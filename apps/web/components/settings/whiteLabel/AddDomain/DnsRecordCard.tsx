"use client";

import {
  Box,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

// TODO: source from a backend config endpoint instead of hardcoding here.
// (See spec section 15 — "Hetzner LB stable target" open question.)
//
// `cname.goat.plan4better.de` is a CNAME we maintain in the
// plan4better.de zone, pointing at the Caddy LB's actual hostname.
// This indirection means the underlying LB can change without
// breaking customer DNS records.
export const CNAME_TARGET = "cname.goat.plan4better.de";

interface DnsRecordCardProps {
  /** The hostname the user is configuring (e.g. "dashboards.example.com"). */
  domain: string;
}

interface CopyableCellProps {
  value: string;
}

function CopyableCell({ value }: CopyableCellProps) {
  const { t } = useTranslation("common");
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // navigator.clipboard can fail in non-secure contexts; we just no-op.
    }
  };

  return (
    <Stack direction="row" alignItems="center" spacing={1}>
      <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
        {value}
      </Typography>
      <Tooltip
        title={
          copied
            ? t("white_label_dns_copied", "Copied")
            : t("white_label_dns_copy", "Copy")
        }>
        <IconButton size="small" onClick={handleCopy} aria-label="copy">
          <Icon iconName={ICON_NAME.COPY} fontSize="small" />
        </IconButton>
      </Tooltip>
    </Stack>
  );
}

export function DnsRecordCard({ domain }: DnsRecordCardProps) {
  const { t } = useTranslation("common");
  // The CNAME host is the leftmost label of the FQDN — DNS providers want
  // the relative name, not the absolute one.
  const host = domain.split(".")[0] || domain;

  return (
    <Box
      sx={{
        border: 1,
        borderColor: "divider",
        borderRadius: 1,
        overflow: "hidden",
      }}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell sx={{ fontWeight: 600 }}>
              {t("white_label_dns_type", "Type")}
            </TableCell>
            <TableCell sx={{ fontWeight: 600 }}>
              {t("white_label_dns_host", "Host")}
            </TableCell>
            <TableCell sx={{ fontWeight: 600 }}>
              {t("white_label_dns_target", "Target")}
            </TableCell>
            <TableCell sx={{ fontWeight: 600 }}>
              {t("white_label_dns_ttl", "TTL")}
            </TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          <TableRow>
            <TableCell>
              <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
                CNAME
              </Typography>
            </TableCell>
            <TableCell>
              <CopyableCell value={host} />
            </TableCell>
            <TableCell>
              <CopyableCell value={CNAME_TARGET} />
            </TableCell>
            <TableCell>
              <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
                3600
              </Typography>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </Box>
  );
}
