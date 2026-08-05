/**
 * The contract every Add Layer flow exposes, and the only thing a host needs.
 *
 * A flow owns its state, its validation and its submit; the host owns the frame,
 * how `steps` is drawn, and where `action` sits. That split is what lets the same
 * flow appear in the modal today and in a side panel or a page later.
 */
export type FlowAction = {
  label: string;
  disabled: boolean;
  /** Shown as a tooltip when disabled, for reasons the label cannot carry. */
  reason?: string;
  run: () => void | Promise<void>;
};

export type FlowController = {
  /** Localized step labels; empty when the flow is a single view. */
  steps: string[];
  step: number;
  goTo: (step: number) => void;
  action: FlowAction;
  isBusy: boolean;
  reset: () => void;
};
