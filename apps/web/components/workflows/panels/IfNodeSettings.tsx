"use client";

import {
  Block as BlockIcon,
  DataObject as VariableIcon,
  Delete as DeleteIcon,
} from "@mui/icons-material";
import {
  Box,
  Button,
  Chip,
  Divider,
  IconButton,
  InputAdornment,
  ListItemIcon,
  Menu,
  MenuItem,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useEdges } from "@xyflow/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useDispatch, useSelector } from "react-redux";
import { v4 as uuidv4 } from "uuid";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import type { AppDispatch, RootState } from "@/lib/store";
import {
  selectNodes,
  selectVariables,
} from "@/lib/store/workflow/selectors";
import { updateNode } from "@/lib/store/workflow/slice";
import {
  type Expression as ExpressionType,
  FilterType,
} from "@/lib/validations/filter";
import {
  type IfNodeData,
  type IfSpatialExpression,
  type IfStatisticExpression,
  type WorkflowNode,
  type WorkflowVariable,
} from "@/lib/validations/workflow";

import type { LayerFieldType } from "@/lib/validations/layer";

import type { SelectorItem } from "@/types/map/common";

import useLayerFields from "@/hooks/map/CommonHooks";
import useLogicalExpressionOperations from "@/hooks/map/FilteringHooks";

import FormLabelHelper from "@/components/common/FormLabelHelper";
import Container from "@/components/map/panels/Container";
import LayerFieldSelector from "@/components/map/common/LayerFieldSelector";
import Selector from "@/components/map/panels/common/Selector";
import ToolsHeader from "@/components/map/panels/common/ToolsHeader";
import { useNodeExecutionStatus } from "@/components/workflows/context/WorkflowExecutionContext";

interface IfNodeSettingsProps {
  node: WorkflowNode;
  onBack: () => void;
}

interface ConditionState {
  op: "and" | "or";
  expressions: Array<ExpressionType | IfStatisticExpression | IfSpatialExpression>;
}

/** Type guards: identify each row variant in the heterogeneous expressions array. */
const isStatisticRow = (
  e: ExpressionType | IfStatisticExpression | IfSpatialExpression
): e is IfStatisticExpression => (e as IfStatisticExpression).kind === "statistic";

const isSpatialRow = (
  e: ExpressionType | IfStatisticExpression | IfSpatialExpression
): e is IfSpatialExpression => (e as IfSpatialExpression).kind === "spatial";

const VARIABLE_REF_REGEX = /^\{\{@([a-zA-Z_][a-zA-Z0-9_]*)\}\}$/;

/** Operators that produce a boolean from the field alone — no value input. */
const VALUE_LESS_OPERATORS = new Set([
  "is_blank",
  "is_not_blank",
  "is_empty_string",
  "is_not_empty_string",
]);

/** Operators that take a list of values; user enters them comma-separated. */
const MULTI_VALUE_OPERATORS = new Set(["includes", "excludes"]);

/** Operators hidden from the logical-row dropdown because they read
 * misleadingly under the implicit "any feature matches" semantic.
 * Example: "name Is 'München'" looks like layer equality but actually means
 * "any feature is named München" — almost always not what users intend. */
const LOGICAL_OPERATORS_REMOVED = new Set([
  "is",
  "is_not",
  "is_blank",
  "is_not_blank",
  "is_empty_string",
  "is_not_empty_string",
  "does_not_contains_the_text",
]);

// --------------------------------------------------------------------------
// VariableTextField — TextField with a `{{@var}}` insertion adornment.
// Used by both row types so the value editor is consistent.
// --------------------------------------------------------------------------

interface VariableTextFieldProps {
  value: string;
  onChange: (next: string) => void;
  variables: WorkflowVariable[];
  placeholder?: string;
  /** Separator to insert before the variable when the field is non-empty
   *  (e.g. ", " for multi-value operators so picks form a comma list). */
  appendSeparator?: string;
}

