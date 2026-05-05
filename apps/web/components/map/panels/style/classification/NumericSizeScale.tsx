import { Box, MenuItem, Select, Stack, TextField, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { formatNumber } from "@/lib/utils/helpers";
import type { ClassBreaks, LayerClassBreaks, SizeOrdinalMap } from "@/lib/validations/layer";
import { classBreaks } from "@/lib/validations/layer";

type Props = {
  type: "stroke_width" | "radius" | "marker_size";
  selectedScaleMethod: ClassBreaks;
  classBreaksValues: LayerClassBreaks | undefined;
  numSteps: number;
  sizeRange: [number, number];
  ordinalMap?: SizeOrdinalMap;
  onScaleMethodChange: (method: ClassBreaks) => void;
  onNumStepsChange: (steps: number) => void;
  onBreaksChange?: (breaks: number[]) => void;
  onOrdinalMapChange?: (map: SizeOrdinalMap) => void;
  setIsClickAwayEnabled?: (enabled: boolean) => void;
};

function SizePreview({
  type,
  size,
  maxSize,
}: {
  type: "stroke_width" | "radius" | "marker_size";
  size: number;
  maxSize: number;
}) {
  const theme = useTheme();
  const color = theme.palette.text.primary;
  const isLine = type === "stroke_width";

  if (isLine) {
    const displayWidth = Math.max(1, (size / Math.max(maxSize, 1)) * 8);
    return (
      <svg width="32" height="20" style={{ flexShrink: 0 }}>
        <line x1="2" y1="10" x2="30" y2="10" stroke={color} strokeWidth={displayWidth} strokeLinecap="round" />
      </svg>
    );
  }

  const displayRadius = Math.max(2, (size / Math.max(maxSize, 1)) * 9);
  return (
    <svg width="32" height="20" style={{ flexShrink: 0 }}>
      <circle cx="16" cy="10" r={displayRadius} fill={color} />
    </svg>
  );
}

const SCALE_OPTIONS = classBreaks.options as ClassBreaks[];

const NumericSizeScale = ({
  type,
  selectedScaleMethod,
  classBreaksValues,
  numSteps,
  sizeRange,
  ordinalMap,
  onScaleMethodChange,
  onNumStepsChange,
  onBreaksChange,
  onOrdinalMapChange,
  setIsClickAwayEnabled,
}: Props) => {
  const { t } = useTranslation("common");
  const breaks = classBreaksValues?.breaks ?? [];
  const N = breaks.length + 1;

  const sizes = Array.from({ length: N }, (_, i) =>
    N === 1 ? sizeRange[0] : sizeRange[0] + (sizeRange[1] - sizeRange[0]) * (i / (N - 1))
  );

  const isCustomBreaks = selectedScaleMethod === "custom_breaks";
  const isOrdinal = selectedScaleMethod === "ordinal";

  // Local state for editable break values (string so user can type freely)
  const [editableBreaks, setEditableBreaks] = useState<string[]>(() => breaks.map(String));

  useEffect(() => {
    setEditableBreaks((prev) => {
      const next = breaks.map(String);
      return prev.length === next.length && prev.every((v, i) => v === next[i]) ? prev : next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classBreaksValues]);

  // Local state for ordinal map size edits
  const [editableOrdinalSizes, setEditableOrdinalSizes] = useState<string[]>(() =>
    (ordinalMap ?? []).map(([, sz]) => String(sz))
  );

  useEffect(() => {
    setEditableOrdinalSizes((prev) => {
      const next = (ordinalMap ?? []).map(([, sz]) => String(sz));
      return prev.length === next.length && prev.every((v, i) => v === next[i]) ? prev : next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ordinalMap]);

  const commitBreaks = () => {
    const parsed = editableBreaks.map(Number);
    if (parsed.every((n) => !isNaN(n))) {
      onBreaksChange?.(parsed);
    }
  };

  const commitOrdinalSizes = (idx: number, rawValue: string) => {
    const parsed = Number(rawValue);
    if (isNaN(parsed) || !ordinalMap) return;
    const newMap: SizeOrdinalMap = ordinalMap.map(([val, sz], i) => [val, i === idx ? parsed : sz]);
    onOrdinalMapChange?.(newMap);
  };

  const methodSelect = (
    <Select
      fullWidth
      size="small"
      IconComponent={() => null}
      value={selectedScaleMethod}
      onOpen={() => setIsClickAwayEnabled?.(false)}
      MenuProps={{
        TransitionProps: {
          onExited: () => setIsClickAwayEnabled?.(true),
        },
      }}
      onChange={(e) => onScaleMethodChange(e.target.value as ClassBreaks)}>
      {SCALE_OPTIONS.map((option) => (
        <MenuItem key={option} value={option}>
          {t(option)}
        </MenuItem>
      ))}
    </Select>
  );

  // Ordinal layout
  if (isOrdinal) {
    return (
      <Box sx={{ pt: 3, pb: 3, pl: 3, pr: 3, display: "flex", flexDirection: "column", gap: 2 }}>
        {methodSelect}
        {!ordinalMap?.length ? null : (
          <Stack spacing={1}>
            {ordinalMap.map(([value, sz], i) => {
              const displaySize = Number(editableOrdinalSizes[i] ?? sz);
              return (
                <Stack key={i} direction="row" alignItems="center" spacing={1}>
                  <SizePreview type={type} size={isNaN(displaySize) ? sz : displaySize} maxSize={sizeRange[1]} />
                  <TextField
                    size="small"
                    disabled
                    value={value}
                    InputProps={{ sx: { height: "28px" } }}
                    sx={{
                      flex: 2,
                      "& .MuiOutlinedInput-input": { padding: "0 8px", fontSize: 12 },
                    }}
                  />
                  <TextField
                    size="small"
                    type="number"
                    value={editableOrdinalSizes[i] ?? sz}
                    inputProps={{ min: sizeRange[0], max: sizeRange[1] }}
                    onChange={(e) => {
                      const next = [...editableOrdinalSizes];
                      next[i] = e.target.value;
                      setEditableOrdinalSizes(next);
                    }}
                    onBlur={(e) => commitOrdinalSizes(i, e.target.value)}
                    InputProps={{ sx: { height: "28px" } }}
                    sx={{
                      flex: 1,
                      "& .MuiOutlinedInput-input": { padding: "0 8px", fontSize: 12 },
                    }}
                  />
                </Stack>
              );
            })}
          </Stack>
        )}
      </Box>
    );
  }

  // Numeric (quantile / equal_interval / std_dev / custom_breaks)
  return (
    <Box sx={{ pt: 3, pb: 3, pl: 3, pr: 3, display: "flex", flexDirection: "column", gap: 2 }}>
      {methodSelect}

      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="caption">
          {t("min")}: <b>{classBreaksValues?.min != null ? formatNumber(classBreaksValues.min) : "—"}</b>
        </Typography>
        {!isCustomBreaks && (
          <Select
            size="small"
            value={numSteps}
            onOpen={() => setIsClickAwayEnabled?.(false)}
            MenuProps={{
              TransitionProps: {
                onExited: () => setIsClickAwayEnabled?.(true),
              },
            }}
            onChange={(e) => onNumStepsChange(Number(e.target.value))}
            sx={{ minWidth: 90 }}>
            {[2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
              <MenuItem key={n} value={n}>
                {n} {t("steps")}
              </MenuItem>
            ))}
          </Select>
        )}
        <Typography variant="caption">
          {t("max")}: <b>{classBreaksValues?.max != null ? formatNumber(classBreaksValues.max) : "—"}</b>
        </Typography>
      </Stack>

      <Stack spacing={1}>
        {sizes.map((size, i) => {
          const startVal =
            i === 0
              ? `<${classBreaksValues?.min != null ? formatNumber(classBreaksValues.min) : "—"}`
              : isCustomBreaks
                ? editableBreaks[i - 1] ?? ""
                : formatNumber(breaks[i - 1], 2);

          const endEditable = isCustomBreaks && i < sizes.length - 1;
          const endVal =
            i === sizes.length - 1
              ? `>${classBreaksValues?.max != null ? formatNumber(classBreaksValues.max) : "—"}`
              : isCustomBreaks
                ? editableBreaks[i] ?? ""
                : formatNumber(breaks[i], 2);

          return (
            <Stack key={i} direction="row" alignItems="center" spacing={1}>
              <SizePreview type={type} size={size} maxSize={sizeRange[1]} />
              <Typography variant="caption" sx={{ minWidth: 28, textAlign: "right", flexShrink: 0 }}>
                {formatNumber(size, 1)}
              </Typography>
              <TextField
                size="small"
                disabled
                value={startVal}
                InputProps={{ sx: { height: "28px" } }}
                sx={{
                  flex: 1,
                  "& .MuiOutlinedInput-input": { padding: "0 8px", fontSize: 12 },
                }}
              />
              <Typography variant="body2">-</Typography>
              <TextField
                size="small"
                disabled={!endEditable}
                value={endVal}
                onChange={
                  endEditable
                    ? (e) => {
                        const next = [...editableBreaks];
                        next[i] = e.target.value;
                        setEditableBreaks(next);
                      }
                    : undefined
                }
                onBlur={endEditable ? commitBreaks : undefined}
                InputProps={{ sx: { height: "28px" } }}
                sx={{
                  flex: 1,
                  "& .MuiOutlinedInput-input": { padding: "0 8px", fontSize: 12 },
                }}
              />
            </Stack>
          );
        })}
      </Stack>
    </Box>
  );
};

export default NumericSizeScale;
