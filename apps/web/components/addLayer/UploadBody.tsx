"use client";

import {
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { useTranslation } from "react-i18next";

import type { UploadFlow } from "@/hooks/addLayer/useUploadFlow";

import { MuiFileInput } from "@/components/common/FileInput";
import FolderSelect from "@/components/dashboard/common/FolderSelect";

/**
 * The Upload flow's content: file, tabular configuration, destination + metadata,
 * confirmation. One step at a time, chosen by the controller.
 *
 * Renders no frame, no footer and no width of its own — see `FlowController`.
 */
const UploadBody = ({ controller }: { controller: UploadFlow }) => {
  const { t } = useTranslation("common");
  const { step, steps, upload } = controller;
  const lastStep = steps.length - 1;
  // With a tabular file the flow gains a step, which shifts everything after it.
  const previewStep = upload.isTabular ? 1 : -1;
  const metadataStep = upload.isTabular ? 2 : 1;

  if (step === 0) {
    return (
      <>
        <Typography variant="caption">{t("select_file_to_upload")}</Typography>
        <MuiFileInput
          sx={{ my: 2 }}
          inputProps={{ accept: upload.acceptedFileTypes.join(",") }}
          fullWidth
          error={!!upload.fileError}
          helperText={upload.fileError}
          value={upload.file}
          multiple={false}
          onChange={upload.setFile}
          placeholder={`${t("eg")} file.gpkg, file.geojson, file.parquet, shapefile.zip`}
        />
        <Typography variant="caption">
          {t("supported")} <b>GeoPackage</b>, <b>GeoJSON</b>, <b>Shapefile (.zip)</b>, <b>KML</b>,{" "}
          <b>CSV</b>, <b>XLSX</b>, <b>Parquet</b>
        </Typography>
      </>
    );
  }

  if (step === previewStep) {
    return (
      <Stack direction="column" spacing={3}>
        {/* Only a multi-sheet workbook needs to be asked. */}
        {upload.preview && upload.preview.sheetNames.length > 1 && (
          <TextField
            select
            fullWidth
            size="small"
            label={t("worksheet")}
            value={upload.sheet}
            onChange={(event) => upload.setSheet(event.target.value)}>
            {upload.preview.sheetNames.map((name) => (
              <MenuItem key={name} value={name}>
                {name}
              </MenuItem>
            ))}
          </TextField>
        )}

        <FormControlLabel
          control={
            <Switch
              checked={upload.hasHeader}
              onChange={(event) => upload.setHasHeader(event.target.checked)}
              color="primary"
              size="small"
            />
          }
          label={
            <Typography variant="body2" fontWeight="bold">
              {t("first_row_is_header")}
            </Typography>
          }
        />

        {upload.preview && upload.preview.headers.length > 0 && (
          <>
            <TableContainer
              sx={{ maxHeight: 280, border: 1, borderColor: "divider", borderRadius: 1 }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    {upload.preview.headers.map((header, index) => (
                      <TableCell key={index} sx={{ fontWeight: "bold", whiteSpace: "nowrap" }}>
                        {header}
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {upload.preview.rows.map((row, rowIndex) => (
                    <TableRow key={rowIndex}>
                      {row.map((cell, cellIndex) => (
                        <TableCell
                          key={cellIndex}
                          sx={{
                            whiteSpace: "nowrap",
                            maxWidth: 200,
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                          }}>
                          <Typography variant="body2">{cell}</Typography>
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            <Typography variant="caption" color="text.secondary">
              {t("showing_first_rows", {
                count: upload.preview.rows.length,
                total: upload.preview.totalRows,
              })}
            </Typography>
            {!upload.hasHeader && (
              <Typography variant="caption" color="text.secondary">
                {t("rename_columns_hint")}
              </Typography>
            )}
          </>
        )}
      </Stack>
    );
  }

  if (step === metadataStep) {
    return (
      <Stack direction="column" spacing={4}>
        <FolderSelect
          folders={upload.folders}
          selectedFolder={upload.selectedFolder}
          setSelectedFolder={upload.setSelectedFolder}
        />
        <TextField
          fullWidth
          required
          defaultValue={upload.suggestedName}
          label={t("name")}
          {...upload.register("name")}
          error={!!upload.errors.name}
          helperText={upload.errors.name?.message}
        />
        <TextField
          fullWidth
          multiline
          rows={4}
          label={t("description")}
          {...upload.register("description")}
          error={!!upload.errors.description}
          helperText={upload.errors.description?.message}
        />
      </Stack>
    );
  }

  if (step === lastStep) {
    return (
      <Stack direction="column" spacing={4}>
        <Typography variant="caption">{t("review")}</Typography>
        <Typography variant="body2">
          <b>{t("file")}:</b> {upload.file?.name}
        </Typography>
        <Typography variant="body2">
          <b>{t("destination")}:</b> {upload.selectedFolder?.name}
        </Typography>
        <Typography variant="body2">
          <b>{t("name")}:</b> {upload.values.name}
        </Typography>
        <Typography variant="body2">
          <b>{t("description")}:</b> {upload.values.description}
        </Typography>
      </Stack>
    );
  }

  return null;
};

export default UploadBody;
