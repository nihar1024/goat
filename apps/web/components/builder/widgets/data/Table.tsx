import { Box, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography } from "@mui/material";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { previewSql } from "@/lib/api/expressions";
import { apiRequestAuth } from "@/lib/api/fetcher";
import { useDatasetCollectionItems } from "@/lib/api/layers";
import { PROCESSES_API_BASE_URL } from "@/lib/api/processes";
import { formatNumber } from "@/lib/utils/format-number";
import type { DatasetCollectionItems, GetCollectionItemsQueryParams } from "@/lib/validations/layer";
import type { AggregationStatsQueryParams, ProjectLayer } from "@/lib/validations/project";
import { aggregationStatsQueryParams } from "@/lib/validations/project";
import { tableDataConfigSchema, tableModeTypes, tableQueryModeTypes, type TableDataSchema } from "@/lib/validations/widget";

import useLayerFields from "@/hooks/map/CommonHooks";
import { useChartWidget } from "@/hooks/map/DashboardBuilderHooks";

import DatasetTable from "@/components/common/DatasetTable";
import { WidgetStatusContainer } from "@/components/builder/widgets/common/WidgetStatusContainer";

interface TableDataWidgetProps {
  widgetId: string;
  config: TableDataSchema;
  projectLayers: ProjectLayer[];
  viewOnly?: boolean;
  onConfigChange?: (nextConfig: TableDataSchema) => void;
}

type GroupedMetricConfig = {
  operation_type: string;
  operation_value?: string;
  label?: string;
};

type GroupedRow = {
  grouped_value: string;
  metrics: number[];
};

