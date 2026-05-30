// A simple top-down plane silhouette pointing "up" (north), as an SVG data URI.
// Used as a tintable mask in deck.gl's IconLayer (getColor recolors it).

const SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
<path fill="#ffffff" d="M32 3c-2.2 0-3.6 2.4-3.6 6.4v12.9L5 37.1v5.1l23.4-7v11.6l-6 4.3v4.1l9.6-2.7 9.6 2.7v-4.1l-6-4.3V35.2l23.4 7v-5.1L35.6 22.3V9.4C35.6 5.4 34.2 3 32 3z"/>
</svg>`;

export const PLANE_ICON_URL = `data:image/svg+xml,${encodeURIComponent(SVG)}`;
export const PLANE_ICON_SIZE = 64;

// A ring used as a pulsing "in severe weather" halo behind blocked aircraft.
// Tintable mask (alpha only on the stroke), recolored via the layer's getColor.
const RING_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
<circle cx="32" cy="32" r="26" fill="none" stroke="#ffffff" stroke-width="6"/>
</svg>`;

export const RING_ICON_URL = `data:image/svg+xml,${encodeURIComponent(RING_SVG)}`;
export const RING_ICON_SIZE = 64;
