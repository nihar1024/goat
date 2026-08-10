import BrowserOnly from "@docusaurus/BrowserOnly";
import React, { useEffect, useRef } from "react";

const OPT_OUT_SRC =
  "https://plan4better.matomo.cloud/index.php?module=CoreAdminHome&action=optOutJS" +
  "&divId=matomo-opt-out&language=auto&showIntro=1";

function OptOutForm() {
  const wrapper = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = wrapper.current;
    if (!node || node.querySelector("script")) {
      return;
    }
    // Matomo renders the form into the element matching `divId`. A <script>
    // written as JSX never executes, so it is appended here instead. It goes
    // on the wrapper rather than the target so Matomo's own markup does not
    // replace it.
    const script = document.createElement("script");
    script.src = OPT_OUT_SRC;
    script.async = true;
    node.appendChild(script);
  }, []);

  return (
    <div ref={wrapper}>
      <div id="matomo-opt-out" />
    </div>
  );
}

/** Matomo's opt-out form. Renders client-side only: it depends on the tracker
 * origin, and with JavaScript disabled there is no tracking to opt out of. */
export default function MatomoOptOut(): React.ReactElement {
  return <BrowserOnly fallback={<div />}>{() => <OptOutForm />}</BrowserOnly>;
}
