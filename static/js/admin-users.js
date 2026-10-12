// The admin's read-only list of users, 20 per page.
async function loadAdminUsersPage() {
  const usersArea = document.getElementById("users-area");
  const paginationArea = document.getElementById("pagination-area");

  // Read the page number from the URL (anything below 1 or not a number becomes 1)
  const pageSize = 20;
  let page = parseInt(new URLSearchParams(window.location.search).get("page"), 10);
  if (!Number.isSafeInteger(page) || page < 1) {
    page = 1;
  }

  // Load the page of users
  let result = null;
  try {
    result = await apiRequest("/admin/users?page=" + page + "&page_size=" + pageSize, "GET");
  } catch (error) {
    usersArea.textContent = "";
    const errorBox = document.createElement("div");
    errorBox.className = "state-error";
    const errorText = document.createElement("p");
    if (error.status === 403) {
      errorText.textContent = "This page is for admin accounts.";
      errorBox.append(errorText);
    } else {
      errorText.textContent = "Could not load the users: " + error.message;
      const retryButton = document.createElement("button");
      retryButton.type = "button";
      retryButton.textContent = "Try again";
      retryButton.addEventListener("click", function () {
        window.location.reload();
      });
      errorBox.append(errorText, retryButton);
    }
    usersArea.append(errorBox);
    return;
  }

  // No users on this page (a page past the last one)
  usersArea.textContent = "";
  if (result.items.length === 0) {
    const emptyBox = document.createElement("div");
    emptyBox.className = "state-empty";
    const emptyText = document.createElement("p");
    emptyText.textContent = "There are no users on this page.";
    emptyBox.append(emptyText);
    usersArea.append(emptyBox);
    return;
  }

  // The table: id, name, email, role, active, created date (textContent only, users typed these values)
  const tableWrapper = document.createElement("div");
  tableWrapper.className = "table-wrapper";
  const table = document.createElement("table");
  table.className = "dashboard-table";
  const tableHead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const columnName of ["ID", "Name", "Email", "Role", "Active", "Created"]) {
    const headCell = document.createElement("th");
    headCell.textContent = columnName;
    headRow.append(headCell);
  }
  tableHead.append(headRow);
  const tableBody = document.createElement("tbody");
  for (const user of result.items) {
    const row = document.createElement("tr");
    const idCell = document.createElement("td");
    idCell.textContent = String(user.id);
    const nameCell = document.createElement("td");
    nameCell.textContent = user.full_name;
    const emailCell = document.createElement("td");
    emailCell.textContent = user.email;
    const roleCell = document.createElement("td");
    roleCell.textContent = user.role;
    const activeCell = document.createElement("td");
    activeCell.textContent = user.is_active ? "Yes" : "No";
    const createdCell = document.createElement("td");
    createdCell.textContent = new Date(user.created_at).toLocaleDateString("en-IN");
    row.append(idCell, nameCell, emailCell, roleCell, activeCell, createdCell);
    tableBody.append(row);
  }
  table.append(tableHead, tableBody);
  tableWrapper.append(table);
  usersArea.append(tableWrapper);

  // Pagination is only needed when there is more than one page
  const totalPages = Math.ceil(result.total / pageSize);
  if (totalPages <= 1) {
    return;
  }
  const pagination = document.createElement("nav");
  pagination.className = "pagination";
  pagination.setAttribute("aria-label", "Pagination");

  // Previous: a link, or plain disabled text on the first page
  let previousItem = null;
  if (page > 1) {
    previousItem = document.createElement("a");
    previousItem.setAttribute("href", "/admin-users.html?page=" + (page - 1));
  } else {
    previousItem = document.createElement("span");
    previousItem.className = "disabled";
  }
  previousItem.textContent = "Previous";

  const pageInfo = document.createElement("span");
  pageInfo.textContent = "Page " + page + " of " + totalPages;

  // Next: a link, or plain disabled text on the last page
  let nextItem = null;
  if (page < totalPages) {
    nextItem = document.createElement("a");
    nextItem.setAttribute("href", "/admin-users.html?page=" + (page + 1));
  } else {
    nextItem = document.createElement("span");
    nextItem.className = "disabled";
  }
  nextItem.textContent = "Next";

  pagination.append(previousItem, pageInfo, nextItem);
  paginationArea.append(pagination);
}

loadAdminUsersPage();
