import { mergeAttributes, Node } from "@tiptap/core";

import type { PopupPlacement, PopupSize, PopupType } from "@/lib/validations/widget";

export type InfoChipPopupType = PopupType;
export type InfoChipPlacement = PopupPlacement;
export type InfoChipSize = PopupSize;

export interface InfoChipOptions {
  HTMLAttributes: Record<string, unknown>;
}

export interface InfoChipUpdateAttrs {
  text?: string;
  url?: string;
  title?: string;
  popup_type?: InfoChipPopupType;
  placement?: InfoChipPlacement;
  size?: InfoChipSize;
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    infoChip: {
      insertInfoChip: () => ReturnType;
      updateInfoChip: (attrs: InfoChipUpdateAttrs) => ReturnType;
      deleteInfoChip: () => ReturnType;
    };
  }
}

const InfoChip = Node.create<InfoChipOptions>({
  name: "infoChip",
  group: "inline",
  inline: true,
  atom: true,
  selectable: true,

  addOptions() {
    return {
      HTMLAttributes: {},
    };
  },

  addAttributes() {
    return {
      infoId: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-info-id"),
        renderHTML: (attributes) => ({
          "data-info-id": attributes.infoId,
        }),
      },
      text: {
        default: "",
        parseHTML: (element) => element.getAttribute("data-info-text"),
        renderHTML: (attributes) => ({
          "data-info-text": attributes.text,
        }),
      },
      url: {
        default: "",
        parseHTML: (element) => element.getAttribute("data-info-url"),
        renderHTML: (attributes) => {
          if (!attributes.url) return {};
          return { "data-info-url": attributes.url };
        },
      },
      title: {
        default: "",
        parseHTML: (element) => element.getAttribute("data-info-title"),
        renderHTML: (attributes) => {
          if (!attributes.title) return {};
          return { "data-info-title": attributes.title };
        },
      },
      popup_type: {
        default: "popover" as InfoChipPopupType,
        parseHTML: (element) => element.getAttribute("data-popup-type") || "popover",
        renderHTML: (attributes) => ({
          "data-popup-type": attributes.popup_type,
        }),
      },
      placement: {
        default: "auto" as InfoChipPlacement,
        parseHTML: (element) => element.getAttribute("data-placement") || "auto",
        renderHTML: (attributes) => ({
          "data-placement": attributes.placement,
        }),
      },
      size: {
        default: "md" as InfoChipSize,
        parseHTML: (element) => element.getAttribute("data-popup-size") || "md",
        renderHTML: (attributes) => ({
          "data-popup-size": attributes.size,
        }),
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: "span[data-info-id]",
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
        class: "info-chip",
      }),
      // Explicit nested element with literal text content. Some ProseMirror
      // serializer paths treat a bare string in this position as a tag name
      // (producing an empty <i></i>) which makes the chip render as an empty
      // circle. Using ["i", {}, "i"] is unambiguous: <i>i</i>.
      ["i", {}, "i"],
    ];
  },

  addCommands() {
    return {
      insertInfoChip:
        () =>
        ({ commands }) => {
          const id = `info_${Date.now()}`;
          return commands.insertContent({
            type: this.name,
            attrs: {
              infoId: id,
              text: "",
              url: "",
              title: "",
              popup_type: "popover",
              placement: "auto",
              size: "md",
            },
          });
        },
      updateInfoChip:
        (attrs) =>
        ({ tr, state, dispatch }) => {
          const { selection } = state;
          const node = state.doc.nodeAt(selection.from);
          if (!node || node.type.name !== "infoChip") return false;
          if (dispatch) {
            tr.setNodeMarkup(selection.from, undefined, {
              ...node.attrs,
              ...attrs,
            });
            dispatch(tr);
          }
          return true;
        },
      deleteInfoChip:
        () =>
        ({ tr, state, dispatch }) => {
          const { selection } = state;
          const node = state.doc.nodeAt(selection.from);
          if (!node || node.type.name !== "infoChip") return false;
          if (dispatch) {
            tr.delete(selection.from, selection.from + node.nodeSize);
            dispatch(tr);
          }
          return true;
        },
    };
  },
});

export default InfoChip;