function VariableTextField({
  value,
  onChange,
  variables,
  placeholder,
  appendSeparator,
}: VariableTextFieldProps) {
  const { t } = useTranslation("common");
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  const isVariableRef = VARIABLE_REF_REGEX.test(value);

  const insertVariable = useCallback(
    (varName: string) => {
      const token = `{{@${varName}}}`;
      const next = value ? `${value}${appendSeparator ?? ""}${token}` : token;
      onChange(next);
      setMenuOpen(false);
    },
    [value, onChange, appendSeparator]
  );

  return (
    <>
      <TextField
        size="small"
        fullWidth
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        sx={
          isVariableRef
            ? {
                "& input": {
                  color: "primary.main",
                  fontFamily: "monospace",
                  fontSize: "0.75rem",
                },
              }
            : undefined
        }
        InputProps={{
          endAdornment: (
            <InputAdornment position="end">
              <Tooltip
                title={t("insert_variable", { defaultValue: "Insert workflow variable" })}
                arrow>
                <IconButton
                  size="small"
                  ref={buttonRef}
                  onClick={() => setMenuOpen((v) => !v)}
                  sx={{ color: "text.secondary", "&:hover": { color: "primary.main" } }}>
                  <VariableIcon sx={{ fontSize: 16 }} />
                </IconButton>
              </Tooltip>
            </InputAdornment>
          ),
        }}
      />
      <Menu
        anchorEl={buttonRef.current}
        open={menuOpen}
        onClose={() => setMenuOpen(false)}>
        {variables.length === 0 ? (
          <MenuItem disabled>
            <Typography variant="caption" color="text.secondary">
              {t("no_workflow_variables_defined", {
                defaultValue: "No workflow variables defined yet",
              })}
            </Typography>
          </MenuItem>
        ) : (
          variables.map((v) => (
            <MenuItem key={v.id} onClick={() => insertVariable(v.name)}>
              <Typography variant="body2" fontFamily="monospace">
                {`{{@${v.name}}}`}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                ({v.type})
              </Typography>
            </MenuItem>
          ))
        )}
      </Menu>
    </>
  );
}

// --------------------------------------------------------------------------
// Shared row-header — icon + title on the left, delete button on the right.
// --------------------------------------------------------------------------

function ConditionRowHeader({
  iconName,
  title,
  onDelete,
}: {
  iconName: ICON_NAME;
  title: string;
  onDelete: () => void;
}) {
  const { t } = useTranslation("common");
  return (
    <Stack direction="row" justifyContent="space-between" alignItems="center">
      <Stack direction="row" alignItems="center">
        <Icon
          iconName={iconName}
          style={{ fontSize: 17, color: "var(--mui-palette-text-secondary, #888)" }}
        />
        <Typography variant="body2" fontWeight="bold" sx={{ pl: 2 }}>
          {title}
        </Typography>
      </Stack>
      <Tooltip title={t("delete")} arrow placement="top">
        <IconButton size="small" onClick={onDelete}>
          <DeleteIcon fontSize="small" color="error" />
        </IconButton>
      </Tooltip>
    </Stack>
  );
}

// --------------------------------------------------------------------------
// LogicalConditionRow — logical-filter editor with free-form value input.
//
// Replaces the canonical <Expression> component for if-node use because the
// filter's value picker (SelectorLayerValue) only offers values that already
// exist in the layer. In a conditional we need to test arbitrary thresholds
// AND workflow-variable references, so the value editor is a free-form
// TextField with the same {{@var}} adornment as StatisticConditionRow.
//
// Reuses the same primitives the filter UI uses: LayerFieldSelector for the
// field, Selector for the operator, useLogicalExpressionOperations for the
// operator list (which adapts to field type — string vs number vs date), and
// the same `Expression` data shape — so the backend CQL pipeline (which turns
// the Expression into DuckDB SQL) needs no changes.
// --------------------------------------------------------------------------

