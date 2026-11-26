// Shared with the website (src/shop/site_template/index.html's
// `numberFormat`) so a price looks the same whether the customer reads
// it on the site or in the bot.
export const numberFormat = new Intl.NumberFormat("vi-VN");

export function formatMoney(amount) {
  return `${numberFormat.format(amount)} ₽`;
}
