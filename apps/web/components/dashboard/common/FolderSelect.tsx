import Autocomplete from "@mui/material/Autocomplete";
import Chip from "@mui/material/Chip";
import InputAdornment from "@mui/material/InputAdornment";
import ListItem from "@mui/material/ListItem";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import TextField from "@mui/material/TextField";
import React from "react";
import { useTranslation } from "react-i18next";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import type { Folder } from "@/lib/validations/folder";

interface FolderSelectProps {
  folders: Folder[] | undefined;
  selectedFolder: Folder | null | undefined;
  setSelectedFolder: (folder: Folder | null) => void;
}

const FolderSelect = ({ folders, selectedFolder, setSelectedFolder }: FolderSelectProps) => {
  const { t } = useTranslation("common");

  return (
    <Autocomplete
      fullWidth
      value={selectedFolder ?? null}
      onChange={(_event, newValue) => {
        setSelectedFolder(newValue);
      }}
      autoHighlight
      isOptionEqualToValue={(option, value) => option.id === value.id}
      id="folder-select"
      options={folders ? [...folders] : []}
      getOptionLabel={(option) => {
        if (typeof option === "string") return option;
        return option.name;
      }}
      renderOption={(props, option) => (
        <ListItem key={option.id} {...props}>
          <ListItemIcon>
            <Icon iconName={ICON_NAME.FOLDER} style={{ marginLeft: 2 }} fontSize="small" />
          </ListItemIcon>
          <ListItemText
            primary={option.name}
            secondary={
              !option.is_owned
                ? option.role === "folder-editor"
                  ? t("write_access")
                  : t("read_access")
                : undefined
            }
          />
          {!option.is_owned && (
            <Chip
              label={t("shared")}
              size="small"
              sx={{ ml: 1, height: 18, fontSize: "10px", "& .MuiChip-label": { px: 0.75 } }}
            />
          )}
        </ListItem>
      )}
      renderInput={(params) => (
        <TextField
          {...params}
          fullWidth
          sx={{ mt: 4 }}
          InputProps={{
            ...params.InputProps,
            startAdornment: (
              <InputAdornment position="start">
                <Icon iconName={ICON_NAME.FOLDER} style={{ marginLeft: 2 }} fontSize="small" />
              </InputAdornment>
            ),
          }}
          label={t("select_folder_destination")}
        />
      )}
    />
  );
};

export default FolderSelect;
