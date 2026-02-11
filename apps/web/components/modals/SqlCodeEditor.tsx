"use client";

import type { ReactCodeMirrorRef } from "@uiw/react-codemirror";
import CodeMirror from "@uiw/react-codemirror";
import { acceptCompletion } from "@codemirror/autocomplete";
import { sql, PostgreSQL } from "@codemirror/lang-sql";
import { Prec } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import { useTheme } from "@mui/material/styles";
import { useMemo } from "react";

// SQL keywords to auto-capitalize
const SQL_KEYWORDS = new Set([
  "select", "from", "where", "and", "or", "not", "in", "is", "null",
  "as", "on", "join", "left", "right", "inner", "outer", "cross",
  "full", "group", "by", "order", "having", "limit", "offset",
  "union", "all", "distinct", "insert", "into", "values", "update",
  "set", "delete", "create", "table", "drop", "alter", "index",
  "between", "like", "ilike", "exists", "case", "when", "then",
  "else", "end", "cast", "with", "recursive", "asc", "desc",
  "true", "false", "over", "partition", "rows", "range", "filter",
  "coalesce", "nullif", "using", "natural", "lateral", "fetch",
  "first", "next", "only", "except", "intersect",
]);

// Accept autocomplete and insert a trailing space
function acceptCompletionWithSpace(view: EditorView): boolean {
  if (acceptCompletion(view)) {
    const { head } = view.state.selection.main;
    view.dispatch(
      view.state.update({
        changes: { from: head, insert: " " },
        selection: { anchor: head + 1 },
      })
    );
    return true;
  }
  return false;
}

// Auto-capitalize SQL keywords after a separator is typed
const autoCapitalizeKeywords = EditorView.updateListener.of((update) => {
  if (!update.docChanged) return;

  let wordToCapitalize: { from: number; to: number; upper: string } | null = null;

  update.changes.iterChanges((_fromA, _toA, fromB, _toB, inserted) => {
    const text = inserted.toString();
    // Trigger on separator characters
    if (!/[\s,();.]/.test(text)) return;

    const pos = fromB;
    const doc = update.state.doc;
    const line = doc.lineAt(pos);
    const textBefore = line.text.slice(0, pos - line.from);
    const match = textBefore.match(/(\w+)$/);
    if (match) {
      const word = match[1];
      if (SQL_KEYWORDS.has(word.toLowerCase()) && word !== word.toUpperCase()) {
        wordToCapitalize = {
          from: pos - word.length,
          to: pos,
          upper: word.toUpperCase(),
        };
      }
    }
  });

  if (wordToCapitalize) {
    const { from, to, upper } = wordToCapitalize;
    setTimeout(() => {
      update.view.dispatch({
        changes: { from, to, insert: upper },
      });
    }, 0);
  }
});

interface SqlCodeEditorProps {
  value: string;
  onChange: (value: string) => void;
  schema: Record<string, string[]>;
  placeholder?: string;
  error?: boolean;
  editorRef?: React.MutableRefObject<ReactCodeMirrorRef | undefined>;
}

export default function SqlCodeEditor({
  value,
  onChange,
  schema,
  placeholder,
  error = false,
  editorRef,
}: SqlCodeEditorProps) {
  const theme = useTheme();

  const sqlExtension = useMemo(
    () => sql({ dialect: PostgreSQL, schema, upperCaseKeywords: true }),
    [schema]
  );

  const editorTheme = useMemo(
    () =>
      EditorView.theme(
        {
          "&": {
            fontSize: "0.875rem",
            border: `1px solid ${error ? theme.palette.error.main : theme.palette.divider}`,
            borderRadius: "4px",
            backgroundColor: theme.palette.background.paper,
          },
          "&.cm-focused": {
            outline: "none",
            borderColor: error ? theme.palette.error.main : theme.palette.primary.main,
          },
          ".cm-content": {
            fontFamily: "monospace",
            padding: "8.5px 14px",
            caretColor: theme.palette.text.primary,
          },
          ".cm-gutters": {
            display: "none",
          },
          ".cm-placeholder": {
            color: theme.palette.text.disabled,
            fontFamily: "monospace",
          },
          ".cm-tooltip-autocomplete": {
            zIndex: "1400 !important",
          },
          ".cm-tooltip": {
            zIndex: "1400 !important",
          },
        },
        { dark: theme.palette.mode === "dark" }
      ),
    [error, theme]
  );

  // Tab accepts autocomplete + adds space (highest precedence)
  const tabKeymap = useMemo(
    () => Prec.highest(keymap.of([{ key: "Tab", run: acceptCompletionWithSpace }])),
    []
  );

  const extensions = useMemo(
    () => [sqlExtension, tabKeymap, autoCapitalizeKeywords, editorTheme],
    [sqlExtension, tabKeymap, editorTheme]
  );

  return (
    <CodeMirror
      ref={editorRef as React.Ref<ReactCodeMirrorRef>}
      value={value}
      onChange={onChange}
      extensions={extensions}
      placeholder={placeholder}
      theme={theme.palette.mode === "dark" ? "dark" : "light"}
      basicSetup={{
        lineNumbers: false,
        foldGutter: false,
        highlightActiveLine: false,
        bracketMatching: true,
        closeBrackets: true,
        autocompletion: true,
        history: true,
      }}
      minHeight="80px"
      maxHeight="200px"
    />
  );
}
