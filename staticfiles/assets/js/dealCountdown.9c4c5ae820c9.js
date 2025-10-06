document.addEventListener("DOMContentLoaded", function () {
    // grab all countdown containers
    const countdownEls = Array.from(document.querySelectorAll(".deal-countdown"))
        .map((el) => {
            const endIso = el.dataset.dealEnd || el.getAttribute("data-deal-end");
            // parse start if needed
            const startIso = el.dataset.dealStart || el.getAttribute("data-deal-start");
            const productCard = el.closest(".product-card");

            return {
                el,
                end: endIso ? new Date(endIso) : null,
                start: startIso ? new Date(startIso) : null,
                productCard,
            };
        })
        .filter((x) => x.end); // only those with end times

    if (!countdownEls.length) return;

    function pad(n) {
        return n.toString().padStart(2, "0");
    }

    function updateTimers() {
        const now = new Date();

        countdownEls.forEach((obj) => {
            const { el, end, start, productCard } = obj;

            // optional: if start in future, show "Starts in..." or hide
            if (start && now < start) {
                // show time until start
                var diff = start - now;
                // you can change labels to "Starts in"
            } else {
                var diff = end - now;
            }

            if (diff <= 0) {
                // deal expired (or not yet started + zero)
                // UI changes when expired:
                el.querySelector(".days").textContent = "0";
                el.querySelector(".hours").textContent = "00";
                el.querySelector(".minutes").textContent = "00";
                el.querySelector(".seconds").textContent = "00";

                // optional: add expired class and disable add button
                el.classList.add("deal-expired");
                const addBtn = productCard && productCard.querySelector("button.add-to-cart");
                if (addBtn) {
                    addBtn.disabled = true;
                    addBtn.classList.add("opacity-50", "cursor-not-allowed");
                    addBtn.textContent = "Deal ended";
                }
                return;
            }

            const secondsTotal = Math.floor(diff / 1000);
            const days = Math.floor(secondsTotal / (3600 * 24));
            const hours = Math.floor((secondsTotal % (3600 * 24)) / 3600);
            const minutes = Math.floor((secondsTotal % 3600) / 60);
            const seconds = Math.floor(secondsTotal % 60);

            const daysEl = el.querySelector(".days");
            const hoursEl = el.querySelector(".hours");
            const minutesEl = el.querySelector(".minutes");
            const secondsEl = el.querySelector(".seconds");

            if (daysEl) daysEl.textContent = days;
            if (hoursEl) hoursEl.textContent = pad(hours);
            if (minutesEl) minutesEl.textContent = pad(minutes);
            if (secondsEl) secondsEl.textContent = pad(seconds);
        });
    }

    // run immediately then every 1s
    updateTimers();
    const interval = setInterval(updateTimers, 1000);

    // optional: clear interval if no timers on screen
    window.addEventListener("beforeunload", () => clearInterval(interval));
});