interface LogicalConditionRowProps {
  expression: ExpressionType;
  layerId?: string;
  variables: WorkflowVariable[];
  onUpdate: (next: ExpressionType) => void;
  onDelete: (id: string) => void;
}

function LogicalConditionRow({
  expression,
  layerId,
  variables,
  onUpdate,
  onDelete,
}: LogicalConditionRowProps) {
  const { t } = useTranslation("common");
  const { layerFields } = useLayerFields(layerId || "");

  const selectedField = useMemo(
    () => (layerFields || []).find((f) => f.name === expression.attribute),
    [layerFields, expression.attribute]
  );

  const { logicalExpressionTypes: rawOperators } = useLogicalExpressionOperations(
    selectedField?.type
  );

  // Hide operators whose semantic is misleading under "any feature matches".
  const logicalExpressionTypes = useMemo(
    () =>
      rawOperators.filter(
        (o) => !LOGICAL_OPERATORS_REMOVED.has(String(o.value))
      ),
    [rawOperators]
  );

  const selectedOperation = useMemo(
    () => logicalExpressionTypes.find((o) => o.value === expression.expression),
    [logicalExpressionTypes, expression.expression]
  );

  const showValue =
    !!selectedField &&
    !!expression.expression &&
    !VALUE_LESS_OPERATORS.has(expression.expression);

  return (
    <Stack direction="column">
      <ConditionRowHeader
        iconName={ICON_NAME.TABLE}
        title={t("logical_expression", { defaultValue: "Logical Expression" })}
        onDelete={() => onDelete(expression.id)}
      />

      <Stack direction="column" spacing={2}>
        <LayerFieldSelector
          fields={layerFields || []}
          selectedField={selectedField}
          setSelectedField={(field) =>
            onUpdate({
              ...expression,
              attribute: field?.name || "",
              expression: "",
              value: "",
            })
          }
          label={t("select_field")}
        />

        {selectedField && (
          <Selector
            selectedItems={selectedOperation}
            setSelectedItems={(item) => {
              const op = (item as SelectorItem | undefined)?.value as string | undefined;
              if (!op) return;
              onUpdate({ ...expression, expression: op, value: "" });
            }}
            items={logicalExpressionTypes}
            label={t("select_operator")}
          />
        )}

        {showValue && (
          <Box>
            <FormLabelHelper
              label={t("select_value")}
              color="inherit"
              tooltip={
                MULTI_VALUE_OPERATORS.has(expression.expression)
                  ? t("multi_value_hint", { defaultValue: "Enter multiple values separated by commas" })
                  : undefined
              }
            />
            <VariableTextField
              value={
                Array.isArray(expression.value)
                  ? expression.value.map(String).join(", ")
                  : String(expression.value ?? "")
              }
              onChange={(next) => {
                if (MULTI_VALUE_OPERATORS.has(expression.expression)) {
                  const parts = next
                    .split(",")
                    .map((s) => s.trim())
                    .filter((s) => s.length > 0);
                  onUpdate({ ...expression, value: parts });
                } else {
                  onUpdate({ ...expression, value: next });
                }
              }}
              variables={variables}
              appendSeparator={
                MULTI_VALUE_OPERATORS.has(expression.expression) ? ", " : undefined
              }
              placeholder={
                MULTI_VALUE_OPERATORS.has(expression.expression)
                  ? t("multi_value_placeholder", {
                      defaultValue: "value1, value2, value3",
                    })
                  : t("select_value")
              }
            />
          </Box>
        )}
      </Stack>
    </Stack>
  );
}

// --------------------------------------------------------------------------
// SpatialConditionRow — cross-layer geometric condition.
//
// Evaluates a spatial predicate between the if-node's upstream input layer
// and a comparison layer wired to the node's `comparison_layer_id` handle.
// The comparison layer is purely a reference for the boolean check — it
// never flows downstream; only `input_layer_id` propagates to True/False.
//
// Reuses the same primitives the other row types use: ConditionRowHeader,
// Selector, FormLabelHelper, VariableTextField. The 8 spatial relations
// mirror the predicates supported by goatlib's CQL evaluator.
// --------------------------------------------------------------------------

