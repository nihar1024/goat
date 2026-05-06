import { Box } from "@mui/material";

import type { ProjectLayer, ProjectLayerGroup } from "@/lib/validations/project";
import type { WidgetInformationConfig } from "@/lib/validations/widget";
import { informationTypes } from "@/lib/validations/widget";

import WidgetDescription from "@/components/builder/widgets/common/WidgetDescription";
import WidgetTitle from "@/components/builder/widgets/common/WidgetTitle";
import { LayerInformationWidget } from "@/components/builder/widgets/information/Layers";

interface WidgetInformationProps {
  widgetId: string;
  config: WidgetInformationConfig;
  projectLayers: ProjectLayer[];
  projectLayerGroups: ProjectLayerGroup[];
  viewOnly?: boolean;
}

const WidgetInformation: React.FC<WidgetInformationProps> = ({
  widgetId,
  config,
  projectLayers,
  projectLayerGroups,
  viewOnly,
}) => {
  return (
    <Box>
      <WidgetTitle title={config.setup?.title} />
      {config.type === informationTypes.Values.layers && (
        <LayerInformationWidget
          widgetId={widgetId}
          config={config}
          projectLayers={projectLayers}
          projectLayerGroups={projectLayerGroups}
          viewOnly={viewOnly}
        />
      )}
      <WidgetDescription description={config.options?.description} sx={{ mt: 1 }} />
    </Box>
  );
};

export default WidgetInformation;
