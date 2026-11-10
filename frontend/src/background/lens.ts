/**
 * Optional edge lensing for small glass elements. Chromium (and only Chromium) applies an SVG filter inside
 * backdrop-filter, so the element bends the liquid slightly at its edges. The filter is injected once and the
 * `lens` class is set on <html> only where it can work; every other browser keeps the plain blur recipe, which is
 * the design. Nothing depends on this.
 */
const MAP = [
  "<svg xmlns='http://www.w3.org/2000/svg' width='100%' height='100%' preserveAspectRatio='none'>",
  "<defs>",
  "<linearGradient id='r' x1='0' x2='1' y1='0' y2='0'><stop offset='0' stop-color='rgb(36,0,0)'/><stop offset='0.06' stop-color='rgb(128,0,0)'/><stop offset='0.94' stop-color='rgb(128,0,0)'/><stop offset='1' stop-color='rgb(220,0,0)'/></linearGradient>",
  "<linearGradient id='g' x1='0' x2='0' y1='0' y2='1'><stop offset='0' stop-color='rgb(0,36,0)'/><stop offset='0.12' stop-color='rgb(0,128,0)'/><stop offset='0.88' stop-color='rgb(0,128,0)'/><stop offset='1' stop-color='rgb(0,220,0)'/></linearGradient>",
  "</defs>",
  "<rect width='100%' height='100%' fill='black'/>",
  "<rect width='100%' height='100%' fill='url(#r)'/>",
  "<rect width='100%' height='100%' fill='url(#g)' style='mix-blend-mode:screen'/>",
  "</svg>",
].join("");

function isChromium(): boolean {
  const brands = (navigator as Navigator & { userAgentData?: { brands: { brand: string }[] } }).userAgentData?.brands;
  return Boolean(brands?.some((entry) => entry.brand === "Chromium"));
}

export function enableLens(): void {
  if (!isChromium()) return;
  if (typeof CSS === "undefined" || !CSS.supports("backdrop-filter", "url(#x)")) return;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("width", "0");
  svg.setAttribute("height", "0");
  svg.style.position = "absolute";
  svg.innerHTML =
    `<filter id="ragassist-lens" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB">` +
    `<feImage href="data:image/svg+xml,${encodeURIComponent(MAP)}" preserveAspectRatio="none" result="map"/>` +
    `<feDisplacementMap in="SourceGraphic" in2="map" scale="16" xChannelSelector="R" yChannelSelector="G"/>` +
    `</filter>`;
  document.body.append(svg);
  document.documentElement.classList.add("lens");
}
