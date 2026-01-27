"use client";

import { Delete as DeleteIcon, ContentCopy as DuplicateIcon } from "@mui/icons-material";
import { Box, IconButton, Stack, Tooltip, Typography } from "@mui/material";
import { styled } from "@mui/material/styles";
import { Handle, type NodeProps, NodeToolbar, Position } from "@xyflow/react";
import React, { memo, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useDispatch, useSelector } from "react-redux";
import { v4 as uuidv4 } from "uuid";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import type { AppDispatch } from "@/lib/store";
import { selectNodes } from "@/lib/store/workflow/selectors";
import { addNode, removeNodes } from "@/lib/store/workflow/slice";
import type { DatasetNodeData } from "@/lib/validations/workflow";

const NodeContainer = styled(Box, {
  shouldForwardProp: (prop) => prop !== "selected",
})<{ selected?: boolean }>(({ theme, selected }) => ({
  padding: theme.spacing(1.5),
  borderRadius: theme.shape.borderRadius,
  backgroundColor: theme.palette.background.paper,
  border: `2px solid ${selected ? theme.palette.primary.main : theme.palette.divider}`,
  // Box-shadow for selection indicator (blue glow)
  boxShadow: selected ? `0 0 0 4px ${theme.palette.primary.main}40, ${theme.shadows[4]}` : theme.shadows[2],
  minWidth: 160,
  maxWidth: 220,
  transition: "all 0.2s ease",
  position: "relative",
  "&:hover": {
    boxShadow: selected ? `0 0 0 4px ${theme.palette.primary.main}40, ${theme.shadows[4]}` : theme.shadows[4],
  },
}));

const NodeHeader = styled(Box)(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(1),
  marginBottom: theme.spacing(0.5),
}));

const NodeIconWrapper = styled(Box)(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  width: 40,
  height: 40,
  minWidth: 40,
  borderRadius: theme.shape.borderRadius,
  border: `1px solid ${theme.palette.divider}`,
  backgroundColor: theme.palette.background.default,
}));

const StyledHandle = styled(Handle, {
  shouldForwardProp: (prop) => prop !== "selected",
})<{ selected?: boolean }>(({ theme, selected }) => ({
  width: 12,
  height: 12,
  backgroundColor: selected ? theme.palette.primary.main : theme.palette.grey[500],
  border: `2px solid ${theme.palette.background.paper}`,
}));

const ToolbarContainer = styled(Stack)(({ theme }) => ({
  backgroundColor: theme.palette.background.paper,
  borderRadius: theme.shape.borderRadius,
  padding: theme.spacing(0.5),
  gap: theme.spacing(0.5),
  flexDirection: "row",
  boxShadow: theme.shadows[4],
  border: `1px solid ${theme.palette.divider}`,
}));

const ToolbarButton = styled(IconButton)(({ theme }) => ({
  padding: theme.spacing(0.5),
  "&:hover": {
    backgroundColor: theme.palette.action.hover,
  },
  "& svg": {
    fontSize: 18,
  },
}));

interface DatasetNodeProps extends NodeProps {
  data: DatasetNodeData;
}

const DatasetNode: React.FC<DatasetNodeProps> = ({ id, data, selected }) => {
  const { t } = useTranslation("common");
  const dispatch = useDispatch<AppDispatch>();
  const nodes = useSelector(selectNodes);

  // Get geometry icon based on layer type
  const getGeometryIcon = () => {
    switch (data.geometryType) {
      case "point":
        return ICON_NAME.POINT_FEATURE;
      case "line":
        return ICON_NAME.LINE_FEATURE;
      case "polygon":
        return ICON_NAME.POLYGON_FEATURE;
      default:
        return ICON_NAME.TABLE;
    }
  };

  // Handle duplicate node
  const handleDuplicate = useCallback(
    (event: React.MouseEvent) => {
      event.stopPropagation();
      const node = nodes.find((n) => n.id === id);
      if (!node) return;

      dispatch(
        addNode({
          ...node,
          id: `dataset-${uuidv4()}`,
          position: {
            x: node.position.x + 50,
            y: node.position.y + 50,
          },
        })
      );
    },
    [id, nodes, dispatch]
  );

  // Handle delete node
  const handleDelete = useCallback(
    (event: React.MouseEvent) => {
      event.stopPropagation();
      dispatch(removeNodes([id]));
    },
    [id, dispatch]
  );

  return (
    <>
      {/* NodeToolbar - automatically shown when selected */}
      <NodeToolbar position={Position.Top} align="end">
        <ToolbarContainer>
          <Tooltip title={t("duplicate")} arrow>
            <ToolbarButton onClick={handleDuplicate}>
              <DuplicateIcon />
            </ToolbarButton>
          </Tooltip>
          <Tooltip title={t("delete")} arrow>
            <ToolbarButton onClick={handleDelete}>
              <DeleteIcon />
            </ToolbarButton>
          </Tooltip>
        </ToolbarContainer>
      </NodeToolbar>

      <NodeContainer selected={selected}>
        {/* Output handle - right */}
        <StyledHandle type="source" position={Position.Right} selected={selected} />

        <NodeHeader>
          <NodeIconWrapper>
            <Icon iconName={getGeometryIcon()} sx={{ fontSize: 20, color: "text.secondary" }} />
          </NodeIconWrapper>
          <Typography variant="body2" fontWeight="bold" sx={{ wordBreak: "break-word" }}>
            {data.layerId ? data.label : t("no_dataset")}
          </Typography>
        </NodeHeader>
      </NodeContainer>
    </>
  );
};

export default memo(DatasetNode);
