// --- PRELOADER SCRIPT ---
const preloader = document.getElementById("preloader");
window.addEventListener("load", () => {
    setTimeout(() => {
        preloader.classList.add("hidden");
    }, 500); // Faster fade out
});

document.addEventListener("DOMContentLoaded", () => {
    const nav = document.getElementById("main-nav");
    const topBar = document.getElementById("top-bar");
    const mainNavContent = document.getElementById("main-nav-content");
    const bottomBar = document.getElementById("bottom-bar");
    const videoHero = document.getElementById("video-hero");
    const mainContent = document.getElementById("main-content");
    const allNavLinks = document.querySelectorAll("nav a");
    const startShoppingBtn = document.getElementById("start-shopping-btn");

    // --- Sidebar Elements ---
    const hamburgerBtn = document.getElementById("hamburger-btn");
    const sidebar = document.getElementById("sidebar");
    const sidebarOverlay = document.getElementById("sidebar-overlay");
    const closeSidebarBtn = document.getElementById("close-sidebar-btn");
    const sidebarLinksContainer = document.getElementById("sidebar-links");
    const desktopLinks = document.getElementById("desktop-links").cloneNode(true);
    sidebarLinksContainer.innerHTML = desktopLinks.innerHTML;

    // --- Modal Elements ---
    const dealsModal = document.getElementById("deals-modal");
    const modalOverlay = document.getElementById("deals-modal-overlay");
    const closeModalBtn = document.getElementById("close-modal-btn");

    const openSidebar = () => {
        sidebar.classList.remove("sidebar-hidden");
        sidebarOverlay.classList.remove("hidden");
    };

    const closeSidebar = () => {
        sidebar.classList.add("sidebar-hidden");
        sidebarOverlay.classList.add("hidden");
    };

    hamburgerBtn.addEventListener("click", openSidebar);
    closeSidebarBtn.addEventListener("click", closeSidebar);
    sidebarOverlay.addEventListener("click", closeSidebar);

    // --- Modal Functions ---
    const showModal = () => {
        dealsModal.classList.remove("modal-hidden");
        modalOverlay.classList.remove("modal-hidden");
    };

    const hideModal = () => {
        dealsModal.classList.add("modal-hidden");
        modalOverlay.classList.add("modal-hidden");
    };

    setTimeout(showModal, 3000);
    closeModalBtn.addEventListener("click", hideModal);
    modalOverlay.addEventListener("click", hideModal);

    const applyScrolledNavStyles = () => {
        nav.style.backgroundColor = "#8C001A";
        nav.classList.add("shadow-lg");
    };

    const applyTransparentNavStyles = () => {
        nav.style.backgroundColor = "transparent";
        nav.classList.remove("shadow-lg");
    };

    const showAllNav = () => {
        if (window.innerWidth >= 768) {
            topBar.style.display = "flex";
            bottomBar.style.display = "flex";
        }
    };

    const hideNavParts = () => {
        if (window.innerWidth >= 768) {
            topBar.style.display = "none";
            bottomBar.style.display = "none";
        }
    };

    const fastScrollTo = (target, duration = 400) => {
        const targetPosition = typeof target === "number" ? target : target.offsetTop;
        const startPosition = window.pageYOffset;
        const distance = targetPosition - startPosition;
        let startTime = null;

        const animation = (currentTime) => {
            if (startTime === null) startTime = currentTime;
            const timeElapsed = currentTime - startTime;
            const run = timeElapsed / duration;
            const easedProgress = run < 1 ? run * (2 - run) : 1;
            const newPosition = startPosition + distance * easedProgress;
            window.scrollTo(0, newPosition);
            if (timeElapsed < duration) requestAnimationFrame(animation);
        };
        requestAnimationFrame(animation);
    };

    const handleNavLinkClick = (e) => {
        e.preventDefault();
        fastScrollTo(mainContent, 500);
        closeSidebar();
    };

    allNavLinks.forEach((link) => link.addEventListener("click", handleNavLinkClick));
    sidebarLinksContainer.querySelectorAll("a").forEach((link) => link.addEventListener("click", handleNavLinkClick));
    startShoppingBtn.addEventListener("click", () => fastScrollTo(mainContent, 500));

    let snapDownLock = false;
    let snapUpLock = false;
    let lastScrollY = window.scrollY;

    window.addEventListener("scroll", () => {
        const currentScrollY = window.scrollY;
        const scrollingDown = currentScrollY > lastScrollY;
        const scrollingUp = currentScrollY < lastScrollY;
        const heroHeight = videoHero.offsetHeight;

        const fadeEnd = heroHeight * 0.8;
        const scrollPercentage = Math.min(1, currentScrollY / fadeEnd);
        videoHero.style.opacity = 1 - scrollPercentage;

        if (window.innerWidth > 768) {
            if (scrollingDown && currentScrollY > 0 && currentScrollY < heroHeight / 2 && !snapDownLock) {
                snapDownLock = true;
                snapUpLock = false;
                fastScrollTo(mainContent, 500);
            }
            if (scrollingUp && currentScrollY < heroHeight - 10 && !snapUpLock) {
                snapUpLock = true;
                snapDownLock = false;
                fastScrollTo(0, 500);
            }
        }

        lastScrollY = currentScrollY <= 0 ? 0 : currentScrollY;

        if (window.scrollY > 50) {
            applyScrolledNavStyles();
            if (!nav.matches(":hover")) {
                hideNavParts();
            }
        } else {
            applyTransparentNavStyles();
            showAllNav();
        }
    });

    nav.addEventListener("mouseenter", () => {
        if (window.scrollY > 50) {
            nav.style.backgroundColor = "#800000";
            showAllNav();
        }
    });

    nav.addEventListener("mouseleave", () => {
        if (window.scrollY > 50) {
            nav.style.backgroundColor = "#8C001A";
            hideNavParts();
        }
    });
});

