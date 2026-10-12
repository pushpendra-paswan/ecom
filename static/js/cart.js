// Loads the cart and draws the whole page. It runs on page load and after every change.
async function loadCart() {
  // Find the two areas on the page
  const cartArea = document.getElementById("cart-area");
  const cartMessage = document.getElementById("cart-message");

  // Load the cart
  let cart = null;
  try {
    cart = await apiRequest("/cart", "GET");
  } catch (error) {
    // Show the problem and a button that reloads the page
    cartArea.textContent = "";
    const errorBox = document.createElement("div");
    errorBox.className = "state-error";
    const errorText = document.createElement("p");
    errorText.textContent = "Could not load your cart: " + error.message;
    const retryButton = document.createElement("button");
    retryButton.type = "button";
    retryButton.textContent = "Try again";
    retryButton.addEventListener("click", function () {
      window.location.reload();
    });
    errorBox.append(errorText, retryButton);
    cartArea.append(errorBox);
    return;
  }

  // Update the navbar badge, if it exists yet
  const cartBadge = document.getElementById("cart-count");
  if (cartBadge) {
    cartBadge.textContent = String(cart.item_count);
    cartBadge.hidden = cart.item_count === 0;
  }

  // Empty cart
  if (cart.items.length === 0) {
    cartArea.textContent = "";
    const emptyBox = document.createElement("div");
    emptyBox.className = "state-empty";
    const emptyText = document.createElement("p");
    emptyText.textContent = "Your cart is empty.";
    const shoppingLink = document.createElement("a");
    shoppingLink.href = "/products.html";
    shoppingLink.textContent = "Continue shopping";
    emptyBox.append(emptyText, shoppingLink);
    cartArea.append(emptyBox);
    return;
  }

  // One row for every cart line
  const cartList = document.createElement("ul");
  cartList.className = "cart-list";
  for (const item of cart.items) {
    const line = document.createElement("li");
    line.className = "cart-line";
    if (!item.available) {
      line.classList.add("cart-line-problem");
    }
    const productLink = "/product.html?id=" + encodeURIComponent(item.product_id);

    // The image, linked to the product page (with a one-time fallback to the placeholder)
    const imageLink = document.createElement("a");
    imageLink.href = productLink;
    const image = document.createElement("img");
    image.className = "cart-line-image";
    image.alt = item.name;
    if (item.image_url) {
      image.src = item.image_url;
    } else {
      image.src = "/static/images/placeholder.svg";
    }
    image.onerror = function () {
      image.onerror = null;
      image.src = "/static/images/placeholder.svg";
    };
    imageLink.append(image);

    // The name (linked), the unit price and the problem text if there is one
    const details = document.createElement("div");
    details.className = "cart-line-details";
    const nameLink = document.createElement("a");
    nameLink.className = "cart-line-name";
    nameLink.href = productLink;
    nameLink.textContent = item.name;
    const unitPrice = document.createElement("div");
    unitPrice.className = "cart-line-unit-price";
    unitPrice.textContent = "₹" + (item.unit_price / 100).toLocaleString("en-IN", { minimumFractionDigits: item.unit_price % 100 === 0 ? 0 : 2, maximumFractionDigits: 2 });
    details.append(nameLink, unitPrice);
    if (item.problem !== null) {
      const problemText = document.createElement("div");
      problemText.className = "cart-problem";
      problemText.textContent = item.problem;
      details.append(problemText);
    }

    // The controls: quantity dropdown, line total and Remove button
    const controls = document.createElement("div");
    controls.className = "cart-line-controls";
    const lineTotal = document.createElement("div");
    lineTotal.className = "cart-line-total";
    lineTotal.textContent = "₹" + (item.line_total / 100).toLocaleString("en-IN", { minimumFractionDigits: item.line_total % 100 === 0 ? 0 : 2, maximumFractionDigits: 2 });
    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "button-secondary";
    removeButton.textContent = "Remove";

    // The dropdown offers 1 to the smaller of the stock and 10. With a limit of 0 there is no dropdown.
    const maximumQuantity = Math.min(item.stock, 10);
    let quantitySelect = null;
    if (maximumQuantity > 0) {
      quantitySelect = document.createElement("select");
      quantitySelect.className = "quantity-select";
      quantitySelect.setAttribute("aria-label", "Quantity of " + item.name);

      // A quantity above the limit is shown as a disabled option, so the customer has to pick a valid one
      if (item.quantity > maximumQuantity) {
        const currentOption = document.createElement("option");
        currentOption.value = String(item.quantity);
        currentOption.textContent = String(item.quantity);
        currentOption.disabled = true;
        quantitySelect.append(currentOption);
      }
      for (let option = 1; option <= maximumQuantity; option++) {
        const optionElement = document.createElement("option");
        optionElement.value = String(option);
        optionElement.textContent = String(option);
        quantitySelect.append(optionElement);
      }
      quantitySelect.value = String(item.quantity);

      // Changing the quantity: disable this line, send PATCH, then draw the cart again
      quantitySelect.addEventListener("change", async function () {
        cartMessage.hidden = true;
        quantitySelect.disabled = true;
        removeButton.disabled = true;
        try {
          await apiRequest("/cart/items/" + encodeURIComponent(item.product_id), "PATCH", {
            quantity: Number(quantitySelect.value),
          });
        } catch (error) {
          cartMessage.textContent = error.message;
          cartMessage.hidden = false;
        }
        await loadCart();
      });
      controls.append(quantitySelect);
    }
    controls.append(lineTotal, removeButton);

    // Removing the line: disable this line, send DELETE, then draw the cart again
    removeButton.addEventListener("click", async function () {
      cartMessage.hidden = true;
      removeButton.disabled = true;
      if (quantitySelect !== null) {
        quantitySelect.disabled = true;
      }
      try {
        await apiRequest("/cart/items/" + encodeURIComponent(item.product_id), "DELETE");
      } catch (error) {
        cartMessage.textContent = error.message;
        cartMessage.hidden = false;
      }
      await loadCart();
    });

    line.append(imageLink, details, controls);
    cartList.append(line);
  }

  // The summary box: subtotal (available lines only), a note about problems and "Clear cart"
  const summary = document.createElement("aside");
  summary.className = "cart-summary";
  const subtotalLabel = document.createElement("div");
  subtotalLabel.textContent = "Subtotal (" + cart.item_count + (cart.item_count === 1 ? " item)" : " items)");
  const subtotalAmount = document.createElement("div");
  subtotalAmount.className = "cart-subtotal";
  subtotalAmount.textContent = "₹" + (cart.subtotal / 100).toLocaleString("en-IN", { minimumFractionDigits: cart.subtotal % 100 === 0 ? 0 : 2, maximumFractionDigits: 2 });
  summary.append(subtotalLabel, subtotalAmount);
  if (cart.has_problems) {
    const problemsNote = document.createElement("p");
    problemsNote.className = "cart-problem";
    problemsNote.textContent = "Some items need your attention. They are not included in the subtotal.";
    summary.append(problemsNote);
  }
  const clearButton = document.createElement("button");
  clearButton.type = "button";
  clearButton.className = "button-secondary";
  clearButton.textContent = "Clear cart";
  clearButton.addEventListener("click", async function () {
    // Ask first
    if (!confirm("Remove all items from your cart?")) {
      return;
    }
    cartMessage.hidden = true;
    clearButton.disabled = true;
    try {
      await apiRequest("/cart", "DELETE");
    } catch (error) {
      cartMessage.textContent = error.message;
      cartMessage.hidden = false;
    }
    await loadCart();
  });
  summary.append(clearButton);

  // Put the list and the summary on the page
  const cartLayout = document.createElement("div");
  cartLayout.className = "cart-layout";
  cartLayout.append(cartList, summary);
  cartArea.textContent = "";
  cartArea.append(cartLayout);
}

loadCart();
