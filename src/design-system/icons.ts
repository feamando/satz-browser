/*
  Satz icon set: 24px grid, 1.7 stroke, round caps and joins, no fill.
  Spec: docs/design/DESIGN_SYSTEM.md section 6 (Icons).
  Usage: el.innerHTML = icon("mail")  or  icon("chev", "ico-sm")
*/

export const ICONS = {
x:'<path d="M6 6l12 12M18 6 6 18"/>',
plus:'<path d="M12 5v14M5 12h14"/>',
more:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
search:'<circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5"/>',
check:'<path d="m5 12 5 5 9-10"/>',
trash:'<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
compare:'<rect x="3" y="4" width="8" height="16" rx="1.5"/><rect x="13" y="4" width="8" height="16" rx="1.5"/>',
external:'<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
translate:'<path d="M4 5h9M8.5 3v2M6 5c1 4 3.5 6.5 6 8M11 5c-1 4-3.5 6.5-6 8M13 21l4-9 4 9M14.5 18h5"/>',
eye:'<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
watch:'<circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/>',

home:'<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"/>',
cmd:'<path d="M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3z"/>',
compose:'<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
mail:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3.5 7 8.5 6 8.5-6"/>',
news:'<path d="M4 5h13v14H6a2 2 0 0 1-2-2zM17 9h3v8a2 2 0 0 1-2 2M8 9h5M8 13h5"/>',
pin:'<path d="M12 17v5M9 3h6l-1 7 4 3H6l4-3z"/>',
chat:'<path d="M4 5h16v11H9l-5 4z"/>',
brain:'<path d="M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 6 0V4zM15 4a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-6 0"/>',
settings:'<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
pulse:'<path d="M3 12h4l3-7 4 14 3-7h4"/>',
chev:'<path d="m6 9 6 6 6-6"/>',
back:'<path d="m15 6-6 6 6 6"/>',
fwd:'<path d="m9 6 6 6-6 6"/>',
reload:'<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>',
panel:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M15 5v14"/>',
send:'<path d="M5 12h14M13 6l6 6-6 6"/>',
globe:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
lock:'<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
spark:'<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
attach:'<path d="m21 11-8.5 8.5a5 5 0 0 1-7-7L14 4a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L15 7"/>',
image:'<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8.5" cy="10" r="1.5"/><path d="m21 15-4.5-4.5-5 5-2.5-2.5L4 18"/>',
reply:'<path d="M9 14 4 9l5-5M4 9h10a6 6 0 0 1 6 6v4"/>',
cal:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
doc:'<path d="M6 3h8l4 4v14H6zM14 3v4h4"/>',
folder:'<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
drive:'<path d="M6.5 18a4.5 4.5 0 0 1-.8-8.9A5.5 5.5 0 0 1 16.4 8a4 4 0 0 1 1.1 7.8H6.5z"/>',
up:'<path d="m6 15 6-6 6 6"/>',
upload:'<path d="M12 15V4M7 9l5-5 5 5M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
sheet:'<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M4 9h16M4 15h16M10 3v18"/>',
slide:'<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
star:'<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
box:'<path d="M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10"/>',
archive:'<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v10h14V9M10 13h4"/>'
} as const;

export type IconName = keyof typeof ICONS;

export function icon(name: IconName, cls = ""): string {
  return `<svg class="ico ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;
}
