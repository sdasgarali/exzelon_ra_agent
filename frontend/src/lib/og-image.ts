// The site-wide share card (app/opengraph-image.png). Next 14 drops the file-based
// image on any page that declares its own `openGraph` metadata, so those pages must
// list it explicitly: `openGraph: { ..., images: [OG_IMAGE] }`.
export const OG_IMAGE = {
  url: '/opengraph-image.png',
  width: 1200,
  height: 630,
  alt: 'NeuraLeads — Finding leads is easy. Knowing what not to send is the product.',
}
