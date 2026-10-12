// The checkout page: order summary, address choice and the "Place order and pay" button.
async function loadCheckoutPage() {
  const checkoutArea = document.getElementById("checkout-area");

  // Load the cart and the addresses at the same time
  let cart = null;
  let addresses = null;
  try {
    const results = await Promise.all([
      apiRequest("/cart", "GET"),
      apiRequest("/users/me/addresses", "GET"),
    ]);
    cart = results[0];
    addresses = results[1];
  } catch (error) {
    // Show the problem and a button that reloads the page
    checkoutArea.textContent = "";
    const errorBox = document.createElement("div");
    errorBox.className = "state-error";
    const errorText = document.createElement("p");
    errorText.textContent = "Could not load the checkout: " + error.message;
    const retryButton = document.createElement("button");
    retryButton.type = "button";
    retryButton.textContent = "Try again";
    retryButton.addEventListener("click", function () {
      window.location.reload();
    });
    errorBox.append(errorText, retryButton);
    checkoutArea.append(errorBox);
    return;
  }

  // Empty cart: nothing to pay for
  checkoutArea.textContent = "";
  if (cart.items.length === 0) {
    const emptyBox = document.createElement("div");
    emptyBox.className = "state-empty";
    const emptyText = document.createElement("p");
    emptyText.textContent = "Your cart is empty.";
    const productsLink = document.createElement("a");
    productsLink.href = "/products.html";
    productsLink.textContent = "Continue shopping";
    emptyBox.append(emptyText, productsLink);
    checkoutArea.append(emptyBox);
    return;
  }

  // The read-only order summary: every line, then the subtotal
  const summary = document.createElement("section");
  summary.className = "checkout-summary";
  const summaryHeading = document.createElement("h2");
  summaryHeading.textContent = "Order summary";
  summary.append(summaryHeading);
  const summaryList = document.createElement("ul");
  summaryList.className = "checkout-lines";
  for (const item of cart.items) {
    const line = document.createElement("li");
    line.className = "checkout-line";
    const lineName = document.createElement("span");
    lineName.className = "checkout-line-name";
    lineName.textContent = item.name + " x " + item.quantity;
    const lineTotal = document.createElement("span");
    lineTotal.textContent = "₹" + (item.line_total / 100).toLocaleString("en-IN", { minimumFractionDigits: item.line_total % 100 === 0 ? 0 : 2, maximumFractionDigits: 2 });
    line.append(lineName, lineTotal);
    summaryList.append(line);
    if (item.problem !== null) {
      const problemText = document.createElement("li");
      problemText.className = "cart-problem";
      problemText.textContent = item.name + ": " + item.problem;
      summaryList.append(problemText);
    }
  }
  const subtotalLine = document.createElement("div");
  subtotalLine.className = "checkout-subtotal";
  const subtotalLabel = document.createElement("span");
  subtotalLabel.textContent = "Subtotal";
  const subtotalAmount = document.createElement("span");
  subtotalAmount.textContent = "₹" + (cart.subtotal / 100).toLocaleString("en-IN", { minimumFractionDigits: cart.subtotal % 100 === 0 ? 0 : 2, maximumFractionDigits: 2 });
  subtotalLine.append(subtotalLabel, subtotalAmount);
  summary.append(summaryList, subtotalLine);

  // The addresses as radio buttons, the default one preselected
  const addressSection = document.createElement("section");
  addressSection.className = "checkout-addresses";
  const addressHeading = document.createElement("h2");
  addressHeading.textContent = "Shipping address";
  addressSection.append(addressHeading);
  for (const address of addresses) {
    const choice = document.createElement("label");
    choice.className = "address-choice";
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "address";
    radio.value = String(address.id);
    radio.checked = address.is_default;
    const choiceText = document.createElement("span");
    let addressText = address.full_name + ", " + address.line1;
    if (address.line2) {
      addressText = addressText + ", " + address.line2;
    }
    addressText = addressText + ", " + address.city + ", " + address.state + " " + address.postal_code + ", " + address.country + ". Phone: " + address.phone;
    choiceText.textContent = addressText;
    choice.append(radio, choiceText);
    addressSection.append(choice);
  }

  // If no address is the default, select the first one so the customer can always continue
  if (addresses.length > 0 && !addresses.some(function (address) { return address.is_default; })) {
    addressSection.querySelector("input[type=radio]").checked = true;
  }

  // The message area and the pay button
  const messageArea = document.createElement("div");
  messageArea.className = "checkout-message";
  messageArea.setAttribute("role", "alert");
  messageArea.hidden = true;
  const payButton = document.createElement("button");
  payButton.type = "button";
  payButton.className = "checkout-button";
  payButton.textContent = "Place order and pay";

  // Reasons why the customer cannot pay yet
  if (cart.has_problems) {
    messageArea.className = "checkout-message error-message";
    messageArea.textContent = "Some items in your cart are not available. ";
    const cartLink = document.createElement("a");
    cartLink.href = "/cart.html";
    cartLink.textContent = "Go to your cart to fix this.";
    messageArea.append(cartLink);
    messageArea.hidden = false;
    payButton.disabled = true;
  }
  if (addresses.length === 0) {
    const addAddressLink = document.createElement("a");
    addAddressLink.href = "/addresses.html?next=/checkout.html";
    addAddressLink.textContent = "Add an address";
    const addressNote = document.createElement("p");
    addressNote.append("You need a shipping address to place an order. ", addAddressLink);
    addressSection.append(addressNote);
    payButton.disabled = true;
  }

  // Pressing the button
  payButton.addEventListener("click", async function () {
    // Disable the button while the request runs, so a double click cannot place two orders
    messageArea.hidden = true;
    payButton.disabled = true;
    payButton.textContent = "Redirecting to payment...";
    const chosenRadio = addressSection.querySelector("input[type=radio]:checked");
    try {
      const result = await apiRequest("/orders/checkout", "POST", {
        address_id: Number(chosenRadio.value),
      });

      // Only go to Stripe's own page
      if (typeof result.checkout_url !== "string" || !result.checkout_url.startsWith("https://checkout.stripe.com/")) {
        messageArea.className = "checkout-message error-message";
        messageArea.textContent = "The payment page address was not valid, so you were not redirected. ";
        const ordersLink = document.createElement("a");
        ordersLink.href = "/orders.html";
        ordersLink.textContent = "Check My Orders.";
        messageArea.append(ordersLink);
        messageArea.hidden = false;
        payButton.textContent = "Place order and pay";
        return;
      }
      window.location.href = result.checkout_url;
    } catch (error) {
      // Show the message from the API
      messageArea.className = "checkout-message error-message";
      messageArea.textContent = error.message;
      if (error.status === 403) {
        messageArea.textContent = "Use a customer account to place orders.";
      }
      if (error.status === 409) {
        messageArea.append(" ");
        const cartLink = document.createElement("a");
        cartLink.href = "/cart.html";
        cartLink.textContent = "Go to your cart.";
        messageArea.append(cartLink);
      }
      messageArea.hidden = false;
      payButton.textContent = "Place order and pay";

      // The payment service was down (502) or the network failed (no status): the cart is unchanged, so retry is fine
      if (error.status === 502 || error.status === undefined) {
        payButton.disabled = false;
      }
    }
  });

  // Put everything on the page
  const layout = document.createElement("div");
  layout.className = "checkout-layout";
  const leftColumn = document.createElement("div");
  leftColumn.append(addressSection);
  const rightColumn = document.createElement("div");
  rightColumn.append(summary, messageArea, payButton);
  layout.append(leftColumn, rightColumn);
  checkoutArea.append(layout);
}

loadCheckoutPage();
