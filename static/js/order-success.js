// The page Stripe sends the customer back to. It never decides that the payment worked:
// it asks the API for the order status and only believes that.
async function loadOrderSuccessPage() {
  const successArea = document.getElementById("success-area");

  // The order id must be a positive whole number that fits the database integer column
  const urlParameters = new URLSearchParams(window.location.search);
  const idText = urlParameters.get("order_id");
  if (idText === null || !/^[1-9][0-9]*$/.test(idText) || Number(idText) > 2147483647) {
    document.title = "Order not found";
    successArea.textContent = "";
    const notFoundBox = document.createElement("div");
    notFoundBox.className = "state-empty";
    const notFoundText = document.createElement("p");
    notFoundText.textContent = "Order not found";
    const ordersLink = document.createElement("a");
    ordersLink.href = "/orders.html";
    ordersLink.textContent = "My Orders";
    notFoundBox.append(notFoundText, ordersLink);
    successArea.append(notFoundBox);
    return;
  }

  // Check the order up to 15 times, 2 seconds apart, until it is no longer waiting for payment
  successArea.textContent = "";
  const waitingText = document.createElement("p");
  waitingText.className = "state-loading";
  waitingText.textContent = "Confirming your payment...";
  successArea.append(waitingText);
  let order = null;
  for (let attempt = 1; attempt <= 15; attempt++) {
    try {
      order = await apiRequest("/orders/" + idText, "GET");
    } catch (error) {
      // Show the problem and a button that reloads the page
      successArea.textContent = "";
      const errorBox = document.createElement("div");
      errorBox.className = "state-error";
      const errorText = document.createElement("p");
      errorText.textContent = error.status === 404 ? "Order not found" : "Could not check your order: " + error.message;
      const retryButton = document.createElement("button");
      retryButton.type = "button";
      retryButton.textContent = "Try again";
      retryButton.addEventListener("click", function () {
        window.location.reload();
      });
      errorBox.append(errorText, retryButton);
      successArea.append(errorBox);
      return;
    }
    if (order.status !== "pending_payment") {
      break;
    }
    if (attempt < 15) {
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
  }

  // Only the status from the API counts
  successArea.textContent = "";
  const resultText = document.createElement("p");
  resultText.className = "success-message";
  if (order.status === "paid" || order.status === "shipped" || order.status === "delivered") {
    resultText.textContent = "Payment received. Thank you!";
  } else if (order.status === "cancelled") {
    resultText.textContent = "This order was cancelled.";
  } else {
    resultText.textContent = "We are still confirming your payment. Check My Orders in a moment.";
  }

  // Links to the order and to My Orders
  const orderLink = document.createElement("a");
  orderLink.href = "/order.html?id=" + encodeURIComponent(order.id);
  orderLink.textContent = "View order #" + order.id;
  const ordersLink = document.createElement("a");
  ordersLink.href = "/orders.html";
  ordersLink.textContent = "My Orders";
  const links = document.createElement("p");
  links.className = "order-links";
  links.append(orderLink, ordersLink);
  successArea.append(resultText, links);
}

loadOrderSuccessPage();
