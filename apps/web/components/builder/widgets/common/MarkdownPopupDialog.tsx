import CloseIcon from "@mui/icons-material/Close";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import { Box, Dialog, DialogContent, DialogTitle, IconButton, Typography } from "@mui/material";
import ReactMarkdown from "react-markdown";

interface MarkdownPopupDialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  content: string;
}

const MarkdownPopupDialog = ({ open, onClose, title, content }: MarkdownPopupDialogProps) => (
  <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
    <DialogTitle sx={{ pr: 6 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <InfoOutlinedIcon sx={{ fontSize: 20, color: "primary.main", opacity: 0.75, flexShrink: 0 }} />
        <Typography variant="h6">{title}</Typography>
      </Box>
      <IconButton
        size="small"
        onClick={onClose}
        sx={{ position: "absolute", right: 12, top: 12 }}>
        <CloseIcon fontSize="small" />
      </IconButton>
    </DialogTitle>
    <DialogContent dividers>
      <Box
        sx={{
          "& p": { mb: 1.5, lineHeight: 1.7 },
          "& p:last-child": { mb: 0 },
          "& h1, & h2, & h3": { mt: 2, mb: 1, fontWeight: 700 },
          "& h1:first-of-type, & h2:first-of-type, & h3:first-of-type": { mt: 0 },
          "& h1": { fontSize: "1.1rem" },
          "& h2": { fontSize: "1rem" },
          "& h3": { fontSize: "0.9rem" },
          "& strong": { fontWeight: 700 },
          "& a": { color: "primary.main" },
          "& ul, & ol": { pl: 2.5, mb: 1.5 },
          "& li": { mb: 0.5 },
        }}>
        <ReactMarkdown>{content}</ReactMarkdown>
      </Box>
    </DialogContent>
  </Dialog>
);

export default MarkdownPopupDialog;
