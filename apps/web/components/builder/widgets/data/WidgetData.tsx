import { Box, Typography } from "@mui/material";

import type { ProjectLayer } from "@/lib/validations/project";
import { type WidgetDataConfig, dataTypes } from "@/lib/validations/widget";

import FilterWidget from "@/components/builder/widgets/data/Filter";
import NumbersWidget from "@/components/builder/widgets/data/Numbers";

interface WidgetDataProps {
  id: string;
  config: WidgetDataConfig;
  projectLayers: ProjectLayer[];
  viewOnly?: boolean;
}

const WidgetData: React.FC<WidgetDataProps> = ({ id, config, projectLayers, viewOnly }) => {
  return (
    <Box sx={{ width: "100%" }}>
      <Typography variant="body1" fontWeight="bold" align="left" gutterBottom>
        {config.setup?.title}
      </Typography>
      {config.type === dataTypes.Values.numbers && (
        <NumbersWidget config={config} projectLayers={projectLayers} viewOnly={viewOnly} />
      )}
      {config.type === dataTypes.Values.filter && (
        <FilterWidget id={id} config={config} projectLayers={projectLayers} viewOnly={viewOnly} />
      )}
      {config.options?.description && (
        <Typography variant="body1" align="left">
          {config.options.description}
        </Typography>
      )}
    </Box>
  );
};

export default WidgetData;
