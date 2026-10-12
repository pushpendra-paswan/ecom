// The seller's order detail page, from ?id=
async function loadSellerOrderPage() {
  const orderArea = document.getElementById("order-area");

  // The labels for the order statuses
  const statusLabels = {
    pending_payment: "Awaiting payment",
    paid: "Paid",
    shipped: "Shipped",
    delivered: "Delivered",
    cancelled: "Cancelled",
  };

  // The id must be a positive whole number that fits the database integer column.
  // Anything else shows "Order not found" without calling the API.
  const idText = new URLSearchParams(window.location.search).get("id");
  let order = null;
  if (idText !== null && /^[1-9][0-9]*$/.test(idText) && Number(idText) <= 2147483647) {
    try {
      order = await apiRequest("/seller/orders/" + idText, "GET");
    } catch (error) {
      if (error.status !== 404) {
        // Some other problem: show it (a 403 means this is not a seller account)
        orderArea.textContent = "";
        const errorBox = document.createElement("div");
        errorBox.className = "state-error";
        const errorText = document.createElement("p");
        if (error.status === 403) {
          errorText.textContent = "This page is for seller accounts.";
          errorBox.append(errorText);
        } else {
          errorText.textContent = "Could not load the order: " + error.message;
          const retryButton = document.createElement("button");
          retryButton.type = "button";
          retryButton.textContent = "Try again";
          retryButton.addEventListener("click", function () {
            window.location.reload();
          });
          errorBox.append(errorText, retryButton);
        }
        orderArea.append(errorBox);
        return;
      }
    }
  }

  // A bad id, or an order this seller may not see
  orderArea.textContent = "";
  if (order === null) {
    document.title = "Order not found";
    const notFoundBox = document.createElement("div");
    notFoundBox.className = "state-empty";
    const notFoundText = document.createElement("p");
    notFoundText.textContent = "Order not found";
    const ordersLink = document.createElement("a");
    ordersLink.href = "/seller-orders.html";
    ordersLink.textContent = "Orders";
    notFoundBox.append(notFoundText, ordersLink);
    orderArea.append(notFoundBox);
    return;
  }
  document.title = "Order #" + order.id;

  // Heading: the order number, the date and the status label
  const heading = document.createElement("h1");
  heading.textContent = "Order #" + order.id;
  const headerRow = document.createElement("div");
  headerRow.className = "order-detail-header";
  const date = document.createElement("span");
  date.className = "order-card-date";
  date.textContent = "Placed on " + new Date(order.created_at).toLocaleString("en-IN");
  const statusBadge = document.createElement("span");
  statusBadge.className = "badge badge-" + order.status.replace("_", "-");
  statusBadge.textContent = statusLabels[order.status] || order.status;
  headerRow.append(date, statusBadge);

  // The shipping address (textContent only, because the customer typed these values)
  const address = order.shipping_address;
  const addressSection = document.createElement("section");
  addressSection.className = "order-detail-section";
  const addressHeading = document.createElement("h2");
  addressHeading.textContent = "Shipping address";
  addressSection.append(addressHeading);
  const addressLines = [address.full_name, address.line1];
  if (address.line2) {
    addressLines.push(address.line2);
  }
  addressLines.push(address.city + ", " + address.state + " " + address.postal_code);
  addressLines.push(address.country);
  addressLines.push("Phone: " + address.phone);
  for (const lineText of addressLines) {
    const addressLine = document.createElement("div");
    addressLine.textContent = lineText;
    addressSection.append(addressLine);
  }

  // The items table: only this seller's lines
  const itemsSection = document.createElement("section");
  itemsSection.className = "order-detail-section";
  const itemsHeading = document.createElement("h2");
  itemsHeading.textContent = "Your items";
  const tableWrapper = document.createElement("div");
  tableWrapper.className = "table-wrapper";
  const table = document.createElement("table");
  table.className = "order-table";
  const tableHead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const columnName of ["Product", "Price", "Quantity", "Total"]) {
    const headCell = document.createElement("th");
    headCell.textContent = columnName;
    headRow.append(headCell);
  }
  tableHead.append(headRow);
  const tableBody = document.createElement("tbody");
  for (const item of order.items) {
    const row = document.createElement("tr");
    const nameCell = document.createElement("td");
    nameCell.textContent = item.product_name;
    const priceCell = document.createElement("td");
    priceCell.textContent = "₹" + (item.unit_price / 100).toLocaleString("en-IN", { minimumFractionDigits: item.unit_price % 100 === 0 ? 0 : 2, maximumFractionDigits: 2 });
    const quantityCell = document.createElement("td");
    quantityCell.textContent = String(item.quantity);
    const lineTotalCell = document.createElement("td");
    lineTotalCell.textContent = "₹" + (item.line_total / 100).toLocaleString("en-IN", { minimumFractionDigits: item.line_total % 100 === 0 ? 0 : 2, maximumFractionDigits: 2 });
    row.append(nameCell, priceCell, quantityCell, lineTotalCell);
    tableBody.append(row);
  }
  table.append(tableHead, tableBody);
  tableWrapper.append(table);
  itemsSection.append(itemsHeading, tableWrapper);

  // The seller's subtotal
  const subtotalLine = document.createElement("div");
  subtotalLine.className = "order-detail-total";
  subtotalLine.textContent = "Your items total: ₹" + (order.seller_subtotal / 100).toLocaleString("en-IN", { minimumFractionDigits: order.seller_subtotal % 100 === 0 ? 0 : 2, maximumFractionDigits: 2 });

  // The actions: only when every item in the order is this seller's
  const actionArea = document.createElement("div");
  actionArea.className = "order-actions";
  const actionMessage = document.createElement("p");
  actionMessage.className = "error-message";
  actionMessage.setAttribute("role", "alert");
  actionMessage.hidden = true;
  actionArea.append(actionMessage);

  if (order.has_other_sellers) {
    const otherSellersNote = document.createElement("p");
    otherSellersNote.className = "order-detail-payment";
    otherSellersNote.textContent = "This order includes products from other sellers. Only an admin can update its status.";
    actionArea.append(otherSellersNote);
  } else if (order.status === "paid" || order.status === "shipped") {
    // paid -> shipped, shipped -> delivered
    let nextStatus = "shipped";
    let buttonText = "Mark as shipped";
    if (order.status === "shipped") {
      nextStatus = "delivered";
      buttonText = "Mark as delivered";
    }
    const statusButton = document.createElement("button");
    statusButton.type = "button";
    statusButton.textContent = buttonText;
    statusButton.addEventListener("click", async function () {
      statusButton.disabled = true;
      actionMessage.hidden = true;
      try {
        await apiRequest("/seller/orders/" + order.id + "/status", "PATCH", { status: nextStatus });
        window.location.reload();
      } catch (error) {
        // Show the API message and do not reload
        actionMessage.textContent = error.message;
        actionMessage.hidden = false;
        statusButton.disabled = false;
      }
    });
    actionArea.append(statusButton);
  }

  const ordersLink = document.createElement("a");
  ordersLink.href = "/seller-orders.html";
  ordersLink.textContent = "Back to Orders";

  orderArea.append(heading, headerRow, addressSection, itemsSection, subtotalLine, actionArea, ordersLink);
}

loadSellerOrderPage();
