import ExecutionEnvironment from "@docusaurus/ExecutionEnvironment";

const MATOMO_BASE = "https://plan4better.matomo.cloud/";
const MATOMO_SCRIPT = "https://cdn.matomo.cloud/plan4better.matomo.cloud/matomo.js";
const SITE_ID = "6";

/** URL of the last tracked page view, sent as the referrer of the next one.
 * Held here rather than derived from the router location, which is relative
 * to the `/docs/` baseUrl. */
let lastTrackedHref = null;

/** Title of the last tracked page view, used to detect when Helmet has
 * applied the new route's title. */
let lastTrackedTitle = null;

const TITLE_POLL_MS = 50;
const TITLE_TIMEOUT_MS = 1000;

function queue() {
  return (window._paq = window._paq || []);
}

if (ExecutionEnvironment.canUseDOM) {
  const _paq = queue();
  // Must precede the first trackPageView, otherwise that request still sets
  // the _pk_id and _pk_ses cookies.
  _paq.push(["disableCookies"]);
  // Without a heartbeat the last page of a visit records zero time on page.
  _paq.push(["enableHeartBeatTimer"]);
  _paq.push(["trackPageView"]);
  _paq.push(["enableLinkTracking"]);
  (function () {
    _paq.push(["setTrackerUrl", `${MATOMO_BASE}matomo.php`]);
    _paq.push(["setSiteId", SITE_ID]);
    const d = document;
    const g = d.createElement("script");
    const s = d.getElementsByTagName("script")[0];
    g.async = true;
    g.src = MATOMO_SCRIPT;
    s.parentNode.insertBefore(g, s);
  })();

  lastTrackedHref = window.location.href;
  lastTrackedTitle = document.title;
}

/** Docusaurus is a single-page app after hydration, so only the first page of
 * a visit reaches Matomo through the snippet above. Every subsequent
 * navigation is tracked here. */
export function onRouteDidUpdate({ location, previousLocation }) {
  // A changed hash alone means the reader jumped to a heading on the same
  // page, which is not a page view.
  if (!previousLocation || location.pathname === previousLocation.pathname) {
    return;
  }

  const referrer = lastTrackedHref;
  const previousTitle = lastTrackedTitle;
  const deadline = Date.now() + TITLE_TIMEOUT_MS;

  const send = () => {
    const href = window.location.href;
    const _paq = queue();
    if (referrer) {
      _paq.push(["setReferrerUrl", referrer]);
    }
    _paq.push(["setCustomUrl", href]);
    _paq.push(["setDocumentTitle", document.title]);
    _paq.push(["trackPageView"]);
    // Re-scan for links rendered by the new route.
    _paq.push(["enableLinkTracking"]);
    lastTrackedHref = href;
    lastTrackedTitle = document.title;
  };

  // Docusaurus sets document.title through Helmet after this fires, so the
  // page view waits until the title changes. Two routes can legitimately
  // share a title, hence the deadline.
  const whenTitleApplied = () => {
    if (document.title !== previousTitle || Date.now() >= deadline) {
      send();
    } else {
      setTimeout(whenTitleApplied, TITLE_POLL_MS);
    }
  };
  setTimeout(whenTitleApplied, 0);
}
