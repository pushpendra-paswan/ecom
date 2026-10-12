// The addresses page: list, add, edit, delete and "Make default".
async function loadAddressesPage() {
  // Find the areas and the form fields on the page
  const addressMessage = document.getElementById("address-message");
  const addressListArea = document.getElementById("address-list-area");
  const formHeading = document.getElementById("address-form-heading");
  const addressForm = document.getElementById("address-form");
  const fullNameInput = document.getElementById("address-full-name");
  const phoneInput = document.getElementById("address-phone");
  const line1Input = document.getElementById("address-line1");
  const line2Input = document.getElementById("address-line2");
  const cityInput = document.getElementById("address-city");
  const stateInput = document.getElementById("address-state");
  const postalCodeInput = document.getElementById("address-postal-code");
  const countryInput = document.getElementById("address-country");
  const isDefaultInput = document.getElementById("address-is-default");
  const submitButton = document.getElementById("address-submit-button");
  const cancelButton = document.getElementById("address-cancel-button");

  // The id of the address being edited, or null when the form adds a new address
  let editingAddressId = null;

  // Puts the form back to "Add an address" with empty fields
  function resetForm() {
    editingAddressId = null;
    addressForm.reset();
    countryInput.value = "India";
    formHeading.textContent = "Add an address";
    submitButton.textContent = "Add address";
    cancelButton.hidden = true;
  }

  // Loads the addresses and draws the list
  async function drawAddresses() {
    let addresses = null;
    try {
      addresses = await apiRequest("/users/me/addresses", "GET");
    } catch (error) {
      // Show the problem and a button that reloads the page
      addressListArea.textContent = "";
      const errorBox = document.createElement("div");
      errorBox.className = "state-error";
      const errorText = document.createElement("p");
      errorText.textContent = "Could not load your addresses: " + error.message;
      const retryButton = document.createElement("button");
      retryButton.type = "button";
      retryButton.textContent = "Try again";
      retryButton.addEventListener("click", function () {
        window.location.reload();
      });
      errorBox.append(errorText, retryButton);
      addressListArea.append(errorBox);
      return;
    }

    // No addresses yet
    addressListArea.textContent = "";
    if (addresses.length === 0) {
      const emptyBox = document.createElement("div");
      emptyBox.className = "state-empty";
      emptyBox.textContent = "You have no saved addresses yet. Add one with the form.";
      addressListArea.append(emptyBox);
      return;
    }

    // One card for every address (textContent only, because the customer typed these values)
    for (const address of addresses) {
      const card = document.createElement("div");
      card.className = "address-card";

      if (address.is_default) {
        const defaultLabel = document.createElement("span");
        defaultLabel.className = "badge badge-default";
        defaultLabel.textContent = "Default";
        card.append(defaultLabel);
      }

      const nameLine = document.createElement("div");
      nameLine.className = "address-card-name";
      nameLine.textContent = address.full_name;
      const phoneLine = document.createElement("div");
      phoneLine.textContent = "Phone: " + address.phone;
      const streetLine = document.createElement("div");
      streetLine.textContent = address.line1;
      card.append(nameLine, streetLine);
      if (address.line2) {
        const line2Line = document.createElement("div");
        line2Line.textContent = address.line2;
        card.append(line2Line);
      }
      const cityLine = document.createElement("div");
      cityLine.textContent = address.city + ", " + address.state + " " + address.postal_code;
      const countryLine = document.createElement("div");
      countryLine.textContent = address.country;
      card.append(cityLine, countryLine, phoneLine);

      // The buttons of this address
      const buttons = document.createElement("div");
      buttons.className = "address-card-buttons";

      const editButton = document.createElement("button");
      editButton.type = "button";
      editButton.className = "button-secondary";
      editButton.textContent = "Edit";
      editButton.addEventListener("click", function () {
        // Fill the same form with this address and switch it to edit mode
        addressMessage.hidden = true;
        editingAddressId = address.id;
        fullNameInput.value = address.full_name;
        phoneInput.value = address.phone;
        line1Input.value = address.line1;
        line2Input.value = address.line2 || "";
        cityInput.value = address.city;
        stateInput.value = address.state;
        postalCodeInput.value = address.postal_code;
        countryInput.value = address.country;
        isDefaultInput.checked = address.is_default;
        formHeading.textContent = "Edit address";
        submitButton.textContent = "Save changes";
        cancelButton.hidden = false;
        fullNameInput.focus();
      });
      buttons.append(editButton);

      if (!address.is_default) {
        const defaultButton = document.createElement("button");
        defaultButton.type = "button";
        defaultButton.className = "button-secondary";
        defaultButton.textContent = "Make default";
        defaultButton.addEventListener("click", async function () {
          // PUT replaces every field, so send all of them with is_default set to true
          addressMessage.hidden = true;
          defaultButton.disabled = true;
          try {
            await apiRequest("/users/me/addresses/" + encodeURIComponent(address.id), "PUT", {
              full_name: address.full_name,
              phone: address.phone,
              line1: address.line1,
              line2: address.line2,
              city: address.city,
              state: address.state,
              postal_code: address.postal_code,
              country: address.country,
              is_default: true,
            });
          } catch (error) {
            addressMessage.textContent = error.message;
            addressMessage.hidden = false;
          }
          await drawAddresses();
        });
        buttons.append(defaultButton);
      }

      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.className = "button-secondary";
      deleteButton.textContent = "Delete";
      deleteButton.addEventListener("click", async function () {
        // Ask first
        if (!confirm("Delete this address?")) {
          return;
        }
        addressMessage.hidden = true;
        deleteButton.disabled = true;
        try {
          await apiRequest("/users/me/addresses/" + encodeURIComponent(address.id), "DELETE");
          // If this address was open in the form, clear the form
          if (editingAddressId === address.id) {
            resetForm();
          }
        } catch (error) {
          addressMessage.textContent = error.message;
          addressMessage.hidden = false;
        }
        await drawAddresses();
      });
      buttons.append(deleteButton);

      card.append(buttons);
      addressListArea.append(card);
    }
  }

  // Cancel editing
  cancelButton.addEventListener("click", function () {
    addressMessage.hidden = true;
    resetForm();
  });

  // Submit: add a new address, or save the changes of the address being edited
  addressForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    addressMessage.hidden = true;
    submitButton.disabled = true;

    // An empty line 2 is sent as null
    const line2Text = line2Input.value.trim();
    const body = {
      full_name: fullNameInput.value,
      phone: phoneInput.value,
      line1: line1Input.value,
      line2: line2Text === "" ? null : line2Text,
      city: cityInput.value,
      state: stateInput.value,
      postal_code: postalCodeInput.value,
      country: countryInput.value,
      is_default: isDefaultInput.checked,
    };

    try {
      if (editingAddressId === null) {
        await apiRequest("/users/me/addresses", "POST", body);

        // After adding, go to the "next" page if there is a safe one (the same check as login.js)
        const nextPath = new URLSearchParams(window.location.search).get("next");
        if (nextPath !== null && nextPath.startsWith("/") && !nextPath.startsWith("//") && !nextPath.includes("\\") && !/[\u0000-\u001f]/.test(nextPath)) {
          window.location.href = nextPath;
          return;
        }
      } else {
        await apiRequest("/users/me/addresses/" + encodeURIComponent(editingAddressId), "PUT", body);
      }
      resetForm();
    } catch (error) {
      addressMessage.textContent = error.message;
      addressMessage.hidden = false;
    }
    submitButton.disabled = false;
    await drawAddresses();
  });

  await drawAddresses();
}

loadAddressesPage();
