import type { SxProps } from "@mui/material";
import { Box, Typography } from "@mui/material";
import Grid from "@mui/material/Unstable_Grid2";

import authScreenshot from "../assets/img/auth-screenshot.webp";
import { GOATLogoFullWhite } from "../assets/svg/GOATLogoFullWhite";

/** The URL of a bundled image. The photo is imported, so each app's bundler
 * ships it with its own build and serves it from wherever that build lives:
 * Next.js yields `{ src }`, Create React App (the Keycloak theme) a string. */
const importedUrl = (image: unknown): string =>
  typeof image === "string" ? image : (image as { src: string }).src;

const SCREENSHOT_URL = importedUrl(authScreenshot);

export interface AuthAside {
  title: React.ReactNode;
  text?: React.ReactNode;
}

/** Sign-in, sign-up and onboarding pages: the form on the left; on the right
 * the GOAT logo, the app itself (the screenshot from the website's GOAT page)
 * and an optional claim. On phones and tablets only the form is shown. */
export default function AuthLayout({
  children,
  sx,
  aside,
}: {
  children: React.ReactNode;
  sx?: SxProps;
  aside?: AuthAside;
}) {
  return (
    <Box
      component="main"
      sx={{
        display: "flex",
        flex: "1 1 auto",
        ...sx,
      }}
    >
      <Grid container sx={{ flex: "1 1 auto" }}>
        <Grid
          xs={12}
          lg={6}
          sx={{
            minHeight: "100vh",
            display: "flex",
            flexDirection: "column",
            position: "relative",
          }}
        >
          <Box
            component="div"
            sx={{
              flex: "1 1 auto",
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              alignItems: "center",
              py: 6,
              px: 2,
            }}
          >
            {children}
          </Box>
        </Grid>
        <Grid
          xs={12}
          lg={6}
          sx={{
            display: { xs: "none", lg: "flex" },
            flexDirection: "column",
            justifyContent: "space-between",
            gap: 6,
            py: 8,
            pl: 8,
            overflow: "hidden",
            color: "#fff",
            background: "radial-gradient(120% 80% at 100% 50%, #22324a 0%, #161f2c 60%)",
          }}
        >
          <Box role="img" aria-label="GOAT" sx={{ width: 170, "& svg": { display: "block", width: "100%" } }}>
            <GOATLogoFullWhite />
          </Box>
          <Box
            component="img"
            src={SCREENSHOT_URL}
            alt=""
            sx={{
              display: "block",
              width: "118%",
              maxWidth: "none",
              borderRadius: "12px 0 0 12px",
              border: "1px solid rgba(255,255,255,0.12)",
              boxShadow: "0 30px 80px rgba(0,0,0,0.45)",
            }}
          />
          {aside ? (
            <Box sx={{ maxWidth: 480, pr: 8 }}>
              <Typography variant="h4" component="p" sx={{ fontWeight: 700, lineHeight: 1.25, color: "inherit" }}>
                {aside.title}
              </Typography>
              {aside.text && (
                <Typography variant="body1" sx={{ mt: 2, opacity: 0.8, color: "inherit" }}>
                  {aside.text}
                </Typography>
              )}
            </Box>
          ) : (
            <Box />
          )}
        </Grid>
      </Grid>
    </Box>
  );
}