export const TableDataWidget = ({
  widgetId,
  config: rawConfig,
  projectLayers,
  viewOnly,
  onConfigChange,
}: TableDataWidgetProps) => {
  const { t, i18n } = useTranslation("common");
  const { config, queryParams, layerId } = useChartWidget(rawConfig, tableDataConfigSchema, aggregationStatsQueryParams);
  const rowsShownSetting = Math.max(1, Math.min(20, Number(config?.options?.page_size ?? 10)));

  const queryMode = config?.setup?.query_mode ?? tableQueryModeTypes.Values.builder;
  const isSqlMode = queryMode === tableQueryModeTypes.Values.sql;
  const mode = config?.setup?.mode ?? tableModeTypes.Values.records;
  const isGroupedMode = mode === tableModeTypes.Values.grouped;

  const [recordsPage, setRecordsPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(rowsShownSetting);
  const [recordsAccumulatedData, setRecordsAccumulatedData] = useState<DatasetCollectionItems | undefined>(undefined);
  const [recordsHasMore, setRecordsHasMore] = useState(true);
  const [groupedVisibleCount, setGroupedVisibleCount] = useState(rowsShownSetting);
  const [groupedRows, setGroupedRows] = useState<GroupedRow[]>([]);
  const [isGroupedLoading, setIsGroupedLoading] = useState(false);
  const [groupedError, setGroupedError] = useState<string | null>(null);
  const [sqlRows, setSqlRows] = useState<Array<Record<string, unknown>>>([]);
  const [sqlColumns, setSqlColumns] = useState<Array<{ name: string; type: string }>>([]);
  const [sqlPage, setSqlPage] = useState(0);
  const [sqlHasMore, setSqlHasMore] = useState(true);
  const [isSqlLoading, setIsSqlLoading] = useState(false);
  const [sqlError, setSqlError] = useState<string | null>(null);
  const [groupedColumnWidths, setGroupedColumnWidths] = useState<Record<string, number>>({});
  const [sqlColumnWidths, setSqlColumnWidths] = useState<Record<string, number>>({});
  const [areWidthsHydrated, setAreWidthsHydrated] = useState(false);
  const [editingHeaderKey, setEditingHeaderKey] = useState<string | null>(null);
  const [editingHeaderValue, setEditingHeaderValue] = useState("");
  const activeResizeRef = useRef<{
    tableType: "grouped" | "sql";
    columnKey: string;
    startX: number;
    startWidth: number;
  } | null>(null);

  const twoLineClampSx = {
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

  useEffect(() => {
    setRowsPerPage(rowsShownSetting);
  }, [rowsShownSetting]);

  useEffect(() => {
    setGroupedVisibleCount(rowsShownSetting);
  }, [rowsShownSetting]);

  const selectedLayer = useMemo(() => {
    return projectLayers.find((layer) => layer.id === config?.setup?.layer_project_id);
  }, [projectLayers, config?.setup?.layer_project_id]);

  const recordsLayerId = selectedLayer?.layer_id;

  const tableMetrics = useMemo(() => {
    if (!isGroupedMode || isSqlMode) return [] as GroupedMetricConfig[];

    const metrics: GroupedMetricConfig[] = [];

    if (config?.setup?.operation_type) {
      metrics.push({
        operation_type: config.setup.operation_type,
        operation_value: config.setup.operation_value,
      });
    }

    const additionalMetrics = (config?.setup?.additional_metrics || []).filter((metric) => metric.operation_type);
    additionalMetrics.forEach((metric) => {
      metrics.push({
        operation_type: metric.operation_type,
        operation_value: metric.operation_value,
        label: metric.label,
      });
    });

    return metrics;
  }, [config?.setup?.additional_metrics, config?.setup?.operation_type, config?.setup?.operation_value, isGroupedMode, isSqlMode]);

  const groupedMetricLabels = useMemo(() => {
    return tableMetrics.map((metric, index) => {
      if (index === 0) {
        if (config?.setup?.primary_metric_label) return config.setup.primary_metric_label;
        const operationValue = config?.setup?.operation_value;
        if (operationValue) return operationValue;
        const operationType = config?.setup?.operation_type;
        if (!operationType) return t("value", { defaultValue: "Value" });
        if (operationType === "expression") return t("expression", { defaultValue: "Expression" });
        return operationType.toUpperCase();
      }
      if (metric.label) return metric.label;
      if (metric.operation_value) return metric.operation_value;
      if (metric.operation_type === "expression") return t("expression", { defaultValue: "Expression" });
      return metric.operation_type.toUpperCase();
    });
  }, [config?.setup?.operation_type, config?.setup?.operation_value, config?.setup?.primary_metric_label, t, tableMetrics]);

  const { layerFields, isLoading: areFieldsLoading } = useLayerFields(recordsLayerId || "");

  const visibleFields = useMemo(() => {
    if (!config?.setup?.visible_columns?.length) return layerFields;
    const visibleFieldSet = new Set(config.setup.visible_columns);
    return layerFields.filter((field) => visibleFieldSet.has(field.name));
  }, [layerFields, config?.setup?.visible_columns]);

  const recordsQueryParams = useMemo(() => {
    if (!recordsLayerId || isGroupedMode || isSqlMode) return undefined;

    const params: GetCollectionItemsQueryParams = {
      limit: rowsPerPage,
      offset: recordsPage * rowsPerPage,
    };

    const defaultSortField = config?.options?.sort_by || visibleFields[0]?.name || layerFields[0]?.name;

    if (defaultSortField) {
      const sortDirectionPrefix = config?.options?.sorting === "desc" ? "-" : "";
      params.sortby = `${sortDirectionPrefix}${defaultSortField}`;
    }

    return params;
  }, [
    recordsLayerId,
    isGroupedMode,
    isSqlMode,
    rowsPerPage,
    recordsPage,
    config?.options?.sort_by,
    config?.options?.sorting,
    visibleFields,
    layerFields,
  ]);

  const {
    data: recordsData,
    isLoading: isRecordsLoading,
    isError: isRecordsError,
  } = useDatasetCollectionItems(recordsLayerId || "", recordsQueryParams);

  const recordsQuerySignature = useMemo(() => {
    const sortBy = config?.options?.sort_by || "";
    const sorting = config?.options?.sorting || "desc";
    return `${recordsLayerId || ""}|${rowsPerPage}|${sortBy}|${sorting}|${isGroupedMode}|${isSqlMode}`;
  }, [config?.options?.sort_by, config?.options?.sorting, isGroupedMode, isSqlMode, recordsLayerId, rowsPerPage]);

  useEffect(() => {
    setRecordsPage(0);
    setRecordsAccumulatedData(undefined);
    setRecordsHasMore(true);
  }, [recordsQuerySignature]);

  useEffect(() => {
    if (!recordsData || isGroupedMode || isSqlMode) return;

    if (recordsPage === 0) {
      setRecordsAccumulatedData(recordsData);
      setRecordsHasMore(recordsData.features.length >= rowsPerPage);
      return;
    }

    setRecordsAccumulatedData((previous) => {
      if (!previous) return recordsData;
      return {
        ...recordsData,
        features: [...previous.features, ...recordsData.features],
        numberReturned: previous.features.length + recordsData.features.length,
      };
    });
    setRecordsHasMore(recordsData.features.length >= rowsPerPage);
  }, [isGroupedMode, isSqlMode, recordsData, recordsPage]);

  useEffect(() => {
    let isCancelled = false;

    async function loadGroupedRows() {
      if (!isGroupedMode || isSqlMode || !layerId || tableMetrics.length === 0) {
        if (!isCancelled) {
          setGroupedRows([]);
          setGroupedError(null);
          setIsGroupedLoading(false);
        }
        return;
      }

      setIsGroupedLoading(true);
      setGroupedError(null);

      try {
        const aggregationQuery = queryParams as AggregationStatsQueryParams | undefined;
        const size = config?.options?.size ?? aggregationQuery?.size ?? 50;
        const order = config?.options?.sorting === "asc" ? "ascendent" : "descendent";
        const filter = aggregationQuery?.query;
        const groupByColumn = config?.setup?.group_by_column_name || aggregationQuery?.group_by_column_name;

        const responses = await Promise.all(
          tableMetrics.map(async (metric) => {
            const inputs: Record<string, unknown> = {
              collection: layerId,
              operation: metric.operation_type,
              operation_column: metric.operation_value,
              group_by_column: groupByColumn,
              limit: size,
              order,
              filter,
            };

            if (!metric.operation_value) {
              delete inputs.operation_column;
            }

            const response = await apiRequestAuth(`${PROCESSES_API_BASE_URL}/aggregation-stats/execution`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ inputs }),
            });

            if (!response.ok) {
              const error = await response.json();
              throw new Error(error.detail?.detail || error.detail || "Failed to get aggregation stats");
            }

            const result = await response.json();
            return (result.items || []) as Array<{ grouped_value: string; operation_value: number }>;
          })
        );

        if (isCancelled) return;

        const groupedMap = new Map<string, number[]>();

        responses.forEach((items, metricIndex) => {
          items.forEach((item) => {
            const groupedValue = String(item.grouped_value ?? "-");
            if (!groupedMap.has(groupedValue)) {
              groupedMap.set(groupedValue, new Array(tableMetrics.length).fill(0));
            }
            const values = groupedMap.get(groupedValue)!;
            values[metricIndex] = item.operation_value ?? 0;
          });
        });

        setGroupedRows(Array.from(groupedMap.entries()).map(([grouped_value, metrics]) => ({ grouped_value, metrics })));
      } catch (error) {
        if (!isCancelled) {
          setGroupedRows([]);
          setGroupedError(error instanceof Error ? error.message : "Failed to load grouped table data");
        }
      } finally {
        if (!isCancelled) {
          setIsGroupedLoading(false);
        }
      }
    }

    void loadGroupedRows();

    return () => {
      isCancelled = true;
    };
  }, [
    config?.options?.size,
    config?.options?.sorting,
    config?.setup?.group_by_column_name,
    isGroupedMode,
    isSqlMode,
    layerId,
    queryParams,
    tableMetrics,
  ]);

  useEffect(() => {
    let isCancelled = false;

    async function loadSqlPreview() {
      if (!isSqlMode || !recordsLayerId || !config?.setup?.sql_query) {
        if (!isCancelled) {
          setSqlPage(0);
          setSqlHasMore(true);
          setSqlRows([]);
          setSqlColumns([]);
          setSqlError(null);
          setIsSqlLoading(false);
        }
        return;
      }

      setIsSqlLoading(true);
      setSqlError(null);

      try {
        const sqlAlias = "input_1";
        const pageOffset = sqlPage * rowsPerPage;
        const result = await previewSql({
          sql_query: config.setup.sql_query,
          layers: { [sqlAlias]: recordsLayerId },
          limit: rowsPerPage,
          offset: pageOffset,
        });

        if (isCancelled) return;

        setSqlColumns((previous) => (sqlPage === 0 ? result.columns || [] : previous));

        const incomingRows = (result.rows || []).map((row) => row.values || {});
        setSqlRows((previous) => (sqlPage === 0 ? incomingRows : [...previous, ...incomingRows]));

        if (typeof result.total_count === "number" && Number.isFinite(result.total_count)) {
          const loadedCount = pageOffset + incomingRows.length;
          setSqlHasMore(loadedCount < result.total_count);
        } else {
          setSqlHasMore(incomingRows.length >= rowsPerPage);
        }
      } catch (error) {
        if (!isCancelled) {
          setSqlRows([]);
          setSqlColumns([]);
          setSqlHasMore(false);
          setSqlError(error instanceof Error ? error.message : "Failed to preview SQL");
        }
      } finally {
        if (!isCancelled) {
          setIsSqlLoading(false);
        }
      }
    }

    void loadSqlPreview();

    return () => {
      isCancelled = true;
    };
  }, [
    config?.setup?.sql_query,
    isSqlMode,
    recordsLayerId,
    rowsPerPage,
    sqlPage,
  ]);

  const sqlQuerySignature = useMemo(() => {
    return `${recordsLayerId || ""}|${config?.setup?.sql_query || ""}|${rowsPerPage}|${isSqlMode}`;
  }, [config?.setup?.sql_query, isSqlMode, recordsLayerId, rowsPerPage]);

  useEffect(() => {
    setSqlPage(0);
    setSqlHasMore(true);
    setSqlRows([]);
  }, [sqlQuerySignature]);

  const startColumnResize = useCallback(
    (event: React.MouseEvent, tableType: "grouped" | "sql", columnKey: string) => {
      event.preventDefault();
      event.stopPropagation();

      const widthMap = tableType === "grouped" ? groupedColumnWidths : sqlColumnWidths;
      const currentRenderedWidth = (event.currentTarget.parentElement as HTMLElement | null)?.getBoundingClientRect().width;
      activeResizeRef.current = {
        tableType,
        columnKey,
        startX: event.clientX,
        startWidth: widthMap[columnKey] ?? currentRenderedWidth ?? 140,
      };
    },
    [groupedColumnWidths, sqlColumnWidths]
  );

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      const activeResize = activeResizeRef.current;
      if (!activeResize) return;

      const nextWidth = Math.max(0, Math.min(900, activeResize.startWidth + (event.clientX - activeResize.startX)));
      if (activeResize.tableType === "grouped") {
        setGroupedColumnWidths((previous) => ({
          ...previous,
          [activeResize.columnKey]: nextWidth,
        }));
      } else {
        setSqlColumnWidths((previous) => ({
          ...previous,
          [activeResize.columnKey]: nextWidth,
        }));
      }
    };

    const handleMouseUp = () => {
      activeResizeRef.current = null;
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  const sortedGroupedRows = useMemo(() => {
    const items = groupedRows;
    const sortByRaw = config?.options?.sort_by;
    const sortBy = sortByRaw === "grouped_value" ? "grouped_value" : sortByRaw || "metric_0";
    const sorting = config?.options?.sorting ?? "desc";

    return [...items].sort((left, right) => {
      const direction = sorting === "asc" ? 1 : -1;
      if (sortBy === "grouped_value") {
        return (
          String(left.grouped_value).localeCompare(String(right.grouped_value), i18n.language, {
            numeric: true,
            sensitivity: "base",
          }) * direction
        );
      }
      const metricIndex = Number(sortBy.replace("metric_", ""));
      const leftMetric = left.metrics[Number.isNaN(metricIndex) ? 0 : metricIndex] ?? 0;
      const rightMetric = right.metrics[Number.isNaN(metricIndex) ? 0 : metricIndex] ?? 0;
      return (leftMetric - rightMetric) * direction;
    });
  }, [groupedRows, config?.options?.sort_by, config?.options?.sorting, i18n.language]);

  const topGroupedRows = useMemo(() => {
    const configuredSize = Number(config?.options?.size);
    if (!Number.isFinite(configuredSize) || configuredSize <= 0) return sortedGroupedRows;
    return sortedGroupedRows.slice(0, configuredSize);
  }, [config?.options?.size, sortedGroupedRows]);

  useEffect(() => {
    setGroupedVisibleCount(rowsPerPage);
  }, [topGroupedRows, rowsPerPage]);

  const totalGroupedMetrics = useMemo(() => {
    if (!config?.options?.show_totals) return [] as Array<number | null>;
    return tableMetrics.map((metric, metricIndex) => {
      if (!["count", "sum"].includes(metric.operation_type)) return null;
      return topGroupedRows.reduce((accumulator, row) => accumulator + (row.metrics[metricIndex] ?? 0), 0);
    });
  }, [config?.options?.show_totals, tableMetrics, topGroupedRows]);

  const sqlNumericColumnNames = useMemo(() => {
    return sqlColumns
      .filter((column) => {
        const type = (column.type || "").toLowerCase();
        return (
          type.includes("int") ||
          type.includes("decimal") ||
          type.includes("numeric") ||
          type.includes("double") ||
          type.includes("float") ||
          type.includes("real")
        );
      })
      .map((column) => column.name);
  }, [sqlColumns]);

  const sqlTotals = useMemo(() => {
    if (!config?.options?.show_totals) return {} as Record<string, number>;
    const totals: Record<string, number> = {};

    sqlNumericColumnNames.forEach((columnName) => {
      totals[columnName] = sqlRows.reduce((sum, row) => {
        const value = row[columnName];
        if (typeof value === "number" && Number.isFinite(value)) return sum + value;
        if (typeof value === "string") {
          const parsed = Number(value);
          return Number.isFinite(parsed) ? sum + parsed : sum;
        }
        return sum;
      }, 0);
    });

    return totals;
  }, [config?.options?.show_totals, sqlNumericColumnNames, sqlRows]);

  const isRecordsConfigured = !!recordsLayerId;
  const isGroupedConfigured = !!layerId && tableMetrics.length > 0;
  const isSqlConfigured = !!recordsLayerId && !!config?.setup?.sql_query;

  const displayRecordsData = recordsAccumulatedData ?? recordsData;

  const hasMoreRecords = useMemo(() => {
    if (!displayRecordsData) return false;

    const loadedCount = displayRecordsData.features.length;
    const totalMatched = displayRecordsData.numberMatched;

    if (typeof totalMatched === "number" && Number.isFinite(totalMatched)) {
      return loadedCount < totalMatched;
    }

    return recordsHasMore;
  }, [displayRecordsData, recordsHasMore]);

  const visibleGroupedRows = useMemo(() => {
    return topGroupedRows.slice(0, groupedVisibleCount);
  }, [groupedVisibleCount, topGroupedRows]);

  const hasMoreGroupedRows = groupedVisibleCount < topGroupedRows.length;

  const visibleSqlRows = useMemo(() => {
    return sqlRows;
  }, [sqlRows]);

  const hasMoreSqlRows = sqlHasMore;

  const tableViewportHeight = useMemo(() => {
    const headerHeight = 44;
    const rowHeight = 40;
    return Math.max(180, headerHeight + rowsPerPage * rowHeight);
  }, [rowsPerPage]);

  const handleRecordsScroll = useCallback(
    (event: React.UIEvent<HTMLDivElement>) => {
      if (!hasMoreRecords || isRecordsLoading || !displayRecordsData) return;
      const target = event.currentTarget;
      const reachedBottom = target.scrollTop + target.clientHeight >= target.scrollHeight - 48;
      if (reachedBottom) {
        setRecordsPage((previous) => previous + 1);
      }
    },
    [displayRecordsData, hasMoreRecords, isRecordsLoading]
  );

  const handleGroupedScroll = useCallback(
    (event: React.UIEvent<HTMLDivElement>) => {
      if (!hasMoreGroupedRows) return;
      const target = event.currentTarget;
      const reachedBottom = target.scrollTop + target.clientHeight >= target.scrollHeight - 48;
      if (reachedBottom) {
        setGroupedVisibleCount((previous) => Math.min(previous + rowsPerPage, topGroupedRows.length));
      }
    },
    [hasMoreGroupedRows, rowsPerPage, topGroupedRows.length]
  );

  const handleSqlScroll = useCallback(
    (event: React.UIEvent<HTMLDivElement>) => {
      if (!hasMoreSqlRows || isSqlLoading) return;
      const target = event.currentTarget;
      const reachedBottom = target.scrollTop + target.clientHeight >= target.scrollHeight - 48;
      if (reachedBottom) {
        setSqlPage((previous) => previous + 1);
      }
    },
    [hasMoreSqlRows, isSqlLoading]
  );

  const widthStorageKey = useMemo(() => {
    const layerKey = config?.setup?.layer_project_id ?? "no-layer";
    const queryModeKey = config?.setup?.query_mode ?? "builder";
    return `table-widget-widths:${widgetId}:${layerKey}:${queryModeKey}`;
  }, [config?.setup?.layer_project_id, config?.setup?.query_mode, widgetId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const saved = window.localStorage.getItem(widthStorageKey);
      if (!saved) return;
      const parsed = JSON.parse(saved) as {
        grouped?: Record<string, number>;
        sql?: Record<string, number>;
      };
      if (parsed.grouped) {
        setGroupedColumnWidths(parsed.grouped);
      }
      if (parsed.sql) {
        setSqlColumnWidths(parsed.sql);
      }
    } catch {
      // Ignore malformed localStorage data.
    } finally {
      setAreWidthsHydrated(true);
    }
  }, [widthStorageKey]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!areWidthsHydrated) return;
    window.localStorage.setItem(
      widthStorageKey,
      JSON.stringify({
        grouped: groupedColumnWidths,
        sql: sqlColumnWidths,
      })
    );
  }, [areWidthsHydrated, groupedColumnWidths, sqlColumnWidths, widthStorageKey]);

  const groupedColWidth = useCallback((columnKey: string) => groupedColumnWidths[columnKey], [groupedColumnWidths]);

  const sqlColWidth = useCallback((columnKey: string) => sqlColumnWidths[columnKey], [sqlColumnWidths]);

  const sqlColumnLabelMap = useMemo(() => {
    return config?.setup?.sql_column_labels || {};
  }, [config?.setup?.sql_column_labels]);

  const beginHeaderRename = useCallback(
    (headerKey: string, currentLabel: string) => {
      if (viewOnly || !onConfigChange) return;
      setEditingHeaderKey(headerKey);
      setEditingHeaderValue(currentLabel);
    },
    [onConfigChange, viewOnly]
  );

  const applyHeaderRename = useCallback(() => {
    if (!editingHeaderKey || !onConfigChange) {
      setEditingHeaderKey(null);
      return;
    }

    const nextLabel = editingHeaderValue.trim();
    const nextSetup = {
      ...(config?.setup || {}),
    } as TableDataSchema["setup"];

    if (editingHeaderKey === "grouped_value") {
      nextSetup.group_by_label = nextLabel || undefined;
    } else if (editingHeaderKey === "metric_0") {
      nextSetup.primary_metric_label = nextLabel || undefined;
    } else if (editingHeaderKey.startsWith("metric_")) {
      const metricNumber = Number(editingHeaderKey.replace("metric_", ""));
      const additionalMetricIndex = metricNumber - 1;
      const additionalMetrics = [...(nextSetup.additional_metrics || [])];
      if (additionalMetricIndex >= 0 && additionalMetricIndex < additionalMetrics.length) {
        additionalMetrics[additionalMetricIndex] = {
          ...additionalMetrics[additionalMetricIndex],
          label: nextLabel || undefined,
        };
        nextSetup.additional_metrics = additionalMetrics;
      }
    } else if (editingHeaderKey.startsWith("sql:")) {
      const sourceColumnName = editingHeaderKey.slice(4);
      const sqlLabels = { ...(nextSetup.sql_column_labels || {}) };
      if (nextLabel) {
        sqlLabels[sourceColumnName] = nextLabel;
      } else {
        delete sqlLabels[sourceColumnName];
      }
      nextSetup.sql_column_labels = Object.keys(sqlLabels).length ? sqlLabels : undefined;
    }

    onConfigChange({
      type: "table",
      ...config,
      setup: nextSetup,
    } as TableDataSchema);
    setEditingHeaderKey(null);
  }, [config, editingHeaderKey, editingHeaderValue, onConfigChange]);

  const renderHeaderLabel = useCallback(
    (headerKey: string, label: string, align: "left" | "right" = "left") => {
      if (editingHeaderKey === headerKey) {
        return (
          <TextField
            autoFocus
            size="small"
            value={editingHeaderValue}
            onChange={(event) => setEditingHeaderValue(event.target.value)}
            onBlur={applyHeaderRename}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                applyHeaderRename();
              }
              if (event.key === "Escape") {
                event.preventDefault();
                setEditingHeaderKey(null);
              }
            }}
            sx={{
              minWidth: 100,
              "& .MuiInputBase-input": { fontSize: "0.75rem", py: 0.5 },
            }}
          />
        );
      }

      return (
        <Typography
          variant="body2"
          fontWeight="bold"
          align={align}
          onDoubleClick={() => beginHeaderRename(headerKey, label)}
          sx={{
            ...twoLineClampSx,
            cursor: viewOnly || !onConfigChange ? "default" : "text",
            pr: 1,
          }}>
          {label}
        </Typography>
      );
    },
    [applyHeaderRename, beginHeaderRename, editingHeaderKey, editingHeaderValue, onConfigChange, twoLineClampSx, viewOnly]
  );

  return (
    <>
      <WidgetStatusContainer
        isLoading={
          isSqlMode
            ? isSqlLoading && sqlRows.length === 0
            : isGroupedMode
              ? isGroupedLoading && groupedRows.length === 0
              : isRecordsLoading && !displayRecordsData
        }
        isNotConfigured={isSqlMode ? !isSqlConfigured : isGroupedMode ? !isGroupedConfigured : !isRecordsConfigured}
        isError={isSqlMode ? !!sqlError : isGroupedMode ? !!groupedError : !!isRecordsError}
        height={140}
      />

      {!isSqlMode && !isGroupedMode && displayRecordsData && isRecordsConfigured && (
        <Box>
          <Box
            sx={{
              maxHeight: `${tableViewportHeight}px`,
              overflowX: "auto",
              overflowY: "auto",
            }}
            onScroll={handleRecordsScroll}>
            <DatasetTable
              areFieldsLoading={areFieldsLoading}
              displayData={displayRecordsData}
              fields={visibleFields}
            />
          </Box>
          {hasMoreRecords && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
              {t("scroll_to_load_more", { defaultValue: "Scroll to load more" })}
            </Typography>
          )}
        </Box>
      )}

      {!isSqlMode && isGroupedMode && isGroupedConfigured && (
        <Box sx={{ overflowX: "auto", maxHeight: `${tableViewportHeight}px`, overflowY: "auto" }} onScroll={handleGroupedScroll}>
          <Table
            size="small"
            stickyHeader
            sx={{
              tableLayout: "fixed",
              width: "100%",
              "& .MuiTableCell-root": {
                borderRight: 1,
                borderColor: "divider",
                verticalAlign: "top",
              },
              "& .MuiTableRow-root > .MuiTableCell-root:last-of-type": {
                borderRight: 0,
              },
            }}>
            <TableHead>
              <TableRow>
                <TableCell
                  sx={{
                    width: groupedColWidth("grouped_value"),
                    maxWidth: 900,
                    position: "relative",
                  }}>
                  {renderHeaderLabel(
                    "grouped_value",
                    config?.setup?.group_by_label || config?.setup?.group_by_column_name || t("group", { defaultValue: "Group" })
                  )}
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
                    onMouseDown={(event) => startColumnResize(event, "grouped", "grouped_value")}
                  />
                </TableCell>
                {groupedMetricLabels.map((label, index) => (
                  <TableCell
                    key={`grouped-header-${index}`}
                    align="right"
                    sx={{
                      width: groupedColWidth(`metric_${index}`),
                      maxWidth: 900,
                      position: "relative",
                    }}>
                    {renderHeaderLabel(`metric_${index}`, label, "right")}
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
                      onMouseDown={(event) => startColumnResize(event, "grouped", `metric_${index}`)}
                    />
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {visibleGroupedRows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={Math.max(groupedMetricLabels.length + 1, 2)} align="center">
                    <Typography variant="body2" color="text.secondary">
                      {t("no_data_for_current_filters", { defaultValue: "No data for current filters." })}
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
              {visibleGroupedRows.map((item, index) => (
                <TableRow key={`${item.grouped_value}-${index}`}>
                  <TableCell sx={{ width: groupedColWidth("grouped_value") }}>
                    <Typography variant="body2" sx={twoLineClampSx}>
                      {item.grouped_value ?? "-"}
                    </Typography>
                  </TableCell>
                  {item.metrics.map((value, metricIndex) => (
                    <TableCell key={`metric-value-${metricIndex}`} align="right" sx={{ width: groupedColWidth(`metric_${metricIndex}`) }}>
                      <Typography variant="body2" sx={twoLineClampSx}>
                        {formatNumber(value, config?.options?.format, i18n.language)}
                      </Typography>
                    </TableCell>
                  ))}
                </TableRow>
              ))}
              {totalGroupedMetrics.some((value) => value !== null) && (
                <TableRow sx={{ "& .MuiTableCell-root": { fontWeight: 700 } }}>
                  <TableCell sx={{ width: groupedColWidth("grouped_value") }}>
                    <Typography variant="body2" fontWeight="bold">
                      {t("total", { defaultValue: "Total" })}
                    </Typography>
                  </TableCell>
                  {totalGroupedMetrics.map((value, metricIndex) => (
                    <TableCell key={`metric-total-${metricIndex}`} align="right" sx={{ width: groupedColWidth(`metric_${metricIndex}`) }}>
                      <Typography variant="body2" fontWeight="bold">
                        {value === null ? "-" : formatNumber(value, config?.options?.format, i18n.language)}
                      </Typography>
                    </TableCell>
                  ))}
                </TableRow>
              )}
            </TableBody>
          </Table>
          {hasMoreGroupedRows && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
              {t("scroll_to_load_more", { defaultValue: "Scroll to load more" })}
            </Typography>
          )}
        </Box>
      )}

      {isSqlMode && isSqlConfigured && (
        <Box sx={{ overflowX: "auto", maxHeight: `${tableViewportHeight}px`, overflowY: "auto" }} onScroll={handleSqlScroll}>
          <Table
            size="small"
            stickyHeader
            sx={{
              tableLayout: "fixed",
              width: "100%",
              "& .MuiTableCell-root": {
                borderRight: 1,
                borderColor: "divider",
                verticalAlign: "top",
              },
              "& .MuiTableRow-root > .MuiTableCell-root:last-of-type": {
                borderRight: 0,
              },
            }}>
            <TableHead>
              <TableRow>
                {sqlColumns.map((column) => {
                  const visibleLabel = sqlColumnLabelMap[column.name] || column.name;
                  return (
                    <TableCell
                      key={column.name}
                      sx={{
                        width: sqlColWidth(column.name),
                        maxWidth: 900,
                        position: "relative",
                      }}>
                      {renderHeaderLabel(`sql:${column.name}`, visibleLabel)}
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
                        onMouseDown={(event) => startColumnResize(event, "sql", column.name)}
                      />
                    </TableCell>
                  );
                })}
              </TableRow>
            </TableHead>
            <TableBody>
              {visibleSqlRows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={Math.max(sqlColumns.length, 1)} align="center">
                    <Typography variant="body2" color="text.secondary">
                      {t("no_data_for_current_filters", { defaultValue: "No data for current filters." })}
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
              {visibleSqlRows.map((row, rowIndex) => (
                <TableRow key={`sql-row-${rowIndex}`}>
                  {sqlColumns.map((column) => (
                    <TableCell key={`${column.name}-${rowIndex}`} sx={{ width: sqlColWidth(column.name) }}>
                      <Typography variant="body2" sx={twoLineClampSx}>
                        {String(row[column.name] ?? "-")}
                      </Typography>
                    </TableCell>
                  ))}
                </TableRow>
              ))}
              {config?.options?.show_totals && sqlColumns.length > 0 && (
                <TableRow sx={{ "& .MuiTableCell-root": { fontWeight: 700 } }}>
                  {sqlColumns.map((column, index) => (
                    <TableCell key={`sql-total-${column.name}`} sx={{ width: sqlColWidth(column.name) }}>
                      <Typography variant="body2" fontWeight="bold">
                        {index === 0
                          ? t("total", { defaultValue: "Total" })
                          : column.name in sqlTotals
                            ? formatNumber(sqlTotals[column.name], config?.options?.format, i18n.language)
                            : "-"}
                      </Typography>
                    </TableCell>
                  ))}
                </TableRow>
              )}
            </TableBody>
          </Table>
          {hasMoreSqlRows && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
              {t("scroll_to_load_more", { defaultValue: "Scroll to load more" })}
            </Typography>
          )}
        </Box>
      )}
    </>
  );
};
