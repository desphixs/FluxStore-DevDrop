(function () {
    // universal addToCart function
    async function addToCart({ variation_id = null, product_id = null, selected_variations = null, selected_value_ids = null, quantity = 1 } = {}) {
        const csrfToken =
            document.querySelector("[name=csrfmiddlewaretoken]")?.value ||
            (function () {
                const c = document.cookie.match(/csrftoken=([^;]+)/);
                return c ? c[1] : null;
            })();

        const body = {
            variation_id,
            product_id,
            selected_variations,
            selected_value_ids,
            quantity,
        };

        try {
            const res = await fetch("/cart/add/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken || "",
                },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || "Failed to add to cart");
            }
            // successful: you can update cart UI, show toast, etc.
            // default fallback:
            window.dispatchEvent(new CustomEvent("cart:added", { detail: data }));
            return data;
        } catch (err) {
            console.error("addToCart error", err);
            window.dispatchEvent(new CustomEvent("cart:add:error", { detail: { error: String(err) } }));
            throw err;
        }
    }

    // expose globally
    window.addToCart = addToCart;

    // Auto-wiring for buttons with data attributes:
    // Buttons can have:
    // data-variation-id
    // data-product-id
    // data-qty (optional)
    // OR the product detail page can call addToCart(...) manually if more control is needed.
    document.addEventListener("click", async function (e) {
        const btn = e.target.closest(".add-to-cart") || e.target.closest("[data-add-to-cart]");
        if (!btn) return;
        e.preventDefault();

        btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i>`;

        const variationId = btn.dataset.variationId ? Number(btn.dataset.variationId) : null;
        const productId = btn.dataset.productId ? Number(btn.dataset.productId) : null;
        const qty = btn.dataset.qty ? Number(btn.dataset.qty) : document.getElementById("qty") ? Number(document.getElementById("qty").value || 1) : 1;
        console.log(variationId);

        // const selectedVariations = btn.dataset.selectedVariations ? JSON.parse(btn.dataset.selectedVariations) : null;

        // Build selected_variations dict + selected_value_ids list
        const selectedVariations = {};
        const selectedValueIds = [];
        document.querySelectorAll(".variation-option.active[data-value-id]").forEach((b) => {
            selectedVariations[b.dataset.cat] = b.dataset.val;
            selectedValueIds.push(Number(b.dataset.valueId));
        });

        console.log(selectedValueIds);

        // simple UI locking
        btn.disabled = true;
        btn.classList.add("opacity-60", "pointer-events-none");

        try {
            const resp = await addToCart({
                variation_id: variationId,
                product_id: productId,
                selected_variations: selectedVariations,
                selected_value_ids: selectedValueIds,
                quantity: qty,
            });
            // Default success action: tiny alert — replace this with your toast
            // alert("Added to cart ✔");
            // Optionally update cart counter dom if you have one:

            btn.innerHTML = `<i class="fas fa-check text-white"></i>`;

            const counter = document.querySelector(".cart_item_count");
            if (counter && resp && resp.cart) counter.textContent = resp.cart.item_count;
        } catch (err) {
            console.log(err);
            alert(err.message || "Could not add to cart");
            btn.innerHTML = `<i class="fas fa-plus"></i> Add`;

        } finally {
            btn.disabled = false;
            btn.classList.remove("opacity-60", "pointer-events-none");
        }
    });

    document.addEventListener("click", function (e) {
        const opt = e.target.closest(".variation-option");
        if (!opt) return;

        e.preventDefault();

        // Deselect siblings in the same category
        const cat = opt.dataset.cat;
        document.querySelectorAll(`.variation-option[data-cat="${cat}"]`).forEach((b) => {
            b.classList.remove("active", "bg-gray-900", "text-white");
        });

        // Mark this one active
        opt.classList.add("active", "bg-gray-900", "text-white");
    });
})();
