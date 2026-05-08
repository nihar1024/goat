import { Box } from "@mui/material";

import type { ProjectLayer } from "@/lib/validations/project";
import { type RichTextDataSchema, type TableDataSchema, type WidgetDataConfig, dataTypes } from "@/lib/validations/widget";

import { NumbersDataWidget } from "@/components/builder/widgets/data/Numbers";
import { RichTextDataWidget } from "@/components/builder/widgets/data/RichText";
import { TableDataWidget } from "@/components/builder/widgets/data/Table";
import { FilterDataWidget } from "@/components/builder/widgets/data/WidgetFilter";
import WidgetDescription from "@/components/builder/widgets/common/WidgetDescription";
import WidgetTitle from "@/components/builder/widgets/common/WidgetTitle";

interface WidgetDataProps {
  id: string;
  config: WidgetDataConfig;
  projectLayers: ProjectLayer[];
  viewOnly?: boolean;
  onConfigChange?: (nextConfig: WidgetDataConfig) => void;
}

const WidgetData: React.FC<WidgetDataProps> = ({ id, config, projectLayers, viewOnly, onConfigChange }) => {
  if (config.type === dataTypes.Values.rich_text) {
    return (
      <Box sx={{ width: "100%", height: "100%" }}>
        <RichTextDataWidget
          config={config as unknown as RichTextDataSchema}
          projectLayers={projectLayers}
          viewOnly={viewOnly}
          onConfigChange={onConfigChange as ((nextConfig: RichTextDataSchema) => void) | undefined}
        />
      </Box>
    );
  }

  return (
    <Box sx={{ width: "100%" }}>
      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
      <WidgetTitle title={(config.setup as any)?.title} />
      {config.type === dataTypes.Values.numbers && (
        <NumbersDataWidget config={config} projectLayers={projectLayers} viewOnly={viewOnly} />
      )}
      {config.type === dataTypes.Values.filter && (
        <FilterDataWidget id={id} config={config} projectLayers={projectLayers} viewOnly={viewOnly} />
      )}
      {config.type === dataTypes.Values.table && (
        <TableDataWidget
          widgetId={id}
          config={config}
          projectLayers={projectLayers}
          viewOnly={viewOnly}
          onConfigChange={onConfigChange as ((nextConfig: TableDataSchema) => void) | undefined}
        />
      )}
      <WidgetDescription description={config.options?.description} sx={{ mt: 0.5 }} />
    </Box>
  );
};

export default WidgetData;
