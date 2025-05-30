/* eslint-disable @typescript-eslint/no-explicit-any */
import { Box } from "@mui/material";

import type { BuilderWidgetSchema, ProjectLayer } from "@/lib/validations/project";
import type {
  WidgetChartConfig,
  WidgetDataConfig,
  WidgetElementConfig,
  WidgetInformationConfig,
} from "@/lib/validations/widget";
import { chartTypes, dataTypes, elementTypes, informationTypes } from "@/lib/validations/widget";

import WidgetChart from "@/components/builder/widgets/chart/WidgetChart";
import WidgetData from "@/components/builder/widgets/data/WidgetData";
import WidgetElement from "@/components/builder/widgets/elements/WidgetElement";
import WidgetInformation from "@/components/builder/widgets/information/WidgetInformation";

interface WidgetWrapper {
  widget: BuilderWidgetSchema;
  projectLayers: ProjectLayer[];
  viewOnly?: boolean;
}

const WidgetWrapper: React.FC<WidgetWrapper> = ({ widget, projectLayers, viewOnly }) => {
  return (
    <Box sx={{ width: "100%", p: 2, pointerEvents: "all" }}>
      {widget.config?.type && informationTypes.options.includes(widget.config?.type as any) && (
        <WidgetInformation
          config={widget.config as WidgetInformationConfig}
          projectLayers={projectLayers}
          viewOnly={viewOnly}
        />
      )}
      {widget.config?.type && dataTypes.options.includes(widget.config?.type as any) && (
        <WidgetData
          id={widget.id}
          config={widget.config as WidgetDataConfig}
          projectLayers={projectLayers}
          viewOnly={viewOnly}
        />
      )}
      {widget.config?.type && chartTypes.options.includes(widget.config?.type as any) && (
        <WidgetChart config={widget.config as WidgetChartConfig} viewOnly={viewOnly} />
      )}
      {widget.config?.type && elementTypes.options.includes(widget.config?.type as any) && (
        <WidgetElement config={widget.config as WidgetElementConfig} viewOnly={viewOnly} />
      )}
    </Box>
  );
};

export default WidgetWrapper;
