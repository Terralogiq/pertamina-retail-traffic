const BRAND_NAME = "Pertamina Retail";
const PRODUCT_LINE = "SPBU traffic";

/** The one product name: wordmark text, tab titles and the home link all read this. */
export const PRODUCT_NAME = `${BRAND_NAME} ${PRODUCT_LINE}`;

/** Logo size comes from the 770x202 source; CSS sets the displayed height (--logo-height). */
const LOGO = { src: "/brand/pertamina-retail-logo.png", width: 770, height: 202 };

/** Logo image (alt = brand name) followed by the product line, so the accessible name reads PRODUCT_NAME. */
export function Wordmark() {
  return (
    <span className="wordmark">
      <img className="wordmark-logo" src={LOGO.src} alt={BRAND_NAME} width={LOGO.width} height={LOGO.height} />{" "}
      <span className="wordmark-product">{PRODUCT_LINE}</span>
    </span>
  );
}
