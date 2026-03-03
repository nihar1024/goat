import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import { Box, Collapse, IconButton, Skeleton } from "@mui/material";
import { Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from "@mui/material";
import React, { useMemo, useState } from "react";

import type { DatasetCollectionItems } from "@/lib/validations/layer";

import NoValuesFound from "@/components/map/common/NoValuesFound";

const TWO_LINE_CLAMP_SX = {
  display: "-webkit-box",
  WebkitLineClamp: 2,
  WebkitBoxOrient: "vertical" as const,
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "normal",
  wordBreak: "break-word",
  lineHeight: 1.25,
  maxHeight: "2.5em",
};

const formatCellValue = (value: unknown): string => {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
};

const Row = ({ row, fields }) => {
  const [open, setOpen] = useState(false);

  const primitiveFields = useMemo(() => fields.filter((field) => field.type !== "object"), [fields]);

  const objectFields = useMemo(() => fields.filter((field) => field.type === "object"), [fields]);

  return (
    <>
      <TableRow key={row.id}>
        {objectFields.length > 0 && (
          <TableCell>
            <IconButton aria-label="expand row" size="small" onClick={() => setOpen(!open)}>
              {open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
            </IconButton>
          </TableCell>
        )}
        {primitiveFields.map((field, fieldIndex) => (
          <TableCell key={fieldIndex}>
            <Typography variant="body2" sx={TWO_LINE_CLAMP_SX}>
              {formatCellValue(row.properties[field.name])}
            </Typography>
          </TableCell>
        ))}
      </TableRow>

      {!!objectFields.length && (
        <TableRow>
          <TableCell style={{ paddingBottom: 0, paddingTop: 0 }} colSpan={primitiveFields.length + 1}>
            <Collapse in={open} timeout="auto" unmountOnExit>
              <Box sx={{ margin: 2 }}>
                {objectFields.map((field) => {
                  const rawValue = row.properties[field.name];
                  let jsonData = rawValue;
                  if (typeof rawValue === "string") {
                    try {
                      jsonData = JSON.parse(rawValue);
                    } catch {
                      // Not valid JSON, keep as-is
                    }
                  }
                  const isJsonDataArrayOfObjects =
                    Array.isArray(jsonData) &&
                    jsonData.length > 0 &&
                    typeof jsonData[0] === "object" &&
                    !Array.isArray(jsonData[0]);

                  return (
                    <React.Fragment key={field.name}>
                      <Stack direction="column" spacing={1} sx={{ py: 1, pl: 4 }}>
                        <Typography variant="body2" fontWeight="bold">
                          {field.name}
                        </Typography>
                      </Stack>
                      {isJsonDataArrayOfObjects ? (
                        <Table size="small" aria-label="purchases" key={field.name}>
                          <TableHead>
                            <TableRow>
                              {Object.keys(jsonData[0]).map((key) => (
                                <TableCell key={key}>{key}</TableCell>
                              ))}
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {jsonData.map((item, rowIndex) => (
                              <TableRow key={rowIndex}>
                                {Object.values(item).map((value: string, cellIndex) => (
                                  <TableCell key={cellIndex}>{formatCellValue(value)}</TableCell>
                                ))}
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      ) : (
                        <Typography>{JSON.stringify(jsonData, null, 2)}</Typography>
                      )}
                    </React.Fragment>
                  );
                })}
              </Box>
            </Collapse>
          </TableCell>
        </TableRow>
      )}
    </>
  );
};

interface WidgetRecordsTableProps {
  areFieldsLoading: boolean;
  displayData?: DatasetCollectionItems;
  fields: Array<{ name: string; type: string }>;
  headerLabelMap?: Record<string, string>;
  getColumnWidth?: (columnName: string) => number | undefined;
  renderHeaderLabel?: (columnName: string, label: string) => React.ReactNode;
  onHeaderResizeStart?: (event: React.MouseEvent, columnName: string) => void;
}

const WidgetRecordsTable: React.FC<WidgetRecordsTableProps> = ({
  areFieldsLoading,
  displayData,
  fields,
  headerLabelMap,
  getColumnWidth,
  renderHeaderLabel,
  onHeaderResizeStart,
}) => {
  const primitiveFields = useMemo(() => fields.filter((field) => field.type !== "object"), [fields]);

  return (
    <>
      {areFieldsLoading && !displayData && (
        <>
          <Skeleton variant="rectangular" height={60} sx={{ m: 4 }} />
          <Skeleton variant="rectangular" height={240} sx={{ m: 4 }} />
        </>
      )}

      {!areFieldsLoading && displayData && (
        <Table
          size="small"
          aria-label="simple table"
          stickyHeader
          sx={{
            tableLayout: "auto",
            width: "max-content",
            minWidth: "100%",
            "& .MuiTableCell-root": {
              verticalAlign: "top",
              borderRight: 1,
              borderColor: "divider",
            },
            "& .MuiTableRow-root > .MuiTableCell-root:last-of-type": {
              borderRight: 0,
            },
          }}>
          <TableHead>
            <TableRow>
              {fields.some((field) => field.type === "object") && <TableCell />}
              {primitiveFields.map((field) => {
                const label = headerLabelMap?.[field.name] || field.name;
                return (
                  <TableCell key={field.name} sx={{ width: getColumnWidth?.(field.name), maxWidth: 900, position: "relative" }}>
                    <Stack direction="column" spacing={1} sx={{ py: 1 }}>
                      {renderHeaderLabel ? (
                        renderHeaderLabel(field.name, label)
                      ) : (
                        <Typography variant="body2" fontWeight="bold" sx={TWO_LINE_CLAMP_SX}>
                          {label}
                        </Typography>
                      )}
                    </Stack>
                    {onHeaderResizeStart && (
                      <Box
                        sx={{
                          position: "absolute",
                          top: 0,
                          right: 0,
                          width: 12,
                          height: "100%",
                          cursor: "col-resize",
                          userSelect: "none",
                          zIndex: 2,
                        }}
                        onMouseDown={(event) => onHeaderResizeStart(event, field.name)}
                      />
                    )}
                  </TableCell>
                );
              })}
            </TableRow>
          </TableHead>
          <TableBody>
            {displayData.features.length === 0 && (
              <TableRow>
                <TableCell align="center" colSpan={fields.length} sx={{ borderBottom: "none" }}>
                  <NoValuesFound />
                </TableCell>
              </TableRow>
            )}
            {displayData.features?.length &&
              displayData.features.map((row, index) => <Row key={index} row={row} fields={fields} />)}
          </TableBody>
        </Table>
      )}
    </>
  );
};

export default WidgetRecordsTable;
