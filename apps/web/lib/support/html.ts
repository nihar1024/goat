import DOMPurify from "dompurify";

// Client-only: DOMParser and DOMPurify need a window, so call this from client components.
// Odoo message bodies: agents' replies and customers' emails. No images
// (their URLs carry Odoo tokens and core strips them anyway), no styles.
const ALLOWED_TAGS = [
  "#text",
  "p",
  "div",
  "span",
  "br",
  "hr",
  "blockquote",
  "pre",
  "code",
  "strong",
  "b",
  "em",
  "i",
  "u",
  "s",
  "small",
  "sub",
  "sup",
  "a",
  "ul",
  "ol",
  "li",
  "table",
  "thead",
  "tbody",
  "tr",
  "th",
  "td",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
];
const ALLOWED_ATTR = ["href", "target", "rel", "colspan", "rowspan"];
// Odoo's mail parser marks signatures and quoted history with these attributes.
const QUOTE_SELECTOR = "[data-o-mail-quote], [data-o-mail-quote-container]";

// ALLOW_DATA_ATTR lets every data-* attribute through the sanitizer, which the
// quote detection below needs; none of them may reach the rendered output.
const stripDataAttributes = (root: Element) => {
  [root, ...Array.from(root.querySelectorAll("*"))].forEach((el) => {
    Array.from(el.attributes).forEach((attr) => {
      if (attr.name.startsWith("data-")) el.removeAttribute(attr.name);
    });
  });
};

export const prepareSupportHtml = (html: string): { main: string; quoted: string } => {
  const clean = DOMPurify.sanitize(html, { ALLOWED_TAGS, ALLOWED_ATTR, ALLOW_DATA_ATTR: true });
  const doc = new DOMParser().parseFromString(`<body>${clean}</body>`, "text/html");
  // Before the quotes are extracted, so links inside `quoted` get the same treatment.
  doc.body.querySelectorAll("a").forEach((a) => {
    a.setAttribute("target", "_blank");
    a.setAttribute("rel", "noopener noreferrer");
  });
  const quotedEls: Element[] = [];
  doc.body.querySelectorAll(QUOTE_SELECTOR).forEach((el) => {
    if (el.parentElement?.closest(QUOTE_SELECTOR)) return; // nested: moved with its parent
    quotedEls.push(el);
    el.remove();
  });
  stripDataAttributes(doc.body);
  quotedEls.forEach(stripDataAttributes);
  return { main: doc.body.innerHTML.trim(), quoted: quotedEls.map((el) => el.outerHTML).join("") };
};
