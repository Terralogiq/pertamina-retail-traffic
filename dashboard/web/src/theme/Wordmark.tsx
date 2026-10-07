const BRAND_NAME = "Pertamina Retail";
const PRODUCT_LINE = "SPBU traffic";

/** The one product name: wordmark text, tab titles and the home link all read this. */
export const PRODUCT_NAME = `${BRAND_NAME} ${PRODUCT_LINE}`;

/** Text wordmark until the official logo arrives (bead .9.2 swaps this for the SVG). */
export function Wordmark() {
  return (
    <span className="wordmark">
      <span className="wordmark-brand">{BRAND_NAME}</span> <span className="wordmark-product">{PRODUCT_LINE}</span>
    </span>
  );
}