const SPATIAL_RELATIONS: { value: NonNullable<IfSpatialExpression["relation"]>; labelKey: string }[] = [
  { value: "intersects", labelKey: "spatial_intersects" },
  { value: "within", labelKey: "spatial_within" },
  { value: "contains", labelKey: "spatial_contains" },
  { value: "touches", labelKey: "spatial_touches" },
  { value: "crosses", labelKey: "spatial_crosses" },
  { value: "overlaps", labelKey: "spatial_overlaps" },
  { value: "disjoint", labelKey: "spatial_disjoint" },
  { value: "within_distance", labelKey: "spatial_within_distance" },
];

interface SpatialConditionRowProps {
  expression: IfSpatialExpression;
  comparisonWired: boolean;
  variables: WorkflowVariable[];
  onUpdate: (next: IfSpatialExpression) => void;
  onDelete: (id: string) => void;
}

function SpatialConditionRow({
  expression,
  comparisonWired,
  variables,
  onUpdate,
  onDelete,
}: SpatialConditionRowProps) {
  const { t } = useTranslation("common");

  const relationItems: SelectorItem[] = useMemo(
    () =>
      SPATIAL_RELATIONS.map((r) => ({
        value: r.value,
        label: t(r.labelKey, { defaultValue: r.value }),
      })),
    [t]
  );

  const selectedRelation = useMemo(
    () => relationItems.find((r) => r.value === expression.relation),
    [relationItems, expression.relation]
  );

  const showDistance = expression.relation === "within_distance";

  return (
    <Stack direction="column">
      <ConditionRowHeader
        iconName={ICON_NAME.GLOBE}
        title={t("spatial_expression", { defaultValue: "Spatial Expression" })}
        onDelete={() => onDelete(expression.id)}
      />

      <Stack direction="column" spacing={2}>
        <Selector
          selectedItems={selectedRelation}
          setSelectedItems={(item) => {
            const r = (item as SelectorItem | undefined)?.value as
              | NonNullable<IfSpatialExpression["relation"]>
              | undefined;
            if (!r) return;
            onUpdate({
              ...expression,
              relation: r,
              // Drop stale distance when leaving within_distance.
              distance: r === "within_distance" ? expression.distance : undefined,
            });
          }}
          items={relationItems}
          label={t("select_operator")}
        />

        {showDistance && (
          <Box>
            <FormLabelHelper
              label={t("spatial_distance_label", { defaultValue: "Distance (meters)" })}
              color="inherit"
            />
            <VariableTextField
              value={
                expression.distance === undefined || expression.distance === null
                  ? ""
                  : String(expression.distance)
              }
              onChange={(next) => {
                if (!next) {
                  onUpdate({ ...expression, distance: undefined });
                  return;
                }
                // Preserve {{@var}} as a string; otherwise coerce to number when valid.
                const asNum = Number(next);
                onUpdate({
                  ...expression,
                  distance: Number.isFinite(asNum) && !next.includes("{{") ? asNum : next,
                });
              }}
              variables={variables}
              placeholder={t("spatial_distance_placeholder", { defaultValue: "e.g. 500" })}
            />
          </Box>
        )}

        {!comparisonWired && (
          <Typography variant="caption" color="warning.main" sx={{ display: "block" }}>
            {t("comparison_layer_missing", {
              defaultValue:
                "Wire a comparison layer to the side handle to use spatial checks.",
            })}
          </Typography>
        )}
      </Stack>
    </Stack>
  );
}

// --------------------------------------------------------------------------
// StatisticConditionRow — small inline editor for aggregate-style conditions
// --------------------------------------------------------------------------

interface StatisticConditionRowProps {
  expression: IfStatisticExpression;
  layerId?: string;
  variables: WorkflowVariable[];
  onUpdate: (next: IfStatisticExpression) => void;
  onDelete: (id: string) => void;
}

