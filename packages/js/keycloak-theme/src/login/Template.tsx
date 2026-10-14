import { Alert, Stack, Typography, useTheme } from "@mui/material";
import DarkModeSwitch from "@p4b/ui/components/DarkModeSwitch";
import LanguageDropdown from "@p4b/ui/components/LanguageDropdown";
import AuthLayout from "@p4b/ui/components/AuthLayout";
import AuthContainer from "@p4b/ui/components/AuthContainer";
import type { I18n } from "./i18n";
import { ColorModeContext, type KcContext } from "./kcContext";
import type { TemplateProps } from "keycloakify/login/TemplateProps";
import { useContext } from "react";

import clip1 from "../assets/clips/slide-1.mp4";
import clip2 from "../assets/clips/slide-2.mp4";
import clip3 from "../assets/clips/slide-3.mp4";
import clip4 from "../assets/clips/slide-4.mp4";
import clip5 from "../assets/clips/slide-5.mp4";
import clip6 from "../assets/clips/slide-6.mp4";

/** GOAT in motion, from the website's GOAT page (shortened, silent, 960 px). */
const CLIPS = [clip1, clip2, clip3, clip4, clip5, clip6];
export default function Template(props: TemplateProps<KcContext, I18n>) {
  const theme = useTheme();
  const colorMode = useContext(ColorModeContext);
  const {
    displayInfo = false,
    displayMessage = true,
    headerNode,
    infoNode = null,
    kcContext,
    i18n,
    children,
  } = props;
  const { realm, locale, message, isAppInitiatedAction } = kcContext;
  const {
    msg,
    msgStr,
    changeLocale,
    labelBySupportedLanguageTag,
    currentLanguageTag,
  } = i18n;
  return (
    <AuthLayout
      sx={{
        fontFamily: "'Mulish', sans-serif",
      }}
      aside={{ title: msg("authAsideTitle"), text: msg("authAsideText") }}
      clips={CLIPS}
    >
      <AuthContainer
        headerTitle={<Typography variant="h5">{headerNode}</Typography>}
        headerAlert={
          displayMessage &&
          message !== undefined &&
          (message.type !== "warning" || !isAppInitiatedAction) && (
            <Alert severity={message.type}>{message.summary}</Alert>
          )
        }
        body={children}
        footer={
          displayInfo && (
            <Stack
              spacing={theme.spacing(2)}
              sx={{
                mt: theme.spacing(4),
                textAlign: "left",
              }}
            >
              {infoNode}
            </Stack>
          )
        }
        otherFooterActions={
          [
            "register-user-profile.ftl",
            "login.ftl",
            "login-username.ftl",
          ].includes(kcContext.pageId) && (
            <>
              {realm.internationalizationEnabled &&
                locale &&
                locale.supported.length > 1 && (
                  <LanguageDropdown
                    toolTipProps={{
                      title: msgStr("changeLanguage"),
                      placement: "top",
                    }}
                    languages={labelBySupportedLanguageTag}
                    selected={currentLanguageTag}
                    onLanguageChange={changeLocale}
                  />
                )}
              <DarkModeSwitch
                sx={{
                  ml: theme.spacing(2),
                }}
                size="small"
                onClick={() => {
                  colorMode.toggleColorMode();
                }}
                toolTipProps={{
                  title: msgStr("changeTheme"),
                  placement: "top",
                }}
                isDarkModeEnabled={theme.palette.mode === "dark"}
              />
            </>
          )
        }
      />
    </AuthLayout>
  );
}
