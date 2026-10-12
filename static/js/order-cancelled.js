// The page Stripe sends the customer to when they leave the payment page without paying.
function showOrderCancelledPage() {
  const cancelledLinks = document.getElementById("cancelled-links");

  // If the URL has a valid order id, link to that order
  const idText = new URLSearchParams(window.location.search).get("order_id");
  if (idText !== null && /^[1-9][0-9]*$/.test(idText) && Number(idText) <= 2147483647) {
    const orderLink = document.createElement("a");
    orderLink.href = "/order.html?id=" + encodeURIComponent(idText);
    orderLink.textContent = "View order #" + idText;
    cancelledLinks.append(orderLink);
  }

  // Links to My Orders and to the products
  const ordersLink = document.createElement("a");
  ordersLink.href = "/orders.html";
  ordersLink.textContent = "My Orders";
  const productsLink = document.createElement("a");
  productsLink.href = "/products.html";
  productsLink.textContent = "Continue shopping";
  cancelledLinks.append(ordersLink, productsLink);
}

showOrderCancelledPage();