type StatisticMethod = NonNullable<IfStatisticExpression["method"]>;
type ComparisonOperator = NonNullable<IfStatisticExpression["operator"]>;

const STATISTIC_METHODS: { value: StatisticMethod; labelKey: string }[] = [
  { value: "count", labelKey: "count" },
  { value: "sum", labelKey: "sum" },
  { value: "mean", labelKey: "mean" },
  { value: "median", labelKey: "median" },
  { value: "min", labelKey: "min" },
  { value: "max", labelKey: "max" },
];

const COMPARISON_OPERATORS: { value: ComparisonOperator; labelKey: string }[] = [
  { value: "=", labelKey: "filter_expressions.is" },
  { value: "!=", labelKey: "filter_expressions.is_not" },
  { value: ">", labelKey: "filter_expressions.is_greater_than" },
  { value: ">=", labelKey: "filter_expressions.is_at_least" },
  { value: "<", labelKey: "filter_expressions.is_less_than" },
  { value: "<=", labelKey: "filter_expressions.is_at_most" },
];

function StatisticConditionRow({
  expression,
  layerId,
  variables,
  onUpdate,
  onDelete,
}: StatisticConditionRowProps) {
  const { t } = useTranslation("common");
  const { layerFields } = useLayerFields(layerId || "");

  const methodItems: SelectorItem[] = useMemo(
    () =>
      STATISTIC_METHODS.map((m) => ({
        value: m.value,
        label: t(m.labelKey, { defaultValue: m.value }),
      })),
    [t]
  );

  const operatorItems: SelectorItem[] = useMemo(
    () => COMPARISON_OPERATORS.map((o) => ({ value: o.value, label: t(o.labelKey) })),
    [t]
  );

  // Numeric fields only for sum/mean/median/min/max; count(*) needs no field.
  const eligibleFields = useMemo<LayerFieldType[]>(() => {
    if (!layerFields) return [];
    if (expression.method === "count" || !expression.method) return layerFields;
    return layerFields.filter((f) => f.type === "number");
  }, [layerFields, expression.method]);

  const selectedField = useMemo(
    () => eligibleFields.find((f) => f.name === expression.field),
    [eligibleFields, expression.field]
  );

  // Show the field selector once the user has chosen a method (other than count).
  const fieldVisible = !!expression.method && expression.method !== "count";

  return (
    <Stack direction="column">
      <ConditionRowHeader
        iconName={ICON_NAME.CHART}
        title={t("statistic_expression", { defaultValue: "Statistic Expression" })}
        onDelete={() => onDelete(expression.id)}
      />

      <Stack direction="column" spacing={2}>
        <Selector
          selectedItems={methodItems.find((i) => i.value === expression.method)}
          setSelectedItems={(item) => {
            const m = (item as SelectorItem | undefined)?.value as
              | IfStatisticExpression["method"]
              | undefined;
            if (!m) return;
            onUpdate({
              ...expression,
              method: m,
              // Reset field when switching to/from count
              field: m === "count" ? undefined : expression.field,
            });
          }}
          items={methodItems}
          label={t("select_operation")}
          placeholder={t("select_option")}
        />

        {fieldVisible && (
          <LayerFieldSelector
            fields={eligibleFields}
            selectedField={selectedField}
            setSelectedField={(field) =>
              onUpdate({ ...expression, field: field?.name })
            }
            label={t("select_field")}
            tooltip={t("select_numeric_field_for_statistics")}
          />
        )}

        {/* Only show the comparison row once the method is set — otherwise the
            row is "empty by default" and the user picks the method first. */}
        {expression.method && (
          <>
            <Selector
              selectedItems={operatorItems.find((i) => i.value === expression.operator)}
              setSelectedItems={(item) => {
                const op = (item as SelectorItem | undefined)?.value as
                  | IfStatisticExpression["operator"]
                  | undefined;
                if (!op) return;
                onUpdate({ ...expression, operator: op });
              }}
              items={operatorItems}
              label={t("select_operator")}
            />
            <Box>
              <FormLabelHelper label={t("select_value")} color="inherit" />
              <VariableTextField
                value={String(expression.value ?? "")}
                onChange={(next) => onUpdate({ ...expression, value: next })}
                variables={variables}
                placeholder={t("select_value")}
              />
            </Box>
          </>
        )}
      </Stack>
    </Stack>
  );
}

