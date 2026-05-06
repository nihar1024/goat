import { Box } from "@mui/material";

import type { WidgetChartConfig } from "@/lib/validations/widget";
import { chartTypes } from "@/lib/validations/widget";

import { CategoriesChartWidget } from "@/components/builder/widgets/chart/Categories";
import { HistogramChartWidget } from "@/components/builder/widgets/chart/Histogram";
import { PieChartWidget } from "@/components/builder/widgets/chart/Pie";
import WidgetDescription from "@/components/builder/widgets/common/WidgetDescription";
import WidgetTitle from "@/components/builder/widgets/common/WidgetTitle";

interface WidgetChartProps {
  config: WidgetChartConfig;
  viewOnly?: boolean;
}

const WidgetChart: React.FC<WidgetChartProps> = ({ config }) => {
  return (
    <Box sx={{ minHeight: config.type === chartTypes.Values.categories_chart ? "auto" : 200 }}>
      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
      <WidgetTitle title={(config.setup as any)?.title} />
      {config.type === chartTypes.Values.histogram_chart && <HistogramChartWidget config={config} />}
      {config.type === chartTypes.Values.pie_chart && <PieChartWidget config={config} />}
      {config.type === chartTypes.Values.categories_chart && <CategoriesChartWidget config={config} />}
      <WidgetDescription description={config.options?.description} sx={{ mt: 0.5 }} />
    </Box>
  );
};

export default WidgetChart;
