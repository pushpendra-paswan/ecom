// The admin's order detail page, from ?id=
async function loadAdminOrderPage() {
  const orderArea = document.getElementById("order-area");

  // The labels for the order and payment statuses
  const statusLabels = {
    pending_payment: "Awaiting payment",
    paid: "Paid",
    shipped: "Shipped",
    delivered: "Delivered",
    cancelled: "Cancelled",
  };
  const paymentLabels = {
    pending: "Pending",
    succeeded: "Paid",
    failed: "Failed",
    refunded: "Refunded",
  };

  // The id must be a positive whole number that fits the database integer column.
  // Anything else shows "Order not found" without calling the API.
  const idText = new URLSearchParams(window.location.search).get("id");
  let order = null;
  if (idText !== null && /^[1-9][0-9]*$/.test(idText) && Number(idText) <= 2147483647) {
    try {
      order = await apiRequest("/admin/orders/" + idText, "GET");
    } catch (error) {
      if (error.status !== 404) {
        // Some other problem: show it (a 403 means this is not an admin account)
        orderArea.textContent = "";
        const errorBox = document.createElement("div");
        errorBox.className = "state-error";
        const errorText = document.createElement("p");
        if (error.status === 403) {
          errorText.textContent = "This page is for admin accounts.";
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

  // A bad id or a missing order
  orderArea.textContent = "";
  if (order === null) {
    document.title = "Order not found";
    const notFoundBox = document.createElement("div");
    notFoundBox.className = "state-empty";
    const notFoundText = document.createElement("p");
    notFoundText.textContent = "Order not found";
    const ordersLink = document.createElement("a");
    ordersLink.href = "/admin-orders.html";
    ordersLink.textContent = "All orders";
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

  // The customer (textContent only)
  const customerSection = document.createElement("section");
  customerSection.className = "order-detail-section";
  const customerHeading = document.createElement("h2");
  customerHeading.textContent = "Customer";
  const customerLine = document.createElement("div");
  customerLine.textContent = order.customer_email + " (user #" + order.user_id + ")";
  customerSection.append(customerHeading, customerLine);

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

  // The items table: all lines of the order
  const itemsSection = document.createElement("section");
  itemsSection.className = "order-detail-section";
  const itemsHeading = document.createElement("h2");
  itemsHeading.textContent = "Items";
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

  // The total and the payment status
  const totalLine = document.createElement("div");
  totalLine.className = "order-detail-total";
  totalLine.textContent = "Total: ₹" + (order.total_amount / 100).toLocaleString("en-IN", { minimumFractionDigits: order.total_amount % 100 === 0 ? 0 : 2, maximumFractionDigits: 2 });
  const paymentLine = document.createElement("div");
  paymentLine.className = "order-detail-payment";
  if (order.payment !== null) {
    paymentLine.textContent = "Payment: ";
    const paymentBadge = document.createElement("span");
    paymentBadge.className = "badge badge-payment-" + order.payment.status;
    paymentBadge.textContent = paymentLabels[order.payment.status] || order.payment.status;
    paymentLine.append(paymentBadge);
  } else {
    paymentLine.textContent = "Payment: not available";
  }

  // The actions this order allows
  const actionArea = document.createElement("div");
  actionArea.className = "order-actions";
  const actionMessage = document.createElement("p");
  actionMessage.className = "error-message";
  actionMessage.hidden = true;
  actionArea.append(actionMessage);

  // "Mark as shipped" (paid) or "Mark as delivered" (shipped)
  if (order.status === "paid" || order.status === "shipped") {
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
        await apiRequest("/admin/orders/" + order.id + "/status", "PATCH", { status: nextStatus });
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

  // "Cancel order" (pending_payment or paid), after confirm()
  if (order.status === "pending_payment" || order.status === "paid") {
    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "button-secondary";
    cancelButton.textContent = "Cancel order";
    cancelButton.addEventListener("click", async function () {
      let question = "Cancel this order?";
      if (order.status === "paid") {
        question = "Cancel this order? The payment will be refunded.";
      }
      if (!confirm(question)) {
        return;
      }
      cancelButton.disabled = true;
      actionMessage.hidden = true;
      try {
        await apiRequest("/orders/" + order.id + "/cancel", "POST");
        window.location.reload();
      } catch (error) {
        // Show the API message and do not reload
        actionMessage.textContent = error.message;
        actionMessage.hidden = false;
        cancelButton.disabled = false;
      }
    });
    actionArea.append(cancelButton);
  }

  // "Retry refund" (cancelled, but the money has not been given back yet): the same endpoint
  if (order.status === "cancelled" && order.payment !== null && order.payment.status === "succeeded") {
    const retryRefundButton = document.createElement("button");
    retryRefundButton.type = "button";
    retryRefundButton.textContent = "Retry refund";
    retryRefundButton.addEventListener("click", async function () {
      retryRefundButton.disabled = true;
      actionMessage.hidden = true;
      try {
        await apiRequest("/orders/" + order.id + "/cancel", "POST");
        window.location.reload();
      } catch (error) {
        // Show the API message and do not reload
        actionMessage.textContent = error.message;
        actionMessage.hidden = false;
        retryRefundButton.disabled = false;
      }
    });
    actionArea.append(retryRefundButton);
  }

  const ordersLink = document.createElement("a");
  ordersLink.href = "/admin-orders.html";
  ordersLink.textContent = "Back to all orders";

  orderArea.append(heading, headerRow, customerSection, addressSection, itemsSection, totalLine, paymentLine, actionArea, ordersLink);
}

loadAdminOrderPage();
