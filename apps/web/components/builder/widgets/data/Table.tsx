import { Box, TextField, Typography } from "@mui/material";
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

import WidgetRecordsTable from "@/components/builder/widgets/data/WidgetRecordsTable";
import { WidgetStatusContainer } from "@/components/builder/widgets/common/WidgetStatusContainer";

interface TableDataWidgetProps {
  widgetId: string;
  config: TableDataSchema;
  projectLayers: ProjectLayer[];
  viewOnly?: boolean;
  onConfigChange?: (nextConfig: TableDataSchema) => void;
}

type GroupedMetricConfig = {
  operation_type: NonNullable<TableDataSchema["setup"]["operation_type"]>;
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
  const stickyHeaderEnabled = (config?.options?.sticky_header ?? true) === true;

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
  const [isSqlNextPagePending, setIsSqlNextPagePending] = useState(false);
  const [sqlError, setSqlError] = useState<string | null>(null);
  const [recordsColumnWidths, setRecordsColumnWidths] = useState<Record<string, number>>({});
  const [groupedColumnWidths, setGroupedColumnWidths] = useState<Record<string, number>>({});
  const [sqlColumnWidths, setSqlColumnWidths] = useState<Record<string, number>>({});
  const [measuredHeaderHeight, setMeasuredHeaderHeight] = useState(44);
  const [measuredRowHeight, setMeasuredRowHeight] = useState(40);
  const [isRecordsOverflowing, setIsRecordsOverflowing] = useState(false);
  const [isGroupedOverflowing, setIsGroupedOverflowing] = useState(false);
  const [isSqlOverflowing, setIsSqlOverflowing] = useState(false);
  const [areWidthsHydrated, setAreWidthsHydrated] = useState(false);
  const [isResizingColumns, setIsResizingColumns] = useState(false);
  const [editingHeaderKey, setEditingHeaderKey] = useState<string | null>(null);
  const [editingHeaderValue, setEditingHeaderValue] = useState("");

  const recordsScrollRef = useRef<HTMLDivElement | null>(null);
  const groupedScrollRef = useRef<HTMLDivElement | null>(null);
  const sqlScrollRef = useRef<HTMLDivElement | null>(null);
  const lastSqlQuerySignatureRef = useRef("");
  const activeResizeRef = useRef<{
    tableType: "records" | "grouped" | "sql";
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

  const persistentScrollbarSx = {
    scrollbarWidth: "auto" as const,
    scrollbarColor: "rgba(110, 110, 110, 0.5) transparent",
    "&::-webkit-scrollbar": {
      width: 10,
      height: 10,
    },
    "&::-webkit-scrollbar-track": {
      backgroundColor: "transparent",
    },
    "&::-webkit-scrollbar-thumb": {
      backgroundColor: "rgba(110, 110, 110, 0.5)",
      borderRadius: 8,
      border: "2px solid transparent",
      backgroundClip: "padding-box",
      minHeight: 40,
    },
    "&::-webkit-scrollbar-thumb:hover": {
      backgroundColor: "rgba(100, 100, 100, 0.65)",
    },
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

    const additionalMetrics = config?.setup?.additional_metrics || [];
    additionalMetrics.forEach((metric) => {
      if (!metric.operation_type) return;
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
    const selectedVisibleColumns = config?.setup?.visible_columns;
    if (!selectedVisibleColumns || selectedVisibleColumns.length === 0) return [];
    const fieldMap = new Map(layerFields.map((field) => [field.name, field]));
    return selectedVisibleColumns
      .map((name) => fieldMap.get(name))
      .filter((field): field is (typeof layerFields)[number] => Boolean(field));
  }, [layerFields, config?.setup?.visible_columns]);

  const isRecordsColumnsConfigured = visibleFields.length > 0;

  const recordsQueryParams = useMemo(() => {
    if (!recordsLayerId || isGroupedMode || isSqlMode || !isRecordsColumnsConfigured) return undefined;

    const params: GetCollectionItemsQueryParams = {
      limit: rowsPerPage,
      offset: recordsPage * rowsPerPage,
    };

    const configuredSortBy = config?.options?.sort_by;
    const isGroupedOnlySortKey =
      typeof configuredSortBy === "string" &&
      (configuredSortBy === "grouped_value" || configuredSortBy.startsWith("metric_"));

    const defaultSortField = !isGroupedOnlySortKey && configuredSortBy ? configuredSortBy : visibleFields[0]?.name;

    if (defaultSortField) {
      const sortingDirection = config?.options?.sorting ?? "desc";
      const sortDirectionPrefix = sortingDirection === "desc" ? "-" : "";
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
    isRecordsColumnsConfigured,
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
        const size = 5000;
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
    config?.options?.sorting,
    config?.setup?.group_by_column_name,
    isGroupedMode,
    isSqlMode,
    layerId,
    queryParams,
    tableMetrics,
  ]);

  const sqlQuerySignature = useMemo(() => {
    return `${recordsLayerId || ""}|${config?.setup?.sql_query || ""}|${rowsPerPage}|${isSqlMode}`;
  }, [config?.setup?.sql_query, isSqlMode, recordsLayerId, rowsPerPage]);

  useEffect(() => {
    setSqlPage(0);
    setSqlHasMore(true);
    setSqlRows([]);
    setIsSqlNextPagePending(false);
  }, [sqlQuerySignature]);
  useEffect(() => {
    let isCancelled = false;

    async function loadSqlPreview() {
      const currentSqlQuerySignature = sqlQuerySignature;

      if (!isSqlMode || !recordsLayerId || !config?.setup?.sql_query) {
        lastSqlQuerySignatureRef.current = currentSqlQuerySignature;
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

      if (sqlPage > 0 && currentSqlQuerySignature !== lastSqlQuerySignatureRef.current) {
        return;
      }

      lastSqlQuerySignatureRef.current = currentSqlQuerySignature;

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
          setIsSqlNextPagePending(false);
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
    sqlQuerySignature,
  ]);

  const startColumnResize = useCallback(
    (event: React.MouseEvent, tableType: "records" | "grouped" | "sql", columnKey: string) => {
      event.preventDefault();
      event.stopPropagation();

      const widthMap =
        tableType === "records"
          ? recordsColumnWidths
          : tableType === "grouped"
            ? groupedColumnWidths
            : sqlColumnWidths;
      const currentRenderedWidth = (event.currentTarget.parentElement as HTMLElement | null)?.getBoundingClientRect().width;
      activeResizeRef.current = {
        tableType,
        columnKey,
        startX: event.clientX,
        startWidth: widthMap[columnKey] ?? currentRenderedWidth ?? 140,
      };
      setIsResizingColumns(true);
    },
    [groupedColumnWidths, recordsColumnWidths, sqlColumnWidths]
  );

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      const activeResize = activeResizeRef.current;
      if (!activeResize) return;

      const nextWidth = Math.max(0, Math.min(900, activeResize.startWidth + (event.clientX - activeResize.startX)));
      if (activeResize.tableType === "records") {
        setRecordsColumnWidths((previous) => ({
          ...previous,
          [activeResize.columnKey]: nextWidth,
        }));
      } else if (activeResize.tableType === "grouped") {
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
      setIsResizingColumns(false);
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

  useEffect(() => {
    // Grouped rows are already fully fetched; render the full list to keep both table views consistent.
    setGroupedVisibleCount(sortedGroupedRows.length);
  }, [sortedGroupedRows.length]);

  const totalGroupedMetrics = useMemo(() => {
    if (!config?.options?.show_totals) return [] as Array<number | null>;
    return tableMetrics.map((metric, metricIndex) => {
      if (!["count", "sum"].includes(metric.operation_type)) return null;
      return sortedGroupedRows.reduce((accumulator, row) => accumulator + (row.metrics[metricIndex] ?? 0), 0);
    });
  }, [config?.options?.show_totals, tableMetrics, sortedGroupedRows]);

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

  const sqlColumnLabelMap = useMemo(() => {
    return config?.setup?.sql_column_labels || {};
  }, [config?.setup?.sql_column_labels]);

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

  const isRecordsConfigured = !!recordsLayerId && isRecordsColumnsConfigured;
  const isGroupedConfigured = !!layerId && tableMetrics.length > 0;
  const isSqlConfigured = !!recordsLayerId && !!config?.setup?.sql_query;

  const displayRecordsData = recordsAccumulatedData ?? recordsData;

  const hasMoreRecords = useMemo(() => {
    if (!displayRecordsData) return false;

    const loadedCount = displayRecordsData.features.length;
    const totalMatched = displayRecordsData.numberMatched;

    if (typeof totalMatched === "number" && Number.isFinite(totalMatched)) {
      if (loadedCount < totalMatched) return true;
      return recordsHasMore;
    }

    return recordsHasMore;
  }, [displayRecordsData, recordsHasMore]);

  const visibleGroupedRows = useMemo(() => {
    return sortedGroupedRows.slice(0, groupedVisibleCount);
  }, [groupedVisibleCount, sortedGroupedRows]);

  const hasMoreGroupedRows = groupedVisibleCount < sortedGroupedRows.length;

  const groupedTableColumns = useMemo(
    () => {
      const baseColumns = [
        {
          key: "grouped_value",
          label: config?.setup?.group_by_label || config?.setup?.group_by_column_name || t("group", { defaultValue: "Group" }),
          align: "left" as const,
        },
        ...groupedMetricLabels.map((label, index) => ({
          key: `metric_${index}`,
          label,
          align: "right" as const,
        })),
      ];

      const configuredOrder = config?.setup?.grouped_column_order || [];
      if (!configuredOrder.length) return baseColumns;

      const byKey = new Map(baseColumns.map((column) => [column.key, column]));
      const ordered = configuredOrder.map((key) => byKey.get(key)).filter(Boolean) as typeof baseColumns;
      const missing = baseColumns.filter((column) => !configuredOrder.includes(column.key));

      return [...ordered, ...missing];
    },
    [config?.setup?.group_by_column_name, config?.setup?.group_by_label, config?.setup?.grouped_column_order, groupedMetricLabels, t]
  );

  const groupedTableRows = useMemo(() => {
    return visibleGroupedRows.map((item) => {
      const row: Record<string, unknown> = { grouped_value: item.grouped_value ?? "-" };
      item.metrics.forEach((value, metricIndex) => {
        row[`metric_${metricIndex}`] = value;
      });
      return row;
    });
  }, [visibleGroupedRows]);

  const groupedTotalsRow = useMemo(() => {
    if (!totalGroupedMetrics.some((value) => value !== null)) return undefined;
    const row: Record<string, unknown> = { grouped_value: t("total", { defaultValue: "Total" }) };
    totalGroupedMetrics.forEach((value, metricIndex) => {
      row[`metric_${metricIndex}`] = value;
    });
    return row;
  }, [t, totalGroupedMetrics]);

  const formatGroupedCell = useCallback(
    (columnKey: string, value: unknown) => {
      if (columnKey === "grouped_value") {
        return String(value ?? "-");
      }
      if (columnKey.startsWith("metric_")) {
        if (value === null || value === undefined) return "-";
        return formatNumber(value as number, config?.options?.format, i18n.language);
      }
      return String(value ?? "-");
    },
    [config?.options?.format, i18n.language]
  );

  const sqlTableColumns = useMemo(
    () => {
      const baseColumns = sqlColumns.map((column, index) => {
        const align: "left" | "right" =
          index === 0 || !sqlNumericColumnNames.includes(column.name) ? "left" : "right";

        return {
          key: column.name,
          label: sqlColumnLabelMap[column.name] || column.name,
          align,
        };
      });

      const configuredOrder = config?.setup?.sql_column_order || [];
      if (!configuredOrder.length) return baseColumns;

      const byKey = new Map(baseColumns.map((column) => [column.key, column]));
      const ordered = configuredOrder.map((key) => byKey.get(key)).filter(Boolean) as typeof baseColumns;
      const missing = baseColumns.filter((column) => !configuredOrder.includes(column.key));

      return [...ordered, ...missing];
    },
    [config?.setup?.sql_column_order, sqlColumnLabelMap, sqlColumns, sqlNumericColumnNames]
  );

  const reorderKeys = useCallback(
    (keys: string[], fromColumnKey: string, toColumnKey: string) => {
      const fromIndex = keys.indexOf(fromColumnKey);
      const toIndex = keys.indexOf(toColumnKey);
      if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) return keys;

      const next = [...keys];
      const [moved] = next.splice(fromIndex, 1);
      next.splice(toIndex, 0, moved);
      return next;
    },
    []
  );

  const handleReorderColumn = useCallback(
    (tableType: "records" | "grouped" | "sql", fromColumnKey: string, toColumnKey: string) => {
      if (!onConfigChange || viewOnly) return;

      const currentSetup = { ...(config?.setup || {}) } as TableDataSchema["setup"];

      if (tableType === "records") {
        const current =
          currentSetup.visible_columns?.length
            ? [...currentSetup.visible_columns]
            : visibleFields.map((field) => field.name);
        const nextColumns = reorderKeys(current, fromColumnKey, toColumnKey);
        currentSetup.visible_columns = nextColumns;
      }

      if (tableType === "grouped") {
        const current = groupedTableColumns.map((column) => column.key);
        const nextColumns = reorderKeys(current, fromColumnKey, toColumnKey);
        currentSetup.grouped_column_order = nextColumns;
      }

      if (tableType === "sql") {
        const current = sqlTableColumns.map((column) => column.key);
        const nextColumns = reorderKeys(current, fromColumnKey, toColumnKey);
        currentSetup.sql_column_order = nextColumns;
      }

      onConfigChange({
        type: "table",
        ...config,
        setup: currentSetup,
      } as TableDataSchema);
    },
    [config, groupedTableColumns, onConfigChange, reorderKeys, sqlTableColumns, viewOnly, visibleFields]
  );

  const sqlTotalsRow = useMemo(() => {
    if (!config?.options?.show_totals || sqlColumns.length === 0) return undefined;
    const row: Record<string, unknown> = {};
    sqlColumns.forEach((column, index) => {
      row[column.name] =
        index === 0
          ? t("total", { defaultValue: "Total" })
          : column.name in sqlTotals
            ? sqlTotals[column.name]
            : "-";
    });
    return row;
  }, [config?.options?.show_totals, sqlColumns, sqlTotals, t]);

  const formatSqlCell = useCallback(
    (columnKey: string, value: unknown) => {
      if (value === null || value === undefined) return "-";
      if (typeof value === "string" && value === "-") return value;
      if (sqlNumericColumnNames.includes(columnKey) && (typeof value === "number" || typeof value === "string")) {
        const parsed = typeof value === "number" ? value : Number(value);
        if (Number.isFinite(parsed)) {
          return formatNumber(parsed, config?.options?.format, i18n.language);
        }
      }
      return String(value);
    },
    [config?.options?.format, i18n.language, sqlNumericColumnNames]
  );

  const hasMoreSqlRows = sqlHasMore;

  useEffect(() => {
    const container = isSqlMode ? sqlScrollRef.current : isGroupedMode ? groupedScrollRef.current : recordsScrollRef.current;
    if (!container) return;

    const measureHeights = () => {
      const headerRow = container.querySelector("thead tr") as HTMLTableRowElement | null;
      const bodyRow = container.querySelector("tbody tr") as HTMLTableRowElement | null;

      const nextHeaderHeight = Math.max(32, Math.round(headerRow?.getBoundingClientRect().height || 44));
      const nextRowHeight = Math.max(28, Math.round(bodyRow?.getBoundingClientRect().height || 40));

      setMeasuredHeaderHeight((previous) => (previous !== nextHeaderHeight ? nextHeaderHeight : previous));
      setMeasuredRowHeight((previous) => (previous !== nextRowHeight ? nextRowHeight : previous));

      const isOverflowing = container.scrollHeight > container.clientHeight + 1;
      if (isSqlMode) {
        setIsSqlOverflowing(isOverflowing);
      } else if (isGroupedMode) {
        setIsGroupedOverflowing(isOverflowing);
      } else {
        setIsRecordsOverflowing(isOverflowing);
      }
    };

    measureHeights();

    const resizeObserver = new ResizeObserver(() => {
      measureHeights();
    });

    resizeObserver.observe(container);

    const headerEl = container.querySelector("thead") as HTMLElement | null;
    if (headerEl) {
      resizeObserver.observe(headerEl);
    }

    const firstBodyRow = container.querySelector("tbody tr") as HTMLElement | null;
    if (firstBodyRow) {
      resizeObserver.observe(firstBodyRow);
    }

    return () => {
      resizeObserver.disconnect();
    };
  }, [
    config?.setup?.visible_columns,
    displayRecordsData?.features?.length,
    groupedColumnWidths,
    groupedVisibleCount,
    isGroupedMode,
    isSqlMode,
    recordsColumnWidths,
    sqlColumnWidths,
    sqlRows.length,
  ]);

  useEffect(() => {
    if (isSqlMode) {
      setIsRecordsOverflowing(false);
      setIsGroupedOverflowing(false);
      return;
    }
    if (isGroupedMode) {
      setIsRecordsOverflowing(false);
      setIsSqlOverflowing(false);
      return;
    }
    setIsGroupedOverflowing(false);
    setIsSqlOverflowing(false);
  }, [isGroupedMode, isSqlMode]);

  const tableViewportHeight = useMemo(() => {
    return Math.max(180, measuredHeaderHeight + rowsPerPage * measuredRowHeight);
  }, [measuredHeaderHeight, measuredRowHeight, rowsPerPage]);

  const loadMoreRecordsIfNeeded = useCallback((target: HTMLDivElement) => {
    if (!hasMoreRecords || isRecordsLoading || !displayRecordsData) return;
    const reachedBottom = target.scrollTop + target.clientHeight >= target.scrollHeight - 8;
    if (reachedBottom) {
      setRecordsPage((previous) => previous + 1);
    }
  }, [displayRecordsData, hasMoreRecords, isRecordsLoading]);

  const handleRecordsScroll = useCallback(
    (event: React.UIEvent<HTMLDivElement>) => {
      loadMoreRecordsIfNeeded(event.currentTarget);
    },
    [loadMoreRecordsIfNeeded]
  );

  useEffect(() => {
    if (isGroupedMode || isSqlMode) return;
    if (!hasMoreRecords || isRecordsLoading || !displayRecordsData) return;
    const target = recordsScrollRef.current;
    if (!target) return;

    const stillAtBottom = target.scrollTop + target.clientHeight >= target.scrollHeight - 8;
    if (stillAtBottom) {
      setRecordsPage((previous) => previous + 1);
      return;
    }

    if (target.scrollHeight <= target.clientHeight + 1) {
      setRecordsPage((previous) => previous + 1);
    }
  }, [displayRecordsData, hasMoreRecords, isGroupedMode, isRecordsLoading, isSqlMode]);

  useEffect(() => {
    if (!isGroupedMode || isSqlMode) return;
    if (!hasMoreGroupedRows) return;
    const target = groupedScrollRef.current;
    if (!target) return;

    if (target.scrollHeight <= target.clientHeight + 1) {
      setGroupedVisibleCount((previous) => Math.min(previous + rowsPerPage, sortedGroupedRows.length));
    }
  }, [hasMoreGroupedRows, isGroupedMode, isSqlMode, rowsPerPage, sortedGroupedRows.length]);

  useEffect(() => {
    if (!isSqlMode || isGroupedMode) return;
    if (!hasMoreSqlRows || isSqlLoading || isSqlNextPagePending) return;
    const target = sqlScrollRef.current;
    if (!target) return;

    const currentPageLoaded = sqlRows.length >= (sqlPage + 1) * rowsPerPage;
    if (!currentPageLoaded) return;

    if (target.scrollHeight <= target.clientHeight + 1) {
      setIsSqlNextPagePending(true);
      setSqlPage((previous) => previous + 1);
    }
  }, [
    hasMoreSqlRows,
    isGroupedMode,
    isSqlLoading,
    isSqlMode,
    isSqlNextPagePending,
    rowsPerPage,
    sqlPage,
    sqlRows.length,
  ]);

  const handleGroupedScroll = useCallback(
    (event: React.UIEvent<HTMLDivElement>) => {
      if (!hasMoreGroupedRows) return;
      const target = event.currentTarget;
      const reachedBottom = target.scrollTop + target.clientHeight >= target.scrollHeight - 48;
      if (reachedBottom) {
        setGroupedVisibleCount((previous) => Math.min(previous + rowsPerPage, sortedGroupedRows.length));
      }
    },
    [hasMoreGroupedRows, rowsPerPage, sortedGroupedRows.length]
  );

  const handleSqlScroll = useCallback(
    (event: React.UIEvent<HTMLDivElement>) => {
      if (!hasMoreSqlRows || isSqlLoading || isSqlNextPagePending) return;
      const target = event.currentTarget;
      const reachedBottom = target.scrollTop + target.clientHeight >= target.scrollHeight - 8;
      if (reachedBottom) {
        setIsSqlNextPagePending(true);
        setSqlPage((previous) => previous + 1);
      }
    },
    [hasMoreSqlRows, isSqlLoading, isSqlNextPagePending]
  );

  useEffect(() => {
    if (!isSqlMode || isGroupedMode) return;
    if (!hasMoreSqlRows || isSqlLoading || isSqlNextPagePending) return;
    const target = sqlScrollRef.current;
    if (!target) return;

    const stillAtBottom = target.scrollTop + target.clientHeight >= target.scrollHeight - 8;
    if (stillAtBottom) {
      setIsSqlNextPagePending(true);
      setSqlPage((previous) => previous + 1);
    }
  }, [
    hasMoreSqlRows,
    isGroupedMode,
    isSqlLoading,
    isSqlMode,
    isSqlNextPagePending,
  ]);

  const handleSqlWheel = useCallback(
    (event: React.WheelEvent<HTMLDivElement>) => {
      const target = event.currentTarget;
      const canScrollVertically = target.scrollHeight > target.clientHeight + 1;
      if (!canScrollVertically) return;

      const atTop = target.scrollTop <= 0;
      const atBottom = target.scrollTop + target.clientHeight >= target.scrollHeight - 1;
      const scrollingUp = event.deltaY < 0;
      const scrollingDown = event.deltaY > 0;

      // Keep wheel focus inside table while it can still scroll; hand off only at edges.
      if (!((scrollingUp && atTop) || (scrollingDown && atBottom))) {
        event.stopPropagation();
      }

      // If user keeps scrolling down at the bottom, trigger the next SQL page.
      if (scrollingDown && atBottom && hasMoreSqlRows && !isSqlLoading && !isSqlNextPagePending) {
        setIsSqlNextPagePending(true);
        setSqlPage((previous) => previous + 1);
      }
    },
    [hasMoreSqlRows, isSqlLoading, isSqlNextPagePending]
  );

  const trapWheelInTable = useCallback((event: React.WheelEvent<HTMLDivElement>) => {
    const target = event.currentTarget;
    const canScrollVertically = target.scrollHeight > target.clientHeight + 1;
    if (!canScrollVertically) return;

    const atTop = target.scrollTop <= 0;
    const atBottom = target.scrollTop + target.clientHeight >= target.scrollHeight - 1;
    const scrollingUp = event.deltaY < 0;
    const scrollingDown = event.deltaY > 0;

    // Keep wheel focus inside table while it can still scroll; hand off only at bounds.
    if ((scrollingUp && atTop) || (scrollingDown && atBottom)) {
      return;
    }

    event.stopPropagation();
  }, []);

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
        records?: Record<string, number>;
        grouped?: Record<string, number>;
        sql?: Record<string, number>;
      };
      if (parsed.records) {
        setRecordsColumnWidths(parsed.records);
      }
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
    if (isResizingColumns) return;

    const persistTimer = window.setTimeout(() => {
      window.localStorage.setItem(
        widthStorageKey,
        JSON.stringify({
          records: recordsColumnWidths,
          grouped: groupedColumnWidths,
          sql: sqlColumnWidths,
        })
      );
    }, 150);

    return () => {
      window.clearTimeout(persistTimer);
    };
  }, [areWidthsHydrated, groupedColumnWidths, isResizingColumns, recordsColumnWidths, sqlColumnWidths, widthStorageKey]);

  const recordsColWidth = useCallback((columnKey: string) => recordsColumnWidths[columnKey], [recordsColumnWidths]);
  const groupedColWidth = useCallback((columnKey: string) => groupedColumnWidths[columnKey], [groupedColumnWidths]);

  const sqlColWidth = useCallback((columnKey: string) => sqlColumnWidths[columnKey], [sqlColumnWidths]);

  const recordColumnLabelMap = useMemo(() => {
    return config?.setup?.record_column_labels || {};
  }, [config?.setup?.record_column_labels]);

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
    } else if (editingHeaderKey.startsWith("record:")) {
      const sourceColumnName = editingHeaderKey.slice(7);
      const recordLabels = { ...(nextSetup.record_column_labels || {}) };
      if (nextLabel) {
        recordLabels[sourceColumnName] = nextLabel;
      } else {
        delete recordLabels[sourceColumnName];
      }
      nextSetup.record_column_labels = Object.keys(recordLabels).length ? recordLabels : undefined;
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
            ref={recordsScrollRef}
            sx={{
              maxHeight: `${tableViewportHeight}px`,
              overflowX: "auto",
              overflowY: "auto",
              overscrollBehaviorY: "auto",
              pb: 2,
              scrollPaddingBottom: 16,
              ...persistentScrollbarSx,
            }}
            onWheel={trapWheelInTable}
            onScroll={handleRecordsScroll}>
            <WidgetRecordsTable
              areFieldsLoading={areFieldsLoading}
              displayData={displayRecordsData}
              fields={visibleFields}
              stickyHeaderEnabled={stickyHeaderEnabled}
              headerLabelMap={recordColumnLabelMap}
              getColumnWidth={recordsColWidth}
              renderHeaderLabel={(fieldName, label) => renderHeaderLabel(`record:${fieldName}`, label)}
              onReorderColumns={(fromColumnKey, toColumnKey) => {
                handleReorderColumn("records", fromColumnKey, toColumnKey);
              }}
              onHeaderResizeStart={
                viewOnly || !onConfigChange
                  ? undefined
                  : (event, fieldName) => startColumnResize(event, "records", fieldName)
              }
            />
          </Box>
          {(hasMoreRecords || isRecordsOverflowing) && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
              {t("scroll_to_load_more", { defaultValue: "Scroll to see all features" })}
            </Typography>
          )}
        </Box>
      )}

      {!isSqlMode && isGroupedMode && isGroupedConfigured && (
        <Box>
          <Box
            ref={groupedScrollRef}
            sx={{
              overflowX: "auto",
              maxHeight: `${tableViewportHeight}px`,
              overflowY: "auto",
              overscrollBehaviorY: "auto",
              pb: 2,
              scrollPaddingBottom: 16,
              ...persistentScrollbarSx,
            }}
            onWheel={trapWheelInTable}
            onScroll={handleGroupedScroll}>
            <WidgetRecordsTable
              areFieldsLoading={false}
              fields={[]}
              stickyHeaderEnabled={stickyHeaderEnabled}
              tableColumns={groupedTableColumns}
              tableRows={groupedTableRows}
              totalsRow={groupedTotalsRow}
              formatCellValueForColumn={formatGroupedCell}
              emptyMessage={
                <Typography variant="body2" color="text.secondary">
                  {t("no_data_for_current_filters", { defaultValue: "No data for current filters." })}
                </Typography>
              }
              getColumnWidth={groupedColWidth}
              renderHeaderLabel={(columnKey, label, align) => renderHeaderLabel(columnKey, label, align || "left")}
              onReorderColumns={(fromColumnKey, toColumnKey) => {
                handleReorderColumn("grouped", fromColumnKey, toColumnKey);
              }}
              onHeaderResizeStart={
                viewOnly || !onConfigChange
                  ? undefined
                  : (event, columnKey) => startColumnResize(event, "grouped", columnKey)
              }
            />
          </Box>
          {(hasMoreGroupedRows || isGroupedOverflowing) && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
              {t("scroll_to_load_more", { defaultValue: "Scroll to see all features" })}
            </Typography>
          )}
        </Box>
      )}

      {isSqlMode && isSqlConfigured && (
        <Box>
          <Box
            ref={sqlScrollRef}
            sx={{
              overflowX: "auto",
              maxHeight: `${tableViewportHeight}px`,
              overflowY: "scroll",
              overscrollBehaviorY: "auto",
              pb: 2,
              scrollPaddingBottom: 16,
              ...persistentScrollbarSx,
            }}
            onWheel={handleSqlWheel}
            onScroll={handleSqlScroll}>
            <WidgetRecordsTable
              areFieldsLoading={false}
              fields={[]}
              stickyHeaderEnabled={stickyHeaderEnabled}
              tableColumns={sqlTableColumns}
              tableRows={sqlRows}
              formatCellValueForColumn={formatSqlCell}
              emptyMessage={
                <Typography variant="body2" color="text.secondary">
                  {t("no_data_for_current_filters", { defaultValue: "No data for current filters." })}
                </Typography>
              }
              getColumnWidth={sqlColWidth}
              renderHeaderLabel={(columnKey, label, align) => renderHeaderLabel(`sql:${columnKey}`, label, align || "left")}
              onReorderColumns={(fromColumnKey, toColumnKey) => {
                handleReorderColumn("sql", fromColumnKey, toColumnKey);
              }}
              onHeaderResizeStart={
                viewOnly || !onConfigChange
                  ? undefined
                  : (event, columnKey) => startColumnResize(event, "sql", columnKey)
              }
            />
          </Box>
          {sqlTotalsRow && sqlTableColumns.length > 0 && (
            <Box sx={{ overflowX: "auto" }}>
              <Box component="table" sx={{ tableLayout: "fixed", width: "100%", borderCollapse: "collapse" }}>
                <Box component="tbody">
                  <Box component="tr">
                    {sqlTableColumns.map((column) => (
                      <Box
                        key={`sql-total-outside-${column.key}`}
                        component="td"
                        sx={{
                          width: sqlColWidth(column.key),
                          p: 1,
                          borderTop: 1,
                          borderColor: "divider",
                          borderRight: 1,
                          backgroundColor: "background.paper",
                          textAlign: column.align || "left",
                          verticalAlign: "top",
                          "&:last-of-type": {
                            borderRight: 0,
                          },
                        }}>
                        <Typography variant="body2" fontWeight="bold">
                          {formatSqlCell(column.key, sqlTotalsRow[column.key])}
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                </Box>
              </Box>
            </Box>
          )}
          {(hasMoreSqlRows || isSqlOverflowing) && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
              {t("scroll_to_load_more", { defaultValue: "Scroll to see all features" })}
            </Typography>
          )}
        </Box>
      )}
    </>
  );
};