// glide
new Glide(".glide", {
    type: "carousel",
    startAt: 0,
    perView: 4,
    gap: 20,
    // Add these two lines for autoplay
    autoplay: 1500, // Time in milliseconds (e.g., 4000ms = 4 seconds)
    hoverpause: true, // Pauses the autoplay on mouseover

    breakpoints: {
        1024: {
            perView: 3,
        },
        768: {
            perView: 2,
        },
        640: {
            perView: 1,
        },
    },
}).mount();

// --- COUNTDOWN TIMER SCRIPT ---

// Set the date we're counting down to (e.g., 3 days from now)
const countDownDate = new Date();
countDownDate.setDate(countDownDate.getDate() + 3);

// Get elements to display the countdown
const daysEl = document.getElementById("days");
const hoursEl = document.getElementById("hours");
const minutesEl = document.getElementById("minutes");
const secondsEl = document.getElementById("seconds");

// Update the count down every 1 second
const countdownInterval = setInterval(function () {
    // Get today's date and time
    const now = new Date().getTime();

    // Find the distance between now and the count down date
    const distance = countDownDate - now;

    // Time calculations for days, hours, minutes and seconds
    const days = Math.floor(distance / (1000 * 60 * 60 * 24));
    const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((distance % (1000 * 60)) / 1000);

    // Display the result in the elements, adding a leading zero if needed
    daysEl.textContent = String(days).padStart(2, "0");
    hoursEl.textContent = String(hours).padStart(2, "0");
    minutesEl.textContent = String(minutes).padStart(2, "0");
    secondsEl.textContent = String(seconds).padStart(2, "0");

    // If the count down is finished, write some text
    if (distance < 0) {
        clearInterval(countdownInterval);
        document.getElementById("countdown-timer").innerHTML = '<div class="text-center text-red-500 font-bold">EXPIRED</div>';
    }
}, 1000);
