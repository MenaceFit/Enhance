// "Vinted" is a trademark of Vinted UAB. The product name is configurable so the
// service can be operated under its own brand.
export const BRAND = {
  name: process.env.NEXT_PUBLIC_BRAND_NAME ?? "Vinted AI",
  marketplace: "Vinted",
  supportEmail: process.env.NEXT_PUBLIC_SUPPORT_EMAIL ?? "contact@example.com",
};
