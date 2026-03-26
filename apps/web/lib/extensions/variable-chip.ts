import { mergeAttributes, Node } from "@tiptap/core";

export interface VariableChipOptions {
  HTMLAttributes: Record<string, unknown>;
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    variableChip: {
      insertVariable: (name: string) => ReturnType;
    };
  }
}

const VariableChip = Node.create<VariableChipOptions>({
  name: "variableChip",
  group: "inline",
  inline: true,
  atom: true,

  addOptions() {
    return {
      HTMLAttributes: {},
    };
  },

  addAttributes() {
    return {
      variableName: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-variable"),
        renderHTML: (attributes) => ({
          "data-variable": attributes.variableName,
        }),
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: "span[data-variable]",
      },
    ];
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
        "data-variable": node.attrs.variableName,
        class: "variable-chip",
      }),
      `{{@${node.attrs.variableName}}}`,
    ];
  },

  addCommands() {
    return {
      insertVariable:
        (name: string) =>
        ({ commands }) => {
          return commands.insertContent({
            type: this.name,
            attrs: { variableName: name },
          });
        },
    };
  },
});

export default VariableChip;
