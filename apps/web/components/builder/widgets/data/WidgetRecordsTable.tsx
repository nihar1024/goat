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
  stickyHeaderEnabled?: boolean;
  headerLabelMap?: Record<string, string>;
  getColumnWidth?: (columnName: string) => number | undefined;
  renderHeaderLabel?: (columnName: string, label: string, align?: "left" | "right") => React.ReactNode;
  onHeaderResizeStart?: (event: React.MouseEvent, columnName: string) => void;
  tableColumns?: Array<{ key: string; label: string; align?: "left" | "right" }>;
  tableRows?: Array<Record<string, unknown>>;
  totalsRow?: Record<string, unknown>;
  emptyMessage?: React.ReactNode;
  formatCellValueForColumn?: (columnKey: string, value: unknown) => React.ReactNode;
  onReorderColumns?: (fromColumnKey: string, toColumnKey: string) => void;
}

const WidgetRecordsTable: React.FC<WidgetRecordsTableProps> = ({
  areFieldsLoading,
  displayData,
  fields,
  stickyHeaderEnabled = true,
  headerLabelMap,
  getColumnWidth,
  renderHeaderLabel,
  onHeaderResizeStart,
  tableColumns,
  tableRows,
  totalsRow,
  emptyMessage,
  formatCellValueForColumn,
  onReorderColumns,
}) => {
  const primitiveFields = useMemo(() => fields.filter((field) => field.type !== "object"), [fields]);
  const isGenericMode = Array.isArray(tableColumns) && Array.isArray(tableRows);
  const [draggedColumnKey, setDraggedColumnKey] = useState<string | null>(null);

  const getHeaderCellDropSx = (columnKey: string) => {
    if (!draggedColumnKey || draggedColumnKey === columnKey) return undefined;
    return {
      outline: "1px dashed",
      outlineColor: "primary.main",
    };
  };

  const stickyHeaderCellSx = stickyHeaderEnabled
    ? {
        "& .MuiTableCell-stickyHeader": {
          position: "sticky",
          top: 0,
          zIndex: 3,
          backgroundColor: "background.paper",
          boxShadow: "inset 0 -1px 0 rgba(0, 0, 0, 0.12)",
        },
      }
    : {
        "& .MuiTableCell-head": {
          position: "relative",
        },
      };

  return (
    <>
      {areFieldsLoading && !displayData && (
        <>
          <Skeleton variant="rectangular" height={60} sx={{ m: 4 }} />
          <Skeleton variant="rectangular" height={240} sx={{ m: 4 }} />
        </>
      )}

      {!areFieldsLoading && isGenericMode && (
        <Table
          size="small"
          stickyHeader={stickyHeaderEnabled}
          sx={{
            tableLayout: "fixed",
            width: "100%",
            "& .MuiTableCell-root": {
              verticalAlign: "top",
              borderRight: 1,
              borderColor: "divider",
            },
            "& .MuiTableRow-root > .MuiTableCell-root:last-of-type": {
              borderRight: 0,
            },
            ...stickyHeaderCellSx,
          }}>
          <TableHead>
            <TableRow>
              {tableColumns.map((column) => (
                <TableCell
                  key={column.key}
                  align={column.align || "left"}
                  draggable={Boolean(onReorderColumns)}
                  onDragStart={(event) => {
                    if (!onReorderColumns) return;
                    const target = event.target as HTMLElement;
                    if (target.closest("[data-resize-handle='true']")) {
                      event.preventDefault();
                      return;
                    }
                    setDraggedColumnKey(column.key);
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData("text/plain", column.key);
                  }}
                  onDragEnd={() => {
                    setDraggedColumnKey(null);
                  }}
                  onDragOver={(event) => {
                    if (!onReorderColumns) return;
                    event.preventDefault();
                    event.dataTransfer.dropEffect = "move";
                  }}
                  onDrop={(event) => {
                    if (!onReorderColumns) return;
                    event.preventDefault();
                    const fromColumnKey = draggedColumnKey || event.dataTransfer.getData("text/plain");
                    if (fromColumnKey && fromColumnKey !== column.key) {
                      onReorderColumns(fromColumnKey, column.key);
                    }
                    setDraggedColumnKey(null);
                  }}
                  sx={{
                    width: getColumnWidth?.(column.key),
                    maxWidth: 900,
                    position: "relative",
                    cursor: onReorderColumns ? "grab" : undefined,
                    ...getHeaderCellDropSx(column.key),
                  }}>
                  <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", pr: 1.5 }}>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      {renderHeaderLabel ? (
                        renderHeaderLabel(column.key, column.label, column.align || "left")
                      ) : (
                        <Typography
                          variant="body2"
                          fontWeight="bold"
                          align={column.align || "left"}
                          sx={TWO_LINE_CLAMP_SX}>
                          {column.label}
                        </Typography>
                      )}
                    </Box>
                  </Box>
                  {onHeaderResizeStart && (
                    <Box
                      data-resize-handle="true"
                      sx={{
                        position: "absolute",
                        top: 0,
                        right: -1,
                        width: 5,
                        height: "100%",
                        cursor: "col-resize",
                        userSelect: "none",
                        zIndex: 2,
                        backgroundColor: "transparent",
                        transition: "background-color 0.15s ease",
                        "&:hover": {
                          backgroundColor: "primary.main",
                        },
                      }}
                      onMouseDown={(event) => onHeaderResizeStart(event, column.key)}
                    />
                  )}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {tableRows.length === 0 && (
              <TableRow>
                <TableCell align="center" colSpan={Math.max(tableColumns.length, 1)}>
                  {emptyMessage || <NoValuesFound />}
                </TableCell>
              </TableRow>
            )}
            {tableRows.map((row, rowIndex) => (
              <TableRow key={`generic-row-${rowIndex}`}>
                {tableColumns.map((column) => (
                  <TableCell key={`${column.key}-${rowIndex}`} align={column.align || "left"} sx={{ width: getColumnWidth?.(column.key) }}>
                    <Typography variant="body2" sx={TWO_LINE_CLAMP_SX}>
                      {formatCellValueForColumn
                        ? formatCellValueForColumn(column.key, row[column.key])
                        : formatCellValue(row[column.key]) || "-"}
                    </Typography>
                  </TableCell>
                ))}
              </TableRow>
            ))}
            {totalsRow && (
              <TableRow
                sx={{
                  "& .MuiTableCell-root": {
                    fontWeight: 700,
                    backgroundColor: "background.paper",
                    borderTop: 1,
                    borderColor: "divider",
                  },
                }}>
                {tableColumns.map((column) => (
                  <TableCell key={`generic-total-${column.key}`} align={column.align || "left"} sx={{ width: getColumnWidth?.(column.key) }}>
                    <Typography variant="body2" fontWeight="bold">
                      {formatCellValueForColumn
                        ? formatCellValueForColumn(column.key, totalsRow[column.key])
                        : formatCellValue(totalsRow[column.key]) || "-"}
                    </Typography>
                  </TableCell>
                ))}
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}

      {!areFieldsLoading && !isGenericMode && displayData && (
        <Table
          size="small"
          aria-label="simple table"
          stickyHeader={stickyHeaderEnabled}
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
            ...stickyHeaderCellSx,
          }}>
          <TableHead>
            <TableRow>
              {fields.some((field) => field.type === "object") && <TableCell />}
              {primitiveFields.map((field) => {
                const label = headerLabelMap?.[field.name] || field.name;
                return (
                  <TableCell
                    key={field.name}
                    draggable={Boolean(onReorderColumns)}
                    onDragStart={(event) => {
                      if (!onReorderColumns) return;
                      const target = event.target as HTMLElement;
                      if (target.closest("[data-resize-handle='true']")) {
                        event.preventDefault();
                        return;
                      }
                      setDraggedColumnKey(field.name);
                      event.dataTransfer.effectAllowed = "move";
                      event.dataTransfer.setData("text/plain", field.name);
                    }}
                    onDragEnd={() => {
                      setDraggedColumnKey(null);
                    }}
                    onDragOver={(event) => {
                      if (!onReorderColumns) return;
                      event.preventDefault();
                      event.dataTransfer.dropEffect = "move";
                    }}
                    onDrop={(event) => {
                      if (!onReorderColumns) return;
                      event.preventDefault();
                      const fromColumnKey = draggedColumnKey || event.dataTransfer.getData("text/plain");
                      if (fromColumnKey && fromColumnKey !== field.name) {
                        onReorderColumns(fromColumnKey, field.name);
                      }
                      setDraggedColumnKey(null);
                    }}
                    sx={{
                      width: getColumnWidth?.(field.name),
                      maxWidth: 900,
                      position: "relative",
                      cursor: onReorderColumns ? "grab" : undefined,
                      ...getHeaderCellDropSx(field.name),
                    }}>
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        py: 1,
                        pr: 1.5,
                      }}>
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        {renderHeaderLabel ? (
                          renderHeaderLabel(field.name, label, "left")
                        ) : (
                          <Typography variant="body2" fontWeight="bold" sx={TWO_LINE_CLAMP_SX}>
                            {label}
                          </Typography>
                        )}
                      </Box>
                    </Box>
                    {onHeaderResizeStart && (
                      <Box
                        data-resize-handle="true"
                        sx={{
                          position: "absolute",
                          top: 0,
                          right: -1,
                          width: 5,
                          height: "100%",
                          cursor: "col-resize",
                          userSelect: "none",
                          zIndex: 2,
                          backgroundColor: "transparent",
                          transition: "background-color 0.15s ease",
                          "&:hover": {
                            backgroundColor: "primary.main",
                          },
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
