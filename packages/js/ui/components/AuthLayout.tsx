import type { SxProps } from "@mui/material";
import { Box, Typography } from "@mui/material";
import Grid from "@mui/material/Unstable_Grid2";
import { useEffect, useState } from "react";

import slide1 from "../assets/img/auth-slide-1.webp";
import slide2 from "../assets/img/auth-slide-2.webp";
import slide3 from "../assets/img/auth-slide-3.webp";
import slide4 from "../assets/img/auth-slide-4.webp";
import slide5 from "../assets/img/auth-slide-5.webp";
import slide6 from "../assets/img/auth-slide-6.webp";
import { GOATLogoFullWhite } from "../assets/svg/GOATLogoFullWhite";

/** The URL of a bundled image. The photo is imported, so each app's bundler
 * ships it with its own build and serves it from wherever that build lives:
 * Next.js yields `{ src }`, Create React App (the Keycloak theme) a string. */
const importedUrl = (image: unknown): string =>
  typeof image === "string" ? image : (image as { src: string }).src;

/** GOAT as it looks today: the screens from the website's GOAT page. */
const SLIDES = [slide1, slide2, slide3, slide4, slide5, slide6].map(importedUrl);
const SLIDE_SECONDS = 6;

/** Cross-fades through the slides; holds still for people who prefer less motion. */
function useSlide(count: number): [number, (index: number) => void] {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    const reduced =
      typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced || count < 2) return;
    const timer = window.setInterval(() => setIndex((i) => (i + 1) % count), SLIDE_SECONDS * 1000);
    return () => window.clearInterval(timer);
  }, [count]);
  return [index, setIndex];
}

export interface AuthAside {
  title: React.ReactNode;
  text?: React.ReactNode;
}

/** Sign-in, sign-up and onboarding pages: the form on the left; on the right
 * the GOAT logo, the app itself (a slider of the website's GOAT screens) and an
 * optional claim. On phones and tablets only the form is shown. */
export default function AuthLayout({
  children,
  sx,
  aside,
}: {
  children: React.ReactNode;
  sx?: SxProps;
  aside?: AuthAside;
}) {
  const [slide, setSlide] = useSlide(SLIDES.length);
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
          <Box sx={{ position: "relative" }}>
            <Box
              sx={{
                position: "relative",
                width: "118%",
                aspectRatio: "1280 / 696",
                borderRadius: "12px 0 0 12px",
                overflow: "hidden",
                border: "1px solid rgba(255,255,255,0.12)",
                boxShadow: "0 30px 80px rgba(0,0,0,0.45)",
                backgroundColor: "#0f1622",
              }}>
              {SLIDES.map((src, i) => (
                <Box
                  key={src}
                  component="img"
                  src={src}
                  alt=""
                  loading={i === 0 ? "eager" : "lazy"}
                  sx={{
                    position: "absolute",
                    inset: 0,
                    width: "100%",
                    height: "100%",
                    objectFit: "cover",
                    objectPosition: "left top",
                    opacity: i === slide ? 1 : 0,
                    transition: "opacity 900ms ease",
                    "@media (prefers-reduced-motion: reduce)": { transition: "none" },
                  }}
                />
              ))}
            </Box>
            <Box sx={{ display: "flex", gap: 1, mt: 3 }}>
              {SLIDES.map((src, i) => (
                <Box
                  key={src}
                  component="button"
                  type="button"
                  aria-label={`${i + 1} / ${SLIDES.length}`}
                  aria-current={i === slide}
                  onClick={() => setSlide(i)}
                  sx={{
                    width: i === slide ? 22 : 8,
                    height: 8,
                    p: 0,
                    border: 0,
                    borderRadius: 4,
                    cursor: "pointer",
                    backgroundColor: i === slide ? "#2bb381" : "rgba(255,255,255,0.35)",
                    transition: "width 300ms ease, background-color 300ms ease",
                    "&:focus-visible": { outline: "2px solid #fff", outlineOffset: 2 },
                  }}
                />
              ))}
            </Box>
          </Box>
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
