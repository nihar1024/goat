/** Credits as customers see them: whole numbers, in the reader's locale. The
 * ledger keeps exact values (a 3-second run costs half a credit), so rounding
 * happens only for display, never per charge. */
export const formatCredits = (value: number | null | undefined, locale?: string): string =>
  new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(Math.round(value ?? 0));