// --------------------------------------------------------------------------
// IfNodeSettings — Conditional node settings panel
// --------------------------------------------------------------------------

export default function IfNodeSettings({ node, onBack }: IfNodeSettingsProps) {
  const { t } = useTranslation("common");
  const dispatch = useDispatch<AppDispatch>();
  const edges = useEdges();
  const nodes = useSelector((state: RootState) => selectNodes(state));
  const workflowVariables = useSelector(selectVariables);
  const { status: runtimeStatus } = useNodeExecutionStatus(node.id);

  const data = node.data as IfNodeData;

  // Resolve upstream input layer so the LogicalConditionRow / StatisticConditionRow
  // components know which field list to offer. The "main" input edge is any
  // incoming edge that isn't explicitly the comparison-layer side handle.
  const upstreamLayerId = useMemo(() => {
    const incoming = edges.find(
      (e) => e.target === node.id && e.targetHandle !== "comparison_layer_id"
    );
    if (!incoming) return undefined;
    const sourceNode = nodes.find((n) => n.id === incoming.source);
    if (!sourceNode) return undefined;
    const d = sourceNode.data as Record<string, unknown> | undefined;
    if (d?.type === "dataset" && typeof d.layerId === "string") return d.layerId;
    return undefined;
  }, [edges, node.id, nodes]);

  // True if a comparison layer is wired to the side handle.
  // The SpatialConditionRow uses this to show a "missing" hint if needed.
  const isComparisonLayerWired = useMemo(
    () =>
      edges.some(
        (e) => e.target === node.id && e.targetHandle === "comparison_layer_id"
      ),
    [edges, node.id]
  );

  const [condition, setCondition] = useState<ConditionState>(() => ({
    op: (data.condition?.op as "and" | "or") || "and",
    expressions: ((data.condition?.expressions as ConditionState["expressions"] | undefined) ?? []),
  }));

  // "Add expression" menu state
  const [menuAnchorEl, setMenuAnchorEl] = useState<null | HTMLElement>(null);
  const menuOpen = Boolean(menuAnchorEl);

  // Reset local state when the active node changes
  useEffect(() => {
    setCondition({
      op: (data.condition?.op as "and" | "or") || "and",
      expressions: ((data.condition?.expressions as ConditionState["expressions"] | undefined) ?? []),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [node.id]);

  const logicalOperators: SelectorItem[] = useMemo(
    () => [
      { value: "and", label: t("match_all_filters") },
      { value: "or", label: t("match_at_least_one_filter") },
    ],
    [t]
  );

  const persist = useCallback(
    (next: Partial<IfNodeData>) => {
      dispatch(
        updateNode({
          id: node.id,
          changes: { data: { ...data, ...next } },
        })
      );
    },
    [dispatch, node.id, data]
  );

  const saveCondition = useCallback(
    (next: ConditionState) => {
      setCondition(next);
      persist({
        condition:
          next.expressions.length > 0
            ? { op: next.op, expressions: next.expressions as Record<string, unknown>[] }
            : undefined,
      });
    },
    [persist]
  );

  const handleAddExpression = useCallback(
    (kind: "logical" | "statistic" | "spatial") => {
      setMenuAnchorEl(null);
      // Empty row — the user fills in the row-specific fields.
      let newRow: ExpressionType | IfStatisticExpression | IfSpatialExpression;
      if (kind === "statistic") {
        newRow = { id: uuidv4(), kind: "statistic" } as IfStatisticExpression;
      } else if (kind === "spatial") {
        newRow = { id: uuidv4(), kind: "spatial" } as IfSpatialExpression;
      } else {
        newRow = {
          id: uuidv4(),
          attribute: "",
          expression: "",
          value: "",
          type: FilterType.Logical,
        } as ExpressionType;
      }
      saveCondition({
        ...condition,
        expressions: [...condition.expressions, newRow],
      });
    },
    [condition, saveCondition]
  );

  const handleExpressionUpdate = useCallback(
    (updated: ExpressionType | IfStatisticExpression | IfSpatialExpression) => {
      saveCondition({
        ...condition,
        expressions: condition.expressions.map((e) => (e.id === updated.id ? updated : e)),
      });
    },
    [condition, saveCondition]
  );

  const handleExpressionDelete = useCallback(
    (id: string) => {
      saveCondition({
        ...condition,
        expressions: condition.expressions.filter((e) => e.id !== id),
      });
    },
    [condition, saveCondition]
  );

  const handleClearFilter = useCallback(() => {
    saveCondition({ op: condition.op, expressions: [] });
  }, [condition.op, saveCondition]);

  const handleOperatorChange = useCallback(
    (item: SelectorItem | SelectorItem[] | undefined) => {
      const op = (item as SelectorItem | undefined)?.value as "and" | "or" | undefined;
      if (!op) return;
      saveCondition({ ...condition, op });
    },
    [condition, saveCondition]
  );

  const areAllExpressionsValid = useMemo(
    () =>
      condition.expressions.every((e) => {
        if (isStatisticRow(e)) {
          const needsField = e.method !== "count";
          const v = String(e.value ?? "").trim();
          return !!e.method && !!e.operator && v !== "" && (!needsField || !!e.field);
        }
        if (isSpatialRow(e)) {
          if (!e.relation) return false;
          if (e.relation === "within_distance") {
            const d = e.distance;
            return d !== undefined && d !== null && String(d).trim() !== "";
          }
          return true;
        }
        const noValueOps = ["is_empty_string", "is_not_empty_string", "is_blank", "is_not_blank"];
        const hasValue = noValueOps.includes(e.expression || "") || !!e.value?.toString();
        return e.attribute && e.expression && hasValue;
      }),
    [condition.expressions]
  );

  const expressionTypeMenuItems = useMemo(
    () => [
      {
        kind: "logical" as const,
        icon: ICON_NAME.TABLE,
        label: t("logical_expression", { defaultValue: "Logical Expression" }),
      },
      {
        kind: "statistic" as const,
        icon: ICON_NAME.CHART,
        label: t("statistic_expression", { defaultValue: "Statistic Expression" }),
      },
      {
        kind: "spatial" as const,
        icon: ICON_NAME.GLOBE,
        label: t("spatial_expression", { defaultValue: "Spatial Expression" }),
      },
    ],
    [t]
  );

  return (
    <Container
      header={
        <ToolsHeader
          onBack={onBack}
          title={data.label || t("if_node", { defaultValue: "Conditional" })}
        />
      }
      disablePadding={false}
      body={
        <Box>
          <Typography variant="body2" sx={{ fontStyle: "italic", mb: 2 }}>
            {t("conditional_description", {
              defaultValue: "Evaluate a rule and decide how the workflow continues.",
            })}
          </Typography>

          {/* Execution Status Section */}
          <Box sx={{ mb: 2 }}>
            <Typography variant="body2" fontWeight="bold" color="text.secondary" sx={{ mb: 1 }}>
              {t("execution_status")}
            </Typography>
            <Divider sx={{ mb: 1.5 }} />
            <Chip
              label={runtimeStatus ? t(runtimeStatus, { defaultValue: runtimeStatus }) : t("idle")}
              size="small"
              icon={runtimeStatus === "skipped" ? <BlockIcon sx={{ fontSize: 14 }} /> : undefined}
              color={
                runtimeStatus === "completed"
                  ? "primary"
                  : runtimeStatus === "failed"
                    ? "error"
                    : runtimeStatus === "running"
                      ? "warning"
                      : "default"
              }
              variant={runtimeStatus ? "filled" : "outlined"}
              sx={{ fontWeight: 600, textTransform: "uppercase" }}
            />
          </Box>

          <Box>
              {/* Logical operator (only when 2+ expressions) */}
              {condition.expressions.length > 1 && (
                <Box sx={{ mb: 2 }}>
                  <Divider sx={{ mb: 2 }} />
                  <Selector
                    selectedItems={logicalOperators.find((o) => o.value === condition.op)}
                    setSelectedItems={handleOperatorChange}
                    items={logicalOperators}
                    label={t("filter_results")}
                  />
                </Box>
              )}

              {/* Expression list — all row types are if-node-owned components
                  that share the same primitives + VariableTextField. */}
              {condition.expressions.length > 0 && (
                <Stack spacing={2} sx={{ pt: 1 }}>
                  <Divider />
                  {condition.expressions.map((expression) => {
                    if (isStatisticRow(expression)) {
                      return (
                        <StatisticConditionRow
                          key={expression.id}
                          expression={expression}
                          layerId={upstreamLayerId}
                          variables={workflowVariables}
                          onUpdate={handleExpressionUpdate}
                          onDelete={handleExpressionDelete}
                        />
                      );
                    }
                    if (isSpatialRow(expression)) {
                      return (
                        <SpatialConditionRow
                          key={expression.id}
                          expression={expression}
                          comparisonWired={isComparisonLayerWired}
                          variables={workflowVariables}
                          onUpdate={handleExpressionUpdate}
                          onDelete={handleExpressionDelete}
                        />
                      );
                    }
                    return (
                      <LogicalConditionRow
                        key={expression.id}
                        expression={expression}
                        layerId={upstreamLayerId}
                        variables={workflowVariables}
                        onUpdate={handleExpressionUpdate}
                        onDelete={handleExpressionDelete}
                      />
                    );
                  })}
                </Stack>
              )}

              <Stack spacing={2} sx={{ pt: 3 }}>
                <Button
                  onClick={(e) => setMenuAnchorEl(e.currentTarget)}
                  fullWidth
                  size="small"
                  variant="outlined"
                  disabled={!upstreamLayerId || !areAllExpressionsValid}
                  startIcon={<Icon iconName={ICON_NAME.PLUS} style={{ fontSize: 15 }} />}
                  sx={{ borderRadius: 4, textTransform: "none", fontWeight: "bold" }}>
                  {t("add_expression")}
                </Button>

                {/* Type-of-expression menu (Logical / Statistic) */}
                <Menu
                  anchorEl={menuAnchorEl}
                  open={menuOpen}
                  onClose={() => setMenuAnchorEl(null)}
                  anchorOrigin={{ vertical: "top", horizontal: "center" }}
                  transformOrigin={{ vertical: "bottom", horizontal: "center" }}>
                  {expressionTypeMenuItems.map((item) => (
                    <MenuItem
                      key={item.kind}
                      onClick={() => handleAddExpression(item.kind)}>
                      <ListItemIcon>
                        <Icon iconName={item.icon} style={{ fontSize: 15 }} />
                      </ListItemIcon>
                      <Typography variant="body2">{item.label}</Typography>
                    </MenuItem>
                  ))}
                </Menu>

                <Button
                  variant="outlined"
                  fullWidth
                  size="small"
                  color="error"
                  disabled={condition.expressions.length === 0}
                  onClick={handleClearFilter}
                  sx={{ borderRadius: 4, textTransform: "none", fontWeight: "bold" }}>
                  {t("clear_filter")}
                </Button>
              </Stack>

              {!upstreamLayerId && (
                <Typography variant="caption" color="warning.main" sx={{ display: "block", mt: 2 }}>
                  {t("connect_dataset_node")}
                </Typography>
              )}
          </Box>
        </Box>
      }
    />
  );
}
