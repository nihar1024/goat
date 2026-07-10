import { useTheme } from "@mui/material";
import { DateTimePicker } from "@mui/x-date-pickers/DateTimePicker";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import dayjs, { type Dayjs } from "dayjs";

const OUTPUT_FORMAT = "YYYY-MM-DDTHH:mm:ss";

const parseValue = (value?: string): Dayjs | null => {
  if (!value) return null;
  const parsed = dayjs(value);
  return parsed.isValid() ? parsed : null;
};

type TemporalPickerProps = {
  kind?: "datetime";
  value?: string;
  onChange: (value: string) => void;
  label?: string;
};

export default function TemporalPicker(props: TemporalPickerProps) {
  const theme = useTheme();

  const handleChange = (next: Dayjs | null) => {
    props.onChange(next && next.isValid() ? next.format(OUTPUT_FORMAT) : "");
  };

  return (
    <LocalizationProvider dateAdapter={AdapterDayjs}>
      <DateTimePicker
        label={props.label}
        value={parseValue(props.value)}
        onChange={handleChange}
        slotProps={{
          textField: { size: "small", fullWidth: true },
          actionBar: { actions: [] },
        }}
        sx={{
          "& .MuiInputBase-root": {
            height: "40px",
            fontSize: theme.typography.body2.fontSize,
            color: theme.palette.text.secondary,
          },
        }}
      />
    </LocalizationProvider>
  );
}
